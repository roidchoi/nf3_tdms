import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock
from datetime import date

# ─── 커서 Mock 헬퍼 (세션 A) ───
def make_pool_mock(size_bytes: int, latest_dt: date | None):
    """pg_database_size → size_bytes, MAX(dt) → latest_dt 순서 반환"""
    pool = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [
        (size_bytes,),
        (latest_dt,) if latest_dt else (None,),
    ]
    @contextmanager
    def fake_cursor(*a, **kw):
        yield cur
    pool.get_cursor = fake_cursor
    return pool

# ── 정상 동작 (세션 A) ──

def test_compare_returns_safe_report_when_source_is_larger(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker
    from p1_shared.db.connection import DbConnectionPool

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(10_000_000, date(2026, 4, 29)),
            make_pool_mock(100_000, date(2026, 1, 1)),
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", ["daily_ohlcv"])

    assert report.is_safe is True
    assert len(report.warnings) == 0

def test_compare_detects_target_larger_than_source(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(5_000_000, date(2026, 1, 1)),
            make_pool_mock(10_000_000, date(2026, 4, 29)),
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("크기" in w for w in report.warnings)

def test_compare_detects_target_newer_than_source(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(10_000_000, date(2026, 1, 1)),
            make_pool_mock(1_000_000, date(2026, 4, 29)),
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("최신" in w for w in report.warnings)

def test_compare_detects_source_size_zero(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(0, None),
            make_pool_mock(5_000_000, date(2026, 4, 29)),
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("크기" in w or "소스" in w for w in report.warnings)

def test_compare_source_connection_failure_marks_unsafe(mocker):
    import psycopg2
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    def raise_error(*args, **kwargs):
        raise psycopg2.OperationalError("connection refused")

    mocker.patch("p1_shared.ops.sync_manager.DbConnectionPool", side_effect=raise_error)
    checker = FullSyncSafetyChecker()
    report = checker.compare("bad_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False

# ── confirm_with_user ──

def test_confirm_with_user_returns_true_on_correct_input(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker, SyncSafetyReport

    mocker.patch("builtins.input", return_value="CONFIRM-FULL-SYNC")
    mocker.patch("p1_shared.ops.sync_manager.signal")

    checker = FullSyncSafetyChecker()
    report = SyncSafetyReport(
        source_dsn="src", target_dsn="tgt",
        warnings=["대상 DB가 소스보다 큽니다"],
    )
    result = checker.confirm_with_user(report)

    assert result is True

def test_confirm_with_user_returns_false_on_wrong_input(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker, SyncSafetyReport

    mocker.patch("builtins.input", return_value="yes")
    mocker.patch("p1_shared.ops.sync_manager.signal")

    checker = FullSyncSafetyChecker()
    report = SyncSafetyReport(source_dsn="s", target_dsn="t", warnings=["경고"])
    result = checker.confirm_with_user(report)

    assert result is False

def test_confirm_with_user_returns_false_on_timeout(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker, SyncSafetyReport
    import signal as sig

    def raise_alarm(*args, **kwargs):
        raise TimeoutError("timeout")

    mocker.patch("builtins.input", side_effect=TimeoutError("timeout"))
    mocker.patch("p1_shared.ops.sync_manager.signal")

    checker = FullSyncSafetyChecker()
    report = SyncSafetyReport(source_dsn="s", target_dsn="t", warnings=["경고"])
    result = checker.confirm_with_user(report)

    assert result is False

# ── 스키마 변경 감지 ──

def test_compare_detects_missing_column_in_target(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    source_cur = mocker.MagicMock()
    source_cur.fetchone.side_effect = [(10_000_000,), ("2026-04-29",)]
    source_cur.fetchall.return_value = [
        ("open",), ("high",), ("low",), ("close",), ("adj_factor",)
    ]

    target_cur = mocker.MagicMock()
    target_cur.fetchone.side_effect = [(1_000_000,), ("2026-01-01",)]
    target_cur.fetchall.return_value = [
        ("open",), ("high",), ("low",), ("close",)
    ]

    from contextlib import contextmanager
    def make_pool(cur):
        pool = mocker.MagicMock()
        @contextmanager
        def fake(*a, **kw):
            yield cur
        pool.get_cursor = fake
        return pool

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[make_pool(source_cur), make_pool(target_cur)],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src", "tgt", "kdms_db", ["daily_ohlcv"])

    assert report.is_safe is False
    assert any("컬럼" in w or "스키마" in w for w in report.warnings)

def test_compare_detects_missing_table_in_target(mocker):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    source_cur = mocker.MagicMock()
    source_cur.fetchone.side_effect = [(10_000_000,), ("2026-04-29",)]
    source_cur.fetchall.side_effect = [
        [("daily_ohlcv",), ("new_indicator_table",)],
        [("dt",), ("close",)],
    ]

    target_cur = mocker.MagicMock()
    target_cur.fetchone.side_effect = [(1_000_000,), ("2026-01-01",)]
    target_cur.fetchall.side_effect = [
        [("daily_ohlcv",)],
        [("dt",), ("close",)],
    ]

    from contextlib import contextmanager
    def make_pool(cur):
        pool = mocker.MagicMock()
        @contextmanager
        def fake(*a, **kw):
            yield cur
        pool.get_cursor = fake
        return pool

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[make_pool(source_cur), make_pool(target_cur)],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src", "tgt", "kdms_db", ["daily_ohlcv"])

    assert report.is_safe is False
    assert any("테이블" in w or "스키마" in w for w in report.warnings)

# ─── SyncManager 초기화 헬퍼 (세션 B) ───
def make_sync_manager(mocker, monkeypatch):
    from p1_shared.utils.env_detector import EnvDetector
    from p1_shared.ops.backup_manager import BackupManager
    from p1_shared.ops.sync_manager import SyncManager

    monkeypatch.setenv("TDMS_ENV", "dev")
    monkeypatch.setenv("DEV_IP", "192.168.35.205")
    monkeypatch.setenv("SERVER_IP", "192.168.35.97")
    monkeypatch.setenv("DEV_HOSTNAME", "EDM-LAB-ALT02")
    monkeypatch.setenv("SERVER_HOSTNAME", "EDM-LAB-MD02")

    env = EnvDetector()
    backup = mocker.MagicMock(spec=BackupManager)
    backup.backup.return_value = "/tmp/pre_sync.dump"

    return SyncManager(
        env_detector=env,
        backup_manager=backup,
        ssh_user="roid2",
        ssh_key_path="~/.ssh/tdms_sync_rsa",
    ), backup

# ── dry_run ──

def test_sync_full_dry_run_returns_result_without_subprocess(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import SyncResult

    mock_run = mocker.patch("subprocess.run")
    mgr, _ = make_sync_manager(mocker, monkeypatch)

    result = mgr.sync(
        source="dev", target="server",
        target_db="kdms", mode="full", dry_run=True,
    )

    assert isinstance(result, SyncResult)
    assert result.dry_run is True
    assert result.success is True
    mock_run.assert_not_called()

# ── full 모드 ──

def test_sync_full_mode_calls_safety_checker_first(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mock_compare = mocker.patch.object(
        FullSyncSafetyChecker, "compare",
        return_value=mocker.MagicMock(is_safe=True, warnings=[]),
    )
    mocker.patch("subprocess.run", return_value=mocker.MagicMock(returncode=0))

    mgr, backup = make_sync_manager(mocker, monkeypatch)
    mgr.sync(source="dev", target="server", target_db="kdms", mode="full")

    mock_compare.assert_called_once()

def test_sync_full_mode_calls_pre_backup_before_transfer(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch.object(
        FullSyncSafetyChecker, "compare",
        return_value=mocker.MagicMock(is_safe=True, warnings=[]),
    )
    mocker.patch("subprocess.run", return_value=mocker.MagicMock(returncode=0))

    mgr, backup = make_sync_manager(mocker, monkeypatch)
    mgr.sync(source="dev", target="server", target_db="kdms", mode="full")

    backup.backup.assert_called_once()
    call_kwargs = backup.backup.call_args
    assert "pre_sync" in str(call_kwargs)

def test_sync_full_mode_aborts_when_safety_check_fails(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch.object(
        FullSyncSafetyChecker, "compare",
        return_value=mocker.MagicMock(is_safe=False, warnings=["대상이 더 큼"]),
    )
    mocker.patch.object(FullSyncSafetyChecker, "confirm_with_user", return_value=False)
    mock_run = mocker.patch("subprocess.run")

    mgr, backup = make_sync_manager(mocker, monkeypatch)
    result = mgr.sync(source="dev", target="server", target_db="kdms", mode="full")

    assert result.success is False
    mock_run.assert_not_called()

# ── diff / table 모드 ──

def test_sync_diff_mode_skips_safety_checker(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker
    from datetime import date

    mock_compare = mocker.patch.object(FullSyncSafetyChecker, "compare")
    mocker.patch("subprocess.run", return_value=mocker.MagicMock(returncode=0))

    mgr, _ = make_sync_manager(mocker, monkeypatch)
    mgr.sync(
        source="server", target="dev",
        target_db="usdms", mode="diff",
        since=date(2026, 4, 1),
    )

    mock_compare.assert_not_called()

def test_sync_table_mode_uses_specified_tables(mocker, monkeypatch):
    mock_run = mocker.patch("subprocess.run", return_value=mocker.MagicMock(returncode=0))

    mgr, _ = make_sync_manager(mocker, monkeypatch)
    mgr.sync(
        source="server", target="dev",
        target_db="usdms", mode="table",
        tables=["us_ticker_master"],
    )

    all_args = " ".join(
        str(arg)
        for call in mock_run.call_args_list
        for arg in call[0][0]
    )
    assert "us_ticker_master" in all_args

# ── 스키마 불일치 시 diff/table 모드 중단 ──

def test_sync_diff_mode_aborts_when_schema_mismatch_detected(mocker, monkeypatch):
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker
    from datetime import date

    mocker.patch.object(
        FullSyncSafetyChecker, "compare",
        return_value=mocker.MagicMock(
            is_safe=False,
            warnings=["컬럼 불일치: adj_factor 소스에만 존재"],
        ),
    )
    mocker.patch.object(FullSyncSafetyChecker, "confirm_with_user", return_value=False)
    mock_run = mocker.patch("subprocess.run")

    mgr, _ = make_sync_manager(mocker, monkeypatch)
    result = mgr.sync(
        source="dev", target="server",
        target_db="kdms", mode="diff",
        since=date(2026, 4, 1),
    )

    assert result.success is False
    assert "스키마" in result.message or "컬럼" in result.message
    mock_run.assert_not_called()

# ── 연계 테스트 ──

def test_sync_manager_uses_env_detector_for_peer_host(mocker, monkeypatch):
    from p1_shared.utils.env_detector import EnvDetector
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    spy = mocker.spy(EnvDetector, "get_peer_host")
    mocker.patch.object(
        FullSyncSafetyChecker, "compare",
        return_value=mocker.MagicMock(is_safe=True, warnings=[]),
    )
    mocker.patch("subprocess.run", return_value=mocker.MagicMock(returncode=0))

    mgr, _ = make_sync_manager(mocker, monkeypatch)
    mgr.sync(source="dev", target="server", target_db="kdms", mode="full")

    spy.assert_called()

def test_sync_manager_uses_ops_logger(mocker, monkeypatch):
    from p1_shared.ops import logger as logger_module
    spy = mocker.spy(logger_module, "get_logger")

    make_sync_manager(mocker, monkeypatch)

    spy.assert_called()
