# tdms_core/p4_manager/config.py
from pydantic_settings import BaseSettings
from p1_shared.utils.env_detector import EnvDetector

detector = EnvDetector()

class Settings(BaseSettings):
    P2_KDMS_URL: str = f"http://{detector.get_service_host('p2_kdms')}:8000"
    P3_USDMS_URL: str = f"http://{detector.get_service_host('p3_usdms')}:8005"
    TASK_POLL_INTERVAL: int = 30  # 백그라운드 폴링 주기 (초)
    BACKUP_BASE_DIR: str = "/app/backups"
    data_path: str = "/app/data"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
