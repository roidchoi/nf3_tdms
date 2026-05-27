import logging
from datetime import datetime, date, timedelta
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
from tasks.backfill_task import run_backfill_minute_data

task_map = {
    "daily_update": run_daily_update,
    "financial_update": run_financial_update,
    "backfill_minute_data": run_backfill_minute_data,
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
        # 비동기적으로 스케줄러에 단발성 작업 추가
        if task_id == "backfill_market_cap":
            scheduler.add_job(
                func=lambda: task_func(
                    job_statuses=job_statuses,
                    test_mode=test_mode,
                    start_date=parsed_start,
                    end_date=parsed_end
                ),
                trigger="date",
                run_date=datetime.now(),
                id=f"manual_run_{task_id}_{datetime.now().timestamp()}",
                name=task_id
            )
        else:
            scheduler.add_job(
                func=lambda: task_func(job_statuses, test_mode=test_mode),
                trigger="date",
                run_date=datetime.now(),
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

