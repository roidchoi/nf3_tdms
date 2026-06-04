import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from p3_usdms.tasks.daily_routine import DailyRoutine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tasks", tags=["Admin Tasks"])

# 전역 실행 잠금(Lock) 플래그
_is_running_flag = False

def is_routine_running() -> bool:
    """테스트 mocking 및 상태 판별을 위한 헬퍼 함수"""
    global _is_running_flag
    return _is_running_flag

def set_routine_running(status: bool) -> None:
    global _is_running_flag
    _is_running_flag = status

async def _async_run_routine():
    """백그라운드에서 실행할 일일 루틴 래퍼"""
    set_routine_running(True)
    try:
        routine = DailyRoutine()
        await routine.run()
    except Exception as e:
        logger.error(f"Background DailyRoutine run encountered error: {e}")
    finally:
        set_routine_running(False)

@router.post("/daily_routine/run")
async def run_daily_routine(background_tasks: BackgroundTasks):
    """
    일일 수집 파이프라인(Daily Routine)을 수동으로 비동기 백그라운드 기동합니다.
    동시 실행을 강제 제한하며, 구동 중인 경우 409 Conflict를 리턴합니다.
    """
    if is_routine_running():
        raise HTTPException(
            status_code=409,
            detail="The daily collection routine is already running."
        )

    # 백그라운드 태스크로 구동 위임
    background_tasks.add_task(_async_run_routine)
    return {"status": "SUBMITTED", "message": "Daily routine has been triggered in the background."}


@router.post("/weekly_backfill/run")
async def run_weekly_backfill(background_tasks: BackgroundTasks):
    """
    주간 백필 및 유지보수 파이프라인을 백그라운드로 기동합니다.
    """
    if is_routine_running():
        raise HTTPException(
            status_code=409,
            detail="Another background routine is already running."
        )

    async def _async_run_weekly():
        set_routine_running(True)
        try:
            routine = DailyRoutine()
            # run_weekly_backfill는 동기 함수이나 비동기 loop 상태를 판별하여 내부 async 호출 지원
            routine.run_weekly_backfill()
        except Exception as e:
            logger.error(f"Background WeeklyBackfill run encountered error: {e}")
        finally:
            set_routine_running(False)

    background_tasks.add_task(_async_run_weekly)
    return {"status": "SUBMITTED", "message": "Weekly backfill has been triggered in the background."}
