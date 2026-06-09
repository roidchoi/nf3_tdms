# tdms_core/p4_manager/main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from tdms_core.p4_manager.config import settings
from tdms_core.p4_manager.routers import manager
from tdms_core.p4_manager.services.status_service import status_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("p4_manager.main")

async def poll_status_loop():
    logger.info("Background polling task started.")
    while True:
        try:
            await status_service.fetch_and_cache_status()
        except Exception as e:
            logger.error(f"Error in background polling status: {e}")
        await asyncio.sleep(settings.TASK_POLL_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await status_service.fetch_and_cache_status()
    except Exception as e:
        logger.error(f"Initial status fetch failed: {e}")
        
    polling_task = asyncio.create_task(poll_status_loop())
    yield
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        logger.info("Background polling task cancelled successfully.")

app = FastAPI(title="P4 Manager Backend", lifespan=lifespan)

app.include_router(manager.router, prefix="/api/mgr")

@app.get("/api/mgr/health")
def health_check():
    """
    p4 백엔드 상태를 반환하는 기본 헬스 체크 엔드포인트
    """
    return {"status": "ok", "service": "p4_backend"}
