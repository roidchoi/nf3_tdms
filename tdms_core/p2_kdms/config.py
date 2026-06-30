from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    .env 파일을 자동으로 로딩하는 설정 클래스.
    Layer A (EnvDetector용)와 Layer B (앱 내부용) 변수를 모두 포함.
    """
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Layer A — EnvDetector 전용
    tdms_env: str = ""
    dev_hostname: str = ""
    server_hostname: str = ""
    dev_ip: str = ""
    server_ip: str = ""
    
    # DEV DB
    dev_kdms_db_user: str = "roid"
    dev_kdms_db_password: str = ""
    dev_kdms_db_port: int = 5432
    dev_kdms_db_name: str = "kdms_db"
    
    # SERVER DB
    server_kdms_db_user: str = "roid"
    server_kdms_db_password: str = ""
    server_kdms_db_port: int = 5432
    server_kdms_db_name: str = "kdms_db"

    # Layer B — 앱 내부용
    postgres_user: str = ""
    postgres_password: str = ""
    db_pool_min: int = 5
    db_pool_max: int = 20
    log_level: str = "INFO"

    # 공통 스케줄링 일정
    schedule_kdms_daily_update: str = "17:10"
    schedule_kdms_financial_update: str = "sat:14:00"
    schedule_kdms_backfill_minute: str = "sat:16:00"

# 기본적으로는 .env 파일 시도 (없어도 에러는 안남 - 기본값 사용)
settings = Settings(_env_file=".env")

