# tdms_core/p4_manager/tests/test_sync_service.py
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from tdms_core.p4_manager.main import app
from tdms_core.p4_manager.services.sync_service import SyncService

client = TestClient(app)

# ==========================================
# 1. 단위 / 격리 통합 테스트 (Tier 1 & Tier 2)
# ==========================================

def test_sync_task_with_invalid_confirm_text_raises_value_error():
    """
    [목적] 잘못된 confirm_text 입력 시 즉각 ValueError를 발생시켜 동작을 원천 차단하는지 검증.
    """
    service = SyncService()
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.run_sync_task(market="kdms", direction="pull", confirm_text="WRONG TEXT")


def test_sync_task_on_server_with_push_direction_raises_permission_error(mocker):
    """
    [목적] 운영 서버 PC(server)에서 Push(쓰기 수신) 명령이 유입될 때 403 Forbidden 오류에 해당하는 PermissionError를 발생시키는지 검증.
    """
    service = SyncService()
    mocker.patch.object(service.env_detector, "detect", return_value="server")
    
    with pytest.raises(PermissionError, match="서버 PC는 로컬 동기화 수신 쓰기 동작을 허용하지 않습니다"):
        service.run_sync_task(market="kdms", direction="push", confirm_text="PUSH TO SERVER")


def test_sync_sudo_verification_failure_raises_runtime_error(mocker):
    """
    [목적] sudo -n true 검사 결과 비밀번호를 요구하는 상황(Status != 0)일 때, 412 오류용 RuntimeError 및 가이드라인 문구를 적절히 반환하는지 검증.
    """
    service = SyncService()
    # sudo -n true 검증이 실패하는 Mocking (로컬 또는 원격 둘 중 하나 실패)
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "sudo: a password is required"

    with pytest.raises(RuntimeError) as exc_info:
        service.run_sync_task(market="kdms", direction="pull", confirm_text="PULL FROM SERVER")
    
    assert "NOPASSWD" in str(exc_info.value)  # 무인화 명령어 가이드 포함 여부 검증


def test_detect_server_ip_via_powershell_dns_resolver(mocker):
    """
    [목적] WSL2 환경에서 SERVER_HOSTNAME을 받아 powershell.exe DNS 리졸버 호출 결과로 올바른 IP 주소를 리팩토링 및 획득하는지 검증.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": "EDM-LAB-MD02"})
    
    # powershell.exe 결과 모의
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "192.168.35.176\n"
    
    # TCP 통신 검사 모의
    mocker.patch.object(service, "test_connection", return_value={"connected": True, "message": "Success"})

    res = service.detect_server_ip()
    assert res["server_ip"] == "192.168.35.176"
    assert res["method"] == "dns"


def test_detect_server_ip_via_async_port_scanning(mocker):
    """
    [목적] DNS 리졸브 실패 시, 로컬 IP 서브넷 대역을 훑는 비동기 포트 스캔을 수행하여 서버 PC를 정확히 색출해내는지 검증.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": ""})
    
    # 개발 PC IP 모킹
    mocker.patch("p1_shared.utils.env_detector.get_local_ips", return_value=["192.168.35.105"])
    
    # 192.168.35.176 만 서버로 식별되도록 비동기 Mocking
    async def mock_scan_ips(*args, **kwargs):
        return "192.168.35.176"
        
    mocker.patch.object(service, "_async_scan_subnet", side_effect=mock_scan_ips)

    res = service.detect_server_ip()
    assert res["server_ip"] == "192.168.35.176"
    assert res["method"] == "scan"


def test_update_ip_in_env_file_modifies_dev_or_server_ip(tmp_path, mocker):
    """
    [목적] 특정 IP 갱신 API 호출 시 .env 파일 내의 타깃 IP 변수(DEV_IP 또는 SERVER_IP)만 정확하게 수정 보존하는지 검증.
    """
    service = SyncService()
    env_content = "DEV_IP=192.168.35.10\nSERVER_IP=192.168.35.20\n"
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)
    
    mocker.patch("tdms_core.p4_manager.services.sync_service.ENV_FILE_PATH", str(env_file))
    
    service.sync_ip_in_env(target="server", new_ip="192.168.35.176")
    
    updated_content = env_file.read_text()
    assert "SERVER_IP=192.168.35.176" in updated_content
    assert "DEV_IP=192.168.35.10" in updated_content  # 기존 다른 변수 유지 보존


def test_test_connection_with_invalid_ip_format_returns_error():
    """
    [목적] 잘못된 형식의 IP(예: 문자열 "abc") 입력 시 에러 객체를 즉시 안전 반환하는지 검증.
    """
    service = SyncService()
    res = service.test_connection(ip="abc", port=8000)
    assert res["connected"] is False
    assert "invalid" in res["message"].lower()


def test_detect_server_ip_returns_failed_when_no_server_found(mocker):
    """
    [목적] DNS 및 대역 스캔까지 전부 실패하여 서버 PC를 탐색할 수 없을 때, 에러 크래시 없이 안전한 실패 규격을 반환하는지 검증.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": ""})
    mocker.patch("p1_shared.utils.env_detector.get_local_ips", return_value=["192.168.35.105"])
    
    async def mock_scan_ips_failed(*args, **kwargs):
        return None
    mocker.patch.object(service, "_async_scan_subnet", side_effect=mock_scan_ips_failed)

    res = service.detect_server_ip()
    assert res["server_ip"] is None
    assert res["method"] == "failed"


# ==========================================
# 2. REST API 엔드포인트 통합 테스트
# ==========================================

def test_api_sync_forbidden_on_server(mocker):
    """
    [목적] 서버 PC 환경에서 동기화 Push(쓰기 수신) 실행 요청 시 403 Forbidden 반환 검증.
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="server")
    response = client.post("/api/mgr/sync", json={
        "market": "kdms",
        "direction": "push",
        "confirm_text": "PUSH TO SERVER"
    })
    assert response.status_code == 403
    assert "서버 PC는 로컬 동기화 수신 쓰기 동작을 허용하지 않습니다" in response.json()["detail"]


def test_api_sync_precondition_failed_on_sudo_failure(mocker):
    """
    [목적] sudo 권한 검증 실패 시 API에서 412 Precondition Failed와 가이드를 리턴하는지 검증.
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    # sudo -n true 실패 모의
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "sudo: a password is required"

    response = client.post("/api/mgr/sync", json={
        "market": "kdms",
        "direction": "pull",
        "confirm_text": "PULL FROM SERVER"
    })
    assert response.status_code == 412
    assert "NOPASSWD" in response.json()["detail"]


def test_api_sync_invalid_confirm_text(mocker):
    """
    [목적] confirm_text 불일치 시 400 Bad Request 리턴 검증.
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    response = client.post("/api/mgr/sync", json={
        "market": "kdms",
        "direction": "pull",
        "confirm_text": "INVALID CONFIRM TEXT"
    })
    assert response.status_code == 400


def test_api_detect_server_ip_endpoint(mocker):
    """
    [목적] GET /api/mgr/network/detect-server가 탐색된 서버 IP를 정상 응답하는지 검증.
    """
    mocker.patch.object(SyncService, "detect_server_ip", return_value={"server_ip": "192.168.35.176", "method": "dns"})
    response = client.get("/api/mgr/network/detect-server")
    assert response.status_code == 200
    assert response.json()["server_ip"] == "192.168.35.176"


def test_api_sync_ip_endpoint(mocker):
    """
    [목적] POST /api/mgr/network/sync-ip가 갱신 요청을 정상 수행하는지 검증.
    """
    mocker.patch.object(SyncService, "sync_ip_in_env", return_value={"status": "success", "message": "Updated"})
    response = client.post("/api/mgr/network/sync-ip", json={
        "target": "server",
        "ip": "192.168.35.176"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_api_test_connection_endpoint(mocker):
    """
    [목적] POST /api/mgr/network/test-connection이 연결 검증 결과를 리턴하는지 검증.
    """
    mocker.patch.object(SyncService, "test_connection", return_value={"connected": True, "message": "Connection OK"})
    response = client.post("/api/mgr/network/test-connection", json={
        "ip": "192.168.35.176",
        "port": 8000
    })
    assert response.status_code == 200
    assert response.json()["connected"] is True


# ==========================================
# 3. 실제 통합 테스트 (Tier 3)
# ==========================================

@pytest.mark.integration
def test_physical_sync_preflight_check_against_real_target():
    """
    [목적] 실제 .env에 정의된 서버 및 개발 PC 설정을 가지고 PhysicalSyncManager의 preflight_check가 성공하는지 검증.
    """
    from p1_shared.ops.db_sync import PhysicalSyncManager, SyncConfig
    from p1_shared.utils.env_detector import EnvDetector
    
    detector = EnvDetector()
    profile = detector.load_env_profile()
    
    config = SyncConfig(
        db_name="kdms",
        direction="pull",
        source_ip=detector.get_peer_host(),
        target_ip="127.0.0.1",
        ssh_user=profile.get("ssh_user"),
        ssh_key_path=profile.get("ssh_key_path"),
        data_path=profile.get("data_path")
    )
    
    manager = PhysicalSyncManager(config)
    assert manager.preflight_check() is True
