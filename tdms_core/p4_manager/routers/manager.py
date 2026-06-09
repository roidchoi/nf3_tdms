# tdms_core/p4_manager/routers/manager.py
from fastapi import APIRouter
from tdms_core.p4_manager.services.status_service import status_service

router = APIRouter()

@router.get("/status")
def get_integrated_status():
    """
    통합 대시보드 상태 집계 조회 API.
    캐시된 최신 KR/US 데이터를 즉시 반환.
    """
    return status_service.get_status()
