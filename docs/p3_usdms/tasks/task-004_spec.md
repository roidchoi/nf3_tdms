# Task-004: 가치평가 + 재무비율 산출

> **Sub Project**: p3_usdms
> **PRD 근거**: F-08 (PIT 가치평가 산출), F-09 (재무비율 산출)
> **작성일**: 2026-06-02
> **의존 Task**: T-003

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `tdms_core/p3_usdms/config.py` 직접 확인 | ✅ 확인 |
| BaseRepository 시그니처 | `tdms_core/p3_usdms/repositories/base.py` 직접 확인 | ✅ 확인 |
| DB 스키마 | `tdms_core/p1_shared/p1_shared/db/usdms_origin/init.sql` 직접 확인 | ✅ 확인 |
| ValuationRepo | 이 Task에서 최초 설계 | 🆕 신규 |
| ValuationCalculator | 이 Task에서 최초 설계 | 🆕 신규 |
| MetricCalculator | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

개별 종목(CIK)의 일별 가격 데이터와 공시일(filed_dt) 기준 재무/주식수 이력을 Point-in-Time(PIT) 방식으로 매칭하여 일별 가치평가 지표(PER, PBR, PSR, PCR, EV/EBITDA)를 계산하고, 분기별 표준화 재무제표 기준 재무 비율 및 YoY 성장률을 산출하여 데이터베이스에 저장합니다.

**메모리 및 대용량 성능 개선 고려사항:**
- **증분 계산 방식(Incremental Update) 지원**: 모든 일별 주가를 매번 풀스캔하지 않고, 데이터베이스에 이미 적재된 최근 가치평가일(latest dt) 또는 1달의 공백 기간(예: 30일)에 맞춰 최적의 `start_date`를 산출하여 주가를 로드함으로써 메모리 오버헤드를 근본적으로 차단합니다.
- **메모리 누수 방지 설계**: 루프 실행 시 불필요해진 임시 DataFrame 및 대형 객체들에 대한 명시적 객체 삭제(`del`) 및 가비지 컬렉터 호출(`import gc; gc.collect()`)을 수행하여 1달간의 공백 및 전체 종목 전체 계산 수행(Rebuild) 시에도 메모리가 안정적으로 일정 수준 유지되도록 보장합니다.

**구현 범위:**
- **IN**:
  - `repositories/valuation_repo.py` 구현 (`us_daily_price`, `us_share_history`, `us_standard_financials` 데이터 조회 및 `us_daily_valuation`, `us_financial_metrics` 배치 업서트 기능 캡슐화)
  - `engines/valuation_calculator.py` 구현 (merge_asof 기반 PIT 매칭, TTM 연산, 주식수 Hybrid Fallback, 지표 계산, 50건 단위 배치 저장)
  - `engines/metric_calculator.py` 구현 (재무비율 9종 및 YoY 성장률 3종 계산, upsert 처리)
  - 관련 단위 테스트(Tier 1, Tier 2) 및 실제 데이터베이스 통합 테스트(Tier 3) 구현
- **OUT**:
  - 일일 루틴 자동화 오케스트레이터 연동 (Step 5 연동은 차기 Task-005에서 처리)
  - REST API 엔드포인트 연동 (조회 API 완성은 차기 Task-006에서 처리)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/repositories/valuation_repo.py` — 가치평가 및 재무비율 저장/조회용 리포지토리 클래스
- `tdms_core/p3_usdms/engines/valuation_calculator.py` — 일별 PIT 가치평가 지표 계산 엔진
- `tdms_core/p3_usdms/engines/metric_calculator.py` — 분기별 재무 비율 및 YoY 성장률 계산 엔진
- `tdms_core/p3_usdms/tests/test_valuation_metric.py` — TDD 검증을 위한 테스트 스위트

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 3.1 ValuationRepo 인터페이스
```python
# [신규 정의 — 이 Task에서 최초 설계]
# 파일 경로: tdms_core/p3_usdms/repositories/valuation_repo.py

from typing import List, Dict, Any, Tuple
from p3_usdms.repositories.base import BaseRepository

class ValuationRepo(BaseRepository):
    def load_prices(self, cik: str, start_date=None) -> List[Dict[str, Any]]:
        """
        특정 종목의 일별 종가(cls_prc)를 조회하여 dt 오름차순으로 반환합니다.
        
        Args:
            cik: zero-padded CIK 10자리
            start_date: 필터링할 시작 날짜 (Optional)
        """
        ...

    def load_shares(self, cik: str) -> List[Dict[str, Any]]:
        """
        특정 종목의 주식수 변동 이력(val)을 filed_dt 오름차순으로 반환합니다.
        """
        ...

    def load_financials(self, cik: str) -> List[Dict[str, Any]]:
        """
        특정 종목의 표준화 재무 데이터 전체 필드를 report_period 및 filed_dt 오름차순으로 반환합니다.
        """
        ...

    def get_latest_valuation_date(self, cik: str) -> Any:
        """
        특정 종목의 가치평가 데이터 중 최신 날짜(dt)를 조회합니다.
        적재된 데이터가 없을 경우 None을 반환합니다.
        """
        ...

    def save_valuations(self, valuations: List[Tuple]) -> None:
        """
        us_daily_valuation 테이블에 가치평가 지표 목록을 50건 단위 배치로 나누어 Upsert(ON CONFLICT DO UPDATE)합니다.
        
        Args:
            valuations: (dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda) 형태의 튜플 리스트
        """
        ...

    def save_metrics(self, metrics: List[Tuple]) -> None:
        """
        us_financial_metrics 테이블에 재무비율 목록을 Upsert(ON CONFLICT DO UPDATE)합니다.
        
        Args:
            metrics: (cik, report_period, filed_dt, roe, roa, roic, op_margin, net_margin, 
                      gp_a_ratio, debt_ratio, current_ratio, interest_coverage, 
                      rev_growth_yoy, op_growth_yoy, eps_growth_yoy) 형태의 튜플 리스트
        """
        ...
```

### 3.2 ValuationCalculator 인터페이스
```python
# [신규 정의 — 이 Task에서 최초 설계]
# 파일 경로: tdms_core/p3_usdms/engines/valuation_calculator.py

from p3_usdms.repositories.valuation_repo import ValuationRepo

class ValuationCalculator:
    def __init__(self, repo: ValuationRepo = None):
        """
        의존성 주입을 위한 생성자. repo가 지정되지 않을 시 내부적으로 ValuationRepo 인스턴스를 생성합니다.
        """
        self.repo = repo if repo else ValuationRepo()

    def calculate_and_save(self, cik: str, start_date=None, rebuild=False) -> None:
        """
        특정 CIK의 PIT 가치평가 데이터를 계산하고 데이터베이스에 저장합니다.
        
        계산 상세 로직:
          1. rebuild=False이고 start_date가 지정되지 않은 경우, repo.get_latest_valuation_date(cik)를 호출하여 
             가장 최근 적재된 가치평가일(latest dt)을 조회합니다. 최신 날짜가 존재하면, 해당 날짜를 start_date로 
             자동 적용하여 메모리 오버헤드와 연산량을 최적화합니다.
          2. repo로부터 prices, financials, shares 데이터 로드 (prices는 start_date 이후 데이터만)
          3. 데이터 존재 여부 유효성 검증
          4. 주식수 Hybrid Fallback 수행 (shares가 없거나 비어있는 경우, financials.shares_outstanding을 대체값으로 사용)
          5. 4대 재무 팩터(net_income, revenue, ebitda, ocf)에 대해 TTM 연간화(fiscal_period가 'FY'면 원본값, 그 외 분기면 * 4) 적용
          6. pandas.merge_asof(direction='backward')를 이용해 prices(왼쪽), shares(오른쪽) 매칭 (filed_dt 기준)
          7. financials(오른쪽) 매칭 (filed_dt 기준)
          8. 시가총액(mkt_cap = cls_prc * shares) 계산
          9. 5대 가치평가 비율 계산:
             - pe = mkt_cap / net_income_ttm
             - pb = mkt_cap / total_equity
             - ps = mkt_cap / revenue_ttm
             - pcr = mkt_cap / ocf_ttm
             - ev_ebitda = ev / ebitda_ttm (ev = mkt_cap + total_debt.fillna(0) - cash_and_equiv.fillna(0))
             ※ 분모가 0이거나 결측치(NaN/None)인 경우 결과는 None/Null 처리
          10. repo.save_valuations를 호출하여 결과 벌크 저장
          11. [메모리 최적화] 로컬 데이터프레임 및 대량 변수 객체 삭제(del)와 명시적 가비지 컬렉터(import gc; gc.collect()) 
              호출을 통해 루프 내 메모리 축적을 예방합니다.
        """
        ...
```

### 3.3 MetricCalculator 인터페이스
```python
# [신규 정의 — 이 Task에서 최초 설계]
# 파일 경로: tdms_core/p3_usdms/engines/metric_calculator.py

from p3_usdms.repositories.valuation_repo import ValuationRepo

class MetricCalculator:
    def __init__(self, repo: ValuationRepo = None):
        """
        의존성 주입을 위한 생성자. repo가 지정되지 않을 시 내부적으로 ValuationRepo 인스턴스를 생성합니다.
        """
        self.repo = repo if repo else ValuationRepo()

    def calculate_and_save(self, cik: str) -> None:
        """
        특정 CIK의 재무비율 및 YoY 성장률을 계산하여 데이터베이스에 저장합니다.
        
        계산 상세 로직:
          1. repo로부터 financials 데이터 로드
          2. 재무 지표 연산 (Vectorized safe division):
             - Profitability:
               - roe = net_income / total_equity
               - roa = net_income / total_assets
               - roic = op_income / (total_equity + total_debt.fillna(0))
               - op_margin = op_income / revenue
               - net_margin = net_income / revenue
             - Quality & Stability:
               - gp_a_ratio = gross_profit / total_assets
               - debt_ratio = total_liabilities / total_assets
               - current_ratio = current_assets / current_liabilities
               - interest_coverage = op_income / interest_expense
          3. YoY 성장률 연산:
             - 'fiscal_year' 및 'fiscal_period' 컬럼 기준 전년 동기(fiscal_year - 1, fiscal_period) 데이터 매칭
             - 전년 동기 매칭 시, 해당 시점의 가장 최근 공시본(filed_dt 최신순 기준)을 매칭 키로 적용
             - Growth Metrics:
               - rev_growth_yoy = (revenue - revenue_prev) / abs(revenue_prev)
               - op_growth_yoy = (op_income - op_income_prev) / abs(op_income_prev)
               - eps_growth_yoy = (eps - eps_prev) / abs(eps_prev) (eps = net_income / shares_outstanding)
          4. Inf / -Inf 값을 None으로 치환
          5. repo.save_metrics를 호출하여 결과 벌크 저장
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤, 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위]
def test_valuation_calculator_hybrid_fallback_uses_financials(mocker):
    """
    [목적] 주식수 이력(shares) 데이터가 없을 때 재무 데이터의 shares_outstanding을 Fallback으로 정상 매칭하는지 검증
    [유도] ValuationCalculator가 주식수 이력의 빈 판별 후, financials 내의 발행주식수를 정상 추출하여 계산에 전달하는 로직 유도
    """
    import pandas as pd
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
```

```python
# [Tier 1 — 단위]
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
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
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
```

```python
# [Tier 1 — 단위]
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
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
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
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
from datetime import date

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
        execute_values = [
            f"('{p[0]}', '{p[1]}', '{p[2]}', {p[3]}, {p[4]}, {p[5]}, {p[6]}, {p[7]})" for p in price_values
        ]
        cur.execute(f"INSERT INTO us_daily_price (dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol) VALUES {','.join(execute_values)}")
        
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
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_valuation_calculator_hybrid_fallback_uses_financials` | Tier 1 | 정상 | 주식수 이력 부재 시 재무 데이터의 주식수를 사용해 가치지표 산출 |
| 2 | `test_metric_calculator_growth_yoy_calculation_success` | Tier 1 | 정상 | 전년 동기 분기 대비 매출/영업이익/EPS YoY 성장률 정상 산출 |
| 3 | `test_valuation_calculator_with_empty_inputs_returns_early` | Tier 1 | 경계값 | 주가 또는 재무 정보가 없는 경우 예외 없이 조기 리턴 |
| 4 | `test_metric_calculator_with_zero_denom_returns_none` | Tier 1 | 예외 | 분모가 0이 되는 비율(이자비용=0)에 대해 ZeroDivisionError 없이 None 반환 |
| 5 | `test_valuation_calculator_handles_zero_debt_and_cash_filling` | Tier 1 | 예외 | total_debt/cash_and_equiv가 결측(None/NaN)일 때 0으로 대체해 EV 산출 |
| 6 | `test_valuation_repository_upsert_and_fetch_integration` | Tier 3 | 실제 통합 | 실제 데이터베이스의 hypertable 및 관계형 테이블 upsert/select 통합 검증 |

**총 6개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.

- **기술 스택**: Python 3.12, Pandas, Numpy, psycopg2-binary
- **위키 참조 링크**:
  - `pjt_wiki/p3_usdms_wiki/interfaces/schema_usdms_db.md` (혹은 init.sql) — 테이블 구조 및 DDL 참조
- **주의사항**:
  - **대용량 메모리 절약**: `ValuationCalculator.calculate_and_save`는 매번 모든 주가 이력을 가공하는 풀스캔을 기본으로 하지 않으며, `start_date` 혹은 DB 내 `latest_valuation_date` 조회를 통한 **증분(Incremental) 계산**을 적극 사용하여 수백만 건 연산 시의 메모리 오버헤드를 막습니다.
  - **명시적 가비지 컬렉션**: 각 CIK의 계산 루프가 끝난 직후 사용이 완료된 임시 DataFrame 변수를 명시적으로 소멸(`del`)시키고, `gc.collect()`를 호출하여 파이썬 가상머신의 메모리가 환원되도록 강제 보장합니다.
  - **Hypertable Lock Contention 방지**: `us_daily_valuation`은 Hypertable 구조이므로, 대량 insert 시 락 병목이 발생할 수 있습니다. 리포지토리의 벌크 저장 시 `BATCH_SIZE = 50` 단위를 유지하여 배치별 트랜잭션을 짧게 끊어 처리해야 합니다.
  - **Nullable & NaN 치환**: pandas 데이터 연산 도중 발생하는 `np.nan`, `np.inf`, `-np.inf` 값들은 psycopg2가 안전하게 DB `NULL`로 적재할 수 있도록 저장 전 최종적으로 `None`으로 전처리해 주어야 합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 기존 수집 및 파서 테스트 전체 통과 — 회귀 없음
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 Task-004 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-004_walkthrough.md` 작성
