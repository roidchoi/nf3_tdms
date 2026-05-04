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
def test_pool_connects_to_dev_kdms_db():
    """
    [목적] 개발PC KDMS DB(192.168.35.205:5432)에 실제 접속 가능함을 검증
    [유도] DbConnectionPool이 실 DSN으로 psycopg2 풀을 정상 생성하는 구현 강제
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_dev_usdms_db():
    """
    [목적] 개발PC USDMS DB(192.168.35.205:5435)에 실제 접속 가능함을 검증
    [유도] 포트가 다른 DB에도 동일한 DbConnectionPool 클래스가 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_USDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_server_kdms_db():
    """
    [목적] 서버PC KDMS DB(192.168.35.97:5432)에 내부망으로 실제 접속 가능함을 검증
    [유도] localhost 대신 내부망 IP 기반 접속이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=SERVER_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_server_usdms_db():
    """
    [목적] 서버PC USDMS DB(192.168.35.97:5435)에 내부망으로 실제 접속 가능함을 검증
    [유도] 서버PC의 두 번째 DB 포트(5435)도 내부망 접속이 가능함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=SERVER_USDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_execute_select_and_fetch_from_dev_kdms():
    """
    [목적] 개발PC KDMS DB에서 실제 테이블 조회가 가능함을 검증
    [유도] cursor.execute + fetchone/fetchall 흐름이 실 DB에서 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT current_database(), current_user")
        db_name, db_user = cur.fetchone()
    pool.close_all()

    assert db_name == os.getenv("DEV_KDMS_DB_NAME", "kdms_db")
