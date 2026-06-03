import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from datetime import date

# -------------------------------------------------------------------------
# Tier 1 - 단위 테스트 (Unit Tests)
# -------------------------------------------------------------------------

def test_valuation_calculator_hybrid_fallback_uses_financials(mocker):
    """
    [목적] 주식수 이력(shares) 데이터가 없을 때 재무 데이터의 shares_outstanding을 Fallback으로 정상 매칭하는지 검증
    [유도] ValuationCalculator가 주식수 이력의 빈 판별 후, financials 내의 발행주식수를 정상 추출하여 계산에 전달하는 로직 유도
    """
    from p3_usdms.engines.valuation_calculator import ValuationCalculator
    
    mock_repo = mocker.MagicMock()
    # 일봉 주가 1건 (dt: 2026-03-31, cls_prc: 150.0)
    mock_repo.load_prices.return_value = [{'dt': '2026-03-31', 'cls_prc': 150.0}]
    # 주식수 이력은 완전 비어있음
    mock_repo.load_shares.return_value = []
    # 재무 데이터 1건 (shares_outstanding: 1000.0, filed_dt: 2026-03-15)
    mock_repo.load_financials.return_value = [{
        'filed_dt': '2026-03-15', 'fiscal_period': 'Q1',
        'shares_outstanding': 1000.0, 'net_income': 100.0,
        'total_equity': 5000.0, 'revenue': 400.0, 'ebitda': 150.0,
        'ocf': 120.0, 'total_debt': 200.0, 'cash_and_equiv': 50.0
    }]
    
    calc = ValuationCalculator(repo=mock_repo)
    calc.calculate_and_save("0000320193")
    
    # save_valuations에 넘어간 인자 검증
    mock_repo.save_valuations.assert_called_once()
    valuations = mock_repo.save_valuations.call_args[0][0]
    
    # 1건 계산 결과 확인
    assert len(valuations) == 1
    val = valuations[0]
    # mkt_cap = 150.0 (cls_prc) * 1000.0 (shares_outstanding fallback) = 150000.0
    assert val[2] == 150000.0
    # Q1 이므로 net_income_ttm = 100.0 * 4 = 400.0 -> pe = 150000.0 / 400.0 = 375.0
    assert val[3] == 375.0


def test_metric_calculator_growth_yoy_calculation_success(mocker):
    """
    [목적] 전년 동기 분기가 존재할 때 YoY 성장률(매출, 영업이익, EPS)을 올바르게 계산하는지 검증
    [유도] MetricCalculator가 (fiscal_year - 1, fiscal_period) 조인을 통해 올바른 직전년 대비 비율을 연산하도록 유도
    """
    from p3_usdms.engines.metric_calculator import MetricCalculator
    
    mock_repo = mocker.MagicMock()
    # 2025년 Q1 및 2026년 Q1 재무 데이터 준비
    mock_repo.load_financials.return_value = [
        {
            'cik': '0000320193', 'report_period': '2025-03-31', 'filed_dt': '2025-04-15',
            'fiscal_year': 2025, 'fiscal_period': 'Q1',
            'net_income': 100.0, 'total_equity': 1000.0, 'total_assets': 2000.0,
            'op_income': 150.0, 'revenue': 1000.0, 'gross_profit': 400.0,
            'total_liabilities': 1000.0, 'current_assets': 500.0, 'current_liabilities': 250.0,
            'interest_expense': 10.0, 'shares_outstanding': 10.0
        },
        {
            'cik': '0000320193', 'report_period': '2026-03-31', 'filed_dt': '2026-04-15',
            'fiscal_year': 2026, 'fiscal_period': 'Q1',
            'net_income': 150.0, 'total_equity': 1200.0, 'total_assets': 2500.0,
            'op_income': 300.0, 'revenue': 1500.0, 'gross_profit': 600.0,
            'total_liabilities': 1300.0, 'current_assets': 600.0, 'current_liabilities': 300.0,
            'interest_expense': 15.0, 'shares_outstanding': 10.0
        }
    ]
    
    calc = MetricCalculator(repo=mock_repo)
    calc.calculate_and_save("0000320193")
    
    mock_repo.save_metrics.assert_called_once()
    metrics = mock_repo.save_metrics.call_args[0][0]
    
    # 2025년 Q1은 전년 동기가 없어 YoY null, 2026년 Q1은 YoY 연산 완료
    assert len(metrics) == 2
    m26 = [m for m in metrics if m[1] == '2026-03-31'][0]
    
    # roe = 150.0 / 1200.0 = 0.125
    assert m26[3] == 0.125
    # rev_growth_yoy = (1500.0 - 1000.0) / 1000.0 = 0.5 (50% 성장)
    assert m26[12] == 0.5
    # op_growth_yoy = (300.0 - 150.0) / 150.0 = 1.0 (100% 성장)
    assert m26[13] == 1.0
    # eps = 150/10 = 15, prev_eps = 100/10 = 10 -> eps_growth_yoy = (15-10)/10 = 0.5
    assert m26[14] == 0.5


def test_valuation_calculator_with_empty_inputs_returns_early(mocker):
    """
    [목적] 일봉 주가 또는 재무제표가 비어 있을 시 즉각 조기 리턴하여 에러를 방지하는지 검증
    """
    from p3_usdms.engines.valuation_calculator import ValuationCalculator
    
    mock_repo = mocker.MagicMock()
    mock_repo.load_prices.return_value = []
    mock_repo.load_financials.return_value = []
    
    calc = ValuationCalculator(repo=mock_repo)
    calc.calculate_and_save("0000320193")
    
    mock_repo.save_valuations.assert_not_called()


def test_metric_calculator_with_zero_denom_returns_none(mocker):
    """
    [목적] 분모가 0이 되는 기업 데이터(예: 무부채 기업의 이자보상배율 등) 입력 시 ZeroDivisionError 없이 None을 반환하는지 검증
    [유도] safe_div 헬퍼 함수가 정상 분기되어 에러를 방지하도록 설계 유도
    """
    from p3_usdms.engines.metric_calculator import MetricCalculator
    
    mock_repo = mocker.MagicMock()
    mock_repo.load_financials.return_value = [{
        'cik': '0000320193', 'report_period': '2026-03-31', 'filed_dt': '2026-04-15',
        'fiscal_year': 2026, 'fiscal_period': 'Q1',
        'net_income': 100.0, 'total_equity': 1000.0, 'total_assets': 2000.0,
        'op_income': 150.0, 'revenue': 1000.0, 'gross_profit': 400.0,
        'total_liabilities': 1000.0, 'current_assets': 500.0, 'current_liabilities': 250.0,
        'interest_expense': 0.0,  # 이자비용 0
        'shares_outstanding': 10.0
    }]
    
    calc = MetricCalculator(repo=mock_repo)
    calc.calculate_and_save("0000320193")
    
    metrics = mock_repo.save_metrics.call_args[0][0]
    # interest_coverage = op_income / interest_expense -> 150 / 0 -> None 반환 검증
    assert metrics[0][11] is None


def test_valuation_calculator_handles_zero_debt_and_cash_filling(mocker):
    """
    [목적] total_debt 또는 cash_and_equiv 값이 결측(None/NaN)일 때 0으로 fillna하여 EV를 에러 없이 연산하는지 검증
    """
    from p3_usdms.engines.valuation_calculator import ValuationCalculator
    
    mock_repo = mocker.MagicMock()
    mock_repo.load_prices.return_value = [{'dt': '2026-03-31', 'cls_prc': 150.0}]
    mock_repo.load_shares.return_value = [{'filed_dt': '2026-03-15', 'val': 1000.0}]
    mock_repo.load_financials.return_value = [{
        'filed_dt': '2026-03-15', 'fiscal_period': 'Q1',
        'net_income': 100.0, 'total_equity': 5000.0, 'revenue': 400.0, 'ebitda': 150.0,
        'ocf': 120.0,
        'total_debt': None,        # 결측
        'cash_and_equiv': None     # 결측
    }]
    
    calc = ValuationCalculator(repo=mock_repo)
    calc.calculate_and_save("0000320193")
    
    valuations = mock_repo.save_valuations.call_args[0][0]
    # ev = mkt_cap + debt(0) - cash(0) = 150000.0
    # ev_ebitda = 150000.0 / (150.0 * 4) = 150000.0 / 600.0 = 250.0
    assert valuations[0][7] == 250.0

# -------------------------------------------------------------------------
# Tier 3 - 실제 데이터베이스 통합 테스트 (Integration Tests)
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_valuation_repository_upsert_and_fetch_integration(real_pool):
    """
    [목적] 실제 DB에 연결하여 ValuationRepo의 조회 및 저장 연산이 정상 쿼리를 발동하는지 통합 검증
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    from p3_usdms.repositories.valuation_repo import ValuationRepo
    
    repo = ValuationRepo()
    
    # 1. 테스트 더미 데이터 적재
    with repo.get_cursor() as cur:
        # CIK 마스터 적재
        cur.execute("""
            INSERT INTO us_ticker_master (cik, latest_ticker, latest_name, is_collect_target)
            VALUES ('9999999999', 'TEST', 'Test Inc', TRUE)
            ON CONFLICT (cik) DO NOTHING
        """)
        # 시세 데이터 적재
        cur.execute("""
            INSERT INTO us_daily_price (dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol)
            VALUES ('2026-03-31', '9999999999', 'TEST', 10.0, 12.0, 9.0, 11.0, 1000)
            ON CONFLICT (dt, cik) DO NOTHING
        """)
        # 주식수 적재
        cur.execute("""
            INSERT INTO us_share_history (cik, filed_dt, val)
            VALUES ('9999999999', '2026-03-15', 50000.0)
            ON CONFLICT (cik, filed_dt) DO NOTHING
        """)
        # 표준 재무 적재
        cur.execute("""
            INSERT INTO us_standard_financials (cik, report_period, filed_dt, fiscal_year, fiscal_period, total_assets, total_equity, net_income)
            VALUES ('9999999999', '2026-03-31', '2026-03-15', 2026, 'Q1', 100000.0, 50000.0, 1000.0)
            ON CONFLICT (cik, report_period, filed_dt) DO NOTHING
        """)

    # 2. repo.load_XXX 데이터 조회 테스트
    prices = repo.load_prices('9999999999')
    shares = repo.load_shares('9999999999')
    financials = repo.load_financials('9999999999')
    
    assert len(prices) > 0
    assert len(shares) > 0
    assert len(financials) > 0
    
    # 3. repo.save_valuations 가치평가 적재 테스트
    repo.save_valuations([
        ('2026-03-31', '9999999999', 550000.0, 137.5, 11.0, None, None, None)
    ])
    
    # DB 직접 확인
    with repo.get_cursor() as cur:
        cur.execute("SELECT mkt_cap, pe, pb FROM us_daily_valuation WHERE cik = '9999999999' AND dt = '2026-03-31'")
        row = cur.fetchone()
        
    assert row is not None
    assert row['mkt_cap'] == 550000.0
    assert row['pe'] == 137.5
    assert row['pb'] == 11.0


@pytest.mark.integration
def test_valuation_calculator_bulk_performance_with_real_db(real_pool):
    """
    [목적] 약 1달(30일) 간의 일일 주가 수집 공백을 가정한 실 데이터(예: Apple `0000320193`)에 대해 
           증분 및 대량 일별 가치평가 연산을 수행할 때, 메모리 및 커넥션 풀 경합이 과하게 발생하지 않고 
           30일치 데이터가 고성능으로 정상 적재(merge_asof 및 bulk insert)되는지 검증
    [실행 조건] 실제 데이터베이스 컨테이너 기동. `pytest --run-integration`으로 실행.
    """
    import time
    import gc
    from psycopg2.extras import execute_values
    from p3_usdms.repositories.valuation_repo import ValuationRepo
    from p3_usdms.engines.valuation_calculator import ValuationCalculator
    
    # 1. 30일 간의 더미 가격 데이터를 Apple CIK로 DB에 사전 적재
    repo = ValuationRepo()
    test_cik = "0000320193"
    
    with repo.get_cursor() as cur:
        # CIK 존재 확인
        cur.execute("INSERT INTO us_ticker_master (cik, latest_ticker, latest_name, is_collect_target) VALUES (%s, 'AAPL', 'Apple Inc', TRUE) ON CONFLICT (cik) DO NOTHING", (test_cik,))
        # 주식수 적재 (AAPL)
        cur.execute("INSERT INTO us_share_history (cik, filed_dt, val) VALUES (%s, '2026-01-01', 15000000000) ON CONFLICT (cik, filed_dt) DO NOTHING", (test_cik,))
        # 표준 재무 적재 (AAPL)
        cur.execute("""
            INSERT INTO us_standard_financials (cik, report_period, filed_dt, fiscal_year, fiscal_period, total_assets, total_equity, net_income, cash_and_equiv, total_debt, revenue, ebitda, ocf)
            VALUES (%s, '2026-03-31', '2026-04-15', 2026, 'Q2', 350000000000, 70000000000, 25000000000, 30000000000, 100000000000, 90000000000, 32000000000, 28000000000)
            ON CONFLICT (cik, report_period, filed_dt) DO NOTHING
        """, (test_cik,))
        
        # 30일치 가격 대량 적재 (2026-04-16 ~ 2026-05-15)
        price_values = []
        for i in range(30):
            dt_str = f"2026-04-{16+i:02d}" if 16+i <= 30 else f"2026-05-{16+i-30:02d}"
            price_values.append((dt_str, test_cik, 'AAPL', 170.0 + i, 172.0 + i, 169.0 + i, 171.0 + i, 5000000 + i*1000))
            
        cur.execute("DELETE FROM us_daily_price WHERE cik = %s AND dt BETWEEN '2026-04-16' AND '2026-05-15'", (test_cik,))
        
        # psycopg2 bulk insert using execute_values
        insert_query = "INSERT INTO us_daily_price (dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol) VALUES %s"
        execute_values(cur, insert_query, price_values)
        
        # 이전 가치평가 내역 삭제하여 30일 공백 상태 시뮬레이션
        cur.execute("DELETE FROM us_daily_valuation WHERE cik = %s AND dt BETWEEN '2026-04-16' AND '2026-05-15'", (test_cik,))

    # 2. 대량 계산 수행 및 시간 측정
    calc = ValuationCalculator(repo=repo)
    
    start_time = time.time()
    # 30일치를 한번에 계산하도록 시작일을 지정하여 실행
    calc.calculate_and_save(test_cik, start_date="2026-04-16")
    duration = time.time() - start_time
    
    # 3. 데이터 적재 건수 검증
    with repo.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM us_daily_valuation WHERE cik = %s AND dt BETWEEN '2026-04-16' AND '2026-05-15'", (test_cik,))
        row = cur.fetchone()
        
    assert row['cnt'] == 30, f"30일치의 가치평가 데이터가 모두 적재되어야 하나 실제로는 {row['cnt']}건입니다."
    # 30일 정도의 데이터는 1초 내외로 초고속 처리되어야 함 (메모리 누수 경고 임계 시간 2.0초 미만 검증)
    assert duration < 2.0, f"30일 공백 기간에 대한 계산 수행 성능 저하 감지: {duration:.4f}초 소요됨."
    
    # 명시적 GC 기동 후 메모리 안정성 유도
    gc.collect()


@pytest.mark.integration
def test_valuation_calculator_bulk_500_stocks_performance_with_real_db(real_pool):
    """
    [목적] 수집 대상으로 활성화된 최소 500개 이상의 실제 종목(CIK) 목록을 로드하여 
           각 종목에 대해 가치평가(ValuationCalculator) 및 재무비율(MetricCalculator) 연산을 일괄 수행하고, 
           대량 종목 루프 구동 시 메모리 OOM이나 DB Lock 경합 등 예기치 못한 크래시가 나지 않는지 안정성 검증
    [실행 조건] 실제 데이터베이스 컨테이너 기동. `pytest --run-integration`으로 실행.
    """
    import time
    import gc
    from p3_usdms.repositories.valuation_repo import ValuationRepo
    from p3_usdms.engines.valuation_calculator import ValuationCalculator
    from p3_usdms.engines.metric_calculator import MetricCalculator
    
    repo = ValuationRepo()
    val_calc = ValuationCalculator(repo=repo)
    met_calc = MetricCalculator(repo=repo)
    
    # 1. 수집 대상 CIK 목록 조회 (안전성 검증을 위해 500개 초과하여 최대 550개 가져옴)
    with repo.get_cursor() as cur:
        cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target = TRUE LIMIT 550")
        rows = cur.fetchall()
        
    ciks = [r['cik'] for r in rows]
    assert len(ciks) >= 500, f"검증을 위한 실데이터 종목 수가 부족합니다. (현재: {len(ciks)}개, 최소 필요: 500개)"
    
    # 2. 캐시 일괄 사전 조회
    latest_val_cache = repo.get_all_latest_valuation_dates(ciks)
    latest_fin_cache = repo.get_all_latest_financial_filed_dates(ciks)
    latest_met_cache = repo.get_all_latest_metric_filed_dates(ciks)

    print(f"\n[대량 검증 시작] {len(ciks)}개 종목에 대한 실 데이터 일괄 연산 및 적재 검증 구동 중...")
    
    start_time = time.time()
    
    success_count = 0
    # 3. 500종목 루프 연속 구동
    for idx, cik in enumerate(ciks):
        try:
            # 500개 이상 종목에 대해 가치평가 및 재무비율 계산 진행
            # rebuild=False (증분 계산) 모드로 기본 동작시켜 효율성 보장
            val_calc.calculate_and_save(cik, rebuild=False, latest_val_dates_cache=latest_val_cache)
            met_calc.calculate_and_save(cik, rebuild=False, latest_fin_dates_cache=latest_fin_cache, latest_met_dates_cache=latest_met_cache)
            success_count += 1
        except Exception as e:
            pytest.fail(f"종목 {cik} (루프 {idx}번째) 계산 및 적재 중 예외 발생: {str(e)}")
            
    total_duration = time.time() - start_time
    print(f"\n[대량 검증 완료] 총 {success_count}개 종목 연산 무사 차단 완료. 소요 시간: {total_duration:.4f}초")
    
    # 3. 500종목 루프의 총 처리 소요 시간 검증 (안정성 임계치: 150.0초 미만)
    assert total_duration < 150.0, f"500종목 대량 계산 루프 연산 속도 임계치 초과: {total_duration:.4f}초 소요됨."
    
    # 명시적 GC 강제 수행
    gc.collect()

