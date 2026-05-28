import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from repositories.base import create_kdms_pool

# 4.1 정상 동작 케이스

def test_create_kdms_pool_on_dev_env_returns_pool(mocker):
    """
    [목적] DEV 환경에서 EnvDetector가 'dev'를 감지하고
           DEV_KDMS_DB_* 변수로 DSN을 구성하여 풀을 반환하는지 검증
    """
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="dev"
    )
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.load_env_profile",
        return_value={
            "db_host": "192.168.35.205",
            "db_port": 5432,
            "db_name": "kdms_db",
            "db_user": "roid",
            "db_password": "test_pass",
        }
    )
    mock_pool = mocker.patch("repositories.base.DbConnectionPool")

    pool = create_kdms_pool()

    mock_pool.assert_called_once()
    call_dsn = mock_pool.call_args[1]["dsn"]
    assert "192.168.35.205" in call_dsn
    assert "kdms_db" in call_dsn


def test_create_kdms_pool_on_server_env_returns_pool(mocker):
    """
    [목적] SERVER 환경에서도 올바른 SERVER_KDMS_DB_* 변수로 DSN이 구성되는지 검증
    """
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="server"
    )
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.load_env_profile",
        return_value={
            "db_host": "192.168.35.97",
            "db_port": 5432,
            "db_name": "kdms_db",
            "db_user": "roid",
            "db_password": "test_pass",
        }
    )
    mock_pool = mocker.patch("repositories.base.DbConnectionPool")

    pool = create_kdms_pool()

    call_dsn = mock_pool.call_args[1]["dsn"]
    assert "192.168.35.97" in call_dsn


def test_settings_loads_layer_a_env_vars(monkeypatch):
    """
    [목적] Settings가 Layer A (EnvDetector용) 변수를 올바르게 로딩하는지 검증
    """
    # 환경변수 직접 주입 (Pydantic Settings는 환경변수를 우선함)
    monkeypatch.setenv("DEV_KDMS_DB_USER", "testuser")
    monkeypatch.setenv("DEV_KDMS_DB_PORT", "5433")
    monkeypatch.setenv("DEV_KDMS_DB_NAME", "test_kdms")
    monkeypatch.setenv("TDMS_ENV", "dev")

    from config import Settings
    # 기존 인스턴스가 아닌 새로운 인스턴스 생성하여 확인
    s = Settings()

    assert s.dev_kdms_db_user == "testuser"
    assert s.dev_kdms_db_port == 5433
    assert s.tdms_env == "dev"


def test_lifespan_startup_calls_validator_and_passes(mocker):
    """
    [목적] lifespan startup 시 StartupValidator.validate()가 호출되고
           is_healthy=True이면 서비스가 정상 기동하는지 검증
    """
    mock_pool = mocker.patch("main.create_kdms_pool")
    mock_backup = mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app) as client:
        # response = client.get("/") # 기본 route가 없을 수 있으므로 기동만 확인
        # StartupValidator.validate가 1회 호출되었음을 확인
        mock_validator.return_value.validate.assert_called_once_with(
            db_name="kdms",
            expected_tables=mocker.ANY,
            min_row_counts=mocker.ANY,
        )


# 4.2 경계값 케이스

def test_lifespan_startup_unhealthy_report_raises_runtime_error(mocker):
    """
    [목적] StartupValidator가 is_healthy=False를 반환할 때
           RuntimeError가 발생하여 서비스 기동이 차단되는지 검증
    """
    mocker.patch("main.create_kdms_pool")
    mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    unhealthy_report = MagicMock()
    unhealthy_report.is_healthy = False
    unhealthy_report.missing_tables = ["daily_ohlcv"]
    mock_validator.return_value.validate.return_value = unhealthy_report

    from main import app
    with pytest.raises(RuntimeError, match="DB 기동 검증 실패"):
        with TestClient(app):
            pass


def test_create_kdms_pool_raises_runtime_error_when_env_unknown(mocker):
    """
    [목적] EnvDetector가 'unknown'을 반환할 때 RuntimeError 발생 검증
    """
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="unknown"
    )
    with pytest.raises(RuntimeError, match="환경 감지 실패"):
        create_kdms_pool()


# 4.3 예외/오류 처리 케이스

def test_lifespan_shutdown_calls_pool_close_all(mocker):
    """
    [목적] lifespan 종료(shutdown) 시 pool.close_all()이 호출되는지 검증
    """
    mock_pool_instance = MagicMock()
    mocker.patch("main.create_kdms_pool", return_value=mock_pool_instance)
    mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app):
        pass  # 컨텍스트 종료 시 shutdown 실행

    mock_pool_instance.close_all.assert_called_once()


def test_backup_manager_called_with_correct_container_name(mocker):
    """
    [목적] BackupManager 초기화 시 container_name이 정확히
           'kdms_timescaledb'로 전달되는지 검증
    """
    mocker.patch("main.create_kdms_pool")
    mock_backup_cls = mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app):
        pass

    call_kwargs = mock_backup_cls.call_args[1]
    assert call_kwargs["container_name"] == "kdms_timescaledb"
    assert call_kwargs["volume_name"] == "kdms_pgdata"


# 4.4 통합/연계 케이스

def test_pre_migration_backup_script_creates_dump_file(mocker, tmp_path):
    """
    [목적] ops/pre_migration_backup.py 실행 시 BackupManager.backup()이
           호출되고 tag='pre_p2_migration'이 전달되는지 검증
    """
    mock_backup = mocker.patch("ops.pre_migration_backup.BackupManager")
    mock_backup.return_value.backup.return_value = tmp_path / "checkpoint.dump"

    from ops.pre_migration_backup import run_backup
    result = run_backup()

    mock_backup.return_value.backup.assert_called_once_with(tag="pre_p2_migration")
    assert result is not None
