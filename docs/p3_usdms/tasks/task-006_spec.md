# Task-006: 데이터 조회 REST API 완성

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)
> **PRD 근거**: API-데이터 (데이터 조회 엔드포인트 7종)
> **작성일**: 2026-06-04
> **의존 Task**: T-005 (Blacklist + MasterEnricher + 일일 루틴 전체 자동화)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `tdms_core/p3_usdms/config.py` | ✅ 직접 확인 |
| DbConnectionPool & BaseRepository 시그니처 | `tdms_core/p3_usdms/repositories/base.py` | ✅ 직접 확인 |
| USDMS 전체 DB 스키마 | `tdms_core/p1_shared/p1_shared/db/usdms_origin/init.sql` | ✅ 직접 확인 |
| MasterRepo 시그니처 | `tdms_core/p3_usdms/repositories/master_repo.py` | ✅ 직접 확인 |
| PriceRepo 시그니처 | `tdms_core/p3_usdms/repositories/price_repo.py` | ✅ 직접 확인 |
| FinancialRepo 시그니처 | `tdms_core/p3_usdms/repositories/financial_repo.py` | ✅ 직접 확인 |
| ValuationRepo 시그니처 | `tdms_core/p3_usdms/repositories/valuation_repo.py` | ✅ 직접 확인 |
| KDMS routers/data.py 참고 패러다임 | `tdms_core/p2_kdms/routers/data.py` | ✅ 직접 확인 |
| get_tickers_filtered 설계 | 이 Task에서 최초 설계 | 🆕 신규 |
| get_standard_financials (PIT/범위) 설계 | 이 Task에서 최초 설계 | 🆕 신규 |
| get_valuations / get_metrics 설계 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

T-006은 `p4_manager` 및 외부 어플리케이션이 미국 시장의 수집 마스터, 일봉 시세, 수정계수, 표준화 재무, 일별 가치평가, 재무비율 데이터를 일관성 있게 쿼리할 수 있도록 REST API 엔드포인트 7종을 완성하는 단계입니다. 

**구현 범위:**
- **IN**:
  - `routers/data.py` 내 REST API 엔드포인트 7종 완성 및 Pydantic 응답 스키마 적용
  - `repositories/master_repo.py` 확장 (exchange 및 is_collect_target 필터 지원)
  - `repositories/financial_repo.py` 확장 (표준화 재무 정보 범위 조회 및 PIT(Point-in-Time) 조회 구현)
  - `repositories/valuation_repo.py` 확장 (일별 가치평가 및 재무비율 범위 조회 구현)
  - `price_repo`의 수정계수 데이터를 활용하여 `price/daily` 호출 시 `adjusted=True`에 대한 실시간 온더플라이(On-the-fly) 역산 보정 로직 구현
  - `preview/{table}` 엔드포인트의 허용 테이블 제한 및 SQL Injection 방어 바인딩 파라미터 쿼리 구현
- **OUT**:
  - `/api/health` 헬스 및 시스템 어드민 엔드포인트 전체 구현(T-007)
  - Auditors(데이터 검증기)의 온디맨드 검증 및 웹소켓 실시간 로그 연동(T-007)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/tests/test_data_router.py` — REST API 엔드포인트들에 대한 단위 및 격리 통합 테스트(Tiers 1, 2, 3)

### 수정 대상 파일
- `tdms_core/p3_usdms/routers/data.py` — 7종 엔드포인트 전면 재구현 및 헬퍼 로직 추가
- `tdms_core/p3_usdms/repositories/master_repo.py` — 필터링된 티커 조회 메서드 추가
- `tdms_core/p3_usdms/repositories/financial_repo.py` — 표준재무 데이터 범위 조회 및 PIT 조회 메서드 추가
- `tdms_core/p3_usdms/repositories/valuation_repo.py` — 가치평가 및 재무비율 범위 조회 메서드 추가

---

## § 3. 핵심 인터페이스

구현 Agent는 아래 확장 인터페이스와 API 명세 규격을 철저히 준수하여 코드를 작성해야 합니다.

### 3.1 `MasterRepo` 확장 (수정)
```python
# [출처: tdms_core/p3_usdms/repositories/master_repo.py - 기존 클래스에 메서드 추가]
from typing import Optional

class MasterRepo(BaseRepository):
    # 기존 메서드들 보존...
    
    def get_tickers_filtered(self, exchange: Optional[str] = None, is_collect_target: Optional[bool] = None) -> list[dict]:
        """
        [신규 정의 - 구현 Agent가 아래 시그니처로 생성]
        is_active = TRUE인 상태에서 exchange, is_collect_target 조건 필터를 동적으로 적용하여 티커 리스트를 조회합니다.
        
        Args:
            exchange: 거래소 필터 (NYSE, NASDAQ, AMEX 등)
            is_collect_target: 수집 대상 지정 여부 필터
        Returns:
            RealDictRow(또는 dict)의 리스트
        """
        query = """
            SELECT cik, latest_ticker, latest_name, exchange, sector, industry, country, quote_type, market_cap, current_price, is_active, is_collect_target
            FROM us_ticker_master
            WHERE is_active = TRUE
        """
        params = []
        if exchange is not None:
            query += " AND exchange = %s"
            params.append(exchange)
        if is_collect_target is not None:
            query += " AND is_collect_target = %s"
            params.append(is_collect_target)
            
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()
```

### 3.2 `FinancialRepo` 확장 (수정)
```python
# [출처: tdms_core/p3_usdms/repositories/financial_repo.py - 기존 클래스에 메서드 추가]
from typing import Optional

class FinancialRepo(BaseRepository):
    # 기존 메서드들 보존...

    def get_standard_financials(self, cik: str, start_dt: Optional[str] = None, end_dt: Optional[str] = None) -> list[dict]:
        """
        [신규 정의 - 구현 Agent가 아래 시그니처로 생성]
        특정 CIK의 표준화 재무 정보를 filed_dt 오름차순(또는 report_period 내림차순)으로 범위 조회합니다.
        
        Args:
            cik: 회사 CIK (10자리)
            start_dt: 공시일(filed_dt) 시작 범위 (YYYY-MM-DD)
            end_dt: 공시일(filed_dt) 종료 범위 (YYYY-MM-DD)
        """
        query = "SELECT * FROM us_standard_financials WHERE cik = %s"
        params = [str(cik).zfill(10)]
        
        if start_dt:
            query += " AND filed_dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND filed_dt <= %s"
            params.append(end_dt)
            
        query += " ORDER BY report_period DESC, filed_dt DESC"
        
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def get_standard_financials_pit(self, cik: str, as_of_date: str) -> list[dict]:
        """
        [신규 정의 - 구현 Agent가 아래 시그니처로 생성]
        특정 CIK에 대해 특정 시점(as_of_date) 기준으로 최신 공시된 표준 재무제표들을 조회합니다.
        Look-ahead Bias 방지를 위해 DISTINCT ON (report_period)를 수행하며, filed_dt <= as_of_date 조건을 만족하는 
        가장 최근 공시 보고서를 분기(report_period)별로 1개씩만 선택해 가져옵니다.
        
        Args:
            cik: 회사 CIK (10자리)
            as_of_date: 기준 시점 날짜 (YYYY-MM-DD)
        """
        query = """
            SELECT DISTINCT ON (report_period) *
            FROM us_standard_financials
            WHERE cik = %s AND filed_dt <= %s
            ORDER BY report_period DESC, filed_dt DESC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (str(cik).zfill(10), as_of_date))
            return cur.fetchall()
```

### 3.3 `ValuationRepo` 확장 (수정)
```python
# [출처: tdms_core/p3_usdms/repositories/valuation_repo.py - 기존 클래스에 메서드 추가]
from typing import Optional

class ValuationRepo(BaseRepository):
    # 기존 메서드들 보존...

    def get_valuations(self, cik: str, start_dt: Optional[str] = None, end_dt: Optional[str] = None) -> list[dict]:
        """
        [신규 정의 - 구현 Agent가 아래 시그니처로 생성]
        특정 CIK의 일별 가치평가 지표(us_daily_valuation) 데이터를 날짜 오름차순으로 범위 조회합니다.
        """
        query = "SELECT dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda FROM us_daily_valuation WHERE cik = %s"
        params = [str(cik).zfill(10)]
        
        if start_dt:
            query += " AND dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND dt <= %s"
            params.append(end_dt)
            
        query += " ORDER BY dt ASC"
        
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def get_metrics(self, cik: str, start_dt: Optional[str] = None, end_dt: Optional[str] = None) -> list[dict]:
        """
        [신규 정의 - 구현 Agent가 아래 시그니처로 생성]
        특정 CIK의 재무 비율(us_financial_metrics) 데이터를 날짜 오름차순으로 범위 조회합니다.
        (metrics는 공시일(filed_dt)을 범위 필터 기준으로 삼습니다.)
        """
        query = """
            SELECT cik, report_period, filed_dt, roe, roa, roic, op_margin, net_margin,
                   gp_a_ratio, debt_ratio, current_ratio, interest_coverage,
                   rev_growth_yoy, op_growth_yoy, eps_growth_yoy
            FROM us_financial_metrics
            WHERE cik = %s
        """
        params = [str(cik).zfill(10)]
        
        if start_dt:
            query += " AND filed_dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND filed_dt <= %s"
            params.append(end_dt)
            
        query += " ORDER BY report_period ASC, filed_dt ASC"
        
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()
```

---

## § 3a. 기존 기능 보존

기존에 `/tickers`, `/price/daily`, `/price/factors` 3개 엔드포인트의 기본 기능이 작동 중이므로, 이들의 라우팅 경로는 온전히 보존하며 내부 매개변수 및 계산 기능만 하위 호환성을 유지하며 확장합니다.

### 보존 인터페이스
- `GET /api/data/tickers` — 하위 호환을 위해 매개변수가 없을 시 `is_active = TRUE`인 전체 티커를 반환합니다.
- `GET /api/data/price/daily` — 하위 호환을 위해 `adjusted` 매개변수 누락 시 기본값 `False`로 지정되어 원본(Raw) 가격을 반환해야 합니다.
- `GET /api/data/price/factors` — `cik`를 전달받아 전체 수정계수 이력을 반환하는 기존 구현이 정상 동작해야 합니다.

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
import pytest
from datetime import date

def test_get_tickers_with_filters(mocker):
    """
    [목적] /api/data/tickers 엔드포인트가 exchange, is_collect_target 쿼리 필터를 레포지토리에 잘 바인딩해 호출하는가 검증.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_tickers_filtered.return_value = [{"cik": "0000320193", "latest_ticker": "AAPL"}]
    
    # Depends 모킹을 우회하기 위해 DB 커서 및 get_tickers_filtered Mock 적용
    mocker.patch("p3_usdms.routers.data.MasterRepo", return_value=mock_repo)
    
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/tickers?exchange=NASDAQ&is_collect_target=true")
    
    assert response.status_code == 200
    mock_repo.get_tickers_filtered.assert_called_once_with(exchange="NASDAQ", is_collect_target=True)
    assert response.json() == [{"cik": "0000320193", "latest_ticker": "AAPL"}]
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_daily_prices_raw_returns_original(mocker):
    """
    [목적] adjusted=False 일 때, raw daily price 데이터를 온더플라이 조정 없이 그대로 반환하는가 검증.
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = [
        {"dt": date(2026, 6, 1), "cik": "0000320193", "open_prc": 100.0, "cls_prc": 110.0, "vol": 1000}
    ]
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/price/daily?cik=0000320193&adjusted=false")
    
    assert response.status_code == 200
    # 반환 객체는 JSON 직렬화에 의해 date 객체가 문자열로 변환됨
    assert response.json()[0]["dt"] == "2026-06-01"
    assert response.json()[0]["cls_prc"] == 110.0
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_daily_prices_adjusted_performs_on_the_fly_calculation(mocker):
    """
    [목적] adjusted=True 일 때, 가격 수정계수(factor_val)가 주가 정보(open_prc, high_prc, low_prc, cls_prc)에 
           누적으로 온더플라이 곱해지는지 검증.
    [유도] 
        - 가격 데이터: 
          D1: 2026-06-01 종가 100
          D2: 2026-06-02 종가 120 (Ex-Date인 D3 직전)
          D3: 2026-06-03 종가 65  (수정 이벤트 발생일 - Ex-Date)
        - 수정계수: 
          event_dt=2026-06-03, factor_val=0.5 (1:2 액면분할 등으로 전일 종가 반토막 보정)
        - 기대결과 (adjusted = raw * Product(factor | event_dt > price_date)):
          D3 (Ex-Date): 이후 이벤트 없음. Raw=65 -> Adj=65
          D2: 이벤트 D3가 D2보다 미래에 존재하므로 factor_val(0.5) 곱해짐. Raw=120 -> Adj=60
          D1: 이벤트 D3가 D1보다 미래에 존재하므로 factor_val(0.5) 곱해짐. Raw=100 -> Adj=50
          (거래량 vol은 수정계수 보정 없이 raw vol 그대로 반환됨을 보장해야 함.)
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = [
        {"dt": date(2026, 6, 1), "cik": "0000320193", "open_prc": 100.0, "high_prc": 105.0, "low_prc": 98.0, "cls_prc": 100.0, "vol": 1000},
        {"dt": date(2026, 6, 2), "cik": "0000320193", "open_prc": 110.0, "high_prc": 125.0, "low_prc": 108.0, "cls_prc": 120.0, "vol": 2000},
        {"dt": date(2026, 6, 3), "cik": "0000320193", "open_prc": 60.0, "high_prc": 68.0, "low_prc": 59.0, "cls_prc": 65.0, "vol": 4000},
    ]
    # event_dt=2026-06-03에 factor 0.5 발생
    mock_price_repo.get_price_factors.return_value = [
        {"cik": "0000320193", "event_dt": date(2026, 6, 3), "factor_val": 0.5, "event_type": "ADJUSTMENT"}
    ]
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/price/daily?cik=0000320193&adjusted=true")
    
    assert response.status_code == 200
    data = response.json()
    
    # D3: 6/3 (Ex-Date 당일) -> 조정 없음
    assert data[2]["dt"] == "2026-06-03"
    assert data[2]["cls_prc"] == 65.0
    assert data[2]["vol"] == 4000
    
    # D2: 6/2 -> 0.5 곱해짐
    assert data[1]["dt"] == "2026-06-02"
    assert data[1]["cls_prc"] == 60.0 # 120.0 * 0.5
    assert data[1]["open_prc"] == 55.0 # 110.0 * 0.5
    assert data[1]["vol"] == 2000     # 거래량은 무변경
    
    # D1: 6/1 -> 0.5 곱해짐
    assert data[0]["dt"] == "2026-06-01"
    assert data[0]["cls_prc"] == 50.0 # 100.0 * 0.5
    assert data[0]["vol"] == 1000     # 거래량은 무변경
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_financials_with_pit_enabled(mocker):
    """
    [목적] pit=True(기본값) 일 때, as_of 일자 기준의 PIT 조회 메서드(get_standard_financials_pit)가 호출되는지 검증.
    """
    mock_fin_repo = mocker.Mock()
    mock_fin_repo.get_standard_financials_pit.return_value = [
        {"cik": "0000320193", "report_period": date(2026, 3, 31), "filed_dt": date(2026, 4, 15), "revenue": 90000.0}
    ]
    mocker.patch("p3_usdms.routers.data.FinancialRepo", return_value=mock_fin_repo)
    
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    client = TestClient(app)
    
    # as_of_date를 명시하지 않으면 자동으로 금일 날짜가 기본값으로 적용되어 호출되어야 함
    response = client.get("/api/data/financials?cik=0000320193&pit=true")
    
    assert response.status_code == 200
    mock_fin_repo.get_standard_financials_pit.assert_called_once()
    assert response.json()[0]["revenue"] == 90000.0
```

### 4.2 경계값 케이스

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_preview_limits_maximum_records(mocker):
    """
    [목적] preview 테이블 호출 시, limit 파라미터가 1000을 넘을 경우 강제로 1000으로 제한(cap)되는가 검증.
    [유도] limit=9999로 쿼리를 날려도 실제 DB 쿼리에 전달되는 LIMIT 값은 1000이어야 함.
    """
    mock_pool = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = [0] # Total count
    mock_cursor.fetchall.return_value = []   # Data rows
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    # data.py 내 get_db_pool 의존성을 모킹
    from p3_usdms.routers.data import get_db_pool
    from p3_usdms.main import app
    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # 허용된 테이블 중 하나인 us_daily_price 조회
    response = client.get("/api/data/preview/us_daily_price?limit=9999")
    
    assert response.status_code == 200
    
    # SELECT query execute 파라미터 중 LIMIT 값을 확인
    # select_query = "SELECT * FROM us_daily_price ... LIMIT %s OFFSET %s" 
    select_executed = False
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        if "SELECT * FROM US_DAILY_PRICE" in query_str:
            select_executed = True
            params = call[0][1]
            assert params[-2] == 1000
            
    assert select_executed is True
    app.dependency_overrides.clear()
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_preview_forbidden_table_returns_400():
    """
    [목적] ALLOWED_TABLES에 등록되지 않은 테이블명을 preview/{table} 경로에 전달 시,
           400 Bad Request 에러를 던져 DB에 직접 불필요한 질의가 도달하는 것을 방어하는지 검증.
    """
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    client = TestClient(app)
    
    # Forbidden 테이블 명칭 예시: users, pg_shadow, us_daily_price; DROP TABLE us_daily_price; --
    response = client.get("/api/data/preview/users")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
    
    response = client.get("/api/data/preview/pg_shadow")
    assert response.status_code == 400
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
def test_get_preview_with_empty_date_column_skips_where_date_clause(mocker):
    """
    [목적] TABLE_DATE_COLUMNS에 매핑된 날짜 컬럼 정보가 없는 테이블(예: us_ticker_master)에 
           start_date, end_date 필터를 함께 주어 호출해도, 
           날짜 조건문(WHERE dt >= %s 등)이 SQL 쿼리에 삽입되지 않고 오류 없이 동작함을 검증.
    """
    mock_pool = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = [0]
    mock_cursor.fetchall.return_value = []
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    from p3_usdms.routers.data import get_db_pool
    from p3_usdms.main import app
    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # us_ticker_master 테이블은 TABLE_DATE_COLUMNS에 등록되지 않은 테이블임
    response = client.get("/api/data/preview/us_ticker_master?start_date=2026-01-01&end_date=2026-06-01")
    
    assert response.status_code == 200
    
    # SQL execute 호출 시 날짜 필터링 구문이 없어야 함
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        assert ">=" not in query_str
        assert "<=" not in query_str
        
    app.dependency_overrides.clear()
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
# 파일 경로: tdms_core/p3_usdms/tests/test_data_router.py
import pytest

@pytest.mark.integration
def test_api_endpoints_e2e_with_real_db(real_pool):
    """
    [목적] 실제 DB(real_pool)가 기동 중인 상태에서 7종 데이터 조회 API 엔드포인트의 통신과 결과 형태를 검증합니다.
    """
    from fastapi.testclient import TestClient
    from p3_usdms.main import app
    from p3_usdms.routers.data import get_db_pool
    
    # 실제 연결 풀 주입
    app.dependency_overrides[get_db_pool] = lambda: real_pool
    client = TestClient(app)
    
    try:
        # [1] Tickers API
        res = client.get("/api/data/tickers")
        assert res.status_code == 200
        tickers_list = res.json()
        assert isinstance(tickers_list, list)
        
        # 실제 데이터가 존재하는 임의의 CIK 추출 (예: DB 내 최신 타겟 종목)
        target_cik = None
        for t in tickers_list:
            if t.get("is_collect_target"):
                target_cik = t["cik"]
                break
        
        if not target_cik:
            # Fallback CIK (AAPL)
            target_cik = "0000320193"
            
        # [2] Price Daily API
        res = client.get(f"/api/data/price/daily?cik={target_cik}&adjusted=true")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        
        # [3] Price Factors API
        res = client.get(f"/api/data/price/factors?cik={target_cik}")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        
        # [4] Financials API
        res = client.get(f"/api/data/financials?cik={target_cik}&pit=true")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        
        # [5] Valuation API
        res = client.get(f"/api/data/valuation?cik={target_cik}")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        
        # [6] Metrics API
        res = client.get(f"/api/data/metrics?cik={target_cik}")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        
        # [7] Preview Table API (us_ticker_master)
        res = client.get("/api/data/preview/us_ticker_master?limit=10")
        assert res.status_code == 200
        preview_data = res.json()
        assert preview_data["table"] == "us_ticker_master"
        assert isinstance(preview_data["data"], list)
        assert len(preview_data["data"]) <= 10
        
    finally:
        app.dependency_overrides.clear()
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_get_tickers_with_filters` | Tier 2 | 정상 | `exchange` 및 `is_collect_target` 조건 바인딩 쿼리 기능 작동 |
| 2 | `test_get_daily_prices_raw_returns_original` | Tier 2 | 정상 | `adjusted=False` 일 때 원본 Raw Close 시세 반환 검증 |
| 3 | `test_get_daily_prices_adjusted_performs_on_the_fly_calculation` | Tier 2 | 정상 | `adjusted=True` 일 때 수정계수 누적곱 가격 연산 및 Raw 거래량 보존 검증 |
| 4 | `test_get_financials_with_pit_enabled` | Tier 2 | 정상 | `pit=True` 일 때 `as_of` 기준 DISTINCT ON 쿼리 실행 검증 |
| 5 | `test_get_preview_limits_maximum_records` | Tier 2 | 경계값 | `preview` API limit 파라미터 강제 Cap(최대 1000건) 보장 검증 |
| 6 | `test_get_preview_forbidden_table_returns_400` | Tier 1 | 예외 | 허용되지 않은 테이블에 대한 DB 질의 사전 차단 및 400 에러 처리 |
| 7 | `test_get_preview_with_empty_date_column_skips_where_date_clause` | Tier 2 | 예외 | 날짜 컬럼 없는 테이블의 날짜 쿼리 필터 무시 및 안전 실행 검증 |
| 8 | `test_api_endpoints_e2e_with_real_db` | Tier 3 | 실제 통합 | 실제 데이터베이스 환경 하에서 7종 엔드포인트 E2E 응답 및 데이터 통신 검증 |

**총 8개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.

- **기술 스택**: Python 3.12, fastapi, pandas, psycopg2-binary
- **환경 변수**:
  - `DEV_USDMS_DB_HOST`, `DEV_USDMS_DB_PORT`, `DEV_USDMS_DB_NAME`, `DEV_USDMS_DB_USER`, `DEV_USDMS_DB_PASSWORD`
- **온더플라이 가격 보정 공식 가이드**:
  - `adjusted_price = raw_price * Product(factor_val | event_dt > price_date)`
  - 계산 속도 및 안전성을 위해 DataFrame을 이용하여 날짜 오름차순(Past -> Future) 정렬 상태에서 누적곱(Cumulative Product)을 역순으로 처리하는 로직을 참조하세요.
  - 역순 누적곱 연산 팁:
    ```python
    # 1. 특정 CIK의 전체 시세(Raw) 및 수정계수 목록을 DB에서 날짜순으로 조회
    prices = price_repo.get_daily_prices(cik, start_dt, end_dt) # dt ASC
    factors = price_repo.get_price_factors(cik) # event_dt ASC
    
    # 2. Ex-Date를 Key로 가지는 수정계수 Map 작성
    # 동일한 날짜에 다수의 이벤트가 존재할 경우를 고려해 누적곱 처리
    factor_map = {}
    for f in factors:
        ed = f['event_dt']
        val = f['factor_val']
        factor_map[ed] = factor_map.get(ed, 1.0) * val
        
    # 3. 최신 날짜(New)부터 과거 날짜(Old)로 역순 순회하며 누적 계수 계산
    cum_factor = 1.0
    adjusted_records = []
    
    for row in reversed(prices):
        dt = row['dt']
        
        # 3.1 현재 일자의 가격에 최신 시점부터 누적된 cum_factor 적용
        # (Ex-Date 당일 및 그 이후 가격은 해당 factor에 의해 보정되지 않음. Ex-Date 직전 날짜부터 보정)
        adjusted_records.append({
            "dt": dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
            "cik": row['cik'],
            "ticker": row['ticker'],
            "open_prc": float(row['open_prc'] * cum_factor),
            "high_prc": float(row['high_prc'] * cum_factor),
            "low_prc": float(row['low_prc'] * cum_factor),
            "cls_prc": float(row['cls_prc'] * cum_factor),
            "vol": int(row['vol']),
            "amt": float(row.get('amt', 0.0))
        })
        
        # 3.2 만약 현재 일자(dt)가 Ex-Date(factor_map의 Key)라면, 
        # 이 일자보다 과거(reversed 루프에서 다음 방문 대상들)의 모든 가격 보정을 위해 cum_factor에 누적 곱해줌
        if dt in factor_map:
            cum_factor *= factor_map[dt]
            
    # 4. 최종 리턴을 위해 다시 날짜 오름차순(Old -> New)으로 뒤집어서 정렬 반환
    adjusted_records.reverse()
    ```
- **테이블 미리보기(`preview/{table}`) 주의사항**:
  - 사용 가능한 `ALLOWED_TABLES` 및 날짜 컬럼 `TABLE_DATE_COLUMNS`는 아래 상수로 정확하게 제어되어야 합니다.
    ```python
    ALLOWED_TABLES = {
        "us_ticker_master", "us_ticker_history", "us_collection_blacklist",
        "us_financial_facts", "us_standard_financials", "us_share_history",
        "us_daily_price", "us_price_adjustment_factors", "us_daily_valuation",
        "us_financial_metrics"
    }

    TABLE_DATE_COLUMNS = {
        "us_daily_price": "dt",
        "us_daily_valuation": "dt",
        "us_price_adjustment_factors": "event_dt",
        "us_ticker_history": "start_dt",
        "us_financial_facts": "filed_dt",
        "us_standard_financials": "filed_dt",
        "us_share_history": "filed_dt",
        "us_financial_metrics": "filed_dt"
    }
    ```
  - 동적 쿼리 작성 시 테이블명(`table`)은 문자열 포매팅(`f"FROM {table}"`)을 하되, 반드시 사전에 `table in ALLOWED_TABLES` 조건으로 검증되어야 합니다.
  - 필터링용 변수(`cik`, `start_date`, `end_date`, `limit`, `offset`)들은 절대로 포매팅하지 않고 바인딩 파라미터(`%s`)를 사용하여 SQL Injection을 완전히 방지합니다.

- **대용량 데이터 조회 성능 및 메모리 방어 대응**:
  - **조회 날짜 범위 제한 (Throttling)**: `us_daily_price`, `us_daily_valuation`, `us_financial_metrics` 테이블 등 대용량 데이터셋 조회 시, 쿼리 파라미터 `start_date` 및 `end_date`가 누락된 경우 서버 메모리 폭사를 방지하기 위해 기본값으로 최근 1년(`timedelta(days=365)`) 범위를 강제 할당하도록 합니다. 또한, 사용자가 지정할 수 있는 최대 조회 범위를 15년으로 제한(Cap)하여 무제한 쿼리로 인한 DB 커넥션 병목 및 메모리 고갈을 사전에 방단합니다.
  - **Apache Arrow Binary 직렬화 지원**:
    - 대량의 시세 데이터를 JSON으로 직렬화할 때 발생하는 CPU 오버헤드와 네트워크 대역폭 증가를 해결하기 위해, 클라이언트가 `Accept: application/vnd.apache.arrow.stream` 헤더를 포함해 호출할 경우 데이터를 Apache Arrow Stream으로 직렬화해 스트리밍 응답(`StreamingResponse`)하는 헬퍼 메서드를 연동합니다.
    - 구현 예시 (`_format_response_arrow_or_json`):
      ```python
      def _format_response_arrow_or_json(data: list[dict], accept_header: str | None, json_payload):
          if accept_header and "arrow" in accept_header.lower():
              try:
                  import pyarrow as pa
                  import pyarrow.ipc as ipc
                  import io
                  sink = io.BytesIO()
                  if data:
                      normalized_data = []
                      for r in data:
                          row = {}
                          for k, v in r.items():
                              if isinstance(v, (date, datetime)):
                                  row[k] = v.isoformat()
                              else:
                                  row[k] = v
                              # NaN/Inf 값 None 변환
                              if type(row[k]) is float and (row[k] != row[k] or row[k] == float('inf') or row[k] == float('-inf')):
                                  row[k] = None
                          normalized_data.append(row)
                      table = pa.Table.from_pydict({k: [r[k] for r in normalized_data] for k in normalized_data[0]})
                  else:
                      table = pa.table({})
                  writer = ipc.new_stream(sink, table.schema)
                  writer.write_table(table)
                  writer.close()
                  sink.seek(0)
                  return StreamingResponse(sink, media_type="application/vnd.apache.arrow.stream")
              except ImportError:
                  # pyarrow 패키지 미설치 시 JSON으로 Fallback
                  pass
          return json_payload
      ```

---

## § 6. 완료 기준

- [ ] § 4의 단위 및 격리 통합 테스트 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 실제 통합 테스트 통과
- [ ] 기존 T-001 ~ T-005 관련 소스 및 단위 테스트 전체 통과 (회귀 없음)
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 Task-006 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-006_walkthrough.md` 작성 및 변경 내용 요약 기록
