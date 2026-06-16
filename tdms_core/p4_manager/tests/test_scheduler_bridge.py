# tdms_core/p4_manager/tests/test_scheduler_bridge.py
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
# 1. GET /api/mgr/schedules/{market} 테스트 (Tier 2)
# =================================================================

def test_get_integrated_schedules_kr_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 백엔드의 스케줄 원본 데이터를 성공적으로 조회 및 정규화 변환하는지 검증.
    """
    mock_respx.get("http://p2_kdms:8000/api/v1/admin/tasks/scheduler").respond(
        json={
            "is_running": True,
            "jobs_count": 1,
            "jobs": [
                {
                    "id": "daily_update",
                    "name": "daily_update",
                    "next_run_time": "2026-06-09T17:00:00+09:00",
                    "trigger": "cron[hour='17', minute='0']"
                }
            ]
        },
        status_code=200
    )
    
    response = client.get("/api/mgr/schedules/kr")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["job_id"] == "daily_update"
    assert data[0]["is_paused"] is False
    assert "cron" in data[0]["trigger"]


def test_get_integrated_schedules_us_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 백엔드의 스케줄 원본 데이터를 성공적으로 조회 및 정규화 변환하는지 검증.
    """
    mock_respx.get("http://p3_usdms:8005/api/admin/schedules").respond(
        json=[
            {
                "job_id": "daily_collection_job",
                "name": "daily_collection_job",
                "next_run_time": None,
                "trigger": {"hour": "19", "minute": "0"}
            }
        ],
        status_code=200
    )
    
    response = client.get("/api/mgr/schedules/us")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["job_id"] == "daily_collection_job"
    assert data[0]["is_paused"] is True


def test_get_integrated_schedules_invalid_market():
    """
    [Tier 2 - 격리 통합]
    [목적] 잘못된 마켓 입력 시 400 Bad Request 에러 검증.
    """
    response = client.get("/api/mgr/schedules/jp")
    assert response.status_code == 400
    assert "market" in response.json()["detail"]


# =================================================================
# 2. PUT /api/mgr/schedules/{market}/{job_id} 테스트 (Tier 2)
# =================================================================

def test_update_integrated_schedule_kr_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 백엔드의 특정 작업 시간을 성공적으로 수정 중계하는지 검증.
    """
    mock_respx.put("http://p2_kdms:8000/api/v1/admin/tasks/scheduler?job_id=daily_update&hour=18&minute=30").respond(
        json={"status": "SUCCESS", "job_id": "daily_update", "hour": 18, "minute": 30},
        status_code=200
    )
    
    response = client.put("/api/mgr/schedules/kr/daily_update?hour=18&minute=30")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"


# =================================================================
# 3. POST /api/mgr/schedules/{market}/{job_id}/toggle 테스트 (Tier 2)
# =================================================================

def test_toggle_integrated_schedule_us_success(mock_respx):
    """
    [Tier 2 - 격리 통합]
    [목적] 미국 백엔드의 특정 작업을 성공적으로 일시정지 중계하는지 검증.
    """
    mock_respx.post("http://p3_usdms:8005/api/admin/schedules/daily_collection_job/toggle?action=pause").respond(
        json={"status": "PAUSED", "job_id": "daily_collection_job"},
        status_code=200
    )
    
    response = client.post("/api/mgr/schedules/us/daily_collection_job/toggle?action=pause")
    assert response.status_code == 200
    assert response.json()["status"] == "PAUSED"


def test_toggle_integrated_schedule_invalid_action():
    """
    [Tier 2 - 격리 통합]
    [목적] 잘못된 액션값 전달 시 400 에러 검증.
    """
    response = client.post("/api/mgr/schedules/kr/daily_update/toggle?action=delete")
    assert response.status_code == 400
