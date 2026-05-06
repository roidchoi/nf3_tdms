# Task-007: DB 기동 검증기 (StartupValidator)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.11 DB 기동 검증기 (`ops/startup_validator.py`)
> **작성일**: 2026-05-06
> **의존 Task**: T-003 (DbConnectionPool), T-006 (BackupManager)

---

## § 1. 목표

Docker 재기동 또는 이미지 업데이트 후 DB 볼륨이 정상 연결되었는지·기존 데이터가 정상 로드되었는지를 자동으로 검증하고, 문제 발생 시 구체적인 조치 방법을 출력하는 `StartupValidator`를 구현한다. FastAPI `lifespan`에 연동 가능한 패턴으로 설계한다.

**구현 범위:**
- **IN**:
  - `p1_shared/ops/startup_validator.py` — `StartupValidator` 클래스 + `ValidationReport` dataclass
  - `validate()` — DB 접속·테이블 존재·행 수·볼륨 파일·Hypertable 청크 5가지 검증
  - `print_report()` — 실패 항목별 구체적 조치 안내 출력
  - `tests/test_startup_validator.py` — 단위 테스트 (DB는 Mock, BackupManager 연계 포함)
  - `tests/test_startup_validator_integration.py` — 통합 테스트 (실 DB 접속 검증, `pytest -m integration`)
- **OUT**:
  - 실제 PostgreSQL DB 접속 (단위 테스트에서는 Mock)
  - FastAPI 앱 구성 코드 — p2_kdms, p3_usdms 각 Task
  - DB 복구 실행 — T-006 BackupManager가 담당

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/startup_validator.py`
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_startup_validator.py`

### 핵심 인터페이스

```python
# p1_shared/ops/startup_validator.py
from dataclasses import dataclass, field
from typing import Literal
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops.backup_manager import BackupManager

@dataclass
class ValidationReport:
    db_name: str
    is_connected: bool = False
    missing_tables: list[str] = field(default_factory=list)
    low_row_tables: dict[str, tuple[int, int]] = field(default_factory=dict)
    # {table: (actual_rows, expected_min)}
    volume_info: dict = field(default_factory=dict)
    # BackupManager.check_volume_exists() 결과
    hypertable_ok: bool = True

    @property
    def is_healthy(self) -> bool:
        """모든 검증 항목 통과 시 True."""
        return (
            self.is_connected
            and not self.missing_tables
            and not self.low_row_tables
            and self.volume_info.get("exists", False)
        )


class StartupValidator:
    """Docker 재기동 시 DB 연결·데이터 정합성 자가 검증기."""

    def __init__(
        self,
        pool: DbConnectionPool,
        backup_manager: BackupManager | None = None,
    ) -> None:
        """
        Args:
            pool: 검증 대상 DB 커넥션 풀 (T-003)
            backup_manager: 볼륨 확인에 사용할 BackupManager (T-006, None이면 볼륨 검증 건너뜀)
        """
        ...

    def validate(
        self,
        db_name: Literal["kdms", "usdms"],
        expected_tables: list[str],
        min_row_counts: dict[str, int],
    ) -> ValidationReport:
        """
        5가지 항목 순차 검증 후 ValidationReport 반환.
          1. DB 접속 가능 여부 (SELECT 1)
          2. 핵심 테이블 존재 여부
          3. 각 테이블 행 수 >= 최소 예상치
          4. Docker 볼륨 실물 파일 존재 (backup_manager.check_volume_exists())
          5. Hypertable 청크 상태 (timescaledb_information.chunks)

        Returns:
            ValidationReport: 각 항목 검증 결과 집합
        """
        ...

    def print_report(self, report: ValidationReport) -> None:
        """
        검증 결과를 콘솔에 출력.
        실패 항목에 구체적 조치 방법 안내 포함.

        출력 예시:
          ✅ DB 접속: 정상
          ❌ 행 수 부족: daily_ohlcv 현재 0행 (예상: 1,000,000행 이상)
             → 조치: python -m p1_shared.ops.backup_manager restore --target kdms
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트를 먼저 작성한 뒤 통과하도록 구현하세요.
> DB 관련 호출은 `mocker.patch.object(pool, "get_cursor")`로 격리하세요.
> `BackupManager.check_volume_exists()`는 `mocker.patch.object`로 Mock 처리하세요.

### 4.1 정상 동작 케이스

```python
# tests/test_startup_validator.py
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
```

### 4.2 경계값 케이스

```python
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
```

### 4.3 예외/오류 처리 케이스

```python
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
```

### 4.4 연계 케이스 — 기존 구현 모듈 호환성

```python
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
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_validate_returns_healthy_report_when_all_checks_pass` | 정상 | 전 항목 통과 시 is_healthy=True |
| 2 | `test_validate_detects_missing_tables` | 정상 | 누락 테이블 → missing_tables 포함 |
| 3 | `test_validate_detects_low_row_count_tables` | 정상 | 행 수 부족 → low_row_tables 포함 |
| 4 | `test_validate_volume_info_from_backup_manager` | 정상 | BackupManager 결과 → volume_info 포함 |
| 5 | `test_print_report_outputs_success_markers_for_healthy_report` | 정상 | 성공 항목에 ✅ 출력 |
| 6 | `test_print_report_outputs_failure_markers_and_action_guide` | 정상 | 실패 항목에 ❌ + → 조치 안내 출력 |
| 7 | `test_validate_without_backup_manager_skips_volume_check` | 경계값 | backup_manager=None → 볼륨 검증 건너뜀 |
| 8 | `test_validate_with_empty_expected_tables_passes_table_check` | 경계값 | expected_tables=[] → missing_tables=[] |
| 9 | `test_validate_report_is_unhealthy_when_volume_not_found` | 경계값 | 볼륨 없음 → is_healthy=False |
| 10 | `test_validate_sets_is_connected_false_when_db_connection_fails` | 예외 | DB 접속 실패 → is_connected=False |
| 11 | `test_startup_validator_accepts_real_db_connection_pool_interface` | 연계 | T-003 DbConnectionPool 인터페이스 호환 |
| 12 | `test_startup_validator_accepts_real_backup_manager_interface` | 연계 | T-006 BackupManager 인터페이스 호환 |
| 13 | `test_startup_validator_uses_ops_logger` | 연계 | T-001 logger 모듈 사용 확인 |
| 14 | `test_validate_fastapi_lifespan_pattern` | 연계 | PRD FastAPI lifespan 패턴 시뮬레이션 |

**단위 테스트 14개 — 통합 테스트는 별도 파일 확인**

### 4.5 통합 테스트 케이스 (실 DB 접속)

> **실행 조건**: 실제 DB가 가동 중인 환경에서만 실행합니다.
> `pytest -m integration` 으로 단위 테스트와 분리 실행하세요.
>
> **개발PC 사전 준비**: `kdms_timescaledb` 및 `usdms_db` Docker 컨테이너 가동 확인 (`docker ps`)
>
> **서버PC DB**: 내부망(192.168.35.0/24)에서 서버PC가 켜져 있으면 접속 가능

```python
# tests/test_startup_validator_integration.py
import pytest
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

DEV_IP = os.getenv("DEV_IP", "192.168.35.205")
SERVER_IP = os.getenv("SERVER_IP", "192.168.35.97")

DEV_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{DEV_IP}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
DEV_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{DEV_IP}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)
SERVER_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{SERVER_IP}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
SERVER_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{SERVER_IP}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)


@pytest.mark.integration
def test_validator_is_connected_with_dev_kdms_real_db():
    """
    [목적] 개발PC KDMS 실 DB에 StartupValidator가 정상 접속하고 is_connected=True를 반환함을 검증
    [유도] DbConnectionPool + StartupValidator 연동이 실 DB에서 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_dev_usdms_real_db():
    """
    [목적] 개발PC USDMS 실 DB에 StartupValidator가 정상 접속하고 is_connected=True를 반환함을 검증
    [유도] 포트가 다른 DB(5435)에도 동일한 패턴이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_USDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="usdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_server_kdms_real_db():
    """
    [목적] 서버PC KDMS 실 DB에 내부망으로 접속하고 is_connected=True를 반환함을 검증
    [유도] localhost 대신 192.168.35.97 내부망 IP 기반 접속이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=SERVER_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_server_usdms_real_db():
    """
    [목적] 서버PC USDMS 실 DB에 내부망으로 접속하고 is_connected=True를 반환함을 검증
    [유도] 서버PC 두 번째 DB 포트(5435)도 내부망 접속이 가능함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=SERVER_USDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="usdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_detects_real_tables_in_dev_kdms():
    """
    [목적] 개발PC KDMS 실 DB에서 테이블 존재 여부 확인이 동작함을 검증
    [유도] information_schema 쿼리가 실 DB에서 정상 실행됨을 보장.
           존재하지 않는 테이블 지정 시 missing_tables에 포함되어야 함
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["nonexistent_table_xyz"],
        min_row_counts={},
    )
    pool.close_all()

    assert report.is_connected is True
    assert "nonexistent_table_xyz" in report.missing_tables


@pytest.mark.integration
def test_validator_print_report_runs_without_error_on_real_db(capsys):
    """
    [목적] 실 DB 검증 결과를 print_report()로 출력할 때 예외 없이 완료됨을 검증
    [유도] validate() 실행 후 print_report() 호출해도 crash가 없는 구현 유도
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    validator.print_report(report)  # 예외 발생 없이 완료되어야 함
    pool.close_all()

    captured = capsys.readouterr()
    assert len(captured.out) > 0
```

#### 통합 테스트 케이스 요약 (`pytest -m integration`)

| # | 테스트명 | 검증 내용 |
|---|---|---|
| 15 | `test_validator_is_connected_with_dev_kdms_real_db` | 개발PC KDMS 실 접속 |
| 16 | `test_validator_is_connected_with_dev_usdms_real_db` | 개발PC USDMS 실 접속 |
| 17 | `test_validator_is_connected_with_server_kdms_real_db` | 서버PC KDMS 내부망 실 접속 |
| 18 | `test_validator_is_connected_with_server_usdms_real_db` | 서버PC USDMS 내부망 실 접속 |
| 19 | `test_validator_detects_real_tables_in_dev_kdms` | 실 DB에서 테이블 존재 여부 확인 |
| 20 | `test_validator_print_report_runs_without_error_on_real_db` | 실 DB 결과 print_report() 정상 완료 |

**단위 테스트 14개 + 통합 테스트 6개 = 총 20개 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `psycopg2-binary` (T-003), `p1_shared.ops.backup_manager.BackupManager` (T-006)
- **기존 모듈 연계**:
  - `from p1_shared.db.connection import DbConnectionPool` — 커넥션 풀 (T-003)
  - `from p1_shared.ops.backup_manager import BackupManager` — 볼륨 확인 (T-006)
  - `from p1_shared.ops.logger import get_logger` — 로깅 (T-001)
- **테이블 존재 확인 쿼리**:
  ```sql
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = ANY(%s)
  ```
- **Hypertable 청크 확인 쿼리** (TimescaleDB 전용):
  ```sql
  SELECT COUNT(*) FROM timescaledb_information.chunks
  WHERE hypertable_name = %s AND is_compressed = false
  ```
  - TimescaleDB 미설치 환경에서는 쿼리 실패 시 `hypertable_ok=True`로 처리하여 비필수 검증으로 취급
- **ValidationReport.is_healthy** property는 `is_connected`, `missing_tables`, `low_row_tables`, `volume_info["exists"]` 4가지로만 판단 (hypertable은 경고만)
- **print_report() 출력 형식**:
  ```
  ✅ DB 접속: 정상
  ✅ 테이블 존재: daily_ohlcv, stock_info (2/2)
  ❌ 행 수 부족: daily_ohlcv 현재 0행 (예상: 1,000,000행 이상)
     → 조치: python -m p1_shared.ops.backup_manager restore --target kdms
     → 볼륨 경로: /var/lib/docker/volumes/kdms_pgdata/_data/
  ```

---

## § 6. 완료 기준

- [ ] § 4의 단위 테스트 케이스 14개 전체 통과
- [ ] § 4의 통합 테스트 케이스 6개 전체 통과 (개발PC + 서버PC 실 DB 접속 확인)
- [ ] T-001~T-006 기존 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-007 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-007_walkthrough.md` 작성
