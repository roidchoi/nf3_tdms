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
    scheduler = AsyncIOScheduler(
        timezone="Asia/Seoul",
        job_defaults={
            "misfire_grace_time": 36000  # 10시간 유예 (KST/UTC 타임존 차이로 인한 기동 실패 방지)
        }
    )
    
    import routers.admin as admin_module
    admin_module.scheduler = scheduler
    admin_module.job_statuses = job_statuses

    # 4.1. 크론 작업 등록
    from tasks.daily_task import run_daily_update
    from tasks.financial_task import run_financial_update
    from tasks.backfill_task import run_backfill_minute_data
    from config import settings
    from p1_shared.utils.schedule_utils import parse_schedule_string
    import logging

    logger = logging.getLogger("kdms")

    # 4.2. 실시간 로그 브로드캐스트 핸들러 연동
    from utils.log_broadcaster import log_broadcaster
    import asyncio

    try:
        app.state.main_loop = asyncio.get_running_loop()
    except RuntimeError:
        app.state.main_loop = None

    class KstFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dt = datetime.fromtimestamp(record.created, tz=ZoneInfo("Asia/Seoul"))
            if datefmt:
                return dt.strftime(datefmt)
            else:
                return dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    class WebSocketLogHandler(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(log_broadcaster.broadcast(msg))
                except RuntimeError:
                    # 이벤트 루프가 없는 백그라운드 스레드인 경우 메인 루프에 태스크 전송
                    if app.state.main_loop:
                        asyncio.run_coroutine_threadsafe(log_broadcaster.broadcast(msg), app.state.main_loop)
            except Exception:
                self.handleError(record)

    websocket_handler = WebSocketLogHandler()
    websocket_handler.setFormatter(KstFormatter("[%(asctime)s] %(levelname)s - %(message)s"))
    
    # INFO 레벨 이상의 로그를 정상 포착하도록 로거 및 핸들러 레벨 명시적 상향
    websocket_handler.setLevel(logging.INFO)
    logger.setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.INFO)
    
    logging.getLogger().addHandler(websocket_handler)
    logger.addHandler(websocket_handler)

    # 데일리 시세 & 시가총액 수집: settings.schedule_kdms_daily_update 로딩
    try:
        daily_h, daily_m, daily_days = parse_schedule_string(
            settings.schedule_kdms_daily_update, 
            default_days='mon-fri'
        )
        scheduler.add_job(
            func=lambda: run_daily_update(job_statuses, test_mode=False),
            trigger='cron',
            day_of_week=daily_days,
            hour=daily_h,
            minute=daily_m,
            id='daily_update',
            name='daily_update'
        )
    except Exception as e:
        logger.error(f"Failed to register daily_update schedule: {e}. Falling back to default (17:00, mon-fri)")
        scheduler.add_job(
            func=lambda: run_daily_update(job_statuses, test_mode=False),
            trigger='cron',
            day_of_week='mon-fri',
            hour=17,
            minute=0,
            id='daily_update',
            name='daily_update'
        )

    # 분기 재무 데이터 갱신: settings.schedule_kdms_financial_update 로딩
    try:
        fin_h, fin_m, fin_days = parse_schedule_string(
            settings.schedule_kdms_financial_update, 
            default_days=None
        )
        scheduler.add_job(
            func=lambda: run_financial_update(job_statuses, test_mode=False),
            trigger='cron',
            day_of_week=fin_days,
            hour=fin_h,
            minute=fin_m,
            id='financial_update',
            name='financial_update'
        )
    except Exception as e:
        logger.error(f"Failed to register financial_update schedule: {e}. Falling back to default (19:00)")
        scheduler.add_job(
            func=lambda: run_financial_update(job_statuses, test_mode=False),
            trigger='cron',
            hour=19,
            minute=0,
            id='financial_update',
            name='financial_update'
        )

    # 분봉 백필 태스크: settings.schedule_kdms_backfill_minute 로딩
    try:
        bf_h, bf_m, bf_days = parse_schedule_string(
            settings.schedule_kdms_backfill_minute,
            default_days='sat'
        )
        scheduler.add_job(
            func=lambda: run_backfill_minute_data(job_statuses, test_mode=False),
            trigger='cron',
            day_of_week=bf_days,
            hour=bf_h,
            minute=bf_m,
            id='backfill_minute_data',
            name='backfill_minute_data'
        )
    except Exception as e:
        logger.error(f"Failed to register backfill_minute_data schedule: {e}. Scheduling omitted.")



    # 스케줄러 시작
    scheduler.start()
    
    yield
    
    # 종료 시 정리
    scheduler.shutdown()
    pool.close_all()

app = FastAPI(lifespan=lifespan)

from routers.data import router as data_router
from routers.admin import router as admin_router
from routers.health import router as health_router

app.include_router(data_router)
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(health_router)

from fastapi import WebSocket, WebSocketDisconnect
from utils.log_broadcaster import log_broadcaster

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await log_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_broadcaster.disconnect(websocket)
    except Exception:
        log_broadcaster.disconnect(websocket)

@app.get("/")
def read_root():
    return {"message": "KDMS API is running"}




