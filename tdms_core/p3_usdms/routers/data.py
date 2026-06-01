from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any
from p3_usdms.repositories.master_repo import MasterRepo

router = APIRouter(prefix="/api/data", tags=["data"])

@router.get("/tickers")
def get_tickers(
    collect_only: bool = Query(False, description="Filter for collect targets only"),
    repo: MasterRepo = Depends()
) -> List[Dict[str, Any]]:
    """
    미국 주식 마스터 종목 조회 엔드포인트.
    - collect_only=True: 수집 대상 종목만 조회
    - collect_only=False: 활성화된 모든 종목 조회
    """
    if collect_only:
        return repo.get_collect_targets()
    return repo.get_active_tickers()
