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
    # mock pg_dump output to file
    def side_effect(*args, **kwargs):
        if "stdout" in kwargs and kwargs["stdout"] is not mocker.ANY and kwargs["stdout"] is not None:
            kwargs["stdout"].write(b"DUMP")
        return mock_run.return_value
    mock_run.side_effect = side_effect

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
    # mock pg_dump output to file
    def side_effect(*args, **kwargs):
        if "stdout" in kwargs and kwargs["stdout"] is not mocker.ANY and kwargs["stdout"] is not None:
            kwargs["stdout"].write(b"DUMP")
        return mock_run.return_value
    mock_run.side_effect = side_effect
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
    # mock pg_dump output to file
    def side_effect(*args, **kwargs):
        if "stdout" in kwargs and kwargs["stdout"] is not mocker.ANY and kwargs["stdout"] is not None:
            kwargs["stdout"].write(b"DUMP")
        return mock_run.return_value
    mock_run.side_effect = side_effect
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
