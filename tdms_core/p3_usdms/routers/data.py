from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.price_repo import PriceRepo

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

@router.get("/price/daily")
def get_daily_prices(
    cik: str = Query(..., description="SEC CIK of the target company"),
    start_dt: str = Query("1980-01-01", description="Start date (YYYY-MM-DD)"),
    end_dt: str = Query("9999-12-31", description="End date (YYYY-MM-DD)"),
    repo: PriceRepo = Depends()
) -> List[Dict[str, Any]]:
    """
    특정 기간의 미국 주식 일일 가격(Raw)을 조회합니다.
    """
    return repo.get_daily_prices(cik, start_dt, end_dt)

@router.get("/price/factors")
def get_price_factors(
    cik: str = Query(..., description="SEC CIK of the target company"),
    repo: PriceRepo = Depends()
) -> List[Dict[str, Any]]:
    """
    특정 종목의 전체 가격 수정계수(Adjustment Factors) 이력을 조회합니다.
    """
    return repo.get_price_factors(cik)
