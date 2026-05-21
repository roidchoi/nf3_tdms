# routers/data.py

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from datetime import datetime, date
from typing import List, Dict, Any

from repositories.master_repo import MasterRepo
from repositories.factor_repo import FactorRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.financial_repo import FinancialRepo

router = APIRouter(prefix="/api/data", tags=["data"])

# =================================================================
# 1. 의존성 주입 게터 정의
# =================================================================
def get_db_pool(request: Request):
    """FastAPI Request state에서 DB Connection Pool을 가져옵니다."""
    # 테스트 환경에서는 app.state.pool이 없을 수 있으므로 안전장치 적용
    return getattr(request.app.state, "pool", None)

def get_master_repo(pool = Depends(get_db_pool)) -> MasterRepo:
    return MasterRepo(pool)

def get_factor_repo(pool = Depends(get_db_pool)) -> FactorRepo:
    return FactorRepo(pool)

def get_ohlcv_repo(pool = Depends(get_db_pool)) -> OhlcvRepo:
    return OhlcvRepo(pool)

def get_financial_repo(pool = Depends(get_db_pool)) -> FinancialRepo:
    return FinancialRepo(pool)


# =================================================================
# 2. API 엔드포인트 구현
# =================================================================

@router.get("/stocks", response_model=List[Dict[str, Any]])
def get_stocks(master_repo: MasterRepo = Depends(get_master_repo)):
    """
    [T-002] 전체 활성 종목 리스트를 반환합니다.
    """
    try:
        return master_repo.get_all_active_stocks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stocks: {str(e)}")


@router.get("/factors/{stk_cd}", response_model=List[Dict[str, Any]])
def get_factors(
    stk_cd: str,
    price_source: str = "KIS",
    factor_repo: FactorRepo = Depends(get_factor_repo)
):
    """
    [T-003] 특정 종목의 수정계수 이력을 반환합니다.
    """
    try:
        return factor_repo.get_factors_for_stock(stk_cd, price_source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve factors: {str(e)}")


@router.get("/ohlcv/daily/adjusted", response_model=List[Dict[str, Any]])
def get_adjusted_ohlcv_daily(
    stk_cd: str = Query(..., description="종목 코드"),
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    price_source: str = Query("KIS", description="시세 출처"),
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo),
    factor_repo: FactorRepo = Depends(get_factor_repo)
):
    """
    [T-003] 원본 OHLCV 데이터를 기반으로 수정계수 이력을 온더플라이(On-the-fly)로 계산하여
    실시간 수정주가 및 수정거래량 리스트를 반환합니다.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        # 1. 원본 OHLCV 조회
        ohlcv_rows = ohlcv_repo.get_daily_ohlcv(stk_cd, start_dt, end_dt)
        # 2. 수정계수 이력 조회
        factors = factor_repo.get_factors_for_stock(stk_cd, price_source)

        adjusted_records = []
        for row in ohlcv_rows:
            dt = row["dt"]
            
            # event_dt > dt인 수정계수의 곱 계산 (온더플라이 누적곱)
            cum_price_factor = 1.0
            cum_volume_factor = 1.0
            
            for f in factors:
                f_dt = f["event_dt"]
                if isinstance(f_dt, str):
                    f_dt = datetime.strptime(f_dt, "%Y-%m-%d").date()
                
                if f_dt > dt:
                    cum_price_factor *= f["price_ratio"]
                    cum_volume_factor *= f["volume_ratio"]
            
            # date 객체 직렬화를 위해 문자열로 변환
            dt_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)

            adjusted_records.append({
                "stk_cd": row["stk_cd"],
                "dt": dt_str,
                "open": int(round(row["open"] * cum_price_factor)),
                "high": int(round(row["high"] * cum_price_factor)),
                "low": int(round(row["low"] * cum_price_factor)),
                "close": int(round(row["close"] * cum_price_factor)),
                "volume": int(round(row["volume"] * cum_volume_factor)),
                "adj_factor": cum_price_factor
            })
            
        return adjusted_records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"On-the-fly adjustment calculation failed: {str(e)}")


@router.get("/ohlcv/adjusted/{stk_cd}", response_model=List[Dict[str, Any]])
def get_adjusted_ohlcv_from_physical(
    stk_cd: str,
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo)
):
    """
    [T-003] daily_ohlcv_adjusted 물리 테이블에서 직접 수정주가 데이터를 효율적으로 조회하여 반환합니다.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        records = ohlcv_repo.get_adjusted_ohlcv_direct(stk_cd, start_dt, end_dt)
        for r in records:
            if hasattr(r["dt"], "strftime"):
                r["dt"] = r["dt"].strftime("%Y-%m-%d")
            else:
                r["dt"] = str(r["dt"])
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Physical table query failed: {str(e)}")


@router.get("/financials", response_model=Dict[str, Any])
def get_pit_financials(
    stk_cd: str = Query(..., description="종목 코드"),
    as_of: str = Query(None, description="특정 PIT 조회 시점 (ISO 형식: YYYY-MM-DDTHH:MM:SS+TZ 또는 YYYY-MM-DD)"),
    div_cls_code: str = Query("1", description="결산 구분 ('1' 분기, '0' 연간)"),
    financial_repo: FinancialRepo = Depends(get_financial_repo)
):
    """
    [T-004] 특정 종목의 Point-in-Time 재무정보(재무제표 및 재무비율)를 조회합니다.
    as_of가 생략될 경우 현재 시점 기준의 최신 데이터를 반환합니다.
    """
    try:
        if as_of:
            try:
                # timezone 정보가 포함된 표준 ISO 포맷 파싱 시도
                as_of_dt = datetime.fromisoformat(as_of)
            except ValueError:
                # 단순 날짜 포맷일 경우 KST 기준 자정 처리
                from zoneinfo import ZoneInfo
                kst = ZoneInfo("Asia/Seoul")
                as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").replace(tzinfo=kst)
        else:
            from zoneinfo import ZoneInfo
            kst = ZoneInfo("Asia/Seoul")
            as_of_dt = datetime.now(kst)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid as_of date format. Use ISO format or YYYY-MM-DD.")

    try:
        statements = financial_repo.get_statements_as_of(stk_cd, div_cls_code, as_of_dt)
        ratios = financial_repo.get_ratios_as_of(stk_cd, div_cls_code, as_of_dt)

        # datetime/date 타입 필드 직렬화를 위해 정규화
        for s in statements:
            if s.get("retrieved_at") and hasattr(s["retrieved_at"], "isoformat"):
                s["retrieved_at"] = s["retrieved_at"].isoformat()
        for r in ratios:
            if r.get("retrieved_at") and hasattr(r["retrieved_at"], "isoformat"):
                r["retrieved_at"] = r["retrieved_at"].isoformat()

        return {
            "statements": statements,
            "ratios": ratios
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PIT Financials query failed: {str(e)}")

