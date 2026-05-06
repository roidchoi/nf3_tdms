import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

# ─── 커서 Mock 헬퍼 ───
def make_cursor_mock(fetchone_result=None, fetchall_result=None):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_result
    cur.fetchall.return_value = fetchall_result or []
    return cur

def make_pool_mock(cursor_mock):
    pool = MagicMock()
    @contextmanager
    def fake_get_cursor(*args, **kwargs):
        yield cursor_mock
    pool.get_cursor = fake_get_cursor
    return pool


def test_validate_returns_healthy_report_when_all_checks_pass(mocker):
    """
    [목적] 모든 검증 조건이 정상일 때 is_healthy=True인 ValidationReport 반환
    [유도] 5가지 검증 항목 모두 통과 시 is_healthy=True로 설정하는 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator, ValidationReport

    cursor = MagicMock()
    # SELECT 1: 접속 확인
    # information_schema 테이블 존재 확인
    # COUNT(*) 행 수 확인
    cursor.fetchone.side_effect = [(1,), (100,), (500,)]
    cursor.fetchall.return_value = [("daily_ohlcv",), ("stock_info",)]

    pool = make_pool_mock(cursor)

    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {
        "exists": True, "volume_path": "/var/lib/docker/volumes/kdms_pgdata/_data",
        "pg_version": "16", "size_bytes": 1024
    }

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv", "stock_info"],
        min_row_counts={"daily_ohlcv": 10, "stock_info": 10},
    )

    assert isinstance(report, ValidationReport)
    assert report.is_connected is True
    assert report.is_healthy is True


def test_validate_detects_missing_tables(mocker):
    """
    [목적] DB에 존재하지 않는 테이블이 있을 때 missing_tables에 포함됨을 검증
    [유도] information_schema 쿼리 결과와 expected_tables 비교 로직 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.side_effect = [(1,)]
    # 실제 테이블은 daily_ohlcv만 존재, stock_info는 없음
    cursor.fetchall.return_value = [("daily_ohlcv",)]

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {"exists": True, "pg_version": "16", "size_bytes": 1}

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv", "stock_info"],
        min_row_counts={},
    )

    assert "stock_info" in report.missing_tables
    assert report.is_healthy is False


def test_validate_detects_low_row_count_tables(mocker):
    """
    [목적] 행 수가 최소 예상치 미만인 테이블이 low_row_tables에 포함됨을 검증
    [유도] COUNT(*) 결과와 min_row_counts 비교 로직 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        (1,),     # SELECT 1 (접속 확인)
        (5,),     # daily_ohlcv COUNT(*) → 5행 (예상: 1000행)
    ]
    cursor.fetchall.return_value = [("daily_ohlcv",)]

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {"exists": True, "pg_version": "16", "size_bytes": 1}

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv"],
        min_row_counts={"daily_ohlcv": 1000},
    )

    assert "daily_ohlcv" in report.low_row_tables
    actual, expected_min = report.low_row_tables["daily_ohlcv"]
    assert actual == 5
    assert expected_min == 1000
    assert report.is_healthy is False


def test_validate_volume_info_from_backup_manager(mocker):
    """
    [목적] validate()가 BackupManager.check_volume_exists() 결과를 report.volume_info에 포함함을 검증
    [유도] BackupManager 연동 로직 구현 강제 (T-006 연계)
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = [("daily_ohlcv",)]

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    expected_vol = {
        "volume_path": "/var/lib/docker/volumes/kdms_pgdata/_data",
        "exists": True,
        "pg_version": "16",
        "size_bytes": 2048000,
    }
    backup_mgr.check_volume_exists.return_value = expected_vol

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv"],
        min_row_counts={"daily_ohlcv": 1},
    )

    assert report.volume_info == expected_vol
    backup_mgr.check_volume_exists.assert_called_once()


def test_print_report_outputs_success_markers_for_healthy_report(capsys):
    """
    [목적] is_healthy=True인 report의 print_report() 출력에 '✅'가 포함됨을 검증
    [유도] 성공 항목에 ✅ 마커를 출력하는 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator, ValidationReport

    cursor = MagicMock()
    pool = make_pool_mock(cursor)
    validator = StartupValidator(pool=pool)

    report = ValidationReport(
        db_name="kdms",
        is_connected=True,
        missing_tables=[],
        low_row_tables={},
        volume_info={"exists": True},
        hypertable_ok=True,
    )
    validator.print_report(report)

    captured = capsys.readouterr()
    assert "✅" in captured.out


def test_print_report_outputs_failure_markers_and_action_guide(capsys):
    """
    [목적] 실패 항목에 '❌'와 조치 안내(→)가 출력됨을 검증
    [유도] 실패 항목별 조치 메시지 출력 로직 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator, ValidationReport

    cursor = MagicMock()
    pool = make_pool_mock(cursor)
    validator = StartupValidator(pool=pool)

    report = ValidationReport(
        db_name="kdms",
        is_connected=True,
        missing_tables=["stock_info"],
        low_row_tables={"daily_ohlcv": (0, 1_000_000)},
        volume_info={"exists": False},
        hypertable_ok=True,
    )
    validator.print_report(report)

    captured = capsys.readouterr()
    assert "❌" in captured.out
    assert "→" in captured.out


def test_validate_without_backup_manager_skips_volume_check():
    """
    [목적] backup_manager=None 시 볼륨 검증을 건너뛰고 volume_info가 빈 dict임을 검증
    [유도] backup_manager가 None일 때 check_volume_exists() 미호출 분기 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = []

    pool = make_pool_mock(cursor)
    validator = StartupValidator(pool=pool, backup_manager=None)
    report = validator.validate(
        db_name="kdms",
        expected_tables=[],
        min_row_counts={},
    )

    assert report.volume_info == {}


def test_validate_with_empty_expected_tables_passes_table_check():
    """
    [목적] expected_tables=[]일 때 테이블 검증 항목이 통과됨을 검증
    [유도] 빈 리스트 입력 시 missing_tables=[] 처리 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = []

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {"exists": True}

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="usdms",
        expected_tables=[],
        min_row_counts={},
    )

    assert report.missing_tables == []


def test_validate_report_is_unhealthy_when_volume_not_found():
    """
    [목적] Docker 볼륨이 존재하지 않으면 is_healthy=False임을 검증
    [유도] volume_info["exists"]=False 시 is_healthy 계산에 반영하는 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = [("daily_ohlcv",)]

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {
        "exists": False, "volume_path": "/var/lib/docker/volumes/kdms_pgdata/_data",
        "pg_version": None, "size_bytes": 0,
    }

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv"],
        min_row_counts={"daily_ohlcv": 1},
    )

    assert report.is_healthy is False


def test_validate_sets_is_connected_false_when_db_connection_fails():
    """
    [목적] DB 접속 실패 시 is_connected=False이고 이후 검증 항목이 건너뜀을 검증
    [유도] SELECT 1 실패 → is_connected=False, 나머지 검증 스킵 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator
    import psycopg2

    pool = MagicMock()
    @contextmanager
    def failing_get_cursor(*args, **kwargs):
        raise psycopg2.OperationalError("connection refused")
        yield  # unreachable
    pool.get_cursor = failing_get_cursor

    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {"exists": True}

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv"],
        min_row_counts={"daily_ohlcv": 1000},
    )

    assert report.is_connected is False
    assert report.is_healthy is False


def test_startup_validator_accepts_real_db_connection_pool_interface(mocker):
    """
    [목적] StartupValidator가 실제 DbConnectionPool 인터페이스(get_cursor)와 호환됨을 검증 (T-003 연계)
    [유도] pool.get_cursor()를 context manager로 사용하는 구현 강제
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    mock_pool_cls = mocker.patch("psycopg2.pool.ThreadedConnectionPool")
    mock_pool_instance = MagicMock()
    mock_pool_cls.return_value = mock_pool_instance

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_pool_instance.getconn.return_value = mock_conn

    pool = DbConnectionPool(dsn="postgresql://dummy")
    validator = StartupValidator(pool=pool)

    # get_cursor() context manager 프로토콜이 호환되는지 확인
    assert hasattr(pool, "get_cursor")
    assert validator is not None


def test_startup_validator_accepts_real_backup_manager_interface(tmp_path):
    """
    [목적] StartupValidator가 실제 BackupManager.check_volume_exists() 인터페이스와 호환됨을 검증 (T-006 연계)
    [유도] BackupManager 인스턴스를 그대로 주입 가능한 구현 강제
    """
    from p1_shared.ops.backup_manager import BackupManager
    from p1_shared.ops.startup_validator import StartupValidator

    backup_mgr = BackupManager(
        container_name="p2_kdms_db",
        db_name="kdms_db",
        db_user="roid",
        backup_dir=str(tmp_path / "backups"),
        volume_name="kdms_pgdata",
    )

    pool = MagicMock()
    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)

    # check_volume_exists()가 dict를 반환하는지 확인 (실제 파일 없이)
    vol_info = backup_mgr.check_volume_exists()
    assert isinstance(vol_info, dict)
    assert "exists" in vol_info
    assert "volume_path" in vol_info


def test_startup_validator_uses_ops_logger(mocker, tmp_path):
    """
    [목적] StartupValidator가 p1_shared.ops.logger.get_logger를 사용함을 검증 (T-001 연계)
    [유도] 클래스 내부에서 get_logger(__name__) 호출 구현 강제
    """
    from p1_shared.ops import logger as logger_module
    spy = mocker.spy(logger_module, "get_logger")

    from p1_shared.ops.startup_validator import StartupValidator
    pool = MagicMock()
    StartupValidator(pool=pool)

    spy.assert_called()


def test_validate_fastapi_lifespan_pattern(mocker):
    """
    [목적] FastAPI lifespan 패턴에서 StartupValidator 사용이 가능함을 검증
           (PRD §3.11 연동 패턴의 핵심 시나리오)
    [유도] validate() → print_report() → report.is_healthy 체크 흐름 구현 강제
    """
    from p1_shared.ops.startup_validator import StartupValidator, ValidationReport

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.fetchall.return_value = [("daily_ohlcv",), ("stock_info",)]

    pool = make_pool_mock(cursor)
    backup_mgr = MagicMock()
    backup_mgr.check_volume_exists.return_value = {"exists": True, "pg_version": "16", "size_bytes": 1}

    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)

    # FastAPI lifespan 패턴 시뮬레이션
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv", "stock_info"],
        min_row_counts={"daily_ohlcv": 1, "stock_info": 1},
    )
    validator.print_report(report)

    assert isinstance(report.is_healthy, bool)  # bool 값이어야 함 (truthy 아닌 명시적 bool)
