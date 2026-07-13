# tdms_core/p4_manager/routers/manager.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
from tdms_core.p4_manager.config import settings
from tdms_core.p4_manager.services.status_service import status_service
from tdms_core.p4_manager.services.backup_service import backup_service

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
        f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/scheduler"
        if market == "kr"
        else f"{settings.P3_USDMS_URL}/api/admin/schedules"
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
async def update_integrated_schedule(market: str, job_id: str, hour: int = Query(...), minute: int = Query(...), day_of_week: str | None = Query(None)):
    """
    시장(kr/us)별 특정 스케줄 작업의 기동 시각 및 요일을 수정합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    if market == "kr":
        url = f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/scheduler?job_id={job_id}&hour={hour}&minute={minute}"
    else:
        url = f"{settings.P3_USDMS_URL}/api/admin/schedules?job_id={job_id}&hour={hour}&minute={minute}"
        
    if day_of_week:
        url += f"&day_of_week={day_of_week}"
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.put(url, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"스케줄 변경 실패: {resp.text}")
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"{market.upper()} 백엔드 통신 실패: {str(e)}")


@router.post("/schedules/{market}/reload")
async def reload_integrated_schedule(market: str):
    """
    시장(kr/us)별 백엔드의 .env 파일을 메모리에 다시 로드하고 스케줄러 일정을 갱신합니다.
    """
    if market not in ["kr", "us"]:
        raise HTTPException(status_code=400, detail="market 파라미터는 'kr' 또는 'us'이어야 합니다.")
        
    url = (
        f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/scheduler/reload"
        if market == "kr"
        else f"{settings.P3_USDMS_URL}/api/admin/schedules/reload"
    )
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"스케줄 재로드 실패: {resp.text}")
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
        url = f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/scheduler/{job_id}/toggle?action={action}"
    else:
        url = f"{settings.P3_USDMS_URL}/api/admin/schedules/{job_id}/toggle?action={action}"
        
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
        f"{settings.P2_KDMS_URL}/api/health/freshness"
        if market == "kr"
        else f"{settings.P3_USDMS_URL}/api/health/freshness"
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
        f"{settings.P2_KDMS_URL}/api/health/gaps"
        if market == "kr"
        else f"{settings.P3_USDMS_URL}/api/health/gaps"
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
    url = f"{settings.P2_KDMS_URL}/api/health/milestones"
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
    url = f"{settings.P2_KDMS_URL}/api/health/milestones"
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
    url = f"{settings.P3_USDMS_URL}/api/health/blacklist"
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
    url = f"{settings.P3_USDMS_URL}/api/health/blacklist/{cik}/release"
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
    end_date: str | None = Query(None),
    quarter: str | None = Query(None),
    market_filter: str | None = Query(None),
    keyword: str | None = Query(None),
    match_type: str | None = Query(None),
    search_field: str | None = Query(None)
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
    if quarter:
        params["quarter"] = quarter
    if market_filter:
        params["market"] = market_filter
    if keyword:
        params["keyword"] = keyword
    if match_type:
        params["match_type"] = match_type
    if search_field:
        params["search_field"] = search_field
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=5.0)
            if resp.status_code == 200:
                res_data = resp.json()
                ret_obj = {
                    "offline": False,
                    "table": res_data.get("table", table),
                    "count": res_data.get("count", 0),
                    "data": res_data.get("data", [])
                }
                if "applied_quarter" in res_data:
                    ret_obj["applied_quarter"] = res_data["applied_quarter"]
                return ret_obj
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


@router.get("/env")
def get_env_profile():
    """현재 백엔드 구동 시스템의 환경을 조회합니다."""
    return {"env": backup_service.get_env()}


@router.post("/backup")
def create_backup(
    market: str = Query(..., description="시장 구분 (kdms 또는 usdms)"),
    tag: str = Query("manual", description="백업 식별용 태그")
):
    """
    개발 PC 로컬 DB의 물리적 스냅샷 백업을 생성합니다. (서버 PC에서는 403 Forbidden 기각)
    """
    try:
        return backup_service.create_backup(market=market, tag=tag)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup/list")
def list_backups():
    """보관된 물리 백업 스냅샷 목록을 반환합니다."""
    return backup_service.list_backups()


from pydantic import BaseModel, Field

class RestoreRequest(BaseModel):
    market: str = Field(..., description="시장 구분 (kdms 또는 usdms)")
    tag: str = Field(..., description="백업 태그명")
    filename: str = Field(..., description="복구 대상 백업 파일명 (.tar.gz)")
    confirm_text: str = Field(..., description="이중 확인 텍스트 (RESTORE LOCAL DB)")

@router.post("/restore")
def restore_backup(payload: RestoreRequest):
    """
    지정된 백업 스냅샷 아카이브를 이용해 로컬 개발 PC DB를 복구합니다.
    서버 환경 차단 및 오작동 방지 이중 텍스트 검증이 포함되어 있습니다.
    """
    try:
        return backup_service.restore_backup(
            market=payload.market,
            tag=payload.tag,
            filename=payload.filename,
            confirm_text=payload.confirm_text
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from typing import Literal
from tdms_core.p4_manager.services.sync_service import SyncService

sync_service = SyncService()

class SyncRequest(BaseModel):
    market: Literal["kdms", "usdms"] = Field(..., description="대상 시장")
    direction: Literal["pull", "push"] = Field(..., description="동기화 방향")
    confirm_text: str = Field(..., description="이중 컨펌 입력값 (PULL FROM SERVER 또는 PUSH TO SERVER)")

class SyncIPRequest(BaseModel):
    target: Literal["dev", "server"] = Field(..., description="갱신 대상 변수")
    ip: str = Field(..., description="새로운 IP 주소")

class ConnectionTestRequest(BaseModel):
    ip: str = Field(..., description="연결성 검증 대상 IP 주소")
    port: int = Field(8000, description="백엔드 포트 번호")

@router.post("/sync")
def run_physical_sync(payload: SyncRequest):
    """
    개발 PC와 서버 PC 간의 DB 물리 동기화 태스크를 실행합니다.
    """
    try:
        return sync_service.run_sync_task(
            market=payload.market,
            direction=payload.direction,
            confirm_text=payload.confirm_text
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        if "412" in str(e) or "sudo" in str(e):
            raise HTTPException(status_code=412, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync/status")
def get_sync_status():
    """
    현재 진행 중인 백그라운드 물리 동기화 상태 및 로그 목록을 조회합니다.
    """
    return sync_service.get_sync_status()

@router.post("/sync/audit")
def get_sync_audit_report(market: str = Query(..., description="대상 시장 (kdms 또는 usdms)")):
    """
    물리 동기화 완료 후 정밀 감사 스크립트 실행 결과를 리포팅합니다.
    """
    if market not in ["kdms", "usdms"]:
        raise HTTPException(status_code=400, detail="market은 'kdms' 또는 'usdms' 여야 합니다.")
    res = sync_service.get_audit_report(market)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

@router.get("/network/detect-server")
def detect_server_ip():
    """
    네트워크 대역 스캔 및 DNS 리졸브를 통해 서버 PC의 IP를 자동으로 탐색합니다.
    """
    return sync_service.detect_server_ip()

@router.post("/network/sync-ip")
def sync_ip_in_env(payload: SyncIPRequest):
    """
    개발 PC 또는 서버 PC의 IP 설정을 .env 파일 및 환경 변수에 갱신합니다.
    """
    try:
        return sync_service.sync_ip_in_env(target=payload.target, new_ip=payload.ip)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/network/test-connection")
def test_connection(payload: ConnectionTestRequest):
    """
    특정 IP/포트에 대해 TCP 연결성 및 수동 유효성 검증 테스트를 수행합니다.
    """
    return sync_service.test_connection(ip=payload.ip, port=payload.port)


