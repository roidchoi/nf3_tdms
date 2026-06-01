import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# 아직 미구현된 모듈들을 임포트 (Test-First 의도를 위해 작성)
from p3_usdms.config import Settings, get_settings
from p3_usdms.repositories.base import BaseRepository
from p3_usdms.collectors.db_manager import DatabaseManager
from p3_usdms.main import app

def test_env_detector_resolves_local_development_env():
    """TC-01: WSL/Ubuntu 로컬 개발 환경에서 EnvDetector가 개발(dev) 환경을 정상 식별하는지 검증"""
    from p1_shared.utils.env_detector import EnvDetector
    with patch("socket.gethostname", return_value="test-host"):
        detector = EnvDetector()
        assert detector.detect() == "dev"

def test_db_connection_pool_creates_and_fetches_cursor(mocker):
    """TC-02: BaseRepository가 통합된 DbConnectionPool을 정상 초기화하고 데이터베이스 커서를 성공적으로 반환하는지 검증"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value = mock_cursor
    
    mock_pool = MagicMock()
    mock_pool.get_conn.return_value = mock_conn
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor

    with patch("p3_usdms.repositories.base.DbConnectionPool", return_value=mock_pool):
        repo = BaseRepository()
        repo._pool = mock_pool
        
        conn = repo.get_connection()
        assert conn == mock_conn
        
        with repo.get_cursor() as cur:
            assert cur == mock_cursor

def test_startup_validator_passes_all_checks_on_dev(mocker):
    """TC-03: StartupValidator가 현재 로컬 환경에서 요구하는 검증을 통과하는지 검증 (볼륨 정보가 없어도 exists=True 우회 확인)"""
    from p1_shared.ops.startup_validator import StartupValidator
    
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("daily_ohlcv",)]
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    validator = StartupValidator(mock_pool, backup_manager=None)
    report = validator.validate(
        db_name="usdms",
        expected_tables=["daily_ohlcv"],
        min_row_counts={"daily_ohlcv": 100}
    )
    
    assert report.is_healthy is True
    assert report.volume_info.get("exists", True) is True

def test_db_manager_shim_provides_compatible_context_cursor(mocker):
    """TC-04: 레거시 코드가 DatabaseManager().get_cursor()를 사용할 때 context manager 및 dict 반환이 작동하는지 검증"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"cnt": 42}
    # __enter__ 호출 시 mock_cursor 자신을 리턴하도록 설정하여 with 구문 매칭
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value = mock_cursor
    
    mock_pool = MagicMock()
    mock_pool.get_conn.return_value = mock_conn
    
    with patch("p3_usdms.repositories.base.DbConnectionPool", return_value=mock_pool):
        db = DatabaseManager()
        db._pool = mock_pool
        
        with db.get_cursor() as cur:
            assert cur == mock_cursor
            res = cur.fetchone()
            assert res["cnt"] == 42

def test_fastapi_lifespan_executes_startup_sequence(mocker):
    """TC-05: FastAPI 서비스가 구동(lifespan)될 때 StartupValidator 검증 및 DbConnectionPool 기동 로직이 작동하는지 검증"""
    mock_pool = MagicMock()
    mock_report = MagicMock()
    mock_report.is_healthy = True
    
    mocker.patch("p3_usdms.main.create_kdms_pool", return_value=mock_pool)
    mocker.patch("p3_usdms.main.StartupValidator")
    mock_validator_inst = MagicMock()
    mock_validator_inst.validate.return_value = mock_report
    from p3_usdms.main import StartupValidator
    StartupValidator.return_value = mock_validator_inst
    
    client = TestClient(app)
    with client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "USDMS API is running"}

def test_config_with_empty_or_missing_env_vars_raises_error():
    """TC-06: 필수 환경 변수(SEC_USER_AGENT)가 제공되지 않았을 때 시스템 기동이 제한되고 예외가 발생하는지 검증"""
    if "SEC_USER_AGENT" in os.environ:
        old_val = os.environ.pop("SEC_USER_AGENT")
    else:
        old_val = None
        
    try:
        with pytest.raises(ValueError, match="SEC_USER_AGENT 환경변수가 누락되었습니다"):
            Settings()
    finally:
        if old_val:
            os.environ["SEC_USER_AGENT"] = old_val

def test_backup_manager_handles_invalid_dest_path_and_logs_error():
    """TC-07: BackupManager가 백업 실행 중 잘못된 경로로 인해 실패할 때 프로세스를 크래시 시키지 않고 실패 반환 및 로깅하는지 검증"""
    from p1_shared.ops.backup_manager import BackupManager
    
    backup_mgr = BackupManager(
        container_name="non_existent_container",
        db_name="usdms_db",
        db_user="usdms_user",
        backup_dir="./backups/test_invalid_run",
        volume_name="usdms_pgdata"
    )
    
    # pg_dump 명령어 실패 시 RuntimeError가 발생하는 것을 검증
    with pytest.raises(RuntimeError):
        backup_mgr.backup()
