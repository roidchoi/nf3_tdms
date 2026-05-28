# routers/health.py

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from repositories.master_repo import MasterRepo
from repositories.factor_repo import FactorRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.financial_repo import FinancialRepo
from repositories.market_cap_repo import MarketCapRepo


router = APIRouter(prefix="/api/health", tags=["health"])

# =================================================================
# 1. 의존성 주입 게터 정의
# =================================================================
def get_db_pool(request: Request):
    """FastAPI Request state에서 DB Connection Pool을 가져옵니다."""
    return getattr(request.app.state, "pool", None)

def get_master_repo(pool = Depends(get_db_pool)) -> MasterRepo:
    return MasterRepo(pool)

def get_factor_repo(pool = Depends(get_db_pool)) -> FactorRepo:
    return FactorRepo(pool)

def get_ohlcv_repo(pool = Depends(get_db_pool)) -> OhlcvRepo:
    return OhlcvRepo(pool)

def get_financial_repo(pool = Depends(get_db_pool)) -> FinancialRepo:
    return FinancialRepo(pool)

def get_market_cap_repo(pool = Depends(get_db_pool)) -> MarketCapRepo:
    return MarketCapRepo(pool)



class MilestoneInput(BaseModel):
    milestone_name: str
    milestone_date: str  # YYYY-MM-DD
    description: str | None = None


# =================================================================
# 2. API 엔드포인트 구현
# =================================================================

@router.get("/freshness")
def get_freshness(
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo),
    master_repo: MasterRepo = Depends(get_master_repo),
    pool = Depends(get_db_pool)
):
    """
    [T-008] 데이터 최신성 및 수집 커버리지율 검증 API
    """
    try:
        # 1. 영업일 캘린더에서 최신 2개 영업일 조회
        latest_trading_date = None
        prev_trading_date = None
        
        if pool:
            query = "SELECT dt FROM trading_calendar WHERE opnd_yn = 'Y' ORDER BY dt DESC LIMIT 2"
            with pool.get_cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                if len(rows) >= 1:
                    latest_trading_date = rows[0][0]
                if len(rows) >= 2:
                    prev_trading_date = rows[1][0]
                    
        # 캘린더 데이터가 없는 경우 오늘과 어제를 백업용으로 활용
        if not latest_trading_date:
            latest_trading_date = date.today()
        if not prev_trading_date:
            prev_trading_date = latest_trading_date - timedelta(days=1)
            
        # 2. 활성 상장 종목 목록 및 개수
        active_stocks = master_repo.get_all_active_stocks()
        total_active_count = len(active_stocks)
        
        # 3. 최신 영업일 기준 일봉 수집 개수 및 커버리지 계산
        latest_collected_count = ohlcv_repo.get_daily_ohlcv_count_for_date(latest_trading_date)
        
        daily_coverage_ratio = 0.0
        if total_active_count > 0:
            daily_coverage_ratio = latest_collected_count / total_active_count
            
        # 4. 최신성 검증
        now = datetime.now()
        is_after_market = now.hour >= 16
        
        # 장마감 전(16시 이전)이고 오늘 데이터 수집율이 95% 미만인 경우에는 전영업일 기준 95% 이상 완료 시 Fresh 상태로 인정
        is_daily_fresh = False
        if daily_coverage_ratio >= 0.95:
            is_daily_fresh = True
        elif not is_after_market:
            # 전 영업일 기준의 커버리지 체크
            prev_collected_count = ohlcv_repo.get_daily_ohlcv_count_for_date(prev_trading_date)
            prev_coverage = prev_collected_count / total_active_count if total_active_count > 0 else 0.0
            if prev_coverage >= 0.95:
                is_daily_fresh = True
                
        # 5. 분봉 최신성 검증
        latest_minute_dt_tm = ohlcv_repo.get_latest_minute_dt_tm()
        is_minute_fresh = False
        if latest_minute_dt_tm:
            # datetime 객체 타임존 정규화
            latest_minute_date = latest_minute_dt_tm.date() if isinstance(latest_minute_dt_tm, datetime) else latest_minute_dt_tm
            if latest_minute_date >= latest_trading_date:
                is_minute_fresh = True
            elif not is_after_market:
                if latest_minute_date >= prev_trading_date:
                    is_minute_fresh = True
        else:
            # 분봉이 아예 없는 경우는 False
            is_minute_fresh = False
            
        # 6. 종합 상태 판정
        status = "GREEN"
        if not is_daily_fresh:
            status = "RED"
        elif daily_coverage_ratio < 0.98:
            status = "YELLOW"
            
        return {
            "status": status,
            "latest_trading_date": latest_trading_date.strftime("%Y-%m-%d") if hasattr(latest_trading_date, "strftime") else str(latest_trading_date),
            "total_active_stocks": total_active_count,
            "collected_daily_count": latest_collected_count,
            "daily_coverage_ratio": round(daily_coverage_ratio, 4),
            "is_daily_fresh": is_daily_fresh,
            "latest_minute_timestamp": latest_minute_dt_tm.isoformat() if latest_minute_dt_tm and hasattr(latest_minute_dt_tm, "isoformat") else str(latest_minute_dt_tm),
            "is_minute_fresh": is_minute_fresh
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check freshness: {str(e)}")


@router.get("/gaps")
def get_gaps(
    start_date: str = Query(None),
    end_date: str = Query(None),
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo),
    pool = Depends(get_db_pool)
):
    """
    [T-008] 거래정지 및 예외 사유가 등록된 Gap을 필터링하여 실질적 분봉 누락을 검출하는 API
    """
    if not start_date:
        start_date = date.today().strftime("%Y-%m-%d")
    if not end_date:
        end_date = start_date
        
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")
        
    try:
        # 1. 대상 기간 내의 영업일 리스트업
        query_cal = "SELECT dt FROM trading_calendar WHERE opnd_yn = 'Y' AND dt BETWEEN %s AND %s ORDER BY dt ASC"
        trading_days = []
        with pool.get_cursor() as cursor:
            cursor.execute(query_cal, (start_dt, end_dt))
            rows = cursor.fetchall()
            trading_days = [r[0] for r in rows]
            
        # 영업일 데이터가 캘린더에 조회되지 않는 경우 입력받은 날짜 범위를 직접 사용
        if not trading_days:
            curr = start_dt
            while curr <= end_dt:
                trading_days.append(curr)
                curr += timedelta(days=1)
                
        minute_gaps_result = []
        overall_status = "GREEN"
        
        for t_date in trading_days:
            # 2. 해당일의 분봉 수집 타겟 목록
            target_codes = ohlcv_repo.get_minute_target_history_for_date(t_date)
            if not target_codes:
                continue
                
            # 3. DB에서 각 종목별 적재된 분봉 개수 조회 (381개가 만점)
            # 쿼리: date_trunc('day', dt_tm) = %s 또는 dt_tm::date = %s
            query_cnt = """
                SELECT stk_cd, COUNT(*) 
                FROM minute_ohlcv 
                WHERE dt_tm >= %s AND dt_tm < %s 
                GROUP BY stk_cd
            """
            day_start = datetime.combine(t_date, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            
            # 4. 일봉 거래량 조회 (거래정지 필터용: vol == 0)
            query_vol = "SELECT stk_cd, vol FROM daily_ohlcv WHERE dt = %s"
            
            # 5. daily_ohlcv_gap 예외 등록 사유 조회
            query_gap_reasons = "SELECT stk_cd, reason FROM daily_ohlcv_gap WHERE dt = %s"
            
            collected_counts = {}
            daily_volumes = {}
            gap_reasons = {}
            
            with pool.get_cursor() as cursor:
                cursor.execute(query_cnt, (day_start, day_end))
                collected_counts = {r[0]: r[1] for r in cursor.fetchall()}
                
                cursor.execute(query_vol, (t_date,))
                daily_volumes = {r[0]: r[1] for r in cursor.fetchall()}
                
                cursor.execute(query_gap_reasons, (t_date,))
                gap_reasons = {r[0]: r[1] for r in cursor.fetchall()}
                
            missing_stocks = []
            suspended_stocks_count = 0
            gap_reason_stocks_count = 0
            
            for code in target_codes:
                # 381개 분봉 기준 미달 시 누락 의심
                actual_cnt = collected_counts.get(code, 0)
                if actual_cnt < 381:
                    vol = daily_volumes.get(code, 0)
                    has_gap_reason = code in gap_reasons
                    
                    if vol == 0:
                        # 일봉 거래량이 0 이면 거래정지이므로 누락 모수에서 배제
                        suspended_stocks_count += 1
                        continue
                    elif has_gap_reason:
                        # 수집 갭 사유 등록 건도 배제
                        gap_reason_stocks_count += 1
                        continue
                    else:
                        missing_stocks.append(code)
                        
            # 유효 분봉 수집 타겟수 = 전체 타겟 - 거래정지 - 사유배제
            valid_target_count = len(target_codes) - suspended_stocks_count - gap_reason_stocks_count
            valid_rate = 100.0
            if valid_target_count > 0:
                valid_rate = ((valid_target_count - len(missing_stocks)) / valid_target_count) * 100
                
            day_status = "GREEN"
            if valid_rate < 95.0:
                day_status = "CRITICAL"
                overall_status = "CRITICAL"
            elif valid_rate < 98.0:
                day_status = "WARNING"
                if overall_status != "CRITICAL":
                    overall_status = "WARNING"
                    
            minute_gaps_result.append({
                "date": t_date.strftime("%Y-%m-%d") if hasattr(t_date, "strftime") else str(t_date),
                "status": day_status,
                "total_targets": len(target_codes),
                "suspended_targets": suspended_stocks_count,
                "gap_excluded_targets": gap_reason_stocks_count,
                "valid_targets": valid_target_count,
                "missing_stocks_count": len(missing_stocks),
                "missing_stocks": missing_stocks,
                "valid_collection_rate": round(valid_rate, 2)
            })
            
        return {
            "status": overall_status,
            "start_date": start_date,
            "end_date": end_date,
            "minute_gaps": minute_gaps_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve gaps: {str(e)}")


@router.get("/integrity")
def get_integrity(
    master_repo: MasterRepo = Depends(get_master_repo),
    pool = Depends(get_db_pool)
):
    """
    [T-008] 물리 수정주가 정합성, 가격 변동 제한폭(±30.1% + IPO 제외), 시가총액 비교, 재무제표 짝 누락 전수 검증 API
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")
        
    try:
        adjusted_price_mismatches = []
        price_limit_violations = []
        market_cap_mismatches = []
        financial_ratio_mismatches = []
        
        with pool.get_cursor() as cursor:
            # 1. 수정주가 역산 공식 불일치 검증
            # Expected = Round(raw_close * adj_factor) vs Physical Close
            q_mismatch = """
                SELECT a.stk_cd, a.dt, o.cls_prc as raw_close, a.adj_factor, a.cls_prc as adj_close
                FROM daily_ohlcv_adjusted a
                JOIN daily_ohlcv o ON a.stk_cd = o.stk_cd AND a.dt = o.dt
                WHERE ABS(a.cls_prc - ROUND(o.cls_prc * a.adj_factor)) > 0
            """
            cursor.execute(q_mismatch)
            for r in cursor.fetchall():
                expected_val = round(float(r[2]) * float(r[3]))
                adjusted_price_mismatches.append({
                    "stk_cd": r[0],
                    "dt": r[1].strftime("%Y-%m-%d") if hasattr(r[1], "strftime") else str(r[1]),
                    "raw_close": int(r[2]),
                    "adj_factor": float(r[3]),
                    "expected": float(expected_val),
                    "actual": float(r[4])
                })
                
            # 2. 하루 ±30.1% 변동 제한 위반 검증
            # LAG를 활용해 전영업일 수정 종가 대비 당일 수정 종가 등락률 계산
            # stock_info.list_dt (상장일) 당일의 변동 건은 검출에서 제외
            q_limit = """
                WITH prev_adj AS (
                    SELECT stk_cd, dt, cls_prc,
                           LAG(cls_prc) OVER(PARTITION BY stk_cd ORDER BY dt ASC) as prev_close
                    FROM daily_ohlcv_adjusted
                )
                SELECT p.stk_cd, p.dt, p.prev_close, p.cls_prc
                FROM prev_adj p
                JOIN stock_info s ON p.stk_cd = s.stk_cd
                WHERE p.prev_close IS NOT NULL 
                  AND p.prev_close > 0
                  AND ABS((p.cls_prc - p.prev_close)::float / p.prev_close) > 0.301
                  AND p.dt != s.list_dt
            """
            cursor.execute(q_limit)
            # 파이썬 측에서도 IPO 상장일 예외를 이중으로 보완 검증 (master_repo 활용)
            ipo_dates = master_repo.get_ipo_dates()
            
            for r in cursor.fetchall():
                stk_cd = r[0]
                dt = r[1]
                prev_cls = float(r[2])
                curr_cls = float(r[3])
                
                # IPO 당일 변동 건 제외 (이중 체크)
                if stk_cd in ipo_dates and ipo_dates[stk_cd] == dt:
                    continue
                    
                chg_rate = ((curr_cls - prev_cls) / prev_cls) * 100
                price_limit_violations.append({
                    "stk_cd": stk_cd,
                    "dt": dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
                    "prev_close": prev_cls,
                    "close": curr_cls,
                    "change_rate": round(chg_rate, 2)
                })
                
            # 3. 시가총액 종가 불일치 검증
            q_mkt_cap = """
                SELECT o.stk_cd, o.dt, o.cls_prc as ohlcv_close, m.cls_prc as mkt_cap_close
                FROM daily_ohlcv o
                JOIN daily_market_cap m ON o.stk_cd = m.stk_cd AND o.dt = m.dt
                WHERE o.cls_prc != m.cls_prc
            """
            cursor.execute(q_mkt_cap)
            for r in cursor.fetchall():
                market_cap_mismatches.append({
                    "stk_cd": r[0],
                    "dt": r[1].strftime("%Y-%m-%d") if hasattr(r[1], "strftime") else str(r[1]),
                    "ohlcv_close": int(r[2]),
                    "mkt_cap_close": int(r[3])
                })
                
            # 4. 재무제표 짝 누락 검증 (Statements는 적재되었는데 Ratios가 누락된 경우)
            q_financial = """
                SELECT s.stk_cd, s.stac_yymm, s.div_cls_code
                FROM financial_statements s
                LEFT JOIN financial_ratios r ON s.stk_cd = r.stk_cd 
                                            AND s.stac_yymm = r.stac_yymm 
                                            AND s.div_cls_code = r.div_cls_code
                WHERE r.stk_cd IS NULL
            """
            cursor.execute(q_financial)
            for r in cursor.fetchall():
                financial_ratio_mismatches.append({
                    "stk_cd": r[0],
                    "stac_yymm": r[1],
                    "div_cls_code": r[2],
                    "reason": "Ratios missing"
                })
                
        # 5. 종합 판정
        has_issue = (
            len(adjusted_price_mismatches) > 0 or 
            len(price_limit_violations) > 0 or 
            len(market_cap_mismatches) > 0 or 
            len(financial_ratio_mismatches) > 0
        )
        status = "RED" if has_issue else "GREEN"
        
        return {
            "status": status,
            "adjusted_price_mismatch_count": len(adjusted_price_mismatches),
            "adjusted_price_mismatches": adjusted_price_mismatches,
            "price_limit_violations_count": len(price_limit_violations),
            "price_limit_violations": price_limit_violations,
            "market_cap_mismatch_count": len(market_cap_mismatches),
            "market_cap_mismatches": market_cap_mismatches,
            "financial_ratio_mismatch_count": len(financial_ratio_mismatches),
            "financial_ratio_mismatches": financial_ratio_mismatches
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run integrity check: {str(e)}")


@router.get("/milestones", response_model=List[Dict[str, Any]])
def get_milestones(pool = Depends(get_db_pool)):
    """
    [T-008] 시스템 운영 마일스톤 조회 API
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")
        
    try:
        query = """
            SELECT milestone_name, milestone_date, description, updated_at
            FROM system_milestones
            ORDER BY milestone_date DESC, milestone_name ASC
        """
        with pool.get_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            return [
                {
                    "milestone_name": r[0],
                    "milestone_date": r[1].strftime("%Y-%m-%d") if hasattr(r[1], "strftime") else str(r[1]),
                    "description": r[2],
                    "updated_at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3])
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve milestones: {str(e)}")


@router.post("/milestones")
def post_milestone(
    milestone: MilestoneInput,
    pool = Depends(get_db_pool)
):
    """
    [T-008] 시스템 운영 마일스톤 등록/수정 API (UPSERT)
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")
        
    try:
        m_date = datetime.strptime(milestone.milestone_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        
    try:
        query = """
            INSERT INTO system_milestones (milestone_name, milestone_date, description, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (milestone_name) DO UPDATE SET
                milestone_date = EXCLUDED.milestone_date,
                description = EXCLUDED.description,
                updated_at = CURRENT_TIMESTAMP
        """
        with pool.get_cursor() as cursor:
            cursor.execute(query, (milestone.milestone_name, m_date, milestone.description))
            
        return {"status": "SUCCESS", "message": f"Milestone '{milestone.milestone_name}' registered successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register milestone: {str(e)}")
