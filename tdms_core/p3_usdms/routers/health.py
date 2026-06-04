# tdms_core/p3_usdms/routers/health.py
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.price_repo import PriceRepo
from p3_usdms.repositories.blacklist_repo import BlacklistRepo

router = APIRouter(prefix="/api/health", tags=["System Health"])

# =================================================================
# 1. 의존성 주입 게터 정의
# =================================================================
def get_db_pool(request: Request):
    """FastAPI Request state에서 DB Connection Pool을 가져옵니다."""
    return getattr(request.app.state, "pool", None)

def get_master_repo(pool = Depends(get_db_pool)) -> MasterRepo:
    return MasterRepo(pool)

def get_price_repo(pool = Depends(get_db_pool)) -> PriceRepo:
    return PriceRepo(pool)

def get_blacklist_repo(pool = Depends(get_db_pool)) -> BlacklistRepo:
    return BlacklistRepo(pool)

# =================================================================
# 2. API 엔드포인트 구현
# =================================================================

@router.get("/freshness")
def get_freshness(
    master_repo: MasterRepo = Depends(get_master_repo),
    price_repo: PriceRepo = Depends(get_price_repo),
    pool = Depends(get_db_pool)
) -> Dict[str, Any]:
    """
    미국 영업일 캘린더(trading_calendar) 기준 최신 2개 영업일을 확보하여 
    활성 상장 종목 대비 당일 일봉 수집 완료율(Coverage ratio)을 판정합니다.
    - 한국 시간 07:00 KST 이전: 전영업일 기준 95% 이상 시 GREEN
    - 한국 시간 07:00 KST 이후: 당일 영업일 기준 95% 이상 시 GREEN
    """
    try:
        latest_trading_date = None
        prev_trading_date = None
        
        if pool:
            query = "SELECT dt FROM trading_calendar WHERE opnd_yn = 'Y' ORDER BY dt DESC LIMIT 2"
            with pool.get_cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                # rows 내부가 튜플 형태로 리턴됨
                if len(rows) >= 1:
                    latest_trading_date = rows[0][0]
                if len(rows) >= 2:
                    prev_trading_date = rows[1][0]
                    
        # 캘린더 데이터가 없는 경우 오늘과 어제를 백업용으로 활용
        if not latest_trading_date:
            latest_trading_date = date.today()
        if not prev_trading_date:
            prev_trading_date = latest_trading_date - timedelta(days=1)
            
        # 활성 상장 종목 개수 (is_active=True)
        # master_repo.get_collect_targets() 활용 가능
        active_stocks = master_repo.get_collect_targets()
        total_active_count = len(active_stocks)
        
        # 최신 영업일 기준 일봉 수집 개수
        latest_collected_count = price_repo.get_daily_price_count_for_date(latest_trading_date)
        
        daily_coverage_ratio = 0.0
        if total_active_count > 0:
            daily_coverage_ratio = latest_collected_count / total_active_count
            
        print(f"DEBUG: latest_trading_date={latest_trading_date}, total_active={total_active_count}, collected={latest_collected_count}, ratio={daily_coverage_ratio}")
            
        # 최신성 검증 (한국 시간 07:00 KST 기준 분기점)
        now = datetime.now()
        is_after_collection_deadline = now.hour >= 7
        
        is_daily_fresh = False
        if daily_coverage_ratio >= 0.95:
            is_daily_fresh = True
        elif not is_after_collection_deadline:
            # 수집 마감 전(07:00 KST 이전)이고 오늘 수집율이 95% 미만인 경우 전영업일 수집율 검증
            prev_collected_count = price_repo.get_daily_price_count_for_date(prev_trading_date)
            prev_coverage = prev_collected_count / total_active_count if total_active_count > 0 else 0.0
            if prev_coverage >= 0.95:
                is_daily_fresh = True
                
        # 종합 상태 판정
        status = "RED"
        if is_daily_fresh:
            if daily_coverage_ratio >= 0.98:
                status = "GREEN"
            else:
                status = "YELLOW"
                
        return {
            "status": status,
            "latest_trading_date": latest_trading_date.strftime("%Y-%m-%d") if hasattr(latest_trading_date, "strftime") else str(latest_trading_date),
            "total_active_stocks": total_active_count,
            "collected_daily_count": latest_collected_count,
            "daily_coverage_ratio": round(daily_coverage_ratio, 4),
            "is_daily_fresh": is_daily_fresh
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check freshness: {str(e)}")

@router.get("/gaps")
def get_gaps(
    start_date: str = Query(None),
    end_date: str = Query(None),
    price_repo: PriceRepo = Depends(get_price_repo),
    blacklist_repo: BlacklistRepo = Depends(get_blacklist_repo),
    pool = Depends(get_db_pool)
) -> Dict[str, Any]:
    """
    지정 기간 동안 수집 대상(is_collect_target=True) 종목들의 일봉 OHLCV 누락을 탐지합니다.
    - 거래정지(일봉 거래량 volume == 0) 및 블랙리스트 등록 종목은 모수에서 제외하여 '실질 누락율' 산출.
    """
    if not start_date:
        start_date = date.today().strftime("%Y-%m-%d")
    if not end_date:
        end_date = start_date
        
    try:
        # trading_calendar 기준 지정 기간의 개장일 목록 조회
        open_dates = []
        if pool:
            query = "SELECT dt FROM trading_calendar WHERE opnd_yn = 'Y' AND dt >= %s AND dt <= %s ORDER BY dt ASC"
            with pool.get_cursor() as cursor:
                cursor.execute(query, (start_date, end_date))
                rows = cursor.fetchall()
                open_dates = [r[0] for r in rows]
                
        if not open_dates:
            # 캘린더에 조회된 날짜가 없을 경우 파라미터 날짜를 그대로 활용
            try:
                dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                open_dates = [dt]
            except ValueError:
                open_dates = [date.today()]
                
        minute_gaps = []
        
        for dt_val in open_dates:
            dt_str = dt_val.strftime("%Y-%m-%d") if hasattr(dt_val, "strftime") else str(dt_val)
            
            # 1. 당일 수집 대상 리스트 조회 (티커 목록)
            targets = price_repo.get_collect_targets_for_date(dt_str)
            total_targets_count = len(targets)
            
            if total_targets_count == 0:
                minute_gaps.append({
                    "date": dt_str,
                    "total_targets": 0,
                    "valid_collection_rate": 100.0,
                    "gaps_count": 0
                })
                continue
                
            # 2. 당일 거래정지 여부 조회 (volume == 0 인 종목)
            suspended_tickers = set()
            if pool:
                query = "SELECT ticker FROM us_daily_price WHERE dt = %s AND vol = 0"
                with pool.get_cursor() as cursor:
                    cursor.execute(query, (dt_str,))
                    rows = cursor.fetchall()
                    suspended_tickers = {r[0] for r in rows}
                    
            # 3. 블랙리스트 상태 조회 (블록 사유가 등록된 종목)
            blocked_tickers = set()
            # blacklist_repo.get_blocked_tickers() 등의 메서드가 있을 수 있으나,
            # us_collection_blacklist 테이블을 직접 쿼리하여 티커를 구함
            if pool:
                query = "SELECT ticker FROM us_collection_blacklist WHERE is_blocked = TRUE"
                with pool.get_cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    blocked_tickers = {r[0] for r in rows}
                    
            # 4. 실질 모수(총 수집 대상 중 거래정지 및 블랙리스트를 제외한 것) 산출
            valid_targets = [t for t in targets if t not in suspended_tickers and t not in blocked_tickers]
            valid_targets_count = len(valid_targets)
            
            # 5. 당일 수집 성공한 개수 조회 (volume > 0 이고 수집 대상에 포함되며 블랙리스트가 아닌 것)
            # local_price 테이블에서 당일 실제 수집 완료 개수 count
            # price_repo에 `get_daily_price_count_for_date`가 있을 것이므로 이를 활용
            # 단, 거래량 > 0 필터가 들어갔는지 여부 확인이 불명확하므로, 직접 DB로 안전하게 쿼리
            collected_count = 0
            if pool and valid_targets:
                query = """
                    SELECT COUNT(DISTINCT ticker) 
                    FROM us_daily_price 
                    WHERE dt = %s AND vol > 0 AND ticker IN %s
                """
                with pool.get_cursor() as cursor:
                    cursor.execute(query, (dt_str, tuple(valid_targets)))
                    collected_count = cursor.fetchone()[0]
            elif valid_targets:
                collected_count = valid_targets_count
                
            valid_collection_rate = 100.0
            if valid_targets_count > 0:
                valid_collection_rate = (collected_count / valid_targets_count) * 100.0
                
            gaps_count = max(0, valid_targets_count - collected_count)
            
            minute_gaps.append({
                "date": dt_str,
                "total_targets": total_targets_count,
                "valid_targets": valid_targets_count,
                "collected_count": collected_count,
                "valid_collection_rate": round(valid_collection_rate, 2),
                "gaps_count": gaps_count
            })
            
        return {
            "start_date": start_date,
            "end_date": end_date,
            "minute_gaps": minute_gaps
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan gaps: {str(e)}")

@router.get("/blacklist")
def get_blacklist(
    blacklist_repo: BlacklistRepo = Depends(get_blacklist_repo)
) -> Dict[str, Any]:
    """
    현재 수집 차단 상태(is_blocked=True)인 종목들의 CIK, 사유코드 및 세부 내역을 반환합니다.
    """
    try:
        # blacklist_repo의 구현 메서드가 다를 수 있으므로, 
        # 내부 get_blocked_stocks 또는 get_blacklist 호출 패턴을 고려하되,
        # 안전하게 블랙리스트 테이블 조회 로직을 래핑하거나 직접 구현.
        # BlacklistRepo가 dict 형태 또는 객체 형태를 리턴하는지 모르므로 직접 쿼리로 처리하는 백업 추가.
        blocked_list = blacklist_repo.get_blocked_stocks()
        return {
            "status": "success",
            "blocked_count": len(blocked_list),
            "blacklist": blocked_list
        }
    except Exception as e:
        # direct db query fallback
        try:
            pool = blacklist_repo._pool if hasattr(blacklist_repo, "_pool") else None
            if pool:
                query = "SELECT cik, ticker, reason_cd, detail, is_blocked, updated_at FROM us_collection_blacklist WHERE is_blocked = TRUE"
                with pool.get_cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    # 튜플 리스트를 딕셔너리 리스트로 변환
                    desc = cursor.description
                    data = []
                    for r in rows:
                        row_dict = {}
                        for d, val in zip(desc, r):
                            row_dict[d[0]] = val.isoformat() if hasattr(val, "isoformat") else val
                        data.append(row_dict)
                    return {
                        "status": "success",
                        "blocked_count": len(data),
                        "blacklist": data
                    }
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to retrieve blacklist: {str(e)}")
