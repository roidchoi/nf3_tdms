# Interface: BackupManager

> **파일**: `tdms_core/p1_shared/p1_shared/ops/backup_manager.py`
> **Task**: T-006
> **Graphify God Node**: 58 edges (3위)
> **관련**: `[[p1_shared_wiki/interfaces/startup_validator.md]]`, `[[p1_shared_wiki/decisions/dec-001_physical_sync.md]]`

---

## 클래스/데이터클래스 시그니처

```python
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
        container_name: str,  # 예: "kdms_timescaledb"
        db_name: str,          # 예: "kdms_db"
        db_user: str,          # 예: "roid"
        backup_dir: str,       # 예: "./backups/kdms"
        volume_name: str,      # 예: "kdms_pgdata"
    ) -> None: ...

    def backup(self, tag: str = "manual") -> Path:
        """
        pg_dump -Fc 실행 후 {backup_dir}/{tag}/checkpoint_{ts}.dump 저장.
        내부적으로 verify() 자동 호출. 실패 시 RuntimeError 발생.
        """

    def verify(self, dump_path: Path) -> bool:
        """pg_restore --list로 dump 파일 헤더 파싱하여 검증."""

    def restore(
        self,
        dump_path: Path,
        pre_backup: bool = True,
        section_order: bool = True,
    ) -> None:
        """
        강건 복원. pre_backup=True 시 복원 전 스냅샷.
        section_order=True 시 pre-data → data → post-data 순서로 복원.
        (인덱스/FK 순서 문제 해결을 위한 핵심 전략)
        """

    def list_backups(self, tag: str = "manual") -> list[BackupInfo]:
        """특정 tag 디렉토리 내 백업 파일 목록 반환."""

    def cleanup_old(self, tag: str = "manual", keep_count: int = 5) -> int:
        """보관 정책에 따라 오래된 백업 파일 삭제. 삭제된 파일 수 반환."""

    def check_volume_exists(self) -> dict:
        """
        Docker 볼륨 실물 파일 존재 확인.

        Returns:
            {
                "exists": bool,
                "volume_path": str,   # /var/lib/docker/volumes/{volume_name}/_data
                "pg_version": str | None,
                "size_bytes": int,
            }
        """
```

---

## 사용 패턴

```python
from p1_shared.ops.backup_manager import BackupManager

mgr = BackupManager(
    container_name="kdms_timescaledb",
    db_name="kdms_db",
    db_user="roid",
    backup_dir="./backups/kdms",
    volume_name="kdms_pgdata",
)

# 백업
dump_path = mgr.backup(tag="before_sync")

# 복원 (section_order=True 필수 — FK 순서 문제 방지)
mgr.restore(dump_path, pre_backup=True, section_order=True)

# 볼륨 확인 (StartupValidator에서 활용)
vol_info = mgr.check_volume_exists()
# {"exists": True, "volume_path": "...", "pg_version": "16", "size_bytes": 12884901888}
```

---

## 핵심 설계 결정

**`section_order=True` (pre-data → data → post-data)**:
- `pg_restore -j 8` 병렬 복원 시 FK/인덱스가 먼저 생성되어 data INSERT가 실패하는 문제 발생
- 섹션을 분리하여 순서대로 복원함으로써 해결
- 참조: `[[p1_shared_wiki/decisions/dec-002_pg_restore_section_order.md]]`

**볼륨 경로**: `/var/lib/docker/volumes/{volume_name}/_data`
- TimescaleDB의 실제 `PGDATA`는 컨테이너 내부 `/home/postgres/pgdata/data`
- 물리 복제 시 이 경로 기준으로 tar 실행
