#
# main.py
#
import logging
import asyncio # (신규) WebSocket 큐를 위한 임포트
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# (수정) BackgroundScheduler -> AsyncIOScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler 
from contextlib import asynccontextmanager

# (신규) WebSocket 로깅 유틸리티
from log_utils import setup_websocket_logging, PollingLogFilter

# API 라우터 임포트
from routers import admin, data, health, debug # (신규) debug 라우터 임포트
# 백그라운드 태스크 임포트
from tasks import daily_task, financial_task, backfill_task # (신규) backfill_task 임포트

# --- PRD 8.2.2 전역 DB 매니저 생성 ---
from collectors.db_manager import DatabaseManager
db_manager = DatabaseManager()

# --- (신규) PRD 4.1.4: WebSocket 로그 스트리밍 큐 ---
# admin.py의 /logs/ws가 구독할 비동기 큐
log_queue = asyncio.Queue(maxsize=1000)

# --- 전역 상태 관리 (PRD 4.1.1) ---
job_statuses = {
    "daily_update": {"is_running": False, "last_status": "none"},
    "financial_update": {"is_running": False, "last_status": "none"},
    # (신규) backfill_task 상태 추가
    "backfill_minute_data": {"is_running": False, "last_status": "none"}
}

# --- APScheduler 설정 ---
# (수정) AsyncIOScheduler로 변경
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

# --- FastAPI 라이프사이클 이벤트 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === 애플리케이션 시작 ===
    logging.info("🚀 KDMS 통합 서버 시작 (Async Mode)")
    logging.getLogger("uvicorn.access").addFilter(PollingLogFilter())
    
    # (신규) PRD 4.1.4: WebSocket 로깅 핸들러 설정
    # (반드시 스케줄러 주입보다 먼저 설정되어야 함)
    setup_websocket_logging(log_queue)
 
    # PRD 4.1.3: 라우터에 전역 객체 주입
    admin.job_statuses = job_statuses
    admin.scheduler = scheduler
    admin.db = db_manager 
    admin.log_queue = log_queue # (신규) admin에 로그 큐 주입
    
    data.db = db_manager
    
    health.db = db_manager # (신규) health 라우터에 DB 인스턴스 주입
    # -----------------------------------

    # 기본 스케줄 등록 (PRD 4.1.1)
    # (모든 func이 job_statuses를 받도록 수정됨)
    scheduler.add_job(
        func=lambda: daily_task.run_daily_update(job_statuses, test_mode=False),
        trigger='cron',
        day_of_week='mon-fri',
        hour=17,
        minute=10,
        id='daily_update_schedule',
        name='daily_update', # (task_id와 일치시킴)
        misfire_grace_time=60  # 지연 실행 허용 시간(초)
    )
    scheduler.add_job(
        func=lambda: financial_task.run_financial_update(job_statuses, test_mode=False),
        trigger='cron',
        day_of_week='sat',
        hour=9,
        minute=0,
        id='financial_update_schedule',
        name='financial_update', # (task_id와 일치시킴)
        misfire_grace_time=60  # 지연 실행 허용 시간(초)
    )
    # (신규) 백필 스케줄 추가 (매주 토요일 10:20)
    scheduler.add_job(
        func=lambda: backfill_task.run_backfill_minute_data(job_statuses, test_mode=False),
        trigger='cron',
        day_of_week='sat',
        hour=10,
        minute=20,
        id='backfill_schedule',
        name='backfill_minute_data', # (task_id와 일치시킴)
        misfire_grace_time=60  # 지연 실행 허용 시간(초)
    )
    
    if not scheduler.running:
        scheduler.start()
        
    logging.info(f"📅 등록된 스케줄: {len(scheduler.get_jobs())}개")
    yield
    # === 애플리케이션 종료 ===
    if scheduler.running:
        scheduler.shutdown()
    if db_manager.pool:
        db_manager.pool.closeall()
        
    logging.info("🛑 KDMS 통합 서버 종료")

# --- FastAPI 앱 초기화 ---
app = FastAPI(
    title="KDMS API",
    version="6.0",
    description="한국 주식 데이터 수집 및 관리 시스템 (PRD v6.0 기반)",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- 라우터 마운트 (PRD 4.1.1) ---
app.include_router(admin.router, prefix="/api/v1/admin", tags=["운영/관리"])
app.include_router(data.router, prefix="/api/v1/data", tags=["데이터 제공"])
# (신규) health 라우터 마운트
app.include_router(health.router, prefix="/api/v1/health", tags=["데이터 품질"])
# (신규) debug 라우터 마운트
app.include_router(debug.router, prefix="/api/v1/debug", tags=["API 진단"])

@app.get("/")
def root():
    return {
        "message": "KDMS API v6.0",
        "docs": "/docs",
        "available_routes": {
            "admin": "/api/v1/admin",
            "data": "/api/v1/data",
            "health": "/api/v1/health",
            "debug": "/api/v1/debug"
        }
    }

# 로깅 설정 (기본 레벨)
logging.basicConfig(level=logging.INFO)