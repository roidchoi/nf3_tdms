#
# routers/health.py
#
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta

from collectors.db_manager import DatabaseManager #
from pydantic import BaseModel, Field, field_validator
import math

router = APIRouter()
logger = logging.getLogger(__name__)

# --- 전역 객체 주입 (main.py에서 설정) ---
db: DatabaseManager = None
# -------------------------------------------

# 날짜를 분기로 변환
def _get_quarter_from_date(base_date: date) -> str:
    """
    날짜(date)를 'YYYYQQ' 형식의 분기 문자열(str)로 변환합니다.
    (예: 2025-11-17 -> "2025Q4")
    """
    quarter = math.ceil(base_date.month / 3)
    return f"{base_date.year}Q{quarter}"

# --- (신규) Phase 6.4: 데이터 최신성 모델 (PRD 3.1.4) ---

class HealthFreshness(BaseModel):
    """ GET /health/freshness 응답 모델 """
    last_daily_dt: Optional[date] = Field(None, description="일봉 데이터 마지막 수집일")
    last_minute_dt_tm: Optional[datetime] = Field(None, description="분봉 데이터 마지막 수집 시각")
    daily_lag_days: Optional[int] = Field(None, description="일봉 데이터 지연 일수")
    is_daily_fresh: bool = Field(False, description="일봉 데이터 최신 상태 여부 (1일 이내)")

class HealthFinancials(BaseModel):
    """ GET /health/financials 응답 모델 """
    latest_stac_yymm: Optional[str] = Field(None, description="수집된 최신 결산년월")
    distinct_stocks_count: int = Field(0, description="재무 데이터가 수집된 총 종목 수")
    latest_retrieved_at: Optional[datetime] = Field(None, description="가장 최근 재무정보 수집(처리) 시각")

class HealthFactors(BaseModel):
    """ GET /health/factors 응답 모델 """
    total_events_count: int = Field(0, description="누적된 총 수정계수 이벤트 수")
    distinct_stocks_count: int = Field(0, description="수정계수 이벤트가 있는 총 종목 수")
    latest_event_dt: Optional[date] = Field(None, description="가장 최근 발생한 이벤트 날짜")

# [신규] 마일스톤 생성 요청 모델
class SystemMilestoneCreateRequest(BaseModel):
    milestone_name: str = Field(..., description="마일스톤 이름 (대분류:중분류:상세_버전)")
    milestone_date: date = Field(..., description="발생 날짜")
    description: str = Field(..., description="상세 설명")

    @field_validator('milestone_name')
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        if ':' not in v:
            raise ValueError('마일스톤 이름은 콜론(:)으로 구분된 계층 구조여야 합니다.')
        return v.upper() # 대문자 강제 변환

class SystemMilestoneResponse(BaseModel):
    milestone_name: str
    milestone_date: date
    description: Optional[str]
    updated_at: datetime

# --- (기존) Phase 6.2: 데이터 누락일 모델 (PRD 3.1.4) ---
class GapCheckRequest(BaseModel):
    """ POST /health/gaps 요청 Body 모델 """
    start_date: date
    end_date: date

class SingleMarketGapResult(BaseModel):
    """ 각 시장별 누락 검증 결과 """
    market: str = Field(..., description="검증 시장 (KOSPI/KOSDAQ)")
    target_quarter: str = Field(..., description="분봉 대상 조회 분기")
    target_stocks_count: int = Field(..., description="검증에 사용된 대상 종목 수")
    total_trading_days: int
    missing_days_count: int
    missing_days: List[date]

class GapCheckResponse(BaseModel):
    """ POST /health/gaps 응답 모델 (구조 변경) """
    analysis_period: Dict[str, date]
    results: List[SingleMarketGapResult] # (두 시장 결과를 리스트로 반환)


# --- (신규) Phase 6.4: 데이터 최신성 (PRD 3.1.4) ---
@router.get(
    "/freshness",
    response_model=HealthFreshness,
    summary="[PRD 3.1.4] 시세 데이터 최신성 검증"
)
def check_data_freshness():
    """
    daily_ohlcv 및 minute_ohlcv 테이블의
    가장 최신 데이터 수집 시점을 확인합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
        
    try:
        # 1. 일봉 최신성
        query_daily = "SELECT MAX(dt) as max_dt FROM daily_ohlcv;"
        daily_res = db._execute_query(query_daily, fetch='one')
        last_daily_dt = daily_res.get('max_dt') if daily_res else None
        
        is_fresh = False
        lag_days = None
        if last_daily_dt:
            # (주말/휴일 고려: 오늘 또는 어제 또는 그저께)
            today = date.today()
            lag_days = (today - last_daily_dt).days
            # (운영일 기준 1영업일 이내)
            if lag_days <= 3: # (간단하게 3일로 처리, 주말포함)
                is_fresh = True

        # 2. 분봉 최신성
        query_minute = "SELECT MAX(dt_tm) as max_dt_tm FROM minute_ohlcv;"
        minute_res = db._execute_query(query_minute, fetch='one')
        last_minute_dt_tm = minute_res.get('max_dt_tm') if minute_res else None
        
        return HealthFreshness(
            last_daily_dt=last_daily_dt,
            last_minute_dt_tm=last_minute_dt_tm,
            daily_lag_days=lag_days,
            is_daily_fresh=is_fresh
        )
        
    except Exception as e:
        logger.error(f"데이터 최신성 검증 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"최신성 검증 실패: {e}")


# --- (신규) Phase 6.4: 재무 데이터 현황 (PRD 3.1.4) ---
@router.get(
    "/financials",
    response_model=HealthFinancials,
    summary="[PRD 3.1.4] 재무 데이터 현황 검증"
)
def check_financials_health():
    """
    financial_statements 테이블의
    최신 결산월, 총 종목 수, 최신 수집 시각을 확인합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
        
    try:
        query = """
            SELECT
                MAX(stac_yymm) as latest_stac_yymm,
                COUNT(DISTINCT stk_cd) as distinct_stocks_count,
                MAX(retrieved_at) as latest_retrieved_at
            FROM
                financial_statements;
        """
        result = db._execute_query(query, fetch='one')
        
        if not result:
            return HealthFinancials() # (빈 값 반환)

        return HealthFinancials(
            latest_stac_yymm=result.get('latest_stac_yymm'),
            distinct_stocks_count=result.get('distinct_stocks_count', 0),
            latest_retrieved_at=result.get('latest_retrieved_at')
        )
        
    except Exception as e:
        logger.error(f"재무 데이터 현황 검증 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"재무 현황 검증 실패: {e}")


# --- (신규) Phase 6.4: 수정계수 현황 (PRD 3.1.4) ---
@router.get(
    "/factors",
    response_model=HealthFactors,
    summary="[PRD 3.1.4] 수정계수 현황 검증"
)
def check_factors_health():
    """
    price_adjustment_factors 테이블의
    총 이벤트 수, 관련 종목 수, 최신 이벤트 날짜를 확인합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
        
    try:
        query = """
            SELECT
                COUNT(*) as total_events_count,
                COUNT(DISTINCT stk_cd) as distinct_stocks_count,
                MAX(event_dt) as latest_event_dt
            FROM
                price_adjustment_factors;
        """
        result = db._execute_query(query, fetch='one')
        
        if not result:
            return HealthFactors() # (빈 값 반환)

        return HealthFactors(
            total_events_count=result.get('total_events_count', 0),
            distinct_stocks_count=result.get('distinct_stocks_count', 0),
            latest_event_dt=result.get('latest_event_dt')
        )
        
    except Exception as e:
        logger.error(f"수정계수 현황 검증 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"수정계수 현황 검증 실패: {e}")

# [신규] 마일스톤 이력 조회
@router.get(
    "/milestones",
    response_model=List[SystemMilestoneResponse],
    summary="[Phase 7.7] 시스템 마일스톤 전체 이력 조회"
)
def get_system_milestones(days: int = Query(30, description="조회할 기간(일)")):
    """
    system_milestones 테이블에서 이력을 조회합니다.
    (날짜 내림차순 정렬)
    """
    if db is None: raise HTTPException(500, "DB not initialized")
    try:
        # 최근 N일 기준
        start_date = date.today() - timedelta(days=days)
        
        query = """
            SELECT milestone_name, milestone_date, description, updated_at
            FROM system_milestones
            ORDER BY milestone_date DESC, updated_at DESC
            
        """
        results = db._execute_query(query, (start_date,), fetch='all')
        return results
    except Exception as e:
        logger.error(f"Milestones fetch failed: {e}", exc_info=True)
        raise HTTPException(500, f"Error: {e}")

# [신규] 마일스톤 등록
@router.post(
    "/milestones",
    summary="[Phase 7.7] 시스템 마일스톤 수동 등록"
)
def create_system_milestone(req: SystemMilestoneCreateRequest):
    """
    새로운 마일스톤을 등록하거나, 이미 존재하는 이름일 경우 업데이트합니다.
    """
    if db is None: raise HTTPException(500, "DB not initialized")
    try:
        query = """
            INSERT INTO system_milestones (milestone_name, milestone_date, description, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (milestone_name) DO UPDATE SET
                milestone_date = EXCLUDED.milestone_date,
                description = EXCLUDED.description,
                updated_at = NOW();
        """
        db._execute_query(query, (req.milestone_name, req.milestone_date, req.description))
        return {"message": f"마일스톤 '{req.milestone_name}' 등록 완료"}
    except Exception as e:
        logger.error(f"Milestone create failed: {e}", exc_info=True)
        raise HTTPException(500, f"Error: {e}")

# --- (수정) Phase 6.4: 시세 누락일 검증 (PRD 3.1.4) ---
@router.post(
    "/gaps",
    response_model=GapCheckResponse,
    summary="[PRD 3.1.4] 시세 누락일 검증 (KOSPI/KOSDAQ 분봉 대상 기준)"
)
def check_data_gaps(req: GapCheckRequest = Body(...)): # (수정) 단순화된 요청
    """
    (수정)
    지정된 기간 동안, KOSPI/KOSDAQ 각각의 '분봉 수집 대상'
    (get_minute_target_history) 종목을 기준으로 
    일봉 데이터(daily_ohlcv)가 누락된 거래일을 찾습니다.
    
    - 분봉 대상 분기는 'end_date' 기준으로 자동 선정됩니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")

    try:
        # 1. (신규) 조회 분기 결정 (end_date 기준)
        target_quarter = _get_quarter_from_date(req.end_date)
        
        # 2. 거래일 캘린더 조회 (공통)
        calendar_query = """
            SELECT dt FROM trading_calendar
            WHERE opnd_yn = 'Y' AND dt BETWEEN %s AND %s;
        """
        trading_days_res = db._execute_query(
            calendar_query,
            (req.start_date, req.end_date),
            fetch='all'
        )
        total_trading_days = len(trading_days_res)

        # 3. (신규) 두 시장을 순회하며 검증
        final_results: List[SingleMarketGapResult] = []
        markets_to_check = ["KOSPI", "KOSDAQ"]

        for market in markets_to_check:
            
            # 4. (수정) db.get_minute_target_history 호출
            target_stock_dicts = db.get_minute_target_history(
                quarter=target_quarter,
                market=market
            )
            
            # (get_minute_target_history가 'symbol'을 반환)
            target_stocks = [row['symbol'] for row in target_stock_dicts]
            
            if not target_stocks:
                # 대상 종목이 없으면, 누락일 0으로 결과 추가
                final_results.append(SingleMarketGapResult(
                    market=market,
                    target_quarter=target_quarter,
                    target_stocks_count=0,
                    total_trading_days=total_trading_days,
                    missing_days_count=0,
                    missing_days=[]
                ))
                continue # 다음 마켓으로

            # 5. 누락일 탐지 (기존 SQL 재사용)
            gaps_query = """
                SELECT t.dt
                FROM trading_calendar t
                LEFT JOIN daily_ohlcv d ON t.dt = d.dt AND d.stk_cd = ANY(%(target_stocks)s)
                WHERE t.opnd_yn = 'Y'
                  AND t.dt BETWEEN %(start_date)s AND %(end_date)s
                GROUP BY t.dt
                HAVING COUNT(d.stk_cd) = 0
                ORDER BY t.dt DESC;
            """
            gaps_res = db._execute_query(
                gaps_query,
                {
                    "target_stocks": target_stocks,
                    "start_date": req.start_date,
                    "end_date": req.end_date
                },
                fetch='all'
            )
            missing_days = [row['dt'] for row in gaps_res]

            # 6. (신규) 개별 시장 결과 추가
            final_results.append(SingleMarketGapResult(
                market=market,
                target_quarter=target_quarter,
                target_stocks_count=len(target_stocks),
                total_trading_days=total_trading_days,
                missing_days_count=len(missing_days),
                missing_days=missing_days
            ))

        # 7. (수정) 최종 응답 반환
        return GapCheckResponse(
            analysis_period={"start_date": req.start_date, "end_date": req.end_date},
            results=final_results
        )

    except Exception as e:
        logger.error(f"데이터 누락 검증 실패: {e}", exc_info=True) #
        raise HTTPException(
            status_code=500,
            detail=f"데이터 누락 검증 실패: {e}"
        )