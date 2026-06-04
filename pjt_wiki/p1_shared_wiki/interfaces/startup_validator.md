# Interface: StartupValidator

> **파일**: `tdms_core/p1_shared/p1_shared/ops/startup_validator.py`
> **Task**: T-007
> **Graphify God Node**: 48 edges (4위)
> **관련**: `[[p1_shared_wiki/interfaces/db_connection_pool.md]]`, `[[p1_shared_wiki/interfaces/backup_manager.md]]`

---

## 클래스/데이터클래스 시그니처

```python
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
        """
        is_connected AND missing_tables=[] AND low_row_tables={} AND volume_info["exists"]=True
        volume_info가 비어있으면(검증 건너뜀) True로 취급.
        hypertable_ok는 is_healthy에 영향 없음 (경고만)
        """

class StartupValidator:
    """Docker 재기동 시 DB 연결·데이터 정합성 자가 검증기."""

    def __init__(
        self,
        pool: DbConnectionPool,
        backup_manager: BackupManager | None = None,
    ) -> None:
        """
        backup_manager=None이면 볼륨 검증(4번 항목) 건너뜀.
        """

    def validate(
        self,
        db_name: Literal["kdms", "usdms"],
        expected_tables: list[str],
        min_row_counts: dict[str, int],
    ) -> ValidationReport:
        """
        5가지 항목 순차 검증:
          1. DB 접속 가능 여부 (SELECT 1)
          2. 핵심 테이블 존재 여부 (information_schema.tables)
          3. 각 테이블 행 수 >= 최소 예상치 (COUNT(*))
          4. Docker 볼륨 실물 파일 존재 (backup_manager.check_volume_exists())
          5. Hypertable 청크 상태 (timescaledb_information.chunks) — 경고만
        """

    def print_report(self, report: ValidationReport) -> None:
        """
        출력 예시:
          ✅ DB 접속: 정상
          ✅ 테이블 존재: daily_ohlcv, stock_info (2/2)
          ❌ 행 수 부족: daily_ohlcv 현재 0행 (예상: 1,000,000행 이상)
             → 조치: python -m p1_shared.ops.backup_manager restore --target kdms
             → 볼륨 경로: /var/lib/docker/volumes/kdms_pgdata/_data/
        """
```

---

## 사용 패턴 (FastAPI lifespan)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops.startup_validator import StartupValidator
from p1_shared.ops.backup_manager import BackupManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = DbConnectionPool(dsn=os.getenv("KDMS_DSN"))
    backup_mgr = BackupManager(
        container_name="kdms_timescaledb",
        db_name="kdms_db",
        db_user="roid",
        backup_dir="./backups/kdms",
        volume_name="kdms_pgdata",
    )
    validator = StartupValidator(pool=pool, backup_manager=backup_mgr)

    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv", "stock_info"],
        min_row_counts={"daily_ohlcv": 1_000_000},
    )
    validator.print_report(report)

    if not report.is_healthy:
        raise RuntimeError("DB 기동 검증 실패")

    yield
    pool.close_all()
```

---

## SQL 쿼리 (내부 구현)

```sql
-- 테이블 존재 확인
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = ANY(%s)

-- 행 수 확인
SELECT COUNT(*) FROM {table_name}

-- Hypertable 청크 상태
SELECT COUNT(*) FROM timescaledb_information.chunks
WHERE hypertable_name = %s AND is_compressed = false
```

---

## 주의사항

- **DB 접속 실패 시**: `is_connected=False`, 이후 검증 항목 모두 건너뜀
- **TimescaleDB 미설치 환경**: Hypertable 쿼리 실패 시 `hypertable_ok=True`로 처리 (비필수)
- **테스트 패턴**: `mocker.patch.object(pool, "get_cursor")` + `@contextmanager` 헬퍼 사용
