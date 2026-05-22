from contextlib import asynccontextmanager
from fastapi import FastAPI
from p1_shared.ops.startup_validator import StartupValidator
from p1_shared.ops.backup_manager import BackupManager
from repositories.base import create_kdms_pool
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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

# 전역 작업 상태 관리
job_statuses = {
    "daily_update": {"is_running": False, "last_status": "none"},
    "financial_update": {"is_running": False, "last_status": "none"},
    "backfill_minute_data": {"is_running": False, "last_status": "none"},
    "backfill_market_cap": {"is_running": False, "last_status": "none"}
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 기동 시:
      1. 커넥션 풀 생성 (create_kdms_pool)
      2. StartupValidator로 DB 5종 검증
      3. is_healthy=False 시 RuntimeError → 서비스 기동 차단
      4. AsyncIOScheduler 기동 및 Cron 작업 등록
    앱 종료 시:
      1. 스케줄러 종료 (scheduler.shutdown)
      2. 커넥션 풀 정리 (pool.close_all)
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
    
    # 4. 스케줄러 생성 및 의존성 주입
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    
    import routers.admin as admin_module
    admin_module.scheduler = scheduler
    admin_module.job_statuses = job_statuses

    # 4.1. 크론 작업 등록
    from tasks.daily_task import run_daily_update
    from tasks.financial_task import run_financial_update
    from tasks.backfill_task import run_backfill_minute_data

    # 데일리 시세 & 시가총액 수집: 평일 17:00 KST
    scheduler.add_job(
        func=lambda: run_daily_update(job_statuses, test_mode=False),
        trigger='cron',
        day_of_week='mon-fri',
        hour=17,
        minute=0,
        id='daily_update',
        name='daily_update'
    )

    # 분기 재무 데이터 갱신: 매일 19:00 KST
    scheduler.add_job(
        func=lambda: run_financial_update(job_statuses, test_mode=False),
        trigger='cron',
        hour=19,
        minute=0,
        id='financial_update',
        name='financial_update'
    )

    # 분봉 백필 태스크: 수동 트리거 및 백업용으로 유지하며, 주간 자동 크론은 제거됨.


    # 스케줄러 시작
    scheduler.start()
    
    yield
    
    # 종료 시 정리
    scheduler.shutdown()
    pool.close_all()

app = FastAPI(lifespan=lifespan)

from routers.data import router as data_router
from routers.admin import router as admin_router

app.include_router(data_router)
app.include_router(admin_router, prefix="/api/v1/admin")

@app.get("/")
def read_root():
    return {"message": "KDMS API is running"}


