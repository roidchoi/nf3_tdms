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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": f"{market} backend offline",
                "details": str(e)
            }
        )

