# tests/test_data_router.py
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

def test_get_tickers_with_filters(mocker):
    """
    [목적] /api/data/tickers 엔드포인트가 exchange, is_collect_target 쿼리 필터를 레포지토리에 잘 바인딩해 호출하는가 검증.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_tickers_filtered.return_value = [{"cik": "0000320193", "latest_ticker": "AAPL"}]
    
    mocker.patch("p3_usdms.routers.data.MasterRepo", return_value=mock_repo)
    
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/tickers?exchange=NASDAQ&is_collect_target=true")
    
    assert response.status_code == 200
    mock_repo.get_tickers_filtered.assert_called_once_with(exchange="NASDAQ", is_collect_target=True)
    assert response.json() == [{"cik": "0000320193", "latest_ticker": "AAPL"}]

def test_get_daily_prices_raw_returns_original(mocker):
    """
    [목적] adjusted=False 일 때, raw daily price 데이터를 온더플라이 조정 없이 그대로 반환하는가 검증.
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = [
        {"dt": date(2026, 6, 1), "cik": "0000320193", "ticker": "AAPL", "open_prc": 100.0, "high_prc": 105.0, "low_prc": 98.0, "cls_prc": 110.0, "vol": 1000, "amt": 110000.0}
    ]
    mock_price_repo.get_price_factors.return_value = []
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/price/daily?cik=0000320193&adjusted=false")
    
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) == 1
    assert res_data[0]["dt"] == "2026-06-01"
    assert res_data[0]["cls_prc"] == 110.0

def test_get_daily_prices_adjusted_performs_on_the_fly_calculation(mocker):
    """
    [목적] adjusted=True 일 때, 가격 수정계수(factor_val)가 주가 정보(open_prc, high_prc, low_prc, cls_prc)에 
           누적으로 온더플라이 곱해지는지 검증.
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = [
        {"dt": date(2026, 6, 1), "cik": "0000320193", "ticker": "AAPL", "open_prc": 100.0, "high_prc": 105.0, "low_prc": 98.0, "cls_prc": 100.0, "vol": 1000, "amt": 100000.0},
        {"dt": date(2026, 6, 2), "cik": "0000320193", "ticker": "AAPL", "open_prc": 110.0, "high_prc": 125.0, "low_prc": 108.0, "cls_prc": 120.0, "vol": 2000, "amt": 240000.0},
        {"dt": date(2026, 6, 3), "cik": "0000320193", "ticker": "AAPL", "open_prc": 60.0, "high_prc": 68.0, "low_prc": 59.0, "cls_prc": 65.0, "vol": 4000, "amt": 260000.0},
    ]
    # event_dt=2026-06-03에 factor 0.5 발생
    mock_price_repo.get_price_factors.return_value = [
        {"cik": "0000320193", "event_dt": date(2026, 6, 3), "factor_val": 0.5, "event_type": "ADJUSTMENT"}
    ]
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
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

def test_get_financials_with_pit_enabled(mocker):
    """
    [목적] pit=True(기본값) 일 때, as_of 일자 기준의 PIT 조회 메서드(get_standard_financials_pit)가 호출되는지 검증.
    """
    mock_fin_repo = mocker.Mock()
    mock_fin_repo.get_standard_financials_pit.return_value = [
        {"cik": "0000320193", "report_period": date(2026, 3, 31), "filed_dt": date(2026, 4, 15), "revenue": 90000.0}
    ]
    mocker.patch("p3_usdms.routers.data.FinancialRepo", return_value=mock_fin_repo)
    
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/financials?cik=0000320193&pit=true")
    
    assert response.status_code == 200
    mock_fin_repo.get_standard_financials_pit.assert_called_once()
    assert response.json()[0]["revenue"] == 90000.0

def test_get_preview_limits_maximum_records(mocker):
    """
    [목적] preview 테이블 호출 시, limit 파라미터가 1000을 넘을 경우 강제로 1000으로 제한(cap)되는가 검증.
    """
    mock_pool = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = [0]
    mock_cursor.fetchall.return_value = []
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    from p3_usdms.routers.data import get_db_pool
    from p3_usdms.main import app
    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    
    client = TestClient(app)
    
    # 허용된 테이블 중 하나인 us_daily_price 조회
    response = client.get("/api/data/preview/us_daily_price?limit=9999")
    
    assert response.status_code == 200
    
    select_executed = False
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        if "SELECT" in query_str and "LIMIT" in query_str:
            select_executed = True
            params = call[0][1]
            # select_params: [limit, offset] 순으로 들어감
            assert params[-2] == 1000
            
    assert select_executed is True
    app.dependency_overrides.clear()

def test_get_preview_forbidden_table_returns_400():
    """
    [목적] ALLOWED_TABLES에 등록되지 않은 테이블명을 preview/{table} 경로에 전달 시 400 에러 차단 검증.
    """
    from p3_usdms.main import app
    client = TestClient(app)
    
    response = client.get("/api/data/preview/users")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()
    
    response = client.get("/api/data/preview/pg_shadow")
    assert response.status_code == 400

def test_get_preview_with_empty_date_column_skips_where_date_clause(mocker):
    """
    [목적] TABLE_DATE_COLUMNS에 매핑된 날짜 컬럼 정보가 없는 테이블에 날짜 필터를 줘도 날짜 쿼리가 생략됨을 검증.
    """
    mock_pool = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = [0]
    mock_cursor.fetchall.return_value = []
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    from p3_usdms.routers.data import get_db_pool
    from p3_usdms.main import app
    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    
    client = TestClient(app)
    
    response = client.get("/api/data/preview/us_ticker_master?start_date=2026-01-01&end_date=2026-06-01")
    
    assert response.status_code == 200
    
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        assert ">=" not in query_str
        assert "<=" not in query_str
        
    app.dependency_overrides.clear()

def test_get_daily_prices_default_range_throttling(mocker):
    """
    [목적] start_dt, end_dt가 제공되지 않는 경우 기본 1년 범위를 지정하고,
           조회 기간이 15년을 초과할 경우 400 에러를 반환하는 Throttling 검증.
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = []
    mock_price_repo.get_price_factors.return_value = []
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
    from p3_usdms.main import app
    client = TestClient(app)
    
    # 1. 날짜 범위 미지정 시 기본 1년
    response = client.get("/api/data/price/daily?cik=0000320193")
    assert response.status_code == 200
    # PriceRepo.get_daily_prices가 오늘 날짜 - 1년 ~ 오늘 날짜로 호출되었는지 확인
    args = mock_price_repo.get_daily_prices.call_args[0]
    # args: (cik, start_dt, end_dt)
    start_dt_val = datetime.strptime(args[1], "%Y-%m-%d").date()
    end_dt_val = datetime.strptime(args[2], "%Y-%m-%d").date()
    assert (end_dt_val - start_dt_val).days in [365, 366]
    
    # 2. 날짜 범위 15년 초과 시 400 에러
    response = client.get("/api/data/price/daily?cik=0000320193&start_dt=2010-01-01&end_dt=2026-01-01")
    assert response.status_code == 400
    assert "cannot exceed 15 years" in response.json()["detail"].lower()

def test_get_daily_prices_arrow_serialization(mocker):
    """
    [목적] Accept 헤더에 'application/vnd.apache.arrow.stream'이 감지될 경우 Apache Arrow 바이너리 포맷으로 직렬화 및 반환 검증.
    """
    mock_price_repo = mocker.Mock()
    mock_price_repo.get_daily_prices.return_value = [
        {"dt": date(2026, 6, 1), "cik": "0000320193", "ticker": "AAPL", "open_prc": 100.0, "high_prc": 105.0, "low_prc": 98.0, "cls_prc": 110.0, "vol": 1000, "amt": 110000.0}
    ]
    mock_price_repo.get_price_factors.return_value = []
    mocker.patch("p3_usdms.routers.data.PriceRepo", return_value=mock_price_repo)
    
    from p3_usdms.main import app
    client = TestClient(app)
    
    # Accept 헤더에 arrow 명시
    headers = {"Accept": "application/vnd.apache.arrow.stream"}
    response = client.get("/api/data/price/daily?cik=0000320193", headers=headers)
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apache.arrow.stream"
    
    # 바이너리 스트림 검증 (pyarrow로 복원)
    import pyarrow as pa
    import pyarrow.ipc as ipc
    
    reader = ipc.open_stream(response.content)
    table = reader.read_all()
    assert table.num_rows == 1
    assert table.column("ticker")[0].as_py() == "AAPL"
    assert table.column("cls_prc")[0].as_py() == 110.0

@pytest.mark.integration
def test_api_endpoints_e2e_with_real_db(real_pool):
    """
    [목적] 실제 DB(real_pool)가 기동 중인 상태에서 7종 데이터 조회 API 엔드포인트의 통신과 결과 형태를 검증합니다.
    """
    from p3_usdms.main import app
    from p3_usdms.routers.data import get_db_pool
    
    app.dependency_overrides[get_db_pool] = lambda: real_pool
    client = TestClient(app)
    
    try:
        # [1] Tickers API
        res = client.get("/api/data/tickers")
        assert res.status_code == 200
        tickers_list = res.json()
        assert isinstance(tickers_list, list)
        
        target_cik = None
        for t in tickers_list:
            if t.get("is_collect_target"):
                target_cik = t["cik"]
                break
        
        if not target_cik:
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
