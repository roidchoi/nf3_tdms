import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["admin"])

# 전역 상태 및 스케줄러 객체 (main.py lifespan 에서 주입)
job_statuses: Dict[str, Any] = {}
scheduler: AsyncIOScheduler = None


class TaskRunRequest(BaseModel):
    test_mode: bool = Field(default=False, description="테스트 모드 실행 여부")


def trigger_backfill_market_cap(job_statuses: Dict[str, Any], test_mode: bool = False, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """시가총액 백필 작업을 격리 실행하는 래퍼 함수"""
    import os
    from collectors.pub_data_client import PubDataClient
    from repositories.market_cap_repo import MarketCapRepo
    from repositories.base import create_kdms_pool
    from p1_shared.utils.env_detector import EnvDetector
    from tasks.backfill_task import run_backfill_market_cap

    # 1. API 키 및 설정 가져오기
    detector = EnvDetector()
    profile = detector.load_env_profile()
    api_key = profile.get("pub_data_api_key") or os.environ.get("PUB_DATA_API_KEY", "")
    
    if not api_key:
        if test_mode:
            api_key = "mock_api_key"
        else:
            raise ValueError("환경설정에 PUB_DATA_API_KEY가 없습니다.")

    # 2. 리포지토리 및 의존성 주입
    pool = create_kdms_pool()
    mc_repo = MarketCapRepo(pool)
    pub_client = PubDataClient(api_key=api_key)

    # 3. 날짜 범위 기본값 설정
    if start_date is None:
        start_date = date.today() - timedelta(days=30)
    if end_date is None:
        end_date = date.today() - timedelta(days=1)

    # 4. 백필 작업 기동
    run_backfill_market_cap(
        job_statuses=job_statuses,
        pub_client=pub_client,
        mc_repo=mc_repo,
        start_date=start_date,
        end_date=end_date
    )


# 수동 기동 가능한 태스크 맵 정의
from tasks.daily_task import run_daily_update
from tasks.financial_task import run_financial_update
from tasks.backfill_task import run_backfill_minute_data, run_backfill_daily_data

task_map = {
    "daily_update": run_daily_update,
    "financial_update": run_financial_update,
    "backfill_minute_data": run_backfill_minute_data,
    "backfill_daily_data": run_backfill_daily_data,
    "backfill_market_cap": trigger_backfill_market_cap
}

VALID_TASK_IDS = list(task_map.keys())


@router.get("/status", summary="모든 백그라운드 태스크 상태 조회")
async def get_all_task_statuses():
    """
    현재 등록되어 수행되거나 완료된 모든 배치 작업 상태를 반환합니다.
    """
    return job_statuses


@router.post("/{task_id}/run", summary="백그라운드 태스크 수동 실행")
async def run_task(
    task_id: str,
    request: Optional[TaskRunRequest] = None,
    start_date: Optional[str] = Query(None, description="백필 시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="백필 종료 날짜 (YYYY-MM-DD)")
):
    """
    태스크를 스케줄러의 백그라운드 스레드 풀에서 즉시 1회 실행합니다. (Non-Blocking)
    """
    if task_id not in VALID_TASK_IDS:
        raise HTTPException(status_code=404, detail=f"유효하지 않은 Task ID입니다. 사용 가능: {VALID_TASK_IDS}")

    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 정상적으로 기동되지 않았습니다.")

    # 실행 중 중복 방지
    if job_statuses.get(task_id, {}).get("is_running", False):
        raise HTTPException(status_code=409, detail=f"태스크 '{task_id}'가 이미 실행 중입니다.")

    test_mode = request.test_mode if request else False

    # 날짜 범위 파싱
    parsed_start = None
    parsed_end = None
    try:
        if start_date:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 포맷이 잘못되었습니다. YYYY-MM-DD를 사용하십시오.")

    task_func = task_map[task_id]

    try:
        # 비동기적으로 스케줄러에 단발성 작업 추가 (KST timezone-aware 미래 시점으로 즉시 실행 보장)
        current_time = datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(seconds=5)
        if task_id in ["backfill_market_cap", "backfill_minute_data", "backfill_daily_data"]:
            scheduler.add_job(
                func=lambda: task_func(
                    job_statuses=job_statuses,
                    test_mode=test_mode,
                    start_date=parsed_start,
                    end_date=parsed_end
                ),
                trigger="date",
                run_date=current_time,
                misfire_grace_time=900,
                id=f"manual_run_{task_id}_{datetime.now().timestamp()}",
                name=task_id
            )
        else:
            if task_id == "financial_update":
                scheduler.add_job(
                    func=lambda: task_func(job_statuses, test_mode=test_mode, target_group=-1),
                    trigger="date",
                    run_date=current_time,
                    misfire_grace_time=900,
                    id=f"manual_run_{task_id}_{datetime.now().timestamp()}",
                    name=task_id
                )
            else:
                scheduler.add_job(
                    func=lambda: task_func(job_statuses, test_mode=test_mode),
                    trigger="date",
                    run_date=current_time,
                    misfire_grace_time=900,
                    id=f"manual_run_{task_id}_{datetime.now().timestamp()}",
                    name=task_id
                )

        logger.info(f"수동 실행 요청 완료: '{task_id}' 등록 완료 (Test Mode: {test_mode})")
        return {
            "status": "triggered",
            "task_id": task_id,
            "test_mode": test_mode,
            "status_endpoint": "/api/v1/admin/tasks/status"
        }
    except Exception as e:
        logger.error(f"수동 작업 등록 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"수동 작업 기동에 실패했습니다: {str(e)}")


@router.get("/scheduler", summary="스케줄러 정보 및 등록된 작업 목록 조회")
async def get_scheduler_info():
    """스케줄러의 구동 상태 및 등록된 모든 cron/manual job들의 상세 목록을 반환합니다."""
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 정상적으로 기동되지 않았습니다.")
        
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
        
    return {
        "is_running": scheduler.running,
        "jobs_count": len(jobs),
        "jobs": jobs
    }


@router.post("/scheduler/{job_id}/toggle", summary="스케줄러 작업 일시정지 또는 재개")
async def toggle_job(
    job_id: str,
    action: str = Query(..., description="작업 ('pause' 또는 'resume')")
):
    """특정 작업(job_id)을 일시 정지(pause) 또는 재개(resume)합니다."""
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 정상적으로 기동되지 않았습니다.")
        
    if action not in ["pause", "resume"]:
        raise HTTPException(status_code=400, detail="action 파라미터는 'pause' 또는 'resume'이어야 합니다.")
        
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"작업 '{job_id}'을 찾을 수 없습니다.")
        
    try:
        if action == "pause":
            job.pause()
            logger.info(f"스케줄러 작업 일시 정지 완료: {job_id}")
            return {"status": "PAUSED", "job_id": job_id}
        elif action == "resume":
            job.resume()
            logger.info(f"스케줄러 작업 재개 완료: {job_id}")
            return {"status": "RESUMED", "job_id": job_id}
    except Exception as e:
        logger.error(f"스케줄러 작업 상태 변경 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"작업 상태 변경에 실패했습니다: {str(e)}")


@router.put("/scheduler", summary="스케줄러 작업 실행 시간 변경")
async def reschedule_job(
    job_id: str,
    hour: int,
    minute: int,
    day_of_week: Optional[str] = Query(None, description="요일 설정 (예: 'mon-fri', 'wed,sat' 등)")
):
    """
    특정 작업(job_id)의 매일 실행 시간(hour, minute) 및 요일(day_of_week)을 동적으로 변경(reschedule)하며,
    .env 파일의 스케줄 설정도 영구 보존 업데이트합니다.
    """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 정상적으로 기동되지 않았습니다.")
        
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"작업 '{job_id}'을 찾을 수 없습니다.")

    # job_id에 대응하는 .env 변수명 설정
    var_map = {
        "daily_update": "SCHEDULE_KDMS_DAILY_UPDATE",
        "financial_update": "SCHEDULE_KDMS_FINANCIAL_UPDATE",
        "backfill_minute_data": "SCHEDULE_KDMS_BACKFILL_MINUTE"
    }
    
    var_name = var_map.get(job_id)
    
    try:
        if day_of_week:
            new_time_str = f"{day_of_week}:{hour:02d}:{minute:02d}"
        else:
            new_time_str = f"{hour:02d}:{minute:02d}"
        
        # 1. .env 파일 및 os.environ 업데이트
        if var_name:
            from p1_shared.utils.schedule_utils import update_env_value, parse_schedule_string
            import os
            update_env_value(var_name, new_time_str)
            
            # 2. 업데이트된 값에서 요일 정보 등을 다시 읽어 스케줄러 갱신
            updated_val = os.environ.get(var_name, new_time_str)
            h, m, parsed_dow = parse_schedule_string(updated_val)
            
            scheduler.reschedule_job(job_id, trigger="cron", day_of_week=parsed_dow, hour=h, minute=m)
            logger.info(f"스케줄러 작업 일정 변경 완료: {job_id} -> {updated_val}")
        else:
            # 매핑 변수가 없는 특수 job의 경우 기존 방식 적용
            scheduler.reschedule_job(job_id, trigger="cron", day_of_week=day_of_week, hour=hour, minute=minute)
            logger.info(f"스케줄러 작업 일정 변경 완료: {job_id} -> {new_time_str}")
            
        return {"status": "SUCCESS", "job_id": job_id, "hour": hour, "minute": minute, "day_of_week": day_of_week}
    except Exception as e:
        logger.error(f"스케줄러 일정 변경 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"스케줄 일정 변경에 실패했습니다: {str(e)}")


@router.post("/scheduler/reload", summary="환경설정(.env)에서 스케줄을 다시 읽어 스케줄러 갱신")
async def reload_scheduler_from_env():
    """
    물리 .env 파일을 다시 읽고, os.environ 갱신 후 
    스케줄러에 등록된 각 작업들의 일정을 동적으로 갱신합니다.
    """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 작동 중이 아닙니다.")
        
    try:
        from dotenv import load_dotenv
        import os
        from p1_shared.utils.schedule_utils import parse_schedule_string
        
        # 1. .env 파일 강제 덮어쓰기 로드 (override=True)
        env_path = "/app/.env" if os.path.exists("/app/.env") else None
        load_dotenv(dotenv_path=env_path, override=True)
        
        # 2. 각 작업의 설정 키 갱신
        var_map = {
            "daily_update": ("SCHEDULE_KDMS_DAILY_UPDATE", "mon-fri"),
            "financial_update": ("SCHEDULE_KDMS_FINANCIAL_UPDATE", None),
            "backfill_minute_data": ("SCHEDULE_KDMS_BACKFILL_MINUTE", "sat")
        }
        
        updated_jobs = []
        for job_id, (env_key, default_days) in var_map.items():
            job = scheduler.get_job(job_id)
            if not job:
                continue
            
            val = os.environ.get(env_key)
            if not val:
                continue
                
            h, m, day_of_week = parse_schedule_string(val, default_days=default_days)
            scheduler.reschedule_job(job_id, trigger="cron", day_of_week=day_of_week, hour=h, minute=m)
            updated_jobs.append({"job_id": job_id, "schedule": val})
            
        logger.info(f"스케줄러 .env 재로드 완료: {updated_jobs}")
        return {"status": "SUCCESS", "updated_jobs": updated_jobs}
    except Exception as e:
        logger.error(f"스케줄러 .env 재로드 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"스케줄 재로드 실패: {str(e)}")



