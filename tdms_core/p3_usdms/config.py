import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv

# .env 파일 로딩
load_dotenv(find_dotenv())

class Settings(BaseSettings):
    # DSN 및 환경변수
    TDMS_ENV: str = "dev"
    SEC_USER_AGENT: str = ""
    
    # DB (USDMS 전용)
    DEV_USDMS_DB_HOST: str = "127.0.0.1"
    DEV_USDMS_DB_PORT: int = 5433
    DEV_USDMS_DB_NAME: str = "usdms_db"
    DEV_USDMS_DB_USER: str = "usdms_user"
    DEV_USDMS_DB_PASSWORD: str = ""
    
    SERVER_USDMS_DB_HOST: str = ""
    SERVER_USDMS_DB_PORT: int = 5433
    SERVER_USDMS_DB_NAME: str = "usdms_db"
    SERVER_USDMS_DB_USER: str = "usdms_user"
    SERVER_USDMS_DB_PASSWORD: str = ""

    def __init__(self, **values):
        super().__init__(**values)
        # 필수 필드 유효성 검증
        if not self.SEC_USER_AGENT:
            raise ValueError("SEC_USER_AGENT 환경변수가 누락되었습니다")

# 싱글톤 설정 게터
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
