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

    # 수집 기준 환경변수 추가 (T-008)
    TARGET_MIN_MARKET_CAP: float = 50000000.0      # $5천만 (진입)
    TARGET_MIN_PRICE: float = 1.00                 # $1.00 (진입)
    TARGET_RETAIN_MARKET_CAP: float = 35000000.0   # $3.5천만 (유지/탈퇴)
    TARGET_RETAIN_PRICE: float = 0.80              # $0.80 (유지/탈퇴)

    # 일일 루틴 스케줄 추가
    SCHEDULE_DAILY_ROUTINE: str = "07:30"          # 일일 수집 실행 일정 (HH:MM 형식, 디폴트 07:30 KST)

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
