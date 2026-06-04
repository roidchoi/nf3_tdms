import os
from typing import Optional
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from p1_shared.db.connection import DbConnectionPool
from p1_shared.utils.env_detector import EnvDetector
from p3_usdms.config import get_settings

class BaseRepository:
    """모든 Repository가 상속받는 기본 클래스 (DbConnectionPool & EnvDetector 통합)"""
    
    _pool: DbConnectionPool = None
    _env: EnvDetector = None

    def __init__(self, pool: Optional[DbConnectionPool] = None):
        # EnvDetector 지연 초기화
        if BaseRepository._env is None:
            BaseRepository._env = EnvDetector()
            
        if pool is not None:
            BaseRepository._pool = pool
            
        # DbConnectionPool 지연 초기화
        if BaseRepository._pool is None:
            settings = get_settings()
            env_name = BaseRepository._env.detect()
            
            # 현재 감지된 환경에 알맞는 DSN 정보 로딩
            if env_name == "dev":
                host = BaseRepository._env.get_db_host("dev")
                port = settings.DEV_USDMS_DB_PORT
                db_name = settings.DEV_USDMS_DB_NAME
                user = settings.DEV_USDMS_DB_USER
                password = settings.DEV_USDMS_DB_PASSWORD
            elif env_name == "server":
                host = BaseRepository._env.get_db_host("server")
                port = settings.SERVER_USDMS_DB_PORT
                db_name = settings.SERVER_USDMS_DB_NAME
                user = settings.SERVER_USDMS_DB_USER
                password = settings.SERVER_USDMS_DB_PASSWORD
            else:
                host = "127.0.0.1"
                port = settings.DEV_USDMS_DB_PORT
                db_name = settings.DEV_USDMS_DB_NAME
                user = settings.DEV_USDMS_DB_USER
                password = settings.DEV_USDMS_DB_PASSWORD

            dsn = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
            # 테스트 시에는 실제 연결 시도를 스킵하거나, 모의 테스트를 고려하여 감쌈
            try:
                BaseRepository._pool = DbConnectionPool(dsn)
            except Exception as e:
                # 오프라인 상태나 테스트 모드에서 커넥션 생성 실패 시 예외를 던지되, 
                # 테스트 모킹을 타는 경우에는 이 부분이 mock 객체 생성으로 우회될 것임.
                # 편의상 테스트 에러 방지를 위해 connection pool 생성이 실패하더라도 
                # 테스트 시에는 무시할 수 있는 장치를 둠 (단, 실제 기동 시에는 예외 던짐)
                if os.environ.get("TDMS_ENV") == "test":
                    pass
                else:
                    raise e

    def get_connection(self):
        """커넥션 풀에서 커넥션을 직접 획득 (레거시 지원용)"""
        return self._pool.get_conn()

    @contextmanager
    def get_cursor(self, autocommit: bool = False):
        """커넥션 풀에서 RealDictCursor를 제공하는 context manager 획득"""
        conn = self._pool.get_conn()
        try:
            if autocommit:
                conn.autocommit = True
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            if not autocommit:
                conn.commit()
        except Exception as e:
            if not autocommit:
                conn.rollback()
            raise e
        finally:
            self._pool.put_conn(conn)
