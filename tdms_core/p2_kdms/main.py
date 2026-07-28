from contextlib import asynccontextmanager
import os
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

# 전역 작업 상태 관리 (파일 영구화 적용)
from utils.persistent_dict import FilePersistentDict

default_statuses = {
    "daily_update": {"is_running": False, "last_status": "none"},
    "financial_update": {"is_running": False, "last_status": "none"},
    "backfill_minute_data": {"is_running": False, "last_status": "none"},
    "backfill_market_cap": {"is_running": False, "last_status": "none"}
}
cache_dir = "/app/logs" if os.path.exists("/app") else "logs"
cache_path = os.path.join(cache_dir, "task_status_cache.json")
job_statuses = FilePersistentDict(cache_path, default_statuses)

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
    
    scheduler = AsyncIOScheduler(
        timezone="Asia/Seoul",
        job_defaults={
            "misfire_grace_time": 900,   # 15분 유예 (찰나의 지터는 허용하고 과도한 지연 기동은 방지)
            "coalesce": True,            # 동일 작업 누적 시 1회만 병합 실행
            "max_instances": 1           # 중복 동시 실행 철저 제한
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
    
    # 로컬 파일 로깅 설정 (실시간이 아닐 때도 로그가 파일에 남아 모니터링 보드 진입 시 복구 가능하게 지원)
    import sys
    import os
    logs_dir = settings.log_dir
    os.makedirs(logs_dir, exist_ok=True)
    is_test = os.environ.get("TDMS_ENV") == "test" or "pytest" in sys.modules
    log_filename = "daily_update_test.log" if is_test else "daily_update.log"
    log_file_path = os.path.join(logs_dir, log_filename)
    
    file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(KstFormatter("[%(asctime)s] %(levelname)s - %(message)s"))
    file_handler.setLevel(logging.INFO)
    
    # INFO 레벨 이상의 로그를 정상 포착하도록 로거 및 핸들러 레벨 명시적 상향
    websocket_handler.setLevel(logging.INFO)
    logger.setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.INFO)
    
    logging.getLogger().addHandler(websocket_handler)
    logging.getLogger().addHandler(file_handler)

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
    
    # 1. 파일에서 이전 로그 기록이 있으면 마지막 100라인 전송하여 모니터링 보드 진입 시 복구되도록 지원 (tail -f 유사 구현)
    import os
    from config import settings
    logs_dir = settings.log_dir
    log_file_path = os.path.join(logs_dir, "daily_update.log")
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-100:]:
                    await websocket.send_text(line.strip())
        except Exception as e:
            # 로깅 핸들러가 연결되기 전이거나 모듈 내부 로거 사용
            print(f"Failed to pre-stream log file: {e}")

    # 2. 실시간 로그 브로드캐스터 연동
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




