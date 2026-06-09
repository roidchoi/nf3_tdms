# tdms_core/p3_usdms/tests/test_health_release.py
import pytest
from fastapi.testclient import TestClient

def test_usdms_release_blacklist_endpoint(mocker):
    """
    [Tier 2 - 격리 통합]
    [목적] USDMS 백엔드에 신설될 POST /api/health/blacklist/{cik}/release API가
           BlacklistRepo.release_blacklist를 올바르게 호출하는가 검증.
    """
    # BlacklistRepo 모킹
    mock_repo = mocker.Mock()
    mock_repo.release_blacklist.return_value = None
    mocker.patch("p3_usdms.routers.health.BlacklistRepo", return_value=mock_repo)

    from p3_usdms.main import app
    client = TestClient(app)

    response = client.post("/api/health/blacklist/0000320193/release")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    mock_repo.release_blacklist.assert_called_once_with("0000320193", admin_note="Released via P4 Manager Dashboard")
