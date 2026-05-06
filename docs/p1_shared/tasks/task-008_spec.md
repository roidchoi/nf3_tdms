# Task-008: DB 동기화 매니저 (SyncManager + FullSyncSafetyChecker)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.10 DB 동기화 매니저 (`ops/sync_manager.py`)
> **작성일**: 2026-05-06
> **의존 Task**: T-002 (EnvDetector), T-003 (DbConnectionPool), T-006 (BackupManager)

---

## § 1. 목표

개발PC ↔ 서버PC 간 양방향 DB 동기화 기능을 구현한다. full 동기화 전 방향 오류를 방지하는 `FullSyncSafetyChecker`와, full/diff/table 3가지 모드를 지원하는 `SyncManager`로 구성된다.

> **⚠️ 구현 Agent 지침**: 세션 A(`FullSyncSafetyChecker`)를 완전히 구현·테스트 통과 후 세션 B(`SyncManager`)로 진행하세요.

**구현 범위:**
- **IN**:
  - `p1_shared/ops/sync_manager.py` — `FullSyncSafetyChecker`, `SyncManager`, `SyncSafetyReport`, `SyncResult` dataclass, CLI 진입점
  - `tests/test_sync_manager.py` — 세션 A + B 단위 테스트
- **OUT**:
  - 실제 SSH/rsync 실행 (단위 테스트에서는 subprocess Mock)
  - 실제 DB 간 데이터 이동 (단위 테스트에서는 Mock)
  - T-009: 실제 환경 인계 실행

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/sync_manager.py`
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_sync_manager.py`

### 핵심 인터페이스

```python
# p1_shared/ops/sync_manager.py
from dataclasses import dataclass, field
from typing import Literal
from datetime import date
from p1_shared.utils.env_detector import EnvDetector
from p1_shared.ops.backup_manager import BackupManager

@dataclass
class SyncSafetyReport:
    source_dsn: str
    target_dsn: str
    source_size_bytes: int = 0
    target_size_bytes: int = 0
    source_latest_dt: date | None = None
    target_latest_dt: date | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return len(self.warnings) == 0


@dataclass
class SyncResult:
    mode: str
    source: str
    target: str
    db_name: str
    success: bool
    dry_run: bool = False
    message: str = ""


class FullSyncSafetyChecker:
    """Full 동기화 실행 전 소스/대상 DB 비교 안전 검증기."""

    ANOMALY_CONDITIONS = [
        "대상 DB 크기 >= 소스 × 0.8",
        "대상 최신일 > 소스 최신일",
        "소스 DB 크기 == 0 또는 접속 불가",
        "소스·대상 DB명 불일치",
        "소스에 있는 컬럼이 대상에 없음 (스키마 불일치)",  # 추가
        "소스에 있는 테이블이 대상에 없음 (테이블 불일치)",  # 추가
    ]

    def compare(
        self,
        source_dsn: str,
        target_dsn: str,
        db_name: str,
        key_tables: list[str],
    ) -> SyncSafetyReport:
        """
        소스·대상 크기/최신일 비교 후 이상 조건 감지.
        스키마 비교: information_schema.columns로 소스/대상 컬럼 목록 비교.
        → 소스에만 존재하는 컬럼/테이블 발견 시 warnings에 추가.
        """
        ...

    def confirm_with_user(self, report: SyncSafetyReport) -> bool:
        """
        이상 감지 시 경고 출력 + 'CONFIRM-FULL-SYNC' 입력 요구.
        30초 타임아웃 내 미입력 시 False 반환.
        """
        ...


class SyncManager:
    """개발PC ↔ 서버PC 양방향 DB 동기화 관리자."""

    def __init__(
        self,
        env_detector: EnvDetector,
        backup_manager: BackupManager,
        ssh_user: str,
        ssh_key_path: str,
    ) -> None: ...

    def sync(
        self,
        source: Literal["dev", "server"],
        target: Literal["dev", "server"],
        target_db: Literal["kdms", "usdms"],
        mode: Literal["full", "diff", "table"],
        tables: list[str] | None = None,
        since: date | None = None,
        dry_run: bool = False,
    ) -> SyncResult: ...
```

---

## § 4. 세션 A — FullSyncSafetyChecker 테스트

```python
# tests/test_sync_manager.py  (세션 A 부분)
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock
from datetime import date

# ─── 커서 Mock 헬퍼 ───
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


# ── 정상 동작 ──

def test_compare_returns_safe_report_when_source_is_larger(mocker):
    """
    [목적] 소스 DB가 대상보다 훨씬 크고 최신일도 소스가 더 최신일 때 is_safe=True
    [유도] 이상 조건 4종 미해당 → warnings 빈 리스트 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker
    from p1_shared.db.connection import DbConnectionPool

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(10_000_000, date(2026, 4, 29)),  # source: 10MB, 최신
            make_pool_mock(100_000, date(2026, 1, 1)),      # target:  0.1MB, 구형
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", ["daily_ohlcv"])

    assert report.is_safe is True
    assert len(report.warnings) == 0


def test_compare_detects_target_larger_than_source(mocker):
    """
    [목적] 대상 DB >= 소스 × 0.8 이면 경고가 추가됨을 검증
    [유도] 크기 비율 조건 검사 로직 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(5_000_000, date(2026, 1, 1)),   # source: 5MB
            make_pool_mock(10_000_000, date(2026, 4, 29)), # target: 10MB (더 큼)
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("크기" in w for w in report.warnings)


def test_compare_detects_target_newer_than_source(mocker):
    """
    [목적] 대상 최신일 > 소스 최신일이면 경고가 추가됨을 검증
    [유도] 날짜 비교 조건 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(10_000_000, date(2026, 1, 1)),   # source: 구형
            make_pool_mock(1_000_000, date(2026, 4, 29)),   # target: 최신
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("최신" in w for w in report.warnings)


def test_compare_detects_source_size_zero(mocker):
    """
    [목적] 소스 DB 크기가 0이면 경고가 추가됨을 검증
    [유도] 소스 유효성 검사 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    mocker.patch(
        "p1_shared.ops.sync_manager.DbConnectionPool",
        side_effect=[
            make_pool_mock(0, None),       # source: 비어있음
            make_pool_mock(5_000_000, date(2026, 4, 29)),
        ],
    )
    checker = FullSyncSafetyChecker()
    report = checker.compare("src_dsn", "tgt_dsn", "kdms_db", [])

    assert report.is_safe is False
    assert any("크기" in w or "소스" in w for w in report.warnings)


def test_compare_source_connection_failure_marks_unsafe(mocker):
    """
    [목적] 소스 DB 접속 실패 시 is_safe=False로 처리됨을 검증
    [유도] psycopg2.OperationalError catch → warnings 추가 구현 강제
    """
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
    """
    [목적] 'CONFIRM-FULL-SYNC' 입력 시 True 반환
    [유도] input() 래핑 + 문자열 일치 검사 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker, SyncSafetyReport

    mocker.patch("builtins.input", return_value="CONFIRM-FULL-SYNC")
    mocker.patch("p1_shared.ops.sync_manager.signal")  # timeout 시그널 무력화

    checker = FullSyncSafetyChecker()
    report = SyncSafetyReport(
        source_dsn="src", target_dsn="tgt",
        warnings=["대상 DB가 소스보다 큽니다"],
    )
    result = checker.confirm_with_user(report)

    assert result is True


def test_confirm_with_user_returns_false_on_wrong_input(mocker):
    """
    [목적] 잘못된 문자열 입력 시 False 반환
    [유도] 정확한 문자열 매칭 구현 강제
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker, SyncSafetyReport

    mocker.patch("builtins.input", return_value="yes")
    mocker.patch("p1_shared.ops.sync_manager.signal")

    checker = FullSyncSafetyChecker()
    report = SyncSafetyReport(source_dsn="s", target_dsn="t", warnings=["경고"])
    result = checker.confirm_with_user(report)

    assert result is False


def test_confirm_with_user_returns_false_on_timeout(mocker):
    """
    [목적] 30초 타임아웃 시 False 반환
    [유도] signal.alarm(30) + SIGALRM 핸들러 구현 강제
    """
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
    """
    [목적] 소스에 있는 컬럼이 대상 DB에 없을 때 경고가 추가됨을 검증
    [유도] information_schema.columns 쿼리 비교 로직 구현 강제
    [시나리오] 소스 daily_ohlcv에 adj_factor 컬럼 존재 / 대상에는 없음
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    # source pool: 정상 크기 + 최신일 + 컬럼 [open, high, low, close, adj_factor]
    # target pool: 정상 크기 + 구형일 + 컬럼 [open, high, low, close]  ← adj_factor 없음
    source_cur = mocker.MagicMock()
    source_cur.fetchone.side_effect = [
        (10_000_000,),        # pg_database_size
        ("2026-04-29",),     # MAX(dt)
    ]
    source_cur.fetchall.return_value = [
        ("open",), ("high",), ("low",), ("close",), ("adj_factor",)
    ]

    target_cur = mocker.MagicMock()
    target_cur.fetchone.side_effect = [
        (1_000_000,),         # pg_database_size
        ("2026-01-01",),     # MAX(dt)
    ]
    target_cur.fetchall.return_value = [
        ("open",), ("high",), ("low",), ("close",)  # adj_factor 없음
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
    """
    [목적] 소스에 있는 테이블이 대상 DB에 없을 때 경고가 추가됨을 검증
    [유도] information_schema.tables 쿼리 비교 로직 구현 강제
    [시나리오] 소스에 new_indicator_table 추가됨 / 대상에는 없음
    """
    from p1_shared.ops.sync_manager import FullSyncSafetyChecker

    source_cur = mocker.MagicMock()
    source_cur.fetchone.side_effect = [(10_000_000,), ("2026-04-29",)]
    # 소스 테이블 목록: daily_ohlcv + new_indicator_table
    source_cur.fetchall.side_effect = [
        [("daily_ohlcv",), ("new_indicator_table",)],  # tables
        [("dt",), ("close",)],                          # columns
    ]

    target_cur = mocker.MagicMock()
    target_cur.fetchone.side_effect = [(1_000_000,), ("2026-01-01",)]
    # 대상 테이블 목록: daily_ohlcv만 존재
    target_cur.fetchall.side_effect = [
        [("daily_ohlcv",)],   # tables → new_indicator_table 없음
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
```

---

## § 4. 세션 B — SyncManager 테스트

```python
# tests/test_sync_manager.py  (세션 B 부분)

# ─── SyncManager 초기화 헬퍼 ───
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
    """
    [목적] dry_run=True 시 실제 subprocess 호출 없이 SyncResult 반환
    [유도] dry_run 분기 → 계획 출력만, 실제 전송 없음 구현 강제
    """
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
    """
    [목적] full 모드 실행 시 FullSyncSafetyChecker.compare()가 먼저 호출됨을 검증
    [유도] full 모드 흐름: Safety → Backup → dump → rsync → restore 구현 강제
    """
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
    """
    [목적] full 모드에서 데이터 전송 전 대상 PC 사전 백업이 호출됨을 검증 (T-006 연계)
    [유도] BackupManager.backup(tag='pre_sync') 호출 구현 강제
    """
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
    """
    [목적] SafetyChecker가 is_safe=False + 사용자 미확인 시 SyncResult.success=False 반환
    [유도] 안전 검증 실패 시 전송 중단 구현 강제
    """
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
    """
    [목적] diff 모드는 FullSyncSafetyChecker를 호출하지 않음을 검증
    [유도] diff 모드 분기에서 SafetyChecker 미실행 구현 강제
    """
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
    """
    [목적] table 모드 시 tables 파라미터로 지정된 테이블만 dump 대상으로 지정됨을 검증
    [유도] pg_dump -t <table> 인자 구성 구현 강제
    """
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
    """
    [목적] diff 모드 실행 시 스키마 불일치가 감지되면 전송이 중단됨을 검증
    [유도] diff/table 모드에서도 compare()로 스키마 점검 후 불일치 시 중단 구현 강제
    [시나리오] 소스에 새 컬럼 추가 → compare() is_safe=False → 사용자 미확인 → 중단
    """
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
    """
    [목적] SyncManager가 EnvDetector.get_peer_host()로 상대방 IP를 결정함을 검증 (T-002 연계)
    [유도] get_peer_host() 호출 구현 강제 (하드코딩 IP 금지)
    """
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
    """
    [목적] SyncManager가 p1_shared.ops.logger.get_logger를 사용함을 검증 (T-001 연계)
    """
    from p1_shared.ops import logger as logger_module
    spy = mocker.spy(logger_module, "get_logger")

    make_sync_manager(mocker, monkeypatch)

    spy.assert_called()
```

### 테스트 케이스 요약

#### 세션 A — FullSyncSafetyChecker (`test_sync_manager.py` 전반부)

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_compare_returns_safe_report_when_source_is_larger` | 정상 | 소스 크고 최신 → is_safe=True |
| 2 | `test_compare_detects_target_larger_than_source` | 정상 | 대상 >= 소스×0.8 → 경고 추가 |
| 3 | `test_compare_detects_target_newer_than_source` | 정상 | 대상 최신일 > 소스 → 경고 추가 |
| 4 | `test_compare_detects_source_size_zero` | 경계값 | 소스 크기 0 → 경고 추가 |
| 5 | `test_compare_source_connection_failure_marks_unsafe` | 예외 | 소스 접속 실패 → is_safe=False |
| 6 | `test_confirm_with_user_returns_true_on_correct_input` | 정상 | 정확한 문자열 입력 → True |
| 7 | `test_confirm_with_user_returns_false_on_wrong_input` | 경계값 | 잘못된 입력 → False |
| 8 | `test_confirm_with_user_returns_false_on_timeout` | 예외 | 30초 타임아웃 → False |
| **9** | **`test_compare_detects_missing_column_in_target`** | **스키마** | **소스에만 있는 컬럼 감지 → 경고** |
| **10** | **`test_compare_detects_missing_table_in_target`** | **스키마** | **소스에만 있는 테이블 감지 → 경고** |

#### 세션 B — SyncManager (`test_sync_manager.py` 후반부)

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 11 | `test_sync_full_dry_run_returns_result_without_subprocess` | 정상 | dry_run=True → subprocess 미호출 |
| 12 | `test_sync_full_mode_calls_safety_checker_first` | 정상 | full 모드 → SafetyChecker 최우선 호출 |
| 13 | `test_sync_full_mode_calls_pre_backup_before_transfer` | 정상 | full 모드 → pre_sync 백업 먼저 (T-006 연계) |
| 14 | `test_sync_full_mode_aborts_when_safety_check_fails` | 예외 | 안전 검증 실패 → 전송 중단 |
| 15 | `test_sync_diff_mode_skips_safety_checker` | 정상 | diff 모드 (스키마 일치 시) → 데이터 전송 |
| 16 | `test_sync_table_mode_uses_specified_tables` | 정상 | table 모드 → 지정 테이블만 dump |
| **17** | **`test_sync_diff_mode_aborts_when_schema_mismatch_detected`** | **스키마** | **diff/table 모드 스키마 불일치 → 전송 중단** |
| 18 | `test_sync_manager_uses_env_detector_for_peer_host` | 연계 | T-002 EnvDetector.get_peer_host() 호출 |
| 19 | `test_sync_manager_uses_ops_logger` | 연계 | T-001 logger 모듈 사용 |

**세션 A 10개 + 세션 B 9개 = 총 19개 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `subprocess` (내장), `signal` (내장, 타임아웃용), `p1_shared.utils.env_detector`, `p1_shared.ops.backup_manager`
- **기존 모듈 연계**:
  - `EnvDetector.get_peer_host()` — 상대방 PC IP 결정 (T-002)
  - `BackupManager.backup(tag="pre_sync")` — 전송 전 안전 백업 (T-006)
  - `from p1_shared.ops.logger import get_logger` — 로깅 (T-001)
  - `DbConnectionPool` — compare() 내부에서 크기/최신일/스키마 쿼리용 (T-003)
- **rsync 전송 패턴**:
  ```bash
  rsync -avz -e "ssh -i {ssh_key_path}" \
    {dump_path} {ssh_user}@{peer_ip}:{remote_dump_path}
  ```
- **DB 크기 조회**: `SELECT pg_database_size('{db_name}')`
- **최신일 조회**: `SELECT MAX(dt) FROM {table}` (key_tables 각각)
- **스키마 비교 쿼리**:
  ```sql
  -- 컬럼 목록 조회 (테이블별)
  SELECT column_name FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = %s
  ORDER BY ordinal_position

  -- 테이블 목록 조회
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public'
  ```
- **스키마 불일치 대응 전략**:
  - **full 모드**: `pg_dump -Fc`가 스키마+데이터 통합 덤프 → 소스 스키마가 대상을 자동 교체. **스키마 불일치는 full 모드로 자동 해결됨.**
  - **diff/table 모드**: 데이터만 이동 → 스키마 불일치 시 INSERT 오류 발생 위험. compare()에서 불일치 감지 시 `warnings`에 추가하고 `confirm_with_user()`로 재확인 요구. 사용자 미확인 시 중단 + "full 모드 실행 권장" 안내 출력.
- **signal 타임아웃 패턴**:
  ```python
  import signal
  def _timeout_handler(signum, frame):
      raise TimeoutError()
  signal.signal(signal.SIGALRM, _timeout_handler)
  signal.alarm(30)
  try:
      user_input = input("...")
  except TimeoutError:
      return False
  finally:
      signal.alarm(0)
  ```
- **환경변수**: `SSH_USER`, `SSH_KEY_PATH` (.env에서 로드)

---

## § 6. 완료 기준

- [ ] 세션 A 테스트 10개 전체 통과 (`FullSyncSafetyChecker` + 스키마 감지)
- [ ] 세션 B 테스트 9개 전체 통과 (`SyncManager` + diff 스키마 불일치 중단)
- [ ] T-001~T-007 기존 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-008 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-008_walkthrough.md` 작성
