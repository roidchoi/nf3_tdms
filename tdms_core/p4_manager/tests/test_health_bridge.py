# tdms_core/p4_manager/tests/test_health_bridge.py
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
# 1. GET /api/mgr/health/freshness/{market} 테스트 (Tier 2)
# =================================================================

def test_get_integrated_freshness_kr_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 백엔드의 신선도 데이터를 성공적으로 조회 및 중계하는지 검증.
    """
    mock_respx.get("http://p2_kdms:8000/api/health/freshness").respond(
        json={
            "status": "GREEN",
            "latest_trading_date": "2026-06-08",
            "total_active_stocks": 2000,
            "collected_daily_count": 1990,
            "daily_coverage_ratio": 0.995,
            "is_daily_fresh": True,
            "latest_minute_timestamp": "2026-06-08T15:30:00",
            "is_minute_fresh": True
        },
        status_code=200
    )
    
    response = client.get("/api/mgr/health/freshness/kr")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "GREEN"
    assert data["latest_trading_date"] == "2026-06-08"
    assert data["total_active_stocks"] == 2000
    assert data["is_daily_fresh"] is True

def test_get_integrated_freshness_us_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 백엔드의 신선도 데이터를 성공적으로 조회 및 중계하는지 검증.
    """
    mock_respx.get("http://p3_usdms:8005/api/health/freshness").respond(
        json={
            "status": "GREEN",
            "latest_trading_date": "2026-06-08",
            "total_active_stocks": 3900,
            "collected_daily_count": 3890,
            "daily_coverage_ratio": 0.9974,
            "is_daily_fresh": True
        },
        status_code=200
    )
    
    response = client.get("/api/mgr/health/freshness/us")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "GREEN"
    assert data["latest_trading_date"] == "2026-06-08"
    assert data["is_daily_fresh"] is True

def test_get_integrated_freshness_offline_fallback(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 백엔드 오프라인 장애 시 503 전파 없이 status: RED 및 offline: true 응답을 반환하는지 격리 검증.
    """
    # KDMS 정상, USDMS 연결 오류 시뮬레이션
    mock_respx.get("http://p2_kdms:8000/api/health/freshness").respond(200, json={"status": "GREEN"})
    mock_respx.get("http://p3_usdms:8005/api/health/freshness").respond(503)

    response_kr = client.get("/api/mgr/health/freshness/kr")
    assert response_kr.status_code == 200
    assert response_kr.json()["status"] == "GREEN"

    response_us = client.get("/api/mgr/health/freshness/us")
    assert response_us.status_code == 200
    assert response_us.json()["status"] == "RED"
    assert response_us.json()["offline"] is True

# =================================================================
# 2. GET /api/mgr/health/gaps/{market} 테스트 (Tier 2)
# =================================================================

def test_get_integrated_gaps_kr_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 백엔드의 갭 데이터를 정규화 구조로 매핑 반환하는지 검증.
    """
    mock_respx.get("http://p2_kdms:8000/api/health/gaps?start_date=2026-06-08&end_date=2026-06-08").respond(
        json={
            "status": "GREEN",
            "start_date": "2026-06-08",
            "end_date": "2026-06-08",
            "minute_gaps": [
                {
                    "date": "2026-06-08",
                    "status": "GREEN",
                    "total_targets": 2000,
                    "suspended_targets": 10,
                    "gap_excluded_targets": 5,
                    "valid_targets": 1985,
                    "missing_stocks_count": 2,
                    "missing_stocks": ["005930", "000660"],
                    "valid_collection_rate": 99.9
                }
            ]
        },
        status_code=200
    )

    response = client.get("/api/mgr/health/gaps/kr?start_date=2026-06-08&end_date=2026-06-08")
    assert response.status_code == 200
    data = response.json()
    assert data["market"] == "kr"
    assert len(data["gaps"]) == 1
    gap = data["gaps"][0]
    assert gap["date"] == "2026-06-08"
    assert gap["total_targets"] == 2000
    assert gap["valid_targets"] == 1985
    assert gap["missing_count"] == 2
    assert gap["missing_items"] == ["005930", "000660"]

def test_get_integrated_gaps_us_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 백엔드의 갭 데이터를 정규화 구조로 매핑 반환하는지 검증.
    """
    mock_respx.get("http://p3_usdms:8005/api/health/gaps?start_date=2026-06-08&end_date=2026-06-08").respond(
        json={
            "start_date": "2026-06-08",
            "end_date": "2026-06-08",
            "minute_gaps": [
                {
                    "date": "2026-06-08",
                    "total_targets": 3900,
                    "valid_targets": 3890,
                    "collected_count": 3888,
                    "valid_collection_rate": 99.95,
                    "gaps_count": 2
                }
            ]
        },
        status_code=200
    )

    response = client.get("/api/mgr/health/gaps/us?start_date=2026-06-08&end_date=2026-06-08")
    assert response.status_code == 200
    data = response.json()
    assert data["market"] == "us"
    assert len(data["gaps"]) == 1
    gap = data["gaps"][0]
    assert gap["total_targets"] == 3900
    assert gap["valid_targets"] == 3890
    assert gap["missing_count"] == 2
    assert gap["missing_items"] == []

# =================================================================
# 3. 마일스톤 및 블랙리스트 중계 테스트 (Tier 2)
# =================================================================

def test_get_kr_milestones_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 마일스톤 리스트 조회 중계를 검증.
    """
    mock_respx.get("http://p2_kdms:8000/api/health/milestones").respond(
        json=[
            {
                "milestone_name": "DB_INIT",
                "milestone_date": "2026-06-01",
                "description": "Initial Database Setup",
                "updated_at": "2026-06-01T12:00:00"
            }
        ],
        status_code=200
    )

    response = client.get("/api/mgr/health/kr/milestones")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["milestone_name"] == "DB_INIT"

def test_post_kr_milestone_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 마일스톤 등록/수정 중계를 검증.
    """
    mock_payload = {
        "milestone_name": "T006_COMPLETED",
        "milestone_date": "2026-06-09",
        "description": "Completed T-006 Task"
    }
    mock_respx.post("http://p2_kdms:8000/api/health/milestones", json=mock_payload).respond(
        json={"status": "SUCCESS", "message": "Milestone registered successfully"},
        status_code=200
    )

    response = client.post("/api/mgr/health/kr/milestones", json=mock_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_get_us_blacklist_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 블랙리스트 조회 중계를 검증.
    """
    mock_respx.get("http://p3_usdms:8005/api/health/blacklist").respond(
        json={
            "status": "success",
            "blocked_count": 1,
            "blacklist": [
                {
                    "cik": "0000320193",
                    "ticker": "AAPL",
                    "reason_cd": "TIMEOUT",
                    "detail": "Connection timed out repeatedly",
                    "is_blocked": True
                }
            ]
        },
        status_code=200
    )

    response = client.get("/api/mgr/health/us/blacklist")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["blocked_count"] == 1
    assert data["blacklist"][0]["ticker"] == "AAPL"

def test_release_us_blacklist_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 CIK 차단 해제 중계를 검증.
    """
    mock_respx.post("http://p3_usdms:8005/api/health/blacklist/0000320193/release").respond(
        json={"status": "SUCCESS", "message": "CIK 0000320193 released"},
        status_code=200
    )

    response = client.post("/api/mgr/health/us/blacklist/0000320193/release")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
