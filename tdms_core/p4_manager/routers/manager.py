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


# =================================================================
# 4. 공통 헬스 모니터링 중계 및 장애 격리 API
# =================================================================

@router.get("/health/freshness/{market}")
async def get_integrated_freshness(market: str):
    """
    시장(kr/us)별 수집 신선도(Freshness)를 중계 조회합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    url = (
        "http://p2_kdms:8000/api/health/freshness"
        if market == "kr"
        else "http://p3_usdms:8005/api/health/freshness"
    )
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return {"status": "RED", "offline": True, "message": f"Backend returned status {resp.status_code}"}
        except Exception as e:
            return {"status": "RED", "offline": True, "message": f"Backend communication error: {str(e)}"}


@router.get("/health/gaps/{market}")
async def get_integrated_gaps(
    market: str,
    start_date: str = Query(None),
    end_date: str = Query(None)
):
    """
    시장(kr/us)별 수집 누락 갭을 중계 조회하고 단일 규격으로 정규화합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    url = (
        "http://p2_kdms:8000/api/health/gaps"
        if market == "kr"
        else "http://p3_usdms:8005/api/health/gaps"
    )
    
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=5.0)
            if resp.status_code != 200:
                return {
                    "market": market,
                    "start_date": start_date or "",
                    "end_date": end_date or "",
                    "gaps": [],
                    "offline": True,
                    "message": f"Backend returned status {resp.status_code}"
                }
                
            raw_data = resp.json()
            standardized_gaps = []
            
            # minute_gaps 배열 파싱
            minute_gaps = raw_data.get("minute_gaps", [])
            for mg in minute_gaps:
                if market == "kr":
                    standardized_gaps.append({
                        "date": mg.get("date"),
                        "status": mg.get("status", "GREEN"),
                        "total_targets": mg.get("total_targets", 0),
                        "valid_targets": mg.get("valid_targets", 0),
                        "missing_count": mg.get("missing_stocks_count", 0),
                        "missing_items": mg.get("missing_stocks", [])
                    })
                else:
                    standardized_gaps.append({
                        "date": mg.get("date"),
                        "status": "YELLOW" if mg.get("gaps_count", 0) > 0 else "GREEN",
                        "total_targets": mg.get("total_targets", 0),
                        "valid_targets": mg.get("valid_targets", 0),
                        "missing_count": mg.get("gaps_count", 0),
                        "missing_items": []  # 미국은 티커 목록 미제공
                    })
                    
            return {
                "market": market,
                "start_date": raw_data.get("start_date", start_date or ""),
                "end_date": raw_data.get("end_date", end_date or ""),
                "gaps": standardized_gaps
            }
            
        except Exception as e:
            return {
                "market": market,
                "start_date": start_date or "",
                "end_date": end_date or "",
                "gaps": [],
                "offline": True,
                "message": f"Backend communication error: {str(e)}"
            }


@router.get("/health/kr/milestones")
async def get_kr_milestones():
    """
    [KR 전용] 한국 마케팅 마일스톤 이력 조회 중계
    """
    url = "http://p2_kdms:8000/api/health/milestones"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []


@router.post("/health/kr/milestones")
async def post_kr_milestone(payload: dict):
    """
    [KR 전용] 한국 마케팅 마일스톤 생성/수정 중계
    """
    url = "http://p2_kdms:8000/api/health/milestones"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"KDMS 백엔드 연결 오류: {str(e)}")


@router.get("/health/us/blacklist")
async def get_us_blacklist():
    """
    [US 전용] 미국 차단 종목(블랙리스트) 목록 조회 중계
    """
    url = "http://p3_usdms:8005/api/health/blacklist"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "blocked_count": 0, "blacklist": [], "offline": True}
        except Exception:
            return {"status": "error", "blocked_count": 0, "blacklist": [], "offline": True}


@router.post("/health/us/blacklist/{cik}/release")
async def release_us_blacklist(cik: str):
    """
    [US 전용] 미국 특정 CIK 차단 해제 중계
    """
    url = f"http://p3_usdms:8005/api/health/blacklist/{cik}/release"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"USDMS 백엔드 연결 오류: {str(e)}")

