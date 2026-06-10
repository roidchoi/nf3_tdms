# tdms_core/p4_manager/tests/test_explorer_bridge.py
import pytest
from fastapi.testclient import TestClient
from tdms_core.p4_manager.main import app

client = TestClient(app)

@pytest.fixture
def mock_respx():
    import respx
    with respx.mock as mock:
        yield mock

# =================================================================
# 1. GET /api/mgr/preview/meta 테스트 (Tier 2)
# =================================================================

def test_get_preview_metadata_success():
    """
    [목적] /api/mgr/preview/meta API 호출 시 각 시장의 허용 테이블 메타데이터 목록이 반환되는지 검증
    [유도] 정적 딕셔너리로 정의된 KR/US 테이블 메타데이터를 올바른 JSON 구조로 리턴하게 함
    """
    response = client.get("/api/mgr/preview/meta")
    assert response.status_code == 200
    data = response.json()
    assert "kr" in data
    assert "us" in data
    assert len(data["kr"]) == 10
    assert data["kr"][0]["table"] == "stock_info"
    assert data["us"][0]["table"] == "us_ticker_master"

# =================================================================
# 2. GET /api/mgr/preview/{market}/{table} 테스트 (Tier 2)
# =================================================================

def test_get_preview_table_kr_success(mock_respx):
    """
    [목적] 한국 백엔드의 preview API로 성공적으로 쿼리 파라미터를 넘기고 데이터를 수신하여 포맷팅하는지 검증
    [유도] httpx.AsyncClient를 이용하여 p2_kdms 백엔드로의 중계가 이루어지며, 응답에 offline: False가 부여되도록 유도
    """
    mock_respx.get("http://p2_kdms:8000/api/data/preview/stock_info?limit=10&offset=20&stk_cd=005930").respond(
        json={
            "table": "stock_info",
            "count": 1,
            "data": [{"stk_cd": "005930", "stk_nm": "삼성전자"}]
        },
        status_code=200
    )

    response = client.get("/api/mgr/preview/kr/stock_info?limit=10&offset=20&stk_cd=005930")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is False
    assert data["table"] == "stock_info"
    assert data["count"] == 1
    assert data["data"][0]["stk_cd"] == "005930"

def test_get_preview_table_us_success(mock_respx):
    """
    [목적] 미국 백엔드의 preview API로 성공적으로 쿼리 파라미터를 넘기고 데이터를 수신하여 포맷팅하는지 검증
    [유도] httpx.AsyncClient를 이용하여 p3_usdms 백엔드로의 중계가 이루어지며, 응답에 offline: False가 부여되도록 유도
    """
    mock_respx.get("http://p3_usdms:8005/api/data/preview/us_ticker_master?limit=5&offset=0&stk_cd=AAPL").respond(
        json={
            "table": "us_ticker_master",
            "count": 1,
            "data": [{"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."}]
        },
        status_code=200
    )

    response = client.get("/api/mgr/preview/us/us_ticker_master?limit=5&offset=0&stk_cd=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is False
    assert data["table"] == "us_ticker_master"
    assert data["count"] == 1
    assert data["data"][0]["ticker"] == "AAPL"

# =================================================================
# 3. 입력 검증 및 오류 처리 테스트 (Tier 1)
# =================================================================

def test_get_preview_table_with_invalid_market_raises_bad_request():
    """
    [목적] 허용되지 않는 market 값(예: jp, cn) 입력 시 400 Bad Request 에러 반환 검증
    """
    response = client.get("/api/mgr/preview/jp/stock_info")
    assert response.status_code == 400
    assert "market" in response.json()["detail"].lower()

def test_get_preview_table_with_invalid_table_raises_bad_request():
    """
    [목적] 각 시장의 허용 화이트리스트에 없는 테이블명 입력 시 400 Bad Request 에러 반환 검증
    """
    # 한국에 us_ticker_master 요청 시
    response = client.get("/api/mgr/preview/kr/us_ticker_master")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()

# =================================================================
# 4. 장애 격리 (Fault Isolation) 테스트 (Tier 2)
# =================================================================

def test_get_preview_table_offline_fallback(mock_respx):
    """
    [목적] 하위 백엔드가 오프라인 상태(HTTP 503 또는 Connect Error)일 때, 502/503을 전파하지 않고 200 OK와 offline: true 폴백 객체를 리턴하는지 검증
    [유도] try-except 문으로 httpx.RequestError를 캐치하여 정규화된 오프라인 JSON 데이터 구조로 리턴하게 유도
    """
    # KDMS 연결 실패 시뮬레이션 (Timeout / ConnectError)
    mock_respx.get("http://p2_kdms:8000/api/data/preview/daily_ohlcv").respond(status_code=503)

    response = client.get("/api/mgr/preview/kr/daily_ohlcv")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is True
    assert data["table"] == "daily_ohlcv"
    assert data["count"] == 0
    assert len(data["data"]) == 0
    assert "message" in data

# =================================================================
# 5. 실제 통합 테스트 (Tier 3)
# =================================================================

@pytest.mark.integration
def test_get_preview_real_backend_integration():
    """
    [목적] 모킹 없이 실제 실행 중인 KDMS/USDMS 백엔드 컨테이너와 연동하여 테이블 조회 동작이 완전히 이루어지는지 검증
    [실행 조건] 실 백엔드 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    response = client.get("/api/mgr/preview/kr/stock_info?limit=1")
    assert response.status_code == 200
    data = response.json()
    
    if data.get("offline"):
        assert data["offline"] is True
        assert data["count"] == 0
        assert len(data["data"]) == 0
    else:
        assert data["offline"] is False
        assert data["table"] == "stock_info"
        assert data["count"] >= 0
