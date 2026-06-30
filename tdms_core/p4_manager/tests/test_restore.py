# tdms_core/p4_manager/tests/test_restore.py
import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, call
from fastapi.testclient import TestClient

from tdms_core.p4_manager.main import app
from tdms_core.p4_manager.services.backup_service import BackupService
from tdms_core.p4_manager.config import settings

client = TestClient(app)

# --- Tier 1 & 2 Tests ---

def test_restore_backup_with_empty_confirm_text_raises_value_error():
    """
    [Tier 1 — 단위]
    [목적] confirm_text가 빈 값일 때 즉각 ValueError를 던지는지 검증.
    """
    service = BackupService()
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.restore_backup("kdms", "manual", "physical_checkpoint_kdms_20260610_120000.tar.gz", "")


def test_restore_backup_on_server_env_raises_permission_error(mocker):
    """
    [Tier 1 — 단위]
    [목적] 운영 서버PC 환경인 경우 복구를 시도하면 PermissionError를 발생시켜 원천 차단하는지 검증.
    """
    mocker.patch.object(BackupService, "get_env", return_value="server")
    
    service = BackupService()
    with pytest.raises(PermissionError, match="서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다"):
        service.restore_backup("kdms", "manual", "physical_checkpoint_kdms_20260610_120000.tar.gz", "RESTORE LOCAL DB")


def test_restore_backup_with_invalid_confirm_text_raises_value_error():
    """
    [Tier 1 — 단위]
    [목적] confirm_text가 'RESTORE LOCAL DB'와 다르면 ValueError를 던지는지 검증.
    """
    service = BackupService()
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.restore_backup("kdms", "manual", "physical_checkpoint_kdms_20260610_120000.tar.gz", "RESTORE DB")


def test_restore_backup_with_non_existent_file_raises_file_not_found_error(mocker):
    """
    [Tier 1 — 단위]
    [목적] 지정한 백업 아카이브 파일이 존재하지 않는 경우 FileNotFoundError를 던지는지 검증.
    """
    mocker.patch.object(BackupService, "get_env", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=False)
    
    service = BackupService()
    with pytest.raises(FileNotFoundError, match="백업 아카이브 파일을 찾을 수 없습니다"):
        service.restore_backup("kdms", "manual", "non_existent.tar.gz", "RESTORE LOCAL DB")


def test_restore_backup_with_valid_parameters_executes_successfully(mocker):
    """
    [Tier 2 — 격리 통합]
    [목적] 유효한 파일명, 경로, 이중 컨펌 텍스트가 제공되었을 때 정상적으로 
           컨테이너 중지 -> 압축 해제 -> 권한 교정 -> 컨테이너 기동 -> 검증 연동 흐름이 수행되는지 검증.
    """
    # 1. 환경 및 파일 존재 여부 모킹
    mocker.patch.object(BackupService, "get_env", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.mkdir")
    
    # 2. subprocess 호출 모킹
    mock_run = mocker.patch("subprocess.run")
    
    # 3. 시간 지연 및 DB 커넥션 대기 스킵
    mocker.patch("time.sleep")
    
    # 4. DbConnectionPool 모킹
    mock_pool = mocker.MagicMock()
    mocker.patch("tdms_core.p4_manager.services.backup_service.DbConnectionPool", return_value=mock_pool)
    
    # 5. StartupValidator 및 ValidationReport 모킹
    mock_report = mocker.MagicMock()
    mock_report.is_healthy = True
    mock_report.is_connected = True
    mock_report.missing_tables = []
    mock_report.low_row_tables = {}
    mock_report.volume_info = {"exists": True}
    mock_report.hypertable_ok = True
    
    mock_validator = mocker.MagicMock()
    mock_validator.validate.return_value = mock_report
    mocker.patch("tdms_core.p4_manager.services.backup_service.StartupValidator", return_value=mock_validator)
    
    service = BackupService()
    result = service.restore_backup(
        market="kdms",
        tag="manual",
        filename="physical_checkpoint_kdms_20260610_120000.tar.gz",
        confirm_text="RESTORE LOCAL DB"
    )
    
    assert result["status"] == "success"
    assert "validation_results" in result
    assert result["validation_results"]["kdms"]["is_healthy"] is True
    
    # subprocess 호출 내역 검증 (stop -> tar -> chown -> start 순)
    calls = [call[0][0] for call in mock_run.call_args_list]
    assert any("stop" in str(cmd) for cmd in calls)
    assert any("tar" in str(cmd) and "-xz" in str(cmd) for cmd in calls)
    assert any("chown" in str(cmd) for cmd in calls)
    assert any("start" in str(cmd) for cmd in calls)


def test_create_backup_on_server_env_raises_permission_error_remains_unchanged(mocker):
    """
    [Tier 1 — 단위]
    [목적] T-008 기존 물리 백업 서버 환경 차단 로직 회귀 방지 검증.
    """
    mocker.patch.object(BackupService, "get_env", return_value="server")
    
    service = BackupService()
    with pytest.raises(PermissionError):
        service.create_backup("kdms")


# --- API Endpoint Tests ---

def test_api_restore_on_server_raises_403(mocker):
    """
    [목적] 서버 환경에서 restore API 호출 시 403 Forbidden 리턴 검증
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="server")
    payload = {
        "market": "kdms",
        "tag": "manual",
        "filename": "physical_checkpoint_kdms_20260610_120000.tar.gz",
        "confirm_text": "RESTORE LOCAL DB"
    }
    response = client.post("/api/mgr/restore", json=payload)
    assert response.status_code == 403
    assert "서버 PC는 로컬 스냅샷 백업" in response.json()["detail"]


def test_api_restore_with_invalid_confirm_text_raises_400(mocker):
    """
    [목적] 잘못된 confirm_text를 페이로드로 전송할 경우 400 Bad Request 리턴 검증
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    payload = {
        "market": "kdms",
        "tag": "manual",
        "filename": "physical_checkpoint_kdms_20260610_120000.tar.gz",
        "confirm_text": "RESTORE DB"
    }
    response = client.post("/api/mgr/restore", json=payload)
    assert response.status_code == 400
    assert "이중 확인 텍스트가 일치하지 않습니다" in response.json()["detail"]


def test_api_restore_with_non_existent_file_raises_404(mocker):
    """
    [목적] 존재하지 않는 백업 파일 지정 시 404 Not Found 리턴 검증
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=False)
    payload = {
        "market": "kdms",
        "tag": "manual",
        "filename": "non_existent.tar.gz",
        "confirm_text": "RESTORE LOCAL DB"
    }
    response = client.post("/api/mgr/restore", json=payload)
    assert response.status_code == 404
    assert "백업 아카이브 파일을 찾을 수 없습니다" in response.json()["detail"]


def test_api_restore_success_on_dev(mocker):
    """
    [목적] 개발 환경에서 올바른 페이로드 제공 시 성공적으로 복구를 수행하고 200 리포트 반환 검증
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.mkdir")
    mocker.patch("subprocess.run")
    mocker.patch("time.sleep")
    mocker.patch("tdms_core.p4_manager.services.backup_service.DbConnectionPool")
    
    # StartupValidator 모킹
    mock_report = MagicMock()
    mock_report.is_healthy = True
    mock_report.is_connected = True
    mock_report.missing_tables = []
    mock_report.low_row_tables = {}
    mock_report.volume_info = {"exists": True}
    mock_report.hypertable_ok = True
    
    mock_validator = MagicMock()
    mock_validator.validate.return_value = mock_report
    mocker.patch("tdms_core.p4_manager.services.backup_service.StartupValidator", return_value=mock_validator)

    payload = {
        "market": "kdms",
        "tag": "manual",
        "filename": "physical_checkpoint_kdms_20260610_120000.tar.gz",
        "confirm_text": "RESTORE LOCAL DB"
    }
    response = client.post("/api/mgr/restore", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert "validation_results" in res_data
    assert res_data["validation_results"]["kdms"]["is_healthy"] is True


# --- Tier 3 Integration Test ---

@pytest.mark.integration
def test_restore_backup_with_real_db_and_validation(mocker):
    """
    [Tier 3 — 실제 통합]
    [목적] 실제 로컬 Docker DB 컨테이너들이 가동 중인 환경에서 임시 백업을 작성하고,
           이를 직접 restore_backup으로 복구한 뒤, StartupValidator 정합성 검증이 
           성공(is_healthy=True)을 보고하는지 실제 End-to-End 검증.
    """
    service = BackupService()
    assert service.get_env() == "dev", "통합 테스트는 개발 PC(dev) 환경에서만 실행할 수 있습니다."

    # 1. 통합 테스트용 임시 백업 생성
    backup_result = service.create_backup(market="kdms", tag="integration_test")
    filename = backup_result["filename"]
    
    try:
        # 2. 실제 복구 수행
        restore_result = service.restore_backup(
            market="kdms",
            tag="integration_test",
            filename=filename,
            confirm_text="RESTORE LOCAL DB"
        )
        
        # 3. 결과 검증
        assert restore_result["status"] == "success"
        assert "validation_results" in restore_result
        
        kdms_report = restore_result["validation_results"]["kdms"]
        usdms_report = restore_result["validation_results"]["usdms"]
        
        assert kdms_report["is_connected"] is True
        assert usdms_report["is_connected"] is True
        assert kdms_report["is_healthy"] is True
        assert usdms_report["is_healthy"] is True
        
    finally:
        # 백업 파일 및 디렉토리 정리
        backup_file = Path(settings.BACKUP_BASE_DIR) / "integration_test" / filename
        if backup_file.exists():
            backup_file.unlink()
        backup_dir = backup_file.parent
        if backup_dir.exists() and not any(backup_dir.iterdir()):
            backup_dir.rmdir()
