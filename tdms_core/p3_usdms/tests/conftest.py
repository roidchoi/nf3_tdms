import pytest
import os
from unittest.mock import MagicMock
from p1_shared.db.connection import DbConnectionPool

@pytest.fixture(autouse=True)
def setup_test_env():
    """모든 테스트에 대해 기본적인 환경 변수 모킹"""
    os.environ["TDMS_ENV"] = "dev"
    os.environ["DEV_HOSTNAME"] = "test-host"
    os.environ["DEV_IP"] = "192.168.0.100"
    os.environ["SERVER_IP"] = "192.168.0.200"
    os.environ["DEV_USDMS_DB_HOST"] = "127.0.0.1"
    os.environ["DEV_USDMS_DB_PORT"] = "5433"
    os.environ["DEV_USDMS_DB_NAME"] = "usdms_db"
    os.environ["DEV_USDMS_DB_USER"] = "usdms_user"
    os.environ["DEV_USDMS_DB_PASSWORD"] = "password"
    os.environ["SEC_USER_AGENT"] = "TestAgent/1.0 (test@example.com)"
    yield
    # 필요시 롤백
