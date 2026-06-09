# tdms_core/p4_manager/routers/manager.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
from tdms_core.p4_manager.services.status_service import status_service

router = APIRouter()

@router.get("/status")
def get_integrated_status():
    """
    통합 대시보드 상태 집계 조회 API.
    캐시된 최신 KR/US 데이터를 즉시 반환.
    """
    return status_service.get_status()


@router.post("/run")
async def run_task(
    market: str = Query(..., description="시장 구분 (kr 또는 us)"),
    task_id: str = Query(..., description="실행할 태스크 식별자"),
    is_test: bool = Query(True, description="테스트 모드 여부 (한국 전용)")
):
    """
    통합 태스크 수동 실행 API.
    """
    try:
        result = await status_service.run_task(market=market, task_id=task_id, is_test=is_test)
        if result.get("status") == "error":
            raise HTTPException(status_code=502, detail=result["message"])
        return result
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": f"{market} backend offline",
                "details": str(e)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schedules/{market}")
async def get_integrated_schedules(market: str):
    """
    시장(kr/us)별 백엔드의 스케줄 정보를 통합 조회하여 단일 규격으로 파싱 반환합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    url = (
        "http://p2_kdms:8000/api/v1/admin/scheduler"
        if market == "kr"
        else "http://p3_usdms:8005/api/admin/schedules"
    )
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"{market.upper()} 백엔드 스케줄러 조회 오류: {resp.text}")
                
            raw_data = resp.json()
            standardized_jobs = []
            
            if market == "kr":
                jobs_list = raw_data.get("jobs", [])
                for job in jobs_list:
                    next_run = job.get("next_run_time")
                    standardized_jobs.append({
                        "job_id": job.get("id"),
                        "name": job.get("name"),
                        "next_run_time": next_run,
                        "trigger": job.get("trigger"),
                        "is_paused": next_run is None
                    })
            else:
                for job in raw_data:
                    next_run = job.get("next_run_time")
                    standardized_jobs.append({
                        "job_id": job.get("job_id"),
                        "name": job.get("name"),
                        "next_run_time": next_run,
                        "trigger": str(job.get("trigger")),
                        "is_paused": next_run is None
                    })
            return standardized_jobs
            
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"{market.upper()} 백엔드가 준비되지 않았습니다: {str(e)}")


@router.put("/schedules/{market}/{job_id}")
async def update_integrated_schedule(market: str, job_id: str, hour: int = Query(...), minute: int = Query(...)):
    """
    시장(kr/us)별 특정 스케줄 작업의 기동 시각을 수정합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    if market == "kr":
        url = f"http://p2_kdms:8000/api/v1/admin/scheduler?job_id={job_id}&hour={hour}&minute={minute}"
    else:
        url = f"http://p3_usdms:8005/api/admin/schedules?job_id={job_id}&hour={hour}&minute={minute}"
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.put(url, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"스케줄 변경 실패: {resp.text}")
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"{market.upper()} 백엔드 통신 실패: {str(e)}")


@router.post("/schedules/{market}/{job_id}/toggle")
async def toggle_integrated_schedule(market: str, job_id: str, action: str = Query(...)):
    """
    시장(kr/us)별 특정 스케줄 작업의 활성/비활성 상태를 토글(pause/resume)합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    if action not in ["pause", "resume"]:
        raise HTTPException(status_code=400, detail="action 파라미터는 'pause' 또는 'resume'이어야 합니다.")
        
    if market == "kr":
        url = f"http://p2_kdms:8000/api/v1/admin/scheduler/{job_id}/toggle?action={action}"
    else:
        url = f"http://p3_usdms:8005/api/admin/schedules/{job_id}/toggle?action={action}"
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"스케줄 토글 실패: {resp.text}")
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"{market.upper()} 백엔드 통신 실패: {str(e)}")
