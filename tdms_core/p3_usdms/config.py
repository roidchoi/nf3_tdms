from pydantic_settings import BaseSettings
from p1_shared.utils.env_detector import EnvDetector

# EnvDetector 초기화를 통해 .env 파일의 값을 안전하게 로딩 및 선택적 환경변수 오버라이드 수행
detector = EnvDetector()

class Settings(BaseSettings):
    # DSN 및 환경변수
    TDMS_ENV: str = "dev"
    SEC_USER_AGENT: str = ""
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    
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

    # 일일 루틴 및 주간 관리 스케줄 (중앙화 적용)
    SCHEDULE_USDMS_DAILY_ROUTINE: str = "wed,sat:07:30"
    SCHEDULE_USDMS_WEEKLY_MAINTENANCE: str = "sat:09:00"
    SCHEDULE_USDMS_FINANCIAL_ROUTINE: str = "wed,sat:15:00"

    def __init__(self, **values):
        super().__init__(**values)
        # 필수 필드 유효성 검증
        if not self.SEC_USER_AGENT:
            raise ValueError("SEC_USER_AGENT 환경변수가 누락되었습니다")

        # 도커 컨테이너 환경일 경우 마운트 폴더 경로를 강제하여 환경변수 덮어쓰기 문제 방지
        import os
        if os.path.exists('/.dockerenv'):
            self.LOG_DIR = "/app/logs"


# 싱글톤 설정 게터
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
