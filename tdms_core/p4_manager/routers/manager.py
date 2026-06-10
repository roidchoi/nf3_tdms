# tdms_core/p4_manager/routers/manager.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
from tdms_core.p4_manager.config import settings
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


# =================================================================
# 5. 데이터 익스플로러 테이블 미리보기 중계 API
# =================================================================

ALLOWED_TABLES_KR = {
    "stock_info",
    "daily_ohlcv",
    "daily_market_cap",
    "minute_ohlcv",
    "financial_statements",
    "financial_ratios",
    "price_adjustment_factors",
    "system_milestones",
    "trading_calendar",
    "minute_target_history",
}

ALLOWED_TABLES_US = {
    "us_ticker_master",
    "us_ticker_history",
    "us_collection_blacklist",
    "us_financial_facts",
    "us_standard_financials",
    "us_share_history",
    "us_daily_price",
    "us_price_adjustment_factors",
    "us_daily_valuation",
    "us_financial_metrics",
}


@router.get("/preview/meta")
def get_preview_metadata():
    """
    각 시장별 조회 가능한 테이블 메타데이터 목록을 반환합니다.
    """
    return {
        "kr": [
            { "table": "stock_info", "name": "종목 마스터 정보" },
            { "table": "daily_ohlcv", "name": "일봉 시세" },
            { "table": "daily_market_cap", "name": "일별 시가총액" },
            { "table": "minute_ohlcv", "name": "분봉 시세" },
            { "table": "financial_statements", "name": "PIT 재무제표" },
            { "table": "financial_ratios", "name": "PIT 재무비율" },
            { "table": "price_adjustment_factors", "name": "수정주가 팩터" },
            { "table": "system_milestones", "name": "수집 마일스톤 이력" },
            { "table": "trading_calendar", "name": "영업일 달력" },
            { "table": "minute_target_history", "name": "수집 대상 이력" }
        ],
        "us": [
            { "table": "us_ticker_master", "name": "미국 티커 마스터" },
            { "table": "us_ticker_history", "name": "티커 변경 이력" },
            { "table": "us_collection_blacklist", "name": "차단 종목 목록" },
            { "table": "us_financial_facts", "name": "SEC XBRL 수시 공시 재무 팩트" },
            { "table": "us_standard_financials", "name": "PIT 표준재무제표" },
            { "table": "us_share_history", "name": "주식수 변동 이력" },
            { "table": "us_daily_price", "name": "일봉 시세" },
            { "table": "us_price_adjustment_factors", "name": "수정주가 팩터" },
            { "table": "us_daily_valuation", "name": "일별 가치평가 지표" },
            { "table": "us_financial_metrics", "name": "분기별 재무비율" }
        ]
    }


@router.get("/preview/{market}/{table}")
async def get_preview_table(
    market: str,
    table: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    stk_cd: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None)
):
    """
    시장(kr/us)별 테이블 미리보기 데이터를 조회하여 중계하고 장애를 격리합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    if market == "kr" and table not in ALLOWED_TABLES_KR:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not allowed in KR market.")
    elif market == "us" and table not in ALLOWED_TABLES_US:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not allowed in US market.")
        
    url = (
        f"{settings.P2_KDMS_URL}/api/data/preview/{table}"
        if market == "kr"
        else f"{settings.P3_USDMS_URL}/api/data/preview/{table}"
    )
    
    params = {
        "limit": limit,
        "offset": offset
    }
    if stk_cd:
        params["stk_cd"] = stk_cd
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=5.0)
            if resp.status_code == 200:
                res_data = resp.json()
                return {
                    "offline": False,
                    "table": res_data.get("table", table),
                    "count": res_data.get("count", 0),
                    "data": res_data.get("data", [])
                }
            return {
                "offline": True,
                "table": table,
                "count": 0,
                "data": [],
                "message": f"Backend returned status {resp.status_code}: {resp.text}"
            }
        except Exception as e:
            return {
                "offline": True,
                "table": table,
                "count": 0,
                "data": [],
                "message": f"Backend communication error: {str(e)}"
            }

