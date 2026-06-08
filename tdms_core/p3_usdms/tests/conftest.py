import pytest
import os
from unittest.mock import MagicMock
from p1_shared.db.connection import DbConnectionPool
from p1_shared.utils.env_detector import EnvDetector
from p3_usdms.config import get_settings

@pytest.fixture(autouse=True)
def setup_test_env():
    """모든 테스트에 대해 기본적인 환경 변수 모킹 (기존 값이 없을 때만 설정)"""
    os.environ["TDMS_ENV"] = "dev"
    os.environ["DEV_HOSTNAME"] = "test-host"
    os.environ["DEV_IP"] = "127.0.0.1"
    os.environ["SERVER_IP"] = "192.168.0.200"
    
    os.environ.setdefault("DEV_USDMS_DB_HOST", "127.0.0.1")
    os.environ.setdefault("DEV_USDMS_DB_PORT", "5433")
    os.environ.setdefault("DEV_USDMS_DB_NAME", "usdms_db")
    os.environ.setdefault("DEV_USDMS_DB_USER", "postgres")
    os.environ.setdefault("DEV_USDMS_DB_PASSWORD", "pjsr104edml511")
    os.environ.setdefault("SEC_USER_AGENT", "TestAgent/1.0 (test@example.com)")
    yield


    # 필요시 롤백

def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False, help="Run integration tests")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="--run-integration 플래그 없이는 실행 안 됨")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)

@pytest.fixture(scope="session")
def real_pool():
    """실제 DB에 연결하기 위한 커넥션 풀 피스처"""
    settings = get_settings()
    env = EnvDetector()
    env_name = env.detect()
    
    if env_name == "dev":
        host = env.get_db_host("dev")
        port = settings.DEV_USDMS_DB_PORT
        db_name = settings.DEV_USDMS_DB_NAME
        user = settings.DEV_USDMS_DB_USER
        password = settings.DEV_USDMS_DB_PASSWORD
    elif env_name == "server":
        host = env.get_db_host("server")
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
    pool = DbConnectionPool(dsn)
    yield pool
    pool.close_all()
