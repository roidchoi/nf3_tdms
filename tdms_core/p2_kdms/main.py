from contextlib import asynccontextmanager
from fastapi import FastAPI
from p1_shared.ops.startup_validator import StartupValidator
from p1_shared.ops.backup_manager import BackupManager
from repositories.base import create_kdms_pool

# 상수 관리
CONTAINER_NAME = "kdms_timescaledb"
VOLUME_NAME = "kdms_pgdata"
BACKUP_DIR = "backups/kdms"

KDMS_EXPECTED_TABLES = [
    "daily_ohlcv", "stock_info", "price_adjustment_factors",
    "financial_statements", "financial_ratios", "daily_market_cap",
    "system_milestones", "minute_target_history",
]
KDMS_MIN_ROW_COUNTS = {"daily_ohlcv": 1_000_000}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 기동 시:
      1. 커넥션 풀 생성 (create_kdms_pool)
      2. StartupValidator로 DB 5종 검증
      3. is_healthy=False 시 RuntimeError → 서비스 기동 차단
    앱 종료 시: 커넥션 풀 정리 (pool.close_all)
    """
    # 1. 커넥션 풀 생성
    pool = create_kdms_pool()
    app.state.pool = pool
    
    # 2. BackupManager 초기화
    backup_mgr = BackupManager(
        container_name=CONTAINER_NAME,
        db_name="kdms_db",
        db_user="roid",
        backup_dir=BACKUP_DIR,
        volume_name=VOLUME_NAME
    )
    
    # 3. StartupValidator 연동
    validator = StartupValidator(pool, backup_manager=backup_mgr)
    report = validator.validate(
        db_name="kdms",
        expected_tables=KDMS_EXPECTED_TABLES,
        min_row_counts=KDMS_MIN_ROW_COUNTS
    )
    
    if not report.is_healthy:
        raise RuntimeError(f"DB 기동 검증 실패: {report.missing_tables}")
    
    yield
    
    # 종료 시 정리
    pool.close_all()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message": "KDMS API is running"}
