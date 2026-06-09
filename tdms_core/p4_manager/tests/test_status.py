# tdms_core/p4_manager/tests/test_status.py
import pytest
import respx
from httpx import Response
from fastapi.testclient import TestClient

try:
    from tdms_core.p4_manager.main import app
    from tdms_core.p4_manager.services.status_service import status_service
    client = TestClient(app)
except ImportError:
    client = None
    status_service = None

@pytest.mark.asyncio
@respx.mock
async def test_status_aggregation_success_normalizes_data():
    """
    [Tier 2 — 격리 통합]
    [목적] p2_kdms와 p3_usdms가 정상 응답할 때, status_service가 데이터를 가져와 규격에 맞게 캐싱 및 정규화하는지 검증.
    """
    if status_service is None or client is None:
        pytest.fail("상태 서비스 또는 FastAPI 앱을 임포트할 수 없습니다 (구현 전)")

    # 1. KDMS (p2) Mock 응답 설정
    p2_freshness = {
        "status": "GREEN",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 2500,
        "collected_daily_count": 2490,
        "daily_coverage_ratio": 0.996,
        "is_daily_fresh": True
    }
    p2_tasks = {
        "daily_update": {"is_running": False, "last_status": "success", "last_run_time": "2026-06-08T17:05:00"},
        "financial_update": {"is_running": False, "last_status": "none"}
    }
    respx.get("http://p2_kdms:8000/api/health/freshness").mock(return_value=Response(200, json=p2_freshness))
    respx.get("http://p2_kdms:8000/api/v1/admin/tasks/status").mock(return_value=Response(200, json=p2_tasks))

    # 2. USDMS (p3) Mock 응답 설정
    p3_freshness = {
        "status": "YELLOW",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 6000,
        "collected_daily_count": 5800,
        "daily_coverage_ratio": 0.966,
        "is_daily_fresh": True
    }
    p3_tasks = [
        {"file_name": "daily_routine_2026-06-08.json", "status": "SUCCESS", "end_time": "2026-06-09T07:35:00", "is_running": False},
        {"file_name": "weekly_backfill_2026-06-06.json", "status": "SUCCESS", "end_time": "2026-06-06T09:40:00", "is_running": False}
    ]
    respx.get("http://p3_usdms:8005/api/health/freshness").mock(return_value=Response(200, json=p3_freshness))
    respx.get("http://p3_usdms:8005/api/admin/tasks/status").mock(return_value=Response(200, json=p3_tasks))

    # status_service 수동 갱신 실행
    await status_service.fetch_and_cache_status()

    # /api/mgr/status 호출 및 단언
    response = client.get("/api/mgr/status")
    assert response.status_code == 200
    data = response.json()

    # KR 검증
    assert data["kr"]["status"] == "ONLINE"
    assert data["kr"]["freshness"]["status"] == "GREEN"
    assert data["kr"]["freshness"]["daily_coverage_ratio"] == 0.996
    assert data["kr"]["tasks"]["is_running"] is False
    assert data["kr"]["tasks"]["last_status"] == "success"

    # US 검증
    assert data["us"]["status"] == "ONLINE"
    assert data["us"]["freshness"]["status"] == "YELLOW"
    assert data["us"]["freshness"]["daily_coverage_ratio"] == 0.966
    assert data["us"]["tasks"]["is_running"] is False

@pytest.mark.asyncio
@respx.mock
async def test_status_aggregation_handles_kr_offline_safely():
    """
    [Tier 2 — 격리 통합]
    [목적] p2_kdms가 다운되었거나 타임아웃(Connection Error) 발생 시, kr만 OFFLINE으로 표시하고 us 상태는 정상 제공하는지 장애 격리(Fault Isolation) 검증.
    """
    if status_service is None or client is None:
        pytest.fail("상태 서비스 또는 FastAPI 앱을 임포트할 수 없습니다 (구현 전)")

    # KR (p2) 오프라인 모사 (타임아웃 유발)
    respx.get("http://p2_kdms:8000/api/health/freshness").mock(side_effect=Exception("Connection Timeout"))
    respx.get("http://p2_kdms:8000/api/v1/admin/tasks/status").mock(side_effect=Exception("Connection Timeout"))

    # US (p3) 정상 응답 모사
    p3_freshness = {
        "status": "GREEN",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 6000,
        "collected_daily_count": 5950,
        "daily_coverage_ratio": 0.991,
        "is_daily_fresh": True
    }
    p3_tasks = []
    respx.get("http://p3_usdms:8005/api/health/freshness").mock(return_value=Response(200, json=p3_freshness))
    respx.get("http://p3_usdms:8005/api/admin/tasks/status").mock(return_value=Response(200, json=p3_tasks))

    # status_service 수동 갱신 실행
    await status_service.fetch_and_cache_status()

    response = client.get("/api/mgr/status")
    assert response.status_code == 200
    data = response.json()

    # KR 검증 (격리됨)
    assert data["kr"]["status"] == "OFFLINE"
    assert data["kr"]["freshness"] is None
    assert data["kr"]["tasks"] is None

    # US 검증 (정상 서빙)
    assert data["us"]["status"] == "ONLINE"
    assert data["us"]["freshness"]["status"] == "GREEN"

@pytest.mark.integration
def test_real_backend_status_integration():
    """
    [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
    [목적] 실제 기동된 p2_kdms 및 p3_usdms 컨테이너를 상대로 상태를 폴링하여 ONLINE 여부를 검증.
    """
    import httpx
    try:
        response = httpx.get("http://localhost:80/api/mgr/status", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        
        assert "kr" in data
        assert "us" in data
        assert data["kr"]["status"] in ["ONLINE", "OFFLINE"]
        assert data["us"]["status"] in ["ONLINE", "OFFLINE"]
    except httpx.ConnectError:
        pytest.skip("로컬 Nginx 포트 80(통합 환경)이 기동되어 있지 않아 실제 통합 테스트를 스킵합니다.")


def test_run_kr_task_success():
    """
    [Tier 2 - 격리 통합]
    [목적] POST /api/mgr/run?market=kr&task_id=daily_update 호출 시
           FastAPI 백엔드가 p2_kdms에 POST 요청을 보내고 200 응답을 정상 중계하는지 검증.
    """
    if client is None:
        pytest.fail("FastAPI 앱을 임포트할 수 없습니다.")
        
    with respx.mock:
        respx.post("http://p2_kdms:8000/api/v1/admin/tasks/daily_update/run").mock(
            return_value=Response(200, json={"status": "success"})
        )
        
        response = client.post("/api/mgr/run?market=kr&task_id=daily_update&is_test=true")
        assert response.status_code == 200
        assert response.json()["status"] == "success"


def test_run_us_task_success():
    """
    [Tier 2 - 격리 통합]
    [목적] POST /api/mgr/run?market=us&task_id=daily_routine 호출 시
           FastAPI 백엔드가 p3_usdms에 POST 요청을 보내고 200 응답을 정상 중계하는지 검증.
    """
    if client is None:
        pytest.fail("FastAPI 앱을 임포트할 수 없습니다.")

    with respx.mock:
        respx.post("http://p3_usdms:8005/api/admin/tasks/daily_routine/run").mock(
            return_value=Response(200, json={"status": "success"})
        )
        
        response = client.post("/api/mgr/run?market=us&task_id=daily_routine")
        assert response.status_code == 200
        assert response.json()["status"] == "success"


def test_run_task_invalid_params():
    """
    [Tier 2 - 격리 통합]
    [목적] 잘못된 market 파라미터 전달 시 400 Bad Request 에러 반환 검증.
    """
    if client is None:
        pytest.fail("FastAPI 앱을 임포트할 수 없습니다.")

    response = client.post("/api/mgr/run?market=invalid&task_id=daily_update")
    assert response.status_code == 400
    assert "Invalid market" in response.json()["detail"]


def test_run_task_backend_offline_fault_isolation():
    """
    [Tier 2 - 격리 통합]
    [목적] 대상 백엔드가 오프라인이거나 에러를 발생시킬 때 503 Service Unavailable 및 장애 격리 메시지 반환 검증.
    """
    if client is None:
        pytest.fail("FastAPI 앱을 임포트할 수 없습니다.")

    import httpx
    with respx.mock:
        respx.post("http://p3_usdms:8005/api/admin/tasks/daily_routine/run").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        
        response = client.post("/api/mgr/run?market=us&task_id=daily_routine")
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert "offline" in response.json()["message"]

