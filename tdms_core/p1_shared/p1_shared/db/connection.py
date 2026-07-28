import os
import sys
from contextlib import contextmanager
from typing import Generator
import psycopg2
import psycopg2.pool
import psycopg2.extensions

class DbConnectionPool:
    """
    psycopg2.pool.ThreadedConnectionPool 래퍼.

    get_cursor()를 context manager로 사용하면 커넥션 획득, 커서 제공,
    커밋(또는 rollback), 커넥션 반환이 자동으로 처리된다.

    Args:
        dsn: PostgreSQL 접속 문자열
             예: "postgresql://user:pass@192.168.1.10:5432/kdms_db"
        min_conn: 풀 최소 커넥션 수 (기본값 5)
        max_conn: 풀 최대 커넥션 수 (기본값 20)
    """

    def __init__(self, dsn: str, min_conn: int = 5, max_conn: int = 20) -> None:
        """
        Raises:
            psycopg2.OperationalError: DSN이 유효하지 않거나 DB에 연결 불가한 경우
        """
        # 테스트 실행 중 실 DB 접근 차단 Guard
        is_test_runner = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
        is_explicit_integration = os.environ.get("RUN_INTEGRATION_TESTS", "false").lower() in ("true", "1")
        is_live_db = any(ip in dsn for ip in ["192.168.35.249", "192.168.35.176", "EDM-LAB-ALT02", "EDM-LAB-MD02"])
        
        if is_test_runner and is_live_db and not is_explicit_integration:
            raise RuntimeError(
                f"🚨 [DB Connection Guard] Test environment detected! "
                f"Connecting to live database ({dsn}) is blocked during unit tests "
                f"to prevent data corruption. Please mock your database repositories or set RUN_INTEGRATION_TESTS=true."
            )
            
        self._pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, dsn)

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

        Yields:
            psycopg2 cursor 객체

        Raises:
            psycopg2.pool.PoolError: 풀에서 커넥션을 얻지 못한 경우
            Exception: 쿼리 실행 중 발생한 예외 (rollback 후 재발생)
        """
        conn = self._pool.getconn()
        try:
            if autocommit:
                conn.autocommit = True
            
            with conn.cursor() as cur:
                yield cur
                
            if not autocommit:
                conn.commit()
        except Exception as e:
            if not autocommit:
                conn.rollback()
            raise e
        finally:
            self._pool.putconn(conn)

    def get_conn(self):
        """커넥션 풀에서 커넥션을 직접 획득한다 (레거시/어댑터 호환용)."""
        return self._pool.getconn()

    def put_conn(self, conn) -> None:
        """획득한 커넥션을 풀에 반환한다 (레거시/어댑터 호환용)."""
        self._pool.putconn(conn)

    def close_all(self) -> None:
        """풀의 모든 커넥션을 닫는다."""
        self._pool.closeall()
