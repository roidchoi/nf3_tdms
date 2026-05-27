import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from main import app
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
import pyarrow as pa
import pyarrow.ipc as ipc
import io

KST = ZoneInfo("Asia/Seoul")

# routers.data 에서 의존성 주입 게터 임포트
from routers.data import (
    get_ohlcv_repo,
    get_master_repo,
    get_factor_repo,
    get_financial_repo
)
# 신규 추가할 게터
from routers.data import get_market_cap_repo

@pytest.fixture
def client():
    return TestClient(app)

# =================================================================
# A. GET /api/data/ohlcv/daily 테스트
# =================================================================

def test_ohlcv_daily_raw_returns_unadjusted_data(client, mocker):
    """
    TC-01: adjusted=False(기본값) 시 raw OHLCV를 반환하는지 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_ohlcv_repo.get_daily_ohlcv.return_value = [
        {"stk_cd": "005930", "dt": date(2026, 5, 23), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 100000}
    ]
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo

    response = client.get("/api/data/ohlcv/daily?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["dt"] == "2026-05-23"
    assert "adj_factor" not in body[0]
    mock_ohlcv_repo.get_daily_ohlcv.assert_called_once_with("005930", date(2026, 5, 23), date(2026, 5, 23))
    app.dependency_overrides.clear()

def test_ohlcv_daily_adjusted_returns_on_the_fly_result(client, mocker):
    """
    TC-02: adjusted=True 시 On-the-fly 수정주가가 반환되는지 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_ohlcv_repo.get_daily_ohlcv.return_value = [
        {"stk_cd": "005930", "dt": date(2026, 5, 23), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 100000}
    ]
    mock_factor_repo = MagicMock()
    mock_factor_repo.get_factors_for_stock.return_value = [
        {"stk_cd": "005930", "event_dt": date(2026, 6, 1), "price_ratio": 0.5, "volume_ratio": 2.0, "price_source": "KIS"}
    ]
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_factor_repo] = lambda: mock_factor_repo

    response = client.get("/api/data/ohlcv/daily?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23&adjusted=true")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    # event_dt(06-01) > dt(05-23) 이므로 수정계수 반영 
    assert body[0]["close"] == 35000
    assert body[0]["adj_factor"] == 0.5
    app.dependency_overrides.clear()

def test_ohlcv_daily_invalid_date_format_returns_422(client):
    """
    TC-03: 잘못된 날짜 포맷 입력 시 400 또는 422 반환
    """
    response = client.get("/api/data/ohlcv/daily?stk_cd=005930&start_date=20260523&end_date=20260523")
    assert response.status_code in (400, 422)

# =================================================================
# B. GET /api/data/ohlcv/minute 테스트
# =================================================================

def test_ohlcv_minute_returns_correct_records(client, mocker):
    """
    TC-04: 특정 종목·기간의 분봉 데이터를 정상 반환하는지 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_ohlcv_repo.get_minute_ohlcv.return_value = [
        {"stk_cd": "005930", "dt_tm": datetime(2026, 5, 23, 9, 0, tzinfo=KST), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 1000}
    ]
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo

    response = client.get("/api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-05-23T09:00:00&end_dt=2026-05-23T15:30:00")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["stk_cd"] == "005930"
    assert "2026-05-23T09:00:00" in body[0]["dt_tm"]
    app.dependency_overrides.clear()

def test_ohlcv_minute_repo_queries_correct_table(mocker):
    """
    TC-05: OhlcvRepo.get_minute_ohlcv()가 minute_ohlcv 테이블을 올바른 조건으로 조회하는지 단위 검증
    """
    from repositories.ohlcv_repo import OhlcvRepo
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        ("005930", datetime(2026, 5, 23, 9, 0), 70000, 71000, 69000, 70000, 1000)
    ]

    repo = OhlcvRepo(mock_pool)
    start = datetime(2026, 5, 23, 9, 0)
    end = datetime(2026, 5, 23, 15, 30)
    res = repo.get_minute_ohlcv("005930", start, end)

    assert len(res) == 1
    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "minute_ohlcv" in executed_sql.lower()
    assert "stk_cd" in executed_sql.lower()
    assert "dt_tm" in executed_sql.lower()

# =================================================================
# C. GET /api/data/market-cap 테스트
# =================================================================

def test_market_cap_returns_correct_data_for_date_range(client, mocker):
    """
    TC-06: 시가총액 데이터가 날짜 범위 내에서 올바르게 반환되는지 검증
    """
    mock_market_cap_repo = MagicMock()
    mock_market_cap_repo.get_daily_market_cap.return_value = [
        {"dt": date(2026, 5, 23), "stk_cd": "005930", "cls_prc": 70000, "mkt_cap": 4200000000000, "vol": 100000, "amt": 7000000000, "listed_shares": 6000000000}
    ]
    app.dependency_overrides[get_market_cap_repo] = lambda: mock_market_cap_repo

    response = client.get("/api/data/market-cap?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["mkt_cap"] == 4200000000000
    assert body[0]["dt"] == "2026-05-23"
    app.dependency_overrides.clear()

def test_market_cap_empty_result_returns_empty_list(client, mocker):
    """
    TC-07: 해당 기간 데이터 없을 때 빈 리스트 반환 (500 아닌 200)
    """
    mock_market_cap_repo = MagicMock()
    mock_market_cap_repo.get_daily_market_cap.return_value = []
    app.dependency_overrides[get_market_cap_repo] = lambda: mock_market_cap_repo

    response = client.get("/api/data/market-cap?stk_cd=999999&start_date=2026-01-01&end_date=2026-01-01")
    assert response.status_code == 200
    assert response.json() == []
    app.dependency_overrides.clear()

# =================================================================
# D. POST /api/data/screening 테스트
# =================================================================

def test_screening_filters_by_roe(client, mocker):
    """
    TC-08: min_roe 조건으로 재무비율 필터링이 동작하는지 검증
    """
    mock_financial_repo = MagicMock()
    mock_financial_repo.screen_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자", "stac_yymm": "202503", "roe_val": 15.0}
    ]
    app.dependency_overrides[get_financial_repo] = lambda: mock_financial_repo

    payload = {
        "stac_yymm": "202503",
        "div_cls_code": "1",
        "filters": [
            {"field": "roe_val", "operator": "gte", "value": 10.0}
        ]
    }
    response = client.post("/api/data/screening", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["stk_cd"] == "005930"
    assert body[0]["roe_val"] == 15.0
    app.dependency_overrides.clear()

def test_screening_with_no_matching_stocks_returns_empty(client, mocker):
    """
    TC-09: 조건에 맞는 종목이 없을 때 빈 리스트 반환
    """
    mock_financial_repo = MagicMock()
    mock_financial_repo.screen_stocks.return_value = []
    app.dependency_overrides[get_financial_repo] = lambda: mock_financial_repo

    payload = {
        "stac_yymm": "202503",
        "div_cls_code": "1",
        "filters": [
            {"field": "roe_val", "operator": "gte", "value": 999.0}
        ]
    }
    response = client.post("/api/data/screening", json=payload)
    assert response.status_code == 200
    assert response.json() == []
    app.dependency_overrides.clear()

def test_screening_invalid_body_returns_422(client):
    """
    TC-10: 필수 필드 누락 시 422 반환
    """
    # stac_yymm 누락
    payload = {
        "div_cls_code": "1"
    }
    response = client.post("/api/data/screening", json=payload)
    assert response.status_code == 422

# =================================================================
# E. GET /api/data/preview/{table} 테스트
# =================================================================

def test_preview_allowed_table_returns_data(client, mocker):
    """
    TC-11: 허용된 테이블명 입력 시 데이터를 반환하는지 검증
    """
    from routers.data import get_db_pool
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        ("005930", date(2026, 5, 23), 70000, 71000, 69000, 70000, 100000)
    ]
    # descripton
    mock_cursor.description = [
        ("stk_cd",), ("dt",), ("open_prc",), ("high_prc",), ("low_prc",), ("cls_prc",), ("vol",)
    ]
    app.dependency_overrides[get_db_pool] = lambda: mock_pool

    response = client.get("/api/data/preview/daily_ohlcv?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["table"] == "daily_ohlcv"
    assert "data" in body
    app.dependency_overrides.clear()

def test_preview_disallowed_table_returns_400(client):
    """
    TC-12: 허용 목록에 없는 테이블명 시 400 반환
    """
    response = client.get("/api/data/preview/users?limit=3")
    assert response.status_code == 400

def test_preview_limit_capped_at_1000(client, mocker):
    """
    TC-13: limit=2000 요청해도 실제로 1000건 이하만 조회하는지 검증
    """
    from routers.data import get_db_pool
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    mock_cursor.description = [("stk_cd",)]
    app.dependency_overrides[get_db_pool] = lambda: mock_pool

    response = client.get("/api/data/preview/daily_ohlcv?limit=2000")
    assert response.status_code == 200
    
    # execute 인자 검사
    assert len(mock_cursor.execute.call_args_list) >= 1
    args = mock_cursor.execute.call_args_list[-1][0]
    params = args[1]
    # params = params_where + [limit, offset] 이므로 뒤에서 두 번째가 limit
    assert params[-2] == 1000
    app.dependency_overrides.clear()

# =================================================================
# F. 회귀 테스트 (기존 API 보존)
# =================================================================

def test_existing_get_stocks_still_works(client, mocker):
    """
    TC-17: T-007 변경 후에도 기존 GET /api/data/stocks 가 정상 동작하는지 회귀 검증
    """
    mock_master_repo = MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930", "stk_nm": "삼성전자"}]
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo

    response = client.get("/api/data/stocks")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["stk_cd"] == "005930"
    app.dependency_overrides.clear()

def test_existing_get_financials_still_works(client, mocker):
    """
    TC-18: T-007 변경 후 GET /api/data/financials 가 정상 동작하는지 회귀 검증
    """
    mock_financial_repo = MagicMock()
    mock_financial_repo.get_statements_as_of.return_value = [{"stk_cd": "005930", "stac_yymm": "202512"}]
    mock_financial_repo.get_ratios_as_of.return_value = [{"stk_cd": "005930", "stac_yymm": "202512"}]
    app.dependency_overrides[get_financial_repo] = lambda: mock_financial_repo

    response = client.get("/api/data/financials?stk_cd=005930&as_of_date=2026-05-23")
    assert response.status_code == 200
    body = response.json()
    assert "statements" in body
    assert "ratios" in body
    app.dependency_overrides.clear()

# =================================================================
# G. 조회 품질 테스트
# =================================================================

def test_minute_ohlcv_rejects_range_over_30_days(client):
    """
    TC-19: 분봉 날짜 범위가 30일 초과 시 API 레이어에서 즉시 400 반환하는지 검증
    """
    response = client.get("/api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-01-01&end_dt=2026-03-01")
    assert response.status_code == 400
    assert "30일" in response.json()["detail"]

def test_minute_ohlcv_accepts_exactly_30_day_range(client, mocker):
    """
    TC-20: 정확히 30일 범위는 허용되는지 경계값 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_ohlcv_repo.get_minute_ohlcv.return_value = []
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo

    # 4월 27일부터 5월 27일까지는 정확히 30일 차이
    response = client.get("/api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-04-27&end_dt=2026-05-27")
    assert response.status_code == 200
    app.dependency_overrides.clear()

def test_minute_ohlcv_returns_arrow_stream_when_requested(client, mocker):
    """
    TC-21: Accept: application/vnd.apache.arrow.stream 헤더 시 Arrow IPC 응답을 반환하는지 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_ohlcv_repo.get_minute_ohlcv.return_value = [
        {"stk_cd": "005930", "dt_tm": datetime(2026, 5, 27, 9, 0, tzinfo=KST), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 1000}
    ]
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo

    response = client.get(
        "/api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-05-27&end_dt=2026-05-27",
        headers={"Accept": "application/vnd.apache.arrow.stream"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apache.arrow.stream"
    
    # 바이너리 스트림 읽기
    stream = response.content
    reader = ipc.open_stream(io.BytesIO(stream))
    table = reader.read_all()
    assert "stk_cd" in table.column_names
    assert "dt_tm" in table.column_names
    assert table.to_pydict()["stk_cd"] == ["005930"]
    app.dependency_overrides.clear()

def test_minute_ohlcv_no_pandas_in_repo_method():
    """
    TC-22: OhlcvRepo.get_minute_ohlcv() 구현에 pandas가 임포트/사용되지 않는지 정적 검증
    """
    import inspect
    from repositories.ohlcv_repo import OhlcvRepo
    source = inspect.getsource(OhlcvRepo.get_minute_ohlcv)
    assert "import pandas" not in source
    assert "pd.DataFrame" not in source
    assert "pd." not in source

def test_screening_uses_db_level_filter_not_python_filter(client, mocker):
    """
    TC-23: Screening이 DB 레벨에서 필터링함을 검증 (전체 종목 조회 후 Python 필터 방식이 아닌지 검증)
    """
    mock_financial_repo = MagicMock()
    mock_financial_repo.screen_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자", "stac_yymm": "202503", "roe_val": 15.0}
    ]
    app.dependency_overrides[get_financial_repo] = lambda: mock_financial_repo

    payload = {
        "stac_yymm": "202503",
        "div_cls_code": "1",
        "filters": [
            {"field": "roe_val", "operator": "gte", "value": 10.0}
        ]
    }
    response = client.post("/api/data/screening", json=payload)
    assert response.status_code == 200
    
    mock_financial_repo.screen_stocks.assert_called_once()
    # get_ratios_as_of나 get_statements_as_of 가 호출되지 않았는지 확인
    assert not mock_financial_repo.get_ratios_as_of.called
    assert not mock_financial_repo.get_statements_as_of.called
    app.dependency_overrides.clear()

def test_preview_supports_limit_offset_pagination(client, mocker):
    """
    TC-24: Preview API가 LIMIT + OFFSET 페이지네이션을 올바르게 지원하는지 검증
    """
    from routers.data import get_db_pool
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    mock_cursor.description = [("stk_cd",)]
    app.dependency_overrides[get_db_pool] = lambda: mock_pool

    response = client.get("/api/data/preview/daily_ohlcv?limit=3&offset=6")
    assert response.status_code == 200
    
    assert len(mock_cursor.execute.call_args_list) >= 1
    args = mock_cursor.execute.call_args_list[-1][0]
    params = args[1]
    # LIMIT %s OFFSET %s 에 전달된 파라미터 확인 (끝에서 2개)
    assert params[-2] == 3
    assert params[-1] == 6
    app.dependency_overrides.clear()
