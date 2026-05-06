# Task-006: 백업 매니저 (BackupManager)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.5 백업 매니저 (`ops/backup_manager.py`)
> **작성일**: 2026-05-06
> **의존 Task**: T-002 (EnvDetector), T-003 (DbConnectionPool)

---

## § 1. 목표

Docker 컨테이너 내 TimescaleDB를 `pg_dump -Fc` 포맷으로 백업하고, `pre-data → data → post-data` 순서로 강건 복원하는 `BackupManager`를 구현한다. 과거 인덱스/FK 순서 오류로 인한 복원 실패를 방지하기 위해 섹션 분리 복원이 핵심이다.

**구현 범위:**
- **IN**:
  - `p1_shared/ops/backup_manager.py` — `BackupManager` 클래스 + `BackupInfo` dataclass + CLI 진입점
  - `backup()` — `pg_dump -Fc` → `.dump` 파일 저장 → `verify()` 자동 호출
  - `verify()` — `pg_restore --list` 헤더 파싱 (테이블 존재·파일 크기)
  - `restore()` — `pre_backup=True`(기본) 사전 스냅샷 + 섹션 분리 복원
  - `check_volume_exists()` — Docker 볼륨 실물 파일 존재 확인
  - `list_backups()` / `cleanup_old()` — 파일 목록 조회 및 보관 정책 삭제
  - `tests/test_backup_manager.py` — 단위 테스트 (subprocess, 파일시스템 Mock)
- **OUT**:
  - 실제 Docker 컨테이너 실행 (단위 테스트는 subprocess Mock)
  - `StartupValidator` 연동 — T-007

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/backup_manager.py`
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_backup_manager.py`

### 핵심 인터페이스

```python
# p1_shared/ops/backup_manager.py
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

@dataclass
class BackupInfo:
    path: Path
    tag: str
    created_at: datetime
    size_bytes: int
    verified: bool

class BackupManager:
    """TimescaleDB pg_dump 기반 백업·복구·검증 관리자."""

    def __init__(
        self,
        container_name: str,   # Docker 컨테이너명 (예: "p2_kdms_db")
        db_name: str,          # DB명 (예: "kdms_db")
        db_user: str,
        backup_dir: str,       # 백업 파일 저장 디렉토리
        volume_name: str,      # Docker 볼륨명 (예: "kdms_pgdata")
    ) -> None: ...

    def backup(self, tag: str = "manual") -> Path:
        """
        pg_dump -Fc 실행 후 .dump 파일 저장.
        파일명: {backup_dir}/{tag}/checkpoint_{YYYYMMDD_HHMMSS}.dump
        완료 후 verify() 자동 호출.
        Raises:
            RuntimeError: pg_dump 실패 또는 verify() 실패 시
        """
        ...

    def verify(self, dump_path: Path) -> bool:
        """
        pg_restore --list로 dump 파일 헤더 파싱.
        확인: 파일 크기 > 0, 헤더 파싱 성공.
        Returns:
            True: 검증 통과 / False: 검증 실패
        """
        ...

    def restore(
        self,
        dump_path: Path,
        pre_backup: bool = True,
        section_order: bool = True,
    ) -> bool:
        """
        강건 복원. pre_backup=True 시 복원 전 스냅샷.
        section_order=True 시 pre-data → data → post-data 순서 적용.
        """
        ...

    def check_volume_exists(self) -> dict:
        """
        Docker 볼륨 실물 파일 존재 확인.
        Returns:
            {"volume_path": str, "exists": bool, "pg_version": str|None, "size_bytes": int}
        """
        ...

    def list_backups(self, tag: str | None = None) -> list[BackupInfo]:
        """저장된 백업 파일 목록 반환."""
        ...

    def cleanup_old(self, retain_daily: int = 30, retain_weekly: int = 12) -> int:
        """보관 정책에 따라 오래된 백업 파일 삭제. 삭제된 파일 수 반환."""
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트를 먼저 작성한 뒤 통과하도록 구현하세요.
> subprocess는 `mocker.patch("subprocess.run")`으로, 파일시스템은 `tmp_path`로 격리하세요.

### 4.1 정상 동작 케이스

```python
# tests/test_backup_manager.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# ─── BackupManager 초기화 헬퍼 ───
def make_manager(tmp_path):
    from p1_shared.ops.backup_manager import BackupManager
    return BackupManager(
        container_name="p2_kdms_db",
        db_name="kdms_db",
        db_user="roid",
        backup_dir=str(tmp_path / "backups"),
        volume_name="kdms_pgdata",
    )


def test_backup_creates_dump_file_in_tagged_subdir(tmp_path, mocker):
    """
    [목적] backup() 호출 시 {backup_dir}/{tag}/ 하위에 .dump 파일 생성
    [유도] 파일명 패턴 checkpoint_{YYYYMMDD_HHMMSS}.dump 구현 강제
    """
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"TABLE: daily_ohlcv\n", stderr=b"")

    mgr = make_manager(tmp_path)
    dump_path = mgr.backup(tag="daily")

    assert dump_path.suffix == ".dump"
    assert "daily" in str(dump_path)
    assert dump_path.parent.exists()


def test_backup_calls_pg_dump_with_fc_format(tmp_path, mocker):
    """
    [목적] backup()이 pg_dump -Fc 옵션으로 subprocess를 호출함을 검증
    [유도] subprocess.run 호출 시 '-Fc' 인자 포함 구현 강제
    """
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"TABLE: daily_ohlcv\n", stderr=b"")

    mgr = make_manager(tmp_path)
    mgr.backup(tag="manual")

    called_args = mock_run.call_args_list[0][0][0]
    assert "pg_dump" in called_args
    assert "-Fc" in called_args


def test_backup_calls_verify_automatically(tmp_path, mocker):
    """
    [목적] backup() 완료 후 verify()가 자동 호출됨을 검증
    [유도] backup() 내부에서 self.verify(dump_path) 호출 구현 강제
    """
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"TABLE: daily_ohlcv\n", stderr=b"")

    mgr = make_manager(tmp_path)
    mocker.patch.object(mgr, "verify", return_value=True)
    mgr.backup(tag="manual")

    mgr.verify.assert_called_once()


def test_verify_returns_true_for_valid_dump(tmp_path, mocker):
    """
    [목적] pg_restore --list가 성공하고 파일이 존재하면 True 반환
    [유도] 파일 크기 > 0 + returncode == 0 조건 구현 강제
    """
    dump_file = tmp_path / "test.dump"
    dump_file.write_bytes(b"FAKE_DUMP_CONTENT")

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"TABLE: daily_ohlcv\n", stderr=b"")

    mgr = make_manager(tmp_path)
    result = mgr.verify(dump_file)

    assert result is True


def test_restore_creates_pre_backup_before_restoring(tmp_path, mocker):
    """
    [목적] pre_backup=True(기본값) 시 복원 전 backup()이 먼저 호출됨을 검증
    [유도] restore() 시작 시 self.backup(tag="pre_restore") 호출 구현 강제
    """
    dump_file = tmp_path / "restore.dump"
    dump_file.write_bytes(b"FAKE_DUMP")

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

    mgr = make_manager(tmp_path)
    mocker.patch.object(mgr, "backup", return_value=dump_file)
    mocker.patch.object(mgr, "verify", return_value=True)

    mgr.restore(dump_file, pre_backup=True)

    mgr.backup.assert_called_once()


def test_restore_with_section_order_calls_pg_restore_three_times(tmp_path, mocker):
    """
    [목적] section_order=True 시 pg_restore가 pre-data/data/post-data 3회 호출됨을 검증
    [유도] 섹션 분리 복원 루프 구현 강제 (인덱스 순서 오류 방지)
    """
    dump_file = tmp_path / "restore.dump"
    dump_file.write_bytes(b"FAKE_DUMP")

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

    mgr = make_manager(tmp_path)
    mocker.patch.object(mgr, "backup", return_value=dump_file)
    mocker.patch.object(mgr, "verify", return_value=True)

    mgr.restore(dump_file, pre_backup=False, section_order=True)

    pg_restore_calls = [
        c for c in mock_run.call_args_list
        if "pg_restore" in c[0][0]
    ]
    sections = [
        arg for call in pg_restore_calls
        for arg in call[0][0]
        if arg in ("pre-data", "data", "post-data")
    ]
    assert set(sections) == {"pre-data", "data", "post-data"}


def test_list_backups_returns_backup_info_list(tmp_path, mocker):
    """
    [목적] list_backups()가 BackupInfo 목록을 반환함을 검증
    [유도] .dump 파일을 읽어 BackupInfo로 변환하는 구현 강제
    """
    backup_dir = tmp_path / "backups" / "daily"
    backup_dir.mkdir(parents=True)
    (backup_dir / "checkpoint_20260506_030000.dump").write_bytes(b"FAKE")

    mgr = make_manager(tmp_path)
    results = mgr.list_backups(tag="daily")

    assert len(results) == 1
    assert results[0].tag == "daily"
    assert results[0].size_bytes > 0


def test_cleanup_old_deletes_files_exceeding_retain_count(tmp_path):
    """
    [목적] retain_daily=2일 때 가장 오래된 파일부터 삭제됨을 검증
    [유도] 생성일시 기준 정렬 후 초과분 삭제 구현 강제
    """
    backup_dir = tmp_path / "backups" / "daily"
    backup_dir.mkdir(parents=True)
    for i in range(4):
        f = backup_dir / f"checkpoint_202605{i+1:02d}_030000.dump"
        f.write_bytes(b"X")

    mgr = make_manager(tmp_path)
    deleted = mgr.cleanup_old(retain_daily=2)

    remaining = list(backup_dir.glob("*.dump"))
    assert len(remaining) == 2
    assert deleted == 2
```

### 4.2 경계값 케이스

```python
def test_list_backups_returns_empty_when_no_files_exist(tmp_path):
    """
    [목적] 백업 파일이 없으면 빈 리스트 반환 (예외 없음)
    [유도] glob 결과가 0개일 때 [] 반환 구현 강제
    """
    mgr = make_manager(tmp_path)
    result = mgr.list_backups()
    assert result == []


def test_check_volume_exists_returns_false_when_volume_path_not_found(tmp_path, mocker):
    """
    [목적] Docker 볼륨 경로가 존재하지 않으면 exists=False 반환
    [유도] Path.exists() 체크 후 dict 구성 구현 강제
    """
    mocker.patch(
        "p1_shared.ops.backup_manager.VOLUME_BASE_PATH",
        str(tmp_path / "nonexistent"),
    )
    mgr = make_manager(tmp_path)
    result = mgr.check_volume_exists()

    assert result["exists"] is False
    assert result["pg_version"] is None


def test_cleanup_old_does_nothing_when_files_within_retain_count(tmp_path):
    """
    [목적] 파일 수가 보관 기준 이하이면 삭제 없이 0 반환
    [유도] 삭제 조건 분기 구현 강제
    """
    backup_dir = tmp_path / "backups" / "daily"
    backup_dir.mkdir(parents=True)
    (backup_dir / "checkpoint_20260506_030000.dump").write_bytes(b"X")

    mgr = make_manager(tmp_path)
    deleted = mgr.cleanup_old(retain_daily=30)

    assert deleted == 0
```

### 4.3 예외/오류 처리 케이스

```python
def test_backup_raises_runtime_error_when_pg_dump_fails(tmp_path, mocker):
    """
    [목적] pg_dump가 비정상 종료(returncode != 0) 시 RuntimeError 발생
    [유도] subprocess.run returncode 체크 후 RuntimeError 변환 구현 강제
    """
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"ERROR: permission denied")

    mgr = make_manager(tmp_path)
    with pytest.raises(RuntimeError, match="pg_dump"):
        mgr.backup(tag="manual")


def test_verify_returns_false_for_empty_dump_file(tmp_path, mocker):
    """
    [목적] 크기가 0인 .dump 파일은 verify()가 False 반환
    [유도] 파일 크기 > 0 조건 구현 강제
    """
    dump_file = tmp_path / "empty.dump"
    dump_file.write_bytes(b"")

    mocker.patch("subprocess.run")  # pg_restore --list 호출 방지

    mgr = make_manager(tmp_path)
    result = mgr.verify(dump_file)

    assert result is False


def test_restore_raises_runtime_error_when_pg_restore_fails(tmp_path, mocker):
    """
    [목적] pg_restore 실패 시 RuntimeError 발생
    [유도] 복원 subprocess returncode != 0 → RuntimeError 구현 강제
    """
    dump_file = tmp_path / "restore.dump"
    dump_file.write_bytes(b"FAKE_DUMP")

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"ERROR: relation already exists")

    mgr = make_manager(tmp_path)
    mocker.patch.object(mgr, "backup", return_value=dump_file)
    mocker.patch.object(mgr, "verify", return_value=True)

    with pytest.raises(RuntimeError):
        mgr.restore(dump_file, pre_backup=False)
```

### 4.4 연계 케이스 — 기존 구현 모듈 호환성

```python
def test_backup_manager_uses_ops_logger(tmp_path, mocker):
    """
    [목적] BackupManager가 p1_shared.ops.logger.get_logger를 사용함을 검증 (T-001 연계)
    [유도] 클래스 내부에서 get_logger(__name__) 호출 구현 강제
    """
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout=b"TABLE: daily_ohlcv\n", stderr=b"")

    from p1_shared.ops import logger as logger_module
    spy = mocker.spy(logger_module, "get_logger")

    make_manager(tmp_path)

    spy.assert_called()


def test_backup_manager_env_detector_compatible(tmp_path, monkeypatch):
    """
    [목적] EnvDetector.load_env_profile()이 반환한 self_ip를 사용해
           BackupManager가 초기화될 수 있음을 검증 (T-002 연계)
    [유도] EnvDetector 반환값 구조와 BackupManager 생성자 파라미터가 호환됨을 보장
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "dev")
    monkeypatch.setenv("DEV_IP", "192.168.35.205")
    monkeypatch.setenv("SERVER_IP", "192.168.35.97")
    monkeypatch.setenv("DEV_HOSTNAME", "EDM-LAB-ALT02")
    monkeypatch.setenv("SERVER_HOSTNAME", "EDM-LAB-MD02")
    monkeypatch.setenv("KDMS_CONTAINER_NAME", "p2_kdms_db")
    monkeypatch.setenv("KDMS_VOLUME_NAME", "kdms_pgdata")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    detector = EnvDetector()
    profile = detector.load_env_profile()

    from p1_shared.ops.backup_manager import BackupManager
    mgr = BackupManager(
        container_name="p2_kdms_db",
        db_name="kdms_db",
        db_user="roid",
        backup_dir=profile["self_ip"],  # IP 확인 가능 여부 검증
        volume_name="kdms_pgdata",
    )
    assert mgr is not None


def test_backup_dir_is_created_automatically_on_init(tmp_path):
    """
    [목적] backup_dir이 존재하지 않아도 초기화 시 자동 생성됨을 검증
    [유도] __init__에서 Path(backup_dir).mkdir(parents=True, exist_ok=True) 구현 강제
    """
    target_dir = tmp_path / "new" / "backup" / "dir"
    assert not target_dir.exists()

    from p1_shared.ops.backup_manager import BackupManager
    BackupManager(
        container_name="p2_kdms_db",
        db_name="kdms_db",
        db_user="roid",
        backup_dir=str(target_dir),
        volume_name="kdms_pgdata",
    )
    assert target_dir.exists()
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_backup_creates_dump_file_in_tagged_subdir` | 정상 | tag 서브디렉토리에 .dump 파일 생성 |
| 2 | `test_backup_calls_pg_dump_with_fc_format` | 정상 | `-Fc` 옵션으로 pg_dump 호출 |
| 3 | `test_backup_calls_verify_automatically` | 정상 | backup() 후 verify() 자동 호출 |
| 4 | `test_verify_returns_true_for_valid_dump` | 정상 | 유효 dump → True |
| 5 | `test_restore_creates_pre_backup_before_restoring` | 정상 | pre_backup=True 시 사전 스냅샷 |
| 6 | `test_restore_with_section_order_calls_pg_restore_three_times` | 정상 | 섹션 분리 복원 3회 호출 |
| 7 | `test_list_backups_returns_backup_info_list` | 정상 | BackupInfo 목록 반환 |
| 8 | `test_cleanup_old_deletes_files_exceeding_retain_count` | 정상 | 보관 초과 파일 삭제 |
| 9 | `test_list_backups_returns_empty_when_no_files_exist` | 경계값 | 파일 없음 → 빈 리스트 |
| 10 | `test_check_volume_exists_returns_false_when_volume_path_not_found` | 경계값 | 볼륨 경로 없음 → exists=False |
| 11 | `test_cleanup_old_does_nothing_when_files_within_retain_count` | 경계값 | 기준 이하 → 삭제 0개 |
| 12 | `test_backup_raises_runtime_error_when_pg_dump_fails` | 예외 | pg_dump 실패 → RuntimeError |
| 13 | `test_verify_returns_false_for_empty_dump_file` | 예외 | 크기 0 파일 → False |
| 14 | `test_restore_raises_runtime_error_when_pg_restore_fails` | 예외 | pg_restore 실패 → RuntimeError |
| 15 | `test_backup_manager_uses_ops_logger` | 연계 | T-001 logger 모듈 사용 확인 |
| 16 | `test_backup_manager_env_detector_compatible` | 연계 | T-002 EnvDetector 반환값과 호환 |
| 17 | `test_backup_dir_is_created_automatically_on_init` | 연계 | 초기화 시 backup_dir 자동 생성 |

**총 17개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `subprocess` (내장), `pathlib` (내장)
- **기존 모듈 연계**:
  - `from p1_shared.ops.logger import get_logger` — 로깅 (T-001)
  - `from p1_shared.utils.env_detector import EnvDetector` — 선택적 환경 감지 (T-002)
  - `DbConnectionPool` — 이 Task에서는 직접 사용 안 함 (T-007 StartupValidator가 연동)
- **pg_dump 호출 패턴**:
  ```bash
  docker exec {container_name} pg_dump -U {db_user} -Fc {db_name} > {dump_path}
  ```
- **pg_restore 섹션 분리 패턴**:
  ```bash
  # 1단계: 테이블 구조
  docker exec {container_name} pg_restore -U {db_user} -d {db_name} --section=pre-data {dump_path}
  # 2단계: 데이터
  docker exec {container_name} pg_restore -U {db_user} -d {db_name} --section=data --data-only {dump_path}
  # 3단계: 인덱스/FK
  docker exec {container_name} pg_restore -U {db_user} -d {db_name} --section=post-data {dump_path}
  ```
- **볼륨 경로 상수**: `VOLUME_BASE_PATH = "/var/lib/docker/volumes"` 를 모듈 레벨 상수로 선언하여 테스트에서 monkeypatch 가능하게 할 것
- **백업 파일 타임스탬프**: `datetime.now().strftime("%Y%m%d_%H%M%S")` 사용

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 17개 전체 통과
- [ ] T-001~T-003 기존 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-006 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-006_walkthrough.md` 작성
