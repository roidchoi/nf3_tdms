import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from p1_shared.ops.startup_validator import StartupValidator
from p3_usdms.repositories.base import BaseRepository
from p3_usdms.config import get_settings
from p3_usdms.routers.data import router as data_router
from p3_usdms.routers.admin import router as admin_router
from p3_usdms.routers.health import router as health_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# USDMS 필수 테이블 정의 (실제 us_ 스키마 테이블 매칭)
USDMS_EXPECTED_TABLES = [
    "us_ticker_master", "us_daily_price", "us_daily_valuation", "us_financial_facts",
    "us_financial_metrics", "us_price_adjustment_factors", "us_share_history",
    "us_standard_financials", "us_ticker_history", "us_collection_blacklist"
]

USDMS_MIN_ROW_COUNTS = {
    "us_daily_price": 100_000  # 로컬 검증 수준 (실제 13,969,437 rows 존재)
}

# 테스트용 Mock/생성 제어 함수
def create_kdms_pool():
    """테스트 모킹 호환을 위한 헬퍼 함수"""
    repo = BaseRepository()
    return repo._pool

async def scheduled_daily():
    from p3_usdms.routers.admin import is_routine_running, set_running_task
    if is_routine_running():
        logger.warning("Scheduled daily routine skipped because another routine is running.")
        return
    set_running_task("daily_routine")
    try:
        from p3_usdms.tasks.daily_routine import DailyRoutine
        routine = DailyRoutine()
        await routine.run()
    except Exception as e:
        logger.error(f"Scheduled daily routine failed: {e}")
    finally:
        set_running_task(None)

async def scheduled_financial():
    from p3_usdms.routers.admin import is_routine_running, set_running_task
    if is_routine_running():
        logger.warning("Scheduled financial routine skipped because another routine is running.")
        return
    set_running_task("us_financial")
    try:
        from p3_usdms.tasks.us_financial_routine import UsFinancialRoutine
        routine = UsFinancialRoutine()
        await routine.run()
    except Exception as e:
        logger.error(f"Scheduled financial routine failed: {e}")
    finally:
        set_running_task(None)

def scheduled_weekly():
    from p3_usdms.routers.admin import is_routine_running, set_running_task
    if is_routine_running():
        logger.warning("Scheduled weekly backfill skipped because another routine is running.")
        return
    set_running_task("weekly_backfill")
    try:
        from p3_usdms.tasks.daily_routine import DailyRoutine
        routine = DailyRoutine()
        routine.run_weekly_backfill()
    except Exception as e:
        logger.error(f"Scheduled weekly backfill failed: {e}")
    finally:
        set_running_task(None)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. 로컬 파일 로깅 설정 (서버 기동 로그 및 일상 로그가 파일에 남아 모니터링 보드 진입 시 복구 가능하게 지원)
    import sys
    import os
    from zoneinfo import ZoneInfo
    from datetime import datetime
    
    class KstFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=ZoneInfo("Asia/Seoul"))
            if datefmt:
                return dt.strftime(datefmt)
            else:
                return dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    settings = get_settings()
    logs_dir = settings.LOG_DIR
    os.makedirs(logs_dir, exist_ok=True)
    is_test = os.environ.get("TDMS_ENV") == "test" or "pytest" in sys.modules
    log_filename = "daily_routine_test.log" if is_test else "daily_routine.log"
    log_file_path = os.path.join(logs_dir, log_filename)
    
    file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(KstFormatter("[%(asctime)s] %(levelname)s - %(message)s"))
    file_handler.setLevel(logging.INFO)
    
    logger.setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)

    # 1. DSN 기반 DB 커넥션 풀 기동
    pool = create_kdms_pool()
    app.state.pool = pool
    
    # 2. StartupValidator 기동 유효성 검증
    validator = StartupValidator(pool, backup_manager=None)
    report = validator.validate(
        db_name="usdms",
        expected_tables=USDMS_EXPECTED_TABLES,
        min_row_counts=USDMS_MIN_ROW_COUNTS
    )
    
    if not report.is_healthy:
        raise RuntimeError(f"USDMS DB 기동 검증 실패: {report.missing_tables} / {report.low_row_tables}")
        
    scheduler = AsyncIOScheduler(
        timezone="Asia/Seoul",
        job_defaults={
            "misfire_grace_time": 900,   # 15분 유예 (찰나의 지터는 허용하고 과도한 지연 기동은 방지)
            "coalesce": True,            # 동일 작업 누적 시 1회만 병합 실행
            "max_instances": 1           # 중복 동시 실행 철저 제한
        }
    )
    
    settings = get_settings()
    from p1_shared.utils.schedule_utils import parse_schedule_string
    
    # 3.1. 일일 수집 실행 일정 등록
    try:
        daily_h, daily_m, daily_days = parse_schedule_string(
            settings.SCHEDULE_USDMS_DAILY_ROUTINE,
            default_days="tue-sat"
        )
        scheduler.add_job(
            scheduled_daily, 
            "cron", 
            day_of_week=daily_days, 
            hour=daily_h, 
            minute=daily_m, 
            id="daily_collection_job"
        )
    except Exception as e:
        logger.warning(f"SCHEDULE_USDMS_DAILY_ROUTINE parsing failed, falling back to tue-sat 07:30. Error: {e}")
        scheduler.add_job(
            scheduled_daily, 
            "cron", 
            day_of_week="tue-sat", 
            hour=7, 
            minute=30, 
            id="daily_collection_job"
        )
        
    # 3.2. 주간 백필 및 유지관리 실행 일정 등록
    try:
        weekly_h, weekly_m, weekly_days = parse_schedule_string(
            settings.SCHEDULE_USDMS_WEEKLY_MAINTENANCE,
            default_days="sat"
        )
        scheduler.add_job(
            scheduled_weekly,
            "cron",
            day_of_week=weekly_days,
            hour=weekly_h,
            minute=weekly_m,
            id="weekly_maintenance_job"
        )
    except Exception as e:
        logger.warning(f"SCHEDULE_USDMS_WEEKLY_MAINTENANCE parsing failed, falling back to sat 09:00. Error: {e}")
        scheduler.add_job(
            scheduled_weekly,
            "cron",
            day_of_week="sat",
            hour=9,
            minute=0,
            id="weekly_maintenance_job"
        )

    # 3.3. 재무 및 가치평가 수집 실행 일정 등록
    try:
        financial_h, financial_m, financial_days = parse_schedule_string(
            settings.SCHEDULE_USDMS_FINANCIAL_ROUTINE,
            default_days="wed,sat"
        )
        scheduler.add_job(
            scheduled_financial, 
            "cron", 
            day_of_week=financial_days, 
            hour=financial_h, 
            minute=financial_m, 
            id="financial_collection_job"
        )
    except Exception as e:
        logger.warning(f"SCHEDULE_USDMS_FINANCIAL_ROUTINE parsing failed, falling back to wed,sat 15:00. Error: {e}")
        scheduler.add_job(
            scheduled_financial, 
            "cron", 
            day_of_week="wed,sat", 
            hour=15, 
            minute=0, 
            id="financial_collection_job"
        )


    
    # 개발 PC(dev)인 경우 기동 시 스케줄을 일시정지 상태로 시작
    from p1_shared.utils.env_detector import EnvDetector
    try:
        env = EnvDetector().detect()
    except Exception:
        env = "unknown"
        
    if env == "dev":
        jobs = scheduler.get_jobs()
        if isinstance(jobs, list):
            for job in jobs:
                job.pause()
                logger.info(f"[DEV ENV] Paused job '{job.id}' on startup.")

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("APScheduler started: daily collection and weekly maintenance jobs registered successfully.")
    
    yield
    
    # 4. 종료 시 스케줄러 및 커넥션 정리
    scheduler.shutdown()
    if pool:
        pool.close_all()

app = FastAPI(lifespan=lifespan)
app.include_router(data_router)
app.include_router(admin_router)
app.include_router(health_router)

@app.get("/")
def read_root():
    return {"message": "USDMS API is running"}

