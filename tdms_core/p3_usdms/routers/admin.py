# tdms_core/p3_usdms/routers/admin.py
import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request, Query

from p3_usdms.tasks.daily_routine import DailyRoutine

logger = logging.getLogger(__name__)

# APIRouter의 prefix를 /api/admin으로 조정 (기존 /api/admin/tasks 에서 변경)
router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])

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

async def _async_run_weekly():
    set_routine_running(True)
    try:
        routine = DailyRoutine()
        routine.run_weekly_backfill()
    except Exception as e:
        logger.error(f"Background WeeklyBackfill run encountered error: {e}")
    finally:
        set_routine_running(False)

# =================================================================
# 1. 태스크 수동 실행 API
# =================================================================

@router.post("/tasks/daily_routine/run")
async def run_daily_routine(background_tasks: BackgroundTasks):
    """
    일일 수집 파이프라인(Daily Routine)을 수동으로 비동기 백그라운드 기동합니다.
    """
    if is_routine_running():
        raise HTTPException(
            status_code=409,
            detail="The daily collection routine is already running."
        )
    background_tasks.add_task(_async_run_routine)
    return {"status": "SUBMITTED", "message": "Daily routine has been triggered in the background."}

@router.post("/tasks/weekly_backfill/run")
async def run_weekly_backfill(background_tasks: BackgroundTasks):
    """
    주간 백필 및 유지보수 파이프라인을 백그라운드로 기동합니다.
    """
    if is_routine_running():
        raise HTTPException(
            status_code=409,
            detail="Another background routine is already running."
        )
    background_tasks.add_task(_async_run_weekly)
    return {"status": "SUBMITTED", "message": "Weekly backfill has been triggered in the background."}

# =================================================================
# 2. 태스크 실행 이력 조회 API
# =================================================================

@router.get("/tasks/status")
def get_tasks_status() -> List[Dict[str, Any]]:
    """
    logs/ 디렉토리에 적재된 daily_routine_*.json 및 weekly_backfill_*.json 파일 목록을
    역순으로 조회하여 최근 10건의 실행 이력 리포트 리스트를 반환합니다.
    """
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        return []
        
    log_files = []
    for f in os.listdir(logs_dir):
        if f.endswith(".json") and (f.startswith("daily_routine_") or f.startswith("weekly_backfill_")):
            log_files.append(f)
            
    # 파일명 역순 정렬 (타임스탬프 기반 최신순)
    log_files.sort(reverse=True)
    
    reports = []
    for f in log_files[:10]:
        file_path = os.path.join(logs_dir, f)
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                reports.append(data)
        except Exception as e:
            logger.warning(f"Failed to read/parse report file {f}: {e}")
            reports.append({"file_name": f, "status": "ERROR", "error": str(e)})
            
    return reports

# =================================================================
# 3. 스케줄러 동적 제어 API
# =================================================================

@router.get("/schedules")
def get_schedules(request: Request) -> List[Dict[str, Any]]:
    """
    FastAPI app.state에 등록된 APScheduler 객체로부터 
    현재 등록된 크론 작업들의 ID, 크론 표현식, 다음 실행 예정 시각을 조회합니다.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler is not running or not registered.")
        
    jobs = scheduler.get_jobs()
    jobs_info = []
    for job in jobs:
        trigger_info = {}
        if hasattr(job.trigger, "fields"):
            # CronTrigger 필드 값 추출
            for field in job.trigger.fields:
                trigger_info[field.name] = str(field)
                
        jobs_info.append({
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": trigger_info or str(job.trigger)
        })
    return jobs_info

@router.put("/schedules")
def update_schedule(
    job_id: str,
    hour: int,
    minute: int,
    request: Request
) -> Dict[str, Any]:
    """
    특정 스케줄 작업(예: daily_collection_job)의 실행 시각을 동적으로 변경합니다.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler is not running or not registered.")
        
    try:
        scheduler.reschedule_job(job_id, trigger="cron", hour=hour, minute=minute)
        return {
            "status": "SUCCESS",
            "message": f"Successfully updated job {job_id} schedule to {hour:02d}:{minute:02d}."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reschedule job {job_id}: {str(e)}")


@router.post("/schedules/{job_id}/toggle", summary="스케줄러 작업 일시정지 또는 재개")
def toggle_job(
    job_id: str,
    request: Request,
    action: str = Query(..., description="작업 ('pause' 또는 'resume')")
) -> Dict[str, Any]:
    """
    특정 작업(job_id)을 일시 정지(pause) 또는 재개(resume)합니다.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler is not running or not registered.")
        
    if action not in ["pause", "resume"]:
        raise HTTPException(status_code=400, detail="Action must be 'pause' or 'resume'.")
        
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        
    try:
        if action == "pause":
            job.pause()
            logger.info(f"Successfully paused job {job_id}.")
            return {"status": "PAUSED", "job_id": job_id}
        elif action == "resume":
            job.resume()
            logger.info(f"Successfully resumed job {job_id}.")
            return {"status": "RESUMED", "job_id": job_id}
    except Exception as e:
        logger.error(f"Failed to toggle job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to change job state: {str(e)}")


# =================================================================
# 4. 실시간 로그 스트리밍 WebSocket
# =================================================================


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, log_file: Optional[str] = None):
    """
    WebSocket 연결을 승인하고, 최신 daily_routine 로그 파일(.log)을
    실시간으로 한 줄씩 스트리밍 전송합니다. (tail -f 방식 구현)
    """
    await websocket.accept()
    
    logs_dir = "logs"
    target_log_path = None
    
    if log_file:
        # 안전한 경로 검증 (logs 디렉토리 내에 있는 파일만 접근하도록 제한)
        safe_path = os.path.join(logs_dir, os.path.basename(log_file))
        if os.path.exists(safe_path):
            target_log_path = safe_path
    else:
        # logs/ 디렉토리 내에서 가장 최신의 daily_routine_*.log 또는 daily_routine.log 파일 탐색
        if os.path.exists(logs_dir):
            log_files = [f for f in os.listdir(logs_dir) if f.endswith(".log")]
            if log_files:
                log_files.sort(reverse=True)
                target_log_path = os.path.join(logs_dir, log_files[0])
                
    if not target_log_path or not os.path.exists(target_log_path):
        await websocket.send_text("No active log file found.")
        await websocket.close()
        return
        
    try:
        # 파일 핸들을 열고 tail -f 방식으로 비동기 실시간 스트리밍
        with open(target_log_path, "r", encoding="utf-8") as file:
            # 먼저 기존 로그 데이터 전체 혹은 마지막 100라인 전송
            lines = file.readlines()
            for line in lines[-100:]:
                await websocket.send_text(line.strip())
                
            # 파일 끝으로 이동 후 실시간 감시
            file.seek(0, os.SEEK_END)
            
            while True:
                line = file.readline()
                if not line:
                    await asyncio.sleep(0.5)
                    continue
                await websocket.send_text(line.strip())
    except WebSocketDisconnect:
        logger.info("WebSocket log client disconnected.")
    except Exception as e:
        logger.error(f"Error streaming logs over WebSocket: {e}")
        try:
            await websocket.send_text(f"Error: {str(e)}")
        except Exception:
            pass
