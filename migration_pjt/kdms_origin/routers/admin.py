#
# routers/admin.py
#
import logging
import asyncio
from fastapi import (
    APIRouter, HTTPException, Depends, Query, 
    WebSocket, WebSocketDisconnect
)
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- (수정) Phase 6.5: 비동기 스케줄러 임포트 ---
from apscheduler.schedulers.asyncio import AsyncIOScheduler #
from apscheduler.job import Job

# --- (수정) PRD 6.5: 모델 및 태스크 임포트 ---
from models.admin_models import TaskRunRequest, ScheduleCreateRequest, ScheduleUpdateRequest
# (backfill_task 추가)
from tasks import daily_task, financial_task, backfill_task 

router = APIRouter()
logger = logging.getLogger(__name__)

# --- 전역 객체 주입 (main.py에서 설정) ---
job_statuses: Dict[str, Any] = None
scheduler: AsyncIOScheduler = None # (BackgroundScheduler -> AsyncIOScheduler)
log_queue: asyncio.Queue = None # (신규) WebSocket 로그 큐
# -----------------------------------

# --- (신규) PRD 4.1.3: 태스크 맵 (backfill_task 포함) ---
task_map = {
    "daily_update": daily_task.run_daily_update,
    "financial_update": financial_task.run_financial_update,
    "backfill_minute_data": backfill_task.run_backfill_minute_data #
}
VALID_TASK_IDS = list(task_map.keys())


@router.get("/tasks/status", summary="[PRD 3.1.1] 모든 백그라운드 태스크 상태 조회")
async def get_all_task_statuses():
    """
    (기존 /status/live -> /tasks/status)
    [PRD 4.1.2] 전역 'job_statuses' 딕셔너리의 현재 상태를 반환합니다.
    (모든 엔드포인트를 async def로 변경)
    """
    if job_statuses is None:
        raise HTTPException(status_code=500, detail="상태 객체가 초기화되지 않았습니다.")
    
    return job_statuses


@router.post(
    "/tasks/{task_id}/run", 
    summary="[PRD 3.1.1] 백그라운드 태스크 수동 실행 (Non-Blocking)"
)
async def run_task(task_id: str, request: TaskRunRequest):
    """
    (수정) BackgroundTasks 대신 'scheduler.add_job' 사용
    
    [PRD 4.1.3] (위험) BackgroundTasks는 동기/무거운 작업을 실행하면
    FastAPI 이벤트 루프를 차단(Block)하여 서버가 멈춥니다.
    
    [PRD 3.1.1] (개선) 스케줄러의 스레드 풀에서 실행하도록 '즉시 실행' 작업을
    스케줄러에 등록합니다. (trigger='date')
    """
    if task_id not in VALID_TASK_IDS:
        raise HTTPException(status_code=404, detail=f"유효하지 않은 Task ID. 사용 가능: {VALID_TASK_IDS}")
        
    if scheduler is None or job_statuses is None:
        raise HTTPException(status_code=500, detail="스케줄러 또는 상태 객체가 초기화되지 않았습니다.")

    if job_statuses.get(task_id, {}).get("is_running", False):
        raise HTTPException(
            status_code=409, 
            detail=f"'{task_id}' 태스크가 이미 실행 중입니다."
        )

    try:
        task_func = task_map[task_id]
        
        # (수정) BackgroundTasks -> scheduler.add_job
        scheduler.add_job(
            func=lambda: task_func(job_statuses, test_mode=request.test_mode),
            trigger='date', # (즉시 1회 실행)
            run_date=datetime.now(),
            id=f"manual_run_{task_id}_{datetime.now().timestamp()}",
            name=f"수동 실행: {task_id} (Test: {request.test_mode})"
        )
        
        logger.info(f"[{task_id}] 수동 실행 요청 (Test Mode: {request.test_mode}). 스케줄러에 작업 추가됨.")
        return {
            "message": "작업 실행 요청 성공 (스케줄러에 등록)",
            "task_id": task_id,
            "test_mode": request.test_mode,
            "status_endpoint": "/api/v1/admin/tasks/status"
        }
        
    except Exception as e:
        logger.error(f"[{task_id}] 작업 실행 요청 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"작업 실행 요청 실패: {e}")


@router.get("/schedules", summary="[PRD 3.1.2] 스케줄 목록 조회")
async def get_schedules():
    """ (기존 코드와 동일, async def로 변경) """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러가 초기화되지 않았습니다.")

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "task_id": job.name,
            "trigger": str(job.trigger),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "is_paused": not job.next_run_time # (기존 로직)
        })
    return {"schedules": jobs}


@router.post("/schedules", summary="[PRD 3.1.2] 새 스케줄 등록")
async def create_schedule(request: ScheduleCreateRequest):
    """ (기존 코드와 동일, async def/task_map 확장) """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러가 초기화되지 않았습니다.")
    
    task_function = task_map.get(request.task_id)
    if not task_function:
        raise HTTPException(status_code=404, detail=f"태스크 '{request.task_id}'를 찾을 수 없습니다.")

    try:
        job = scheduler.add_job(
            func=lambda: task_function(job_statuses, test_mode=False),
            trigger=request.trigger,
            id=f"{request.task_id}_custom_{datetime.now().timestamp()}",
            name=request.task_id,
            **request.config
        )
        return {
            "message": "스케줄이 성공적으로 등록되었습니다.",
            "job_id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"스케줄 등록 실패: {e}")


@router.put("/schedules/{schedule_id}", summary="[PRD 3.1.2] 기존 스케줄 변경")
async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest):
    """ (기존 코드와 동일, async def로 변경) """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러가 초기화되지 않았습니다.")
    
    job: Job = scheduler.get_job(schedule_id)
    if not job:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")
    
    try:
        updated_job = scheduler.reschedule_job(
            job_id=schedule_id, 
            trigger='cron', 
            **request.config
        )
        return {
            "message": "스케줄이 성공적으로 변경되었습니다.",
            "job_id": updated_job.id,
            "next_run": updated_job.next_run_time.isoformat() if updated_job.next_run_time else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"스케줄 변경 실패: {e}")


@router.post("/schedules/{schedule_id}/toggle", summary="[PRD 3.1.2] 스케줄 활성화/비활성화")
async def toggle_schedule(schedule_id: str):
    """ (기존 코드와 동일, async def로 변경) """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러가 초기화되지 않았습니다.")
        
    job: Job = scheduler.get_job(schedule_id)
    if not job:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")

    is_paused = not job.next_run_time
    if is_paused:
        scheduler.resume_job(schedule_id)
        message = "스케줄이 활성화(resume)되었습니다."
        new_status = False
    else:
        scheduler.pause_job(schedule_id)
        message = "스케줄이 일시 중지(pause)되었습니다."
        new_status = True

    return { "schedule_id": schedule_id, "is_paused": new_status, "message": message }


@router.delete("/schedules/{schedule_id}", summary="[PRD 3.1.2] 스케줄 삭제")
async def delete_schedule(schedule_id: str):
    """ (기존 코드와 동일, async def로 변경) """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러가 초기화되지 않았습니다.")

    job: Job = scheduler.get_job(schedule_id)
    if not job:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")

    try:
        scheduler.remove_job(schedule_id)
        return { "message": "스케줄이 성공적으로 삭제되었습니다.", "job_id": schedule_id }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스케줄 삭제 실패: {e}")


# --- (신규) Phase 6.5: 실시간 로그 스트리밍 (PRD 3.1.2) ---
@router.websocket(
    "/logs/ws"
)
async def websocket_log_endpoint(websocket: WebSocket): #
    """
    [PRD 3.1.2] 실시간 로그 스트리밍 (WebSocket)
    
    (기존 @router.get -> @router.websocket으로 수정)
    [PRD 4.1.4] 'log_queue'의 내용을 WebSocket을 통해 실시간으로 스트리밍합니다.
    """
    if log_queue is None:
        await websocket.close(code=1008, reason="로그 큐가 초기화되지 않았습니다.")
        return

    await websocket.accept()
    logger.info("--- WebSocket 클라이언트 연결됨 ---")

    try:
        while True:
            # 큐에서 로그 메시지를 비동기적으로 대기
            log_message = await log_queue.get()
            await websocket.send_text(log_message)
            log_queue.task_done()
            
    except WebSocketDisconnect:
        logger.warning("--- WebSocket 클라이언트 연결 끊김 ---")
    except Exception as e:
        logger.error(f"WebSocket 오류 발생: {e}", exc_info=True)
        await websocket.close(code=1011, reason=f"서버 오류: {e}")
        