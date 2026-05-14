from p1_shared.ops.backup_manager import BackupManager

def run_backup():
    """
    p2 인계 전 기존 DB 백업 실행.
    tag='pre_p2_migration' 사용.
    """
    backup_mgr = BackupManager(
        container_name="kdms_timescaledb",
        db_name="kdms_db",
        db_user="roid",
        backup_dir="backups/kdms",
        volume_name="kdms_pgdata"
    )
    return backup_mgr.backup(tag="pre_p2_migration")

if __name__ == "__main__":
    result = run_backup()
    print(f"✅ 백업 완료: {result}")
