from contextlib import contextmanager
import psycopg2.extras
from p3_usdms.repositories.base import BaseRepository

class DatabaseManager(BaseRepository):
    """
    레거시 코드와의 100% 호환성을 유지하기 위한 Shim 어댑터.
    기존의 db_manager.py API 구조를 유지하면서 내부적으로는 DbConnectionPool을 활용함.
    """
    def __init__(self):
        super().__init__()

    @contextmanager
    def get_cursor(self, autocommit: bool = False):
        """
        기존 db_manager.py와 동일하게 context manager로 동작하는 RealDictCursor 커서 객체를 반환.
        with DatabaseManager().get_cursor() as cur: 형식 지원.
        """
        conn = self.get_connection()
        try:
            if autocommit:
                conn.autocommit = True
            # 레거시 코드가 키-값 쌍 형태로 데이터에 접근할 수 있도록 RealDictCursor 적용
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
            if not autocommit:
                conn.commit()
        except Exception as e:
            if not autocommit:
                conn.rollback()
            raise e
        finally:
            # 커넥션을 풀에 반환
            self._pool.put_conn(conn)
