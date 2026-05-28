# Interface: DbConnectionPool

> **파일**: `tdms_core/p1_shared/p1_shared/db/connection.py`
> **Task**: T-003
> **Graphify God Node**: 80 edges (2위)
> **관련**: `[[environment.md]]`, `[[interfaces/startup_validator.md]]`

---

## 클래스 시그니처

```python
class DbConnectionPool:
    def __init__(self, dsn: str, min_conn: int = 5, max_conn: int = 20) -> None:
        """
        Raises:
            psycopg2.OperationalError: DSN이 유효하지 않거나 DB에 연결 불가한 경우
        """

    @contextmanager
    def get_cursor(self, autocommit: bool = False) -> Generator:
        """
        커넥션 풀에서 커넥션을 획득하고 커서를 yield한다.
        - 정상 종료 시: commit() 후 커넥션 반환
        - 예외 발생 시: rollback() 후 커넥션 반환, 예외 재발생
        - autocommit=True 시: 커밋/롤백 없이 커서만 제공

        Usage:
            with pool.get_cursor() as cur:
                cur.execute("SELECT ...")

        Raises:
            psycopg2.pool.PoolError: 풀에서 커넥션을 얻지 못한 경우
            Exception: 쿼리 실행 중 발생한 예외 (rollback 후 재발생)
        """

    def close_all(self) -> None:
        """모든 커넥션을 닫고 풀을 종료한다."""
```

---

## 사용 패턴

```python
from p1_shared.db.connection import DbConnectionPool

# DSN 형식: "postgresql://user:pass@host:port/dbname"
pool = DbConnectionPool(dsn="postgresql://roid:pass@192.168.35.205:5432/kdms_db")

with pool.get_cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM daily_ohlcv")
    count = cur.fetchone()[0]

pool.close_all()
```

---

## 내부 구현 핵심

- **래핑**: `psycopg2.pool.ThreadedConnectionPool` (멀티스레드 안전)
- **커서 획득**: `conn.cursor()` → context manager 형태로 yield
- **autocommit=True**: DDL(CREATE TABLE 등) 실행 시 사용
- **정상 종료**: `conn.commit()` → `self._pool.putconn(conn)`
- **예외 발생**: `conn.rollback()` → `self._pool.putconn(conn)` → 예외 재발생

---

## 주의사항

- `close_all()` 은 앱 종료 시 또는 통합 테스트 후 반드시 호출할 것
- FastAPI lifespan에서: `startup` 시 생성, `shutdown` 시 `close_all()` 호출
- 단위 테스트에서는 `mocker.patch.object(pool, "get_cursor")` + `@contextmanager` Mock 사용
