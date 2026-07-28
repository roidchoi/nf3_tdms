import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, call
from p2_kdms.collectors.kis_kr_client import KisKrClient
from p2_kdms.repositories.investor_trade_repo import InvestorTradeRepo
from p2_kdms.tasks.backfill_task import run_backfill_investor_trade
from p2_kdms.tasks.daily_task import DailyTask

def test_fetch_investor_trade_daily_parsing(mocker):
    """
    [목적] KisKrClient.fetch_investor_trade_daily가 102개 필드의 KIS API 응답을
           정수/실수 타입 캐스팅을 포함하여 정확히 파싱하는지 검증.
    """
    mock_core = mocker.MagicMock()
    mock_core.request.return_value = {
        "output2": [
            {
                "stck_bsop_date": "20260715",
                "stck_clpr": "70000",
                "prdy_vrss": "100",
                "prdy_vrss_sign": "2",
                "prdy_ctrt": "0.14",
                "acml_vol": "15797656",
                "acml_tr_pbmn": "808470078650",
                "stck_oprc": "69500",
                "stck_hgpr": "70500",
                "stck_lwpr": "69000",
                # 개인 수급
                "prsn_seln_vol": "100",
                "prsn_shnu_vol": "200",
                "prsn_ntby_qty": "100",
                "prsn_seln_tr_pbmn": "7000000",
                "prsn_shnu_tr_pbmn": "14000000",
                "prsn_ntby_tr_pbmn": "7000000",
                # 등록외국인
                "frgn_reg_askp_qty": "50",
                "frgn_reg_bidp_qty": "60",
                "frgn_reg_ntby_qty": "10",
                "frgn_reg_askp_pbmn": "3500000",
                "frgn_reg_bidp_pbmn": "4200000",
                "frgn_reg_ntby_pbmn": "700000",
                # 사모펀드 (ntby_vol 명칭 주의)
                "pe_fund_seln_vol": "10",
                "pe_fund_shnu_vol": "20",
                "pe_fund_ntby_vol": "10",
                "pe_fund_seln_tr_pbmn": "700000",
                "pe_fund_shnu_tr_pbmn": "1400000",
                "pe_fund_ntby_tr_pbmn": "700000"
            }
        ]
    }

    client = KisKrClient(api_core=mock_core)
    records = client.fetch_investor_trade_daily("005930", date(2026, 7, 15), date(2026, 7, 15))

    assert len(records) == 1
    rec = records[0]
    assert rec["dt"] == date(2026, 7, 15)
    assert rec["stk_cd"] == "005930"
    assert rec["stck_clpr"] == 70000
    assert rec["prdy_ctrt"] == 0.14
    
    # 개인
    assert rec["prsn_seln_vol"] == 100
    assert rec["prsn_shnu_vol"] == 200
    assert rec["prsn_ntby_qty"] == 100
    assert rec["prsn_seln_tr_pbmn"] == 7000000
    
    # 등록외국인
    assert rec["frgn_reg_askp_qty"] == 50
    assert rec["frgn_reg_bidp_qty"] == 60
    assert rec["frgn_reg_ntby_qty"] == 10
    assert rec["frgn_reg_askp_pbmn"] == 3500000
    
    # 사모펀드
    assert rec["pe_fund_seln_vol"] == 10
    assert rec["pe_fund_shnu_vol"] == 20
    assert rec["pe_fund_ntby_vol"] == 10
    assert rec["pe_fund_seln_tr_pbmn"] == 700000

    mock_core.request.assert_called_once()


def test_investor_trade_repo_get_active_symbols(mocker):
    """
    [목적] InvestorTradeRepo.get_active_symbols_for_date가 
           해당 날짜에 부합하는 활성 상장 종목 대상을 잘 가져오는지 검증.
    """
    mock_pool = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_cur = mocker.MagicMock()
    
    mock_pool.get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    
    # 2026-07-15 활성 종목
    mock_cur.fetchall.return_value = [("005930",), ("000660",)]
    
    repo = InvestorTradeRepo(mock_pool)
    symbols = repo.get_active_symbols_for_date(date(2026, 7, 15))
    
    assert symbols == ["005930", "000660"]
    mock_cur.execute.assert_called_once()


def test_run_backfill_investor_trade_test_mode():
    """
    [목적] run_backfill_investor_trade가 test_mode=True일 때 
           실제 KIS API 호출 대신 Mock 데이터를 사용하여 정상 수행을 마치는가 검증.
    """
    job_statuses = {}
    
    # test_mode=True로 기동하면 KIS API가 모킹되고 내부 DB 연동은 mock 상태에서도 통과되어야 하므로
    # DatabaseManager와 mock_repo 등을 적절히 모킹하거나 test_mode 내장 로직에 의존
    # run_backfill_investor_trade는 test_mode=True일 때 DatabaseManager를 인스턴스화하고 upsert 및 select를 수행하므로
    # DB 쿼리를 모킹하기 위해 DatabaseManager를 모킹
    
    # 이 테스트에서는 DB가 동작하지 않는 환경에서도 안전하게 돌게 하기 위해
    # DatabaseManager._execute_query를 모킹하여 누락 날짜가 있는 시나리오를 시뮬레이션
    import p2_kdms.tasks.backfill_task as bf_task
    
    original_db_mgr = bf_task.DatabaseManager
    mock_db = MagicMock()
    mock_db.pool = MagicMock()
    # 2026-07-15 일자에 005930 종목 누락 건 발생 시뮬레이션
    mock_db._execute_query.return_value = [
        {"dt": date(2026, 7, 15), "stk_cd": "005930"}
    ]
    bf_task.DatabaseManager = lambda: mock_db
    
    try:
        run_backfill_investor_trade(
            job_statuses=job_statuses,
            test_mode=True,
            start_date=date(2026, 7, 15),
            end_date=date(2026, 7, 15)
        )
        
        job_id = "backfill_investor_trade"
        assert job_statuses[job_id]["is_running"] is False
        assert job_statuses[job_id]["last_status"] == "success"
        assert job_statuses[job_id]["stocks_processed"] == 1
    finally:
        bf_task.DatabaseManager = original_db_mgr


def test_daily_task_investor_trade_integration(mocker):
    """
    [목적] DailyTask가 실행될 때 investor_trade_repo가 주입되어 있으면
           해당 영업일 대상 종목들에 대해 투자자 매매동향을 가져와 적재하는지 연동 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_it_repo = mocker.MagicMock()
    
    # 휴장일 패스 및 active_stocks 반환 모킹
    mock_ohlcv_repo.get_trading_days_count.return_value = 1
    mock_ohlcv_repo.get_open_trading_days.return_value = [date(2026, 7, 15)]
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930", "listed_shares": 10000}]
    
    # active symbols 모킹
    mock_it_repo.get_active_symbols_for_date.return_value = ["005930"]
    
    # KIS API 모킹
    mock_kis.fetch_investor_trade_daily.return_value = [
        {"dt": date(2026, 7, 15), "stk_cd": "005930"}
    ]
    
    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        investor_trade_repo=mock_it_repo
    )
    
    # daily_ohlcv 수집 성공을 위해 ohlcv_list 모킹
    mock_kis.fetch_daily_ohlcv.return_value = {
        "dt": date(2026, 7, 15),
        "stk_cd": "005930",
        "close": 70000,
        "volume": 100000
    }
    
    res = task.run(target_date=date(2026, 7, 15))
    
    # DailyTask가 investor_trade_repo를 호출하여 대상 종목을 찾았는지 검증
    mock_it_repo.get_active_symbols_for_date.assert_called_once_with(date(2026, 7, 15))
    # fetch_investor_trade_daily를 호출했는지 검증
    mock_kis.fetch_investor_trade_daily.assert_called_once_with("005930", start_date=date(2026, 7, 15), end_date=date(2026, 7, 15))
    # DB에 upsert 했는지 검증
    mock_it_repo.upsert_daily_investor_trade.assert_called_once()


def test_investor_trade_repo_get_daily_investor_trade(mocker):
    """
    [목적] InvestorTradeRepo.get_daily_investor_trade가 지정된 종목과 날짜 범위의
           수급 데이터를 DB에서 정상적으로 SELECT 해와 dict 포맷으로 가공하여 반환하는지 검증.
    """
    mock_pool = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_cur = mocker.MagicMock()
    
    mock_pool.get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    
    mock_cur.description = [("dt", None), ("stk_cd", None), ("stck_clpr", None)]
    mock_cur.fetchall.return_value = [(date(2026, 7, 15), "005930", 70000)]
    
    repo = InvestorTradeRepo(mock_pool)
    results = repo.get_daily_investor_trade("005930", date(2026, 7, 15), date(2026, 7, 15))
    
    assert len(results) == 1
    assert results[0] == {"dt": date(2026, 7, 15), "stk_cd": "005930", "stck_clpr": 70000}
    mock_cur.execute.assert_called_once()


def test_get_investor_trade_daily_api_endpoint(mocker):
    """
    [목적] GET /api/data/investor-trade/daily API 호출 시,
           FastAPI 라우터 및 레포지토리 의존성 게터가 정상 연동되어 적절한 JSON 형식 응답을 반환하는지 검증.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from routers.data import router, get_investor_trade_repo
    
    app = FastAPI()
    app.include_router(router)
    
    mock_repo = mocker.MagicMock()
    mock_repo.get_daily_investor_trade.return_value = [
        {"dt": date(2026, 7, 15), "stk_cd": "005930", "stck_clpr": 70000}
    ]
    
    # 의존성 오버라이딩 적용
    app.dependency_overrides[get_investor_trade_repo] = lambda: mock_repo
    
    client = TestClient(app)
    response = client.get("/api/data/investor-trade/daily?stk_cd=005930&start_date=2026-07-15&end_date=2026-07-15")
    
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) == 1
    assert res_data[0]["stk_cd"] == "005930"
    assert res_data[0]["dt"] == "2026-07-15"
    assert res_data[0]["stck_clpr"] == 70000
    mock_repo.get_daily_investor_trade.assert_called_once_with("005930", date(2026, 7, 15), date(2026, 7, 15))
