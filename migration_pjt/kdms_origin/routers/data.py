# routers/data.py
#    

from fastapi import APIRouter, HTTPException, Query, Depends, Header, Response
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import date

# Apache Arrow 지원
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
import io

#import pandas as pd
from models.data_models import *
from collectors.db_manager import DatabaseManager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# --- [수정] 전역 객체 주입 (main.py에서 설정) ---
db: DatabaseManager = None
# -------------------------------------------

# --- (신규) Phase 6.3: 응답 포맷 헬퍼 (PRD 4.1.4) ---

def _format_response(
    data: List[Dict[str, Any]], 
    accept_header: Optional[str],
    pydantic_model: BaseModel, # (JSON 반환 시 사용할 Pydantic 모델)
) -> Response:
    """
    PRD 4.1.4에 따라 Accept 헤더를 기반으로
    JSON (Pydantic) 또는 Apache Arrow 스트림을 반환합니다.
    """
    
    # 1. Apache Arrow 요청 처리
    if accept_header and "arrow" in accept_header.lower():
        try:
            # (데이터가 없는 경우 빈 테이블 반환)
            if not data:
                return StreamingResponse(
                    io.BytesIO(), 
                    media_type="application/vnd.apache.arrow.stream"
                )
                
            # PRD 4.1.4 로직
            df = pd.DataFrame(data)
            table = pa.Table.from_pandas(df)
            
            sink = io.BytesIO()
            writer = ipc.new_stream(sink, table.schema)
            writer.write_table(table)
            writer.close()
            
            sink.seek(0)
            return StreamingResponse(
                sink,
                media_type="application/vnd.apache.arrow.stream"
            )
        except Exception as e:
            logger.error(f"Arrow 스트림 생성 실패: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Arrow 스트림 생성 실패: {e}")

    # 2. JSON (기본값) 요청 처리
    # (Pydantic 모델로 감싸서 반환)
    return pydantic_model

@router.get(
    "/stocks",
    response_model=StockListResponse,
    summary="KOSPI/KOSDAQ 전 종목 정보 조회"
)
def get_stock_list(
    market: Optional[str] = Query(None, enum=["KOSPI", "KOSDAQ"]),
    status: Optional[str] = Query("listed", enum=["listed", "delisted"]),
):
    """
    PRD 섹션 3.2.1: KOSPI/KOSDAQ 전 종목 정보를 조회합니다.
    main.py에서 주입된 전역 db 객체를 사용합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
    
    # 1. 동적 SQL 쿼리 빌드
    query = "SELECT stk_cd, stk_nm, market_type, list_dt, status FROM stock_info"
    conditions = []
    params = []

    if status:
        conditions.append("status = %s")
        params.append(status)
    
    if market:
        conditions.append("market_type = %s")
        params.append(market)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY stk_cd;"

    try:
        # 2. db._execute_query 호출
        # (data_manager_소스코드.md에 따르면 fetch='all'은 dict 리스트를 반환)
        results = db._execute_query(query, tuple(params), fetch='all')

        # 3. PRD 3.2.1 형식으로 응답
        return {
            "total": len(results),
            "stocks": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"종목 정보 조회 실패: {e}"
        )

# --- Phase 6.3: (Anti-Pandas) 일봉 시세 데이터 ---

@router.get(
    "/ohlcv/daily/{stk_cd}",
    #response_model=OhlcvResponse, (동적 반환)
    summary="특정 종목 일봉 데이터 조회 (수정주가 지원)"
)
def get_daily_ohlcv(
    stk_cd: str,
    start_date: date = Query(..., description="YYYY-MM-DD 형식의 시작일"),
    end_date: date = Query(date.today(), description="YYYY-MM-DD 형식의 종료일"),
    adjusted: bool = Query(False, description="True: 수정주가, False: 원본주가 (기본값)"),
    accept: Optional[str] = Header(None) # (신규) Accept 헤더
):
    """
    PRD 섹션 3.2.2: 특정 종목의 일봉 데이터를 조회합니다.
    - adjusted=False: 'daily_ohlcv' 테이블에서 원본 데이터를 반환합니다.
    - adjusted=True: PRD 8.2.1에 따라
      DB에서 직접 계산된(get_adjusted_ohlcv_data) 결과를 반환합니다. 
    - 'pandas'를 사용하지 않아 메모리 팽창을 방지합니다.
      
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
    
    try:
        data = []
        
        if adjusted:
            # 1. (Anti-Pandas) SQL에서 직접 계산된 수정주가 호출
            data = db.get_adjusted_ohlcv_data(stk_cd, start_date, end_date)
        else:
            # 2. (원본) 기존 원본주가 호출
            data = db.get_ohlcv_data(
                table_name='daily_ohlcv',
                start_date=start_date,
                end_date=end_date,
                symbols=[stk_cd]
            )

        if not data:
            raise HTTPException(status_code=404, detail="요청 기간에 해당하는 시세 데이터가 없습니다.")

        # (stk_nm은 첫 번째 결과에서 가져옴)
        stk_nm = data[0].get('stk_nm', stk_cd)

        # (수정) JSON/Arrow 헬퍼 호출
        return _format_response(
            data,
            accept,
            OhlcvResponse(
                stk_cd=stk_cd,
                stk_nm=stk_nm,
                period=OhlcvPeriod(start=start_date, end=end_date),
                data=data
            )
        )
        
    except Exception as e:
        logger.error(f"[{stk_cd}] 시세 조회 실패 (adjusted={adjusted}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"시세 데이터 조회/계산 실패: {e}"
        )

# --- (신규) Phase 6.3: 분봉 시세 데이터 (수정주가 지원) ---

@router.get(
    "/ohlcv/minute/{stk_cd}",
    # response_model=MinuteOhlcvResponse, (동적 반환)
    summary="특정 종목 분봉 데이터 조회 (수정주가, Arrow 지원)"
)
def get_minute_ohlcv(
    stk_cd: str,
    start_date: date = Query(..., description="YYYY-MM-DD 형식의 시작일"),
    end_date: date = Query(date.today(), description="YYYY-MM-DD 형식의 종료일"),
    adjusted: bool = Query(False, description="True: 수정주가, False: 원본주가 (기본값)"),
    accept: Optional[str] = Header(None) # (신규) Accept 헤더
):
    """
    PRD 섹션 3.2.2: 특정 종목의 분봉 데이터를 조회합니다.
    - [수정] 모델 학습 왜곡 방지를 위해 'adjusted=True'를 지원합니다.
    - adjusted=True일 때, 신규 SQL 함수를 호출하여 DB에서 직접 계산합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
        
    try:
        data = []
        
        if adjusted:
            # 1. (Anti-Pandas) SQL에서 직접 계산된 "분봉" 수정주가 호출
            data = db.get_adjusted_minute_ohlcv_data(stk_cd, start_date, end_date)
        else:
            # 2. (원본) 기존 원본 분봉 호출
            data = db.get_ohlcv_data(
                table_name='minute_ohlcv',
                start_date=start_date,
                end_date=end_date,
                symbols=[stk_cd]
            )

        if not data:
            raise HTTPException(status_code=404, detail="요청 기간에 해당하는 분봉 데이터가 없습니다.")

        stk_nm = data[0].get('stk_nm', stk_cd)

        # (수정) JSON/Arrow 헬퍼 호출
        return _format_response(
            data,
            accept,
            MinuteOhlcvResponse(
                stk_cd=stk_cd,
                stk_nm=stk_nm,
                period=OhlcvPeriod(start=start_date, end=end_date),
                data=data
            )
        )
        
    except Exception as e:
        logger.error(f"[{stk_cd}] 분봉 시세 조회 실패 (adjusted={adjusted}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"분봉 시세 데이터 조회/계산 실패: {e}"
        )
    
# --- (신규) Phase 6.3: v3 퀀트 스크리닝 API (POST) ---

# (SQL Injection 방지를 위한 허용 리스트)
ALLOWED_FIELDS = {
    'stk_cd', 'stk_nm', 'pit_cls_prc', 'pbr', 'per', 'cras', 'fxas', 
    'total_aset', 'flow_lblt', 'fix_lblt', 'total_lblt', 'cpfn', 'total_cptl', 
    'sale_account', 'sale_cost', 'sale_totl_prfi', 'bsop_prti', 'op_prfi', 
    'thtr_ntin', 'grs', 'bsop_prfi_inrt', 'ntin_inrt', 'roe_val', 'eps', 
    'sps', 'bps', 'rsrv_rate', 'lblt_rate', 'cptl_ntin_rate', 
    'self_cptl_ntin_inrt', 'sale_ntin_rate', 'sale_totl_rate', 'eva', 
    'ebitda', 'ev_ebitda', 'bram_depn', 'crnt_rate', 'quck_rate', 
    'equt_inrt', 'totl_aset_inrt'
}

OPERATOR_MAP = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "=",
    "neq": "!="
}

def _build_screening_query(request: ScreeningRequest) -> tuple[str, Dict[str, Any]]:
    """
    v3 ScreeningRequest를 기반으로 안전한 동적 SQL 쿼리를 생성합니다.
    """
    
    # 1. Base Criteria 파라미터
    params = {
        "stac_yymm": request.base_criteria.stac_yymm,
        "market": request.base_criteria.market,
        "pit_date": request.base_criteria.pit_date
    }
    
    # 2. CTE 1: latest_versions (필터 동적 생성)
    filter_clauses = []
    for i, f in enumerate(request.filters):
        if f.field not in ALLOWED_FIELDS:
            raise ValueError(f"허용되지 않는 필터 필드입니다: {f.field}")
        if f.operator not in OPERATOR_MAP:
            raise ValueError(f"허용되지 않는 필터 연산자입니다: {f.operator}")
        
        # (SQL Injection 방지: 파라미터 바인딩)
        param_name = f"filter_val_{i}"
        filter_clauses.append(f"{f.field} {OPERATOR_MAP[f.operator]} %({param_name})s")
        params[param_name] = f.value
        
    where_clause = " AND ".join(filter_clauses) if filter_clauses else "1=1"

    # 3. CTE 2: ranked_factors (랭킹 동적 생성)
    rank_clauses = []
    for f in request.ranking_strategy.factors:
        if f.field not in ALLOWED_FIELDS:
            raise ValueError(f"허용되지 않는 랭킹 필드입니다: {f.field}")
        
        order = "DESC" if f.order.lower() == "desc" else "ASC"
        # (예: RANK() OVER (ORDER BY pbr ASC NULLS LAST) AS rank_pbr)
        rank_clauses.append(
            f"RANK() OVER (ORDER BY {f.field} {order} NULLS LAST) AS rank_{f.field}"
        )
    
    rank_select = ", " + ", ".join(rank_clauses) if rank_clauses else ""

    # 4. Final SELECT: combined_score (가중치 동적 생성)
    score_clauses = []
    for f in request.ranking_strategy.factors:
        # (예: (0.5 * rank_pbr))
        score_clauses.append(f"({f.weight} * rank_{f.field})")
    
    combined_score_calc = " + ".join(score_clauses) if score_clauses else "0"
    final_order = "DESC" if request.ranking_strategy.final_order.lower() == "desc" else "ASC"
    
    # 5. LIMIT 파라미터
    params["limit"] = request.ranking_strategy.limit

    # 6. 전체 쿼리 조합
    query = f"""
    WITH latest_versions AS (
        SELECT DISTINCT ON (fs.stk_cd)
            fs.stk_cd, si.stk_nm,
            
            -- PBR/PER 계산
            price.cls_prc AS pit_cls_prc,
            (price.cls_prc / NULLIF(fr.bps, 0)) AS pbr,
            (price.cls_prc / NULLIF(fr.eps, 0)) AS per,

            -- financial_statements
            fs.cras, fs.fxas, fs.total_aset, fs.flow_lblt, fs.fix_lblt, 
            fs.total_lblt, fs.cpfn, fs.total_cptl, fs.sale_account, 
            fs.sale_cost, fs.sale_totl_prfi, fs.bsop_prti, fs.op_prfi, fs.thtr_ntin,
            
            -- financial_ratios
            fr.grs, fr.bsop_prfi_inrt, fr.ntin_inrt, fr.roe_val, fr.eps,
            fr.sps, fr.bps, fr.rsrv_rate, fr.lblt_rate, fr.cptl_ntin_rate,
            fr.self_cptl_ntin_inrt, fr.sale_ntin_rate, fr.sale_totl_rate,
            fr.eva, fr.ebitda, fr.ev_ebitda, fr.bram_depn, fr.crnt_rate,
            fr.quck_rate, fr.equt_inrt, fr.totl_aset_inrt
        FROM
            financial_statements fs
        JOIN
            financial_ratios fr 
                ON fs.stk_cd = fr.stk_cd 
                AND fs.stac_yymm = fr.stac_yymm
                AND fs.div_cls_code = fr.div_cls_code
        JOIN
            stock_info si ON fs.stk_cd = si.stk_cd
        LEFT JOIN LATERAL (
            SELECT cls_prc FROM daily_ohlcv
            WHERE stk_cd = fs.stk_cd AND dt <= %(pit_date)s
            ORDER BY dt DESC LIMIT 1
        ) price ON true
        WHERE
            fs.stac_yymm = %(stac_yymm)s
            AND fs.div_cls_code = '1'
            AND si.market_type = %(market)s
            AND fs.retrieved_at <= %(pit_date)s
            AND fr.retrieved_at <= %(pit_date)s
        ORDER BY
            fs.stk_cd, fs.retrieved_at DESC, fr.retrieved_at DESC
    ),
    ranked_factors AS (
        SELECT 
            *
            {rank_select}
        FROM latest_versions
        WHERE {where_clause} -- (필터는 랭킹 전에 적용)
    )
    SELECT
        *,
        ( {combined_score_calc} ) AS combined_score
    FROM
        ranked_factors
    ORDER BY
        combined_score {final_order} NULLS LAST
    LIMIT %(limit)s;
    """
    
    return query, params


@router.post(
    "/financials/screening",
    # (response_model 제거 -> 동적 반환)
    summary="v3 퀀트 스크리닝 (마법공식/가중치/필터 지원)"
)
def post_financial_screening(
    request: ScreeningRequest, # (POST Body)
    accept: Optional[str] = Header(None)
):
    """
    PRD 3.2.3 고도화: '마법공식'과 '다중 필터'를 지원하는
    v3 퀀트 스크리닝 API (POST)
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
        
    try:
        # 1. 동적 쿼리 및 파라미터 생성
        query, params = _build_screening_query(request)
        
        # 2. 쿼리 실행
        data = db._execute_query(query, params, fetch='all')

        # 3. JSON/Arrow 헬퍼 호출
        return _format_response(
            data,
            accept,
            FinancialScreeningResponse(
                screening=ScreeningMetadata(
                    base_criteria=request.base_criteria,
                    filters_applied=len(request.filters),
                    ranking_factors=len(request.ranking_strategy.factors),
                    total_stocks=len(data)
                ),
                data=data
            )
        )

    except ValueError as ve: # (안전하지 않은 필드/연산자)
        logger.warning(f"[Screening] 잘못된 요청: {ve}")
        raise HTTPException(status_code=400, detail=f"잘못된 요청: {ve}")
    except Exception as e:
        logger.error(f"[Screening] v3 재무 스크리닝 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"재무 스크리닝 실패: {e}")


# --- (신규) Phase 6.3: 수정계수 API (PRD 3.2.4) ---
@router.get(
    "/factors/{stk_cd}",
    # (response_model 제거 -> 동적 반환)
    summary="특정 종목의 수정계수 이력 조회 (Arrow 지원)"
)
def get_adjustment_factors(
    stk_cd: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    accept: Optional[str] = Header(None) # (신규) Accept 헤더
):
    """
    PRD 3.2.4: 특정 종목의 가격 수정계수 이력을 조회합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")

    # (날짜 기본값 설정)
    if not start_date:
        start_date = date(1980, 1, 1)
    if not end_date:
        end_date = date.today()
        
    try:
        # (stock_nm을 위해 stock_info 조회)
        stock_info = db._execute_query(
            "SELECT stk_nm FROM stock_info WHERE stk_cd = %s",
            (stk_cd,),
            fetch='one'
        )
        stk_nm = stock_info['stk_nm'] if stock_info else stk_cd
        
        # (data_manager.get_factors_by_date_range는 컬럼이 부족하므로
        #  PRD 3.2.4에 맞는 쿼리 직접 실행)
        query = """
            SELECT event_dt, price_ratio, volume_ratio, 
                   price_source, effective_dt, details
            FROM price_adjustment_factors
            WHERE stk_cd = %s
              AND event_dt BETWEEN %s AND %s
            ORDER BY event_dt DESC;
        """
        data = db._execute_query(query, (stk_cd, start_date, end_date), fetch='all')

        # JSON/Arrow 헬퍼 호출
        return _format_response(
            data,
            accept,
            FactorResponse(
                stk_cd=stk_cd,
                stk_nm=stk_nm,
                factors=data
            )
        )
    
    except Exception as e:
        logger.error(f"[{stk_cd}] 수정계수 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"수정계수 조회 실패: {e}")

# [신규] 데이터 탐색기 API (Whitelist 기반 동적 조회)
ALLOWED_TABLES = {
    "daily_ohlcv", 
    "minute_ohlcv", 
    "financial_statements", 
    "financial_ratios",
    "stock_info", 
    "price_adjustment_factors",
    "minute_target_history",
    "system_milestones",
    "trading_calendar"
}

@router.get(
    "/preview/{table_name}",
    summary="[Phase 7.8] 데이터 탐색기용 동적 테이블 조회"
)
def preview_table_data(
    table_name: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    stk_cd: Optional[str] = Query(None, description="종목코드 필터"),
    start_date: Optional[date] = Query(None, description="조회 시작일"),
    end_date: Optional[date] = Query(None, description="조회 종료일"),
    quarter: Optional[str] = Query(None, description="분기 필터 (예: 2025Q1) - target_history용")
):
    """
    테이블 성격에 따라 최적화된 필터링을 적용하여 Raw Data를 조회합니다.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")
    
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 테이블입니다. ({table_name})")
    
    try:
        query = f"SELECT * FROM {table_name}"
        conditions = []
        params = []

        # --- [로직 분기 1] 타겟 이력 (분기 기준 조회) ---
        if table_name == "minute_target_history":
            if quarter:
                conditions.append("quarter = %s")
                params.append(quarter)
            # (종목 구분 없이 조회하므로 stk_cd 필터 생략하거나 원하면 추가 가능)
            # 사용자 요청: "종목 구분 없이 해당 분기 정보 필터링" -> stk_cd 조건 제외
            query += " WHERE " + " AND ".join(conditions) if conditions else ""
            query += " ORDER BY rank ASC" # 순위순 정렬

        # --- [로직 분기 2] 재무 정보 (종목 기준 전체 조회) ---
        elif table_name.startswith("financial_"):
            if stk_cd:
                conditions.append("stk_cd = %s")
                params.append(stk_cd)
            
            # 사용자 요청: "기간 구분 없이 전체 데이터" -> 날짜 필터 제외
            query += " WHERE " + " AND ".join(conditions) if conditions else ""
            # 정렬: 최신 데이터 우선
            query += " ORDER BY stac_yymm DESC, retrieved_at DESC"

        # --- [로직 분기 3] 일반 시세/정보 (종목 + 날짜 조회) ---
        else:
            # 1. 종목 필터
            if stk_cd and table_name not in ["system_milestones", "trading_calendar"]:
                conditions.append("stk_cd = %s")
                params.append(stk_cd)
            
            # 2. 날짜 필터 (테이블별 컬럼 매핑)
            date_col = None
            if table_name == "daily_ohlcv": date_col = "dt"
            elif table_name == "minute_ohlcv": date_col = "dt_tm"
            elif table_name == "system_milestones": date_col = "milestone_date"
            elif table_name == "price_adjustment_factors": date_col = "event_dt"
            elif table_name == "trading_calendar": date_col = "dt"
            
            if date_col and start_date and end_date:
                conditions.append(f"{date_col} BETWEEN %s AND %s")
                params.extend([start_date, end_date])

            query += " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 정렬
            if date_col:
                query += f" ORDER BY {date_col} DESC"
            elif table_name == "stock_info":
                query += " ORDER BY stk_cd"

        # 공통: 페이징
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        results = db._execute_query(query, tuple(params), fetch='all')
        
        return {
            "table": table_name,
            "count": len(results),
            "data": results
        }
        
    except Exception as e:
        logger.error(f"Data preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- [신규] Phase KIS-1: 수정주가 일봉 DB 직접 조회 엔드포인트 ---

@router.get(
    "/ohlcv/adjusted/{stk_cd}",
    summary="수정주가 일봉 DB 직접 조회 (daily_ohlcv_adjusted 물리 테이블)"
)
def get_adjusted_ohlcv_direct(
    stk_cd: str,
    start_date: date = Query(..., description="YYYY-MM-DD 형식의 시작일"),
    end_date: date = Query(date.today(), description="YYYY-MM-DD 형식의 종료일"),
    accept: Optional[str] = Header(None)
):
    """
    daily_ohlcv_adjusted 물리화 테이블을 직접 조회하여 수정주가 일봉을 반환합니다.

    - GET /ohlcv/daily/{stk_cd}?adjusted=true 와 동일한 결과를 반환하나,
      SQL CTE 계산 없이 미리 저장된 값을 조회하므로 응답 속도가 빠릅니다.
    - adj_factor 컬럼: 해당 날짜에 적용된 누적 수정계수 (감사 추적용)
    - 데이터가 없을 경우 404 반환.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB 매니저가 초기화되지 않았습니다.")

    try:
        query = """
            SELECT
                a.dt,
                a.stk_cd,
                si.stk_nm,
                a.open_prc,
                a.high_prc,
                a.low_prc,
                a.cls_prc,
                a.vol,
                a.adj_factor,
                a.updated_at
            FROM daily_ohlcv_adjusted a
            JOIN stock_info si USING (stk_cd)
            WHERE a.stk_cd = %s
              AND a.dt BETWEEN %s AND %s
            ORDER BY a.dt ASC;
        """
        data = db._execute_query(query, (stk_cd, start_date, end_date), fetch='all')

        if not data:
            raise HTTPException(
                status_code=404,
                detail="요청 기간에 해당하는 수정주가 데이터가 없습니다. "
                       "daily_task 실행 또는 build_adjusted_ohlcv.py 초기 구축 여부를 확인하세요."
            )

        stk_nm = data[0].get('stk_nm', stk_cd)

        return _format_response(
            data,
            accept,
            OhlcvResponse(
                stk_cd=stk_cd,
                stk_nm=stk_nm,
                period=OhlcvPeriod(start=start_date, end=end_date),
                data=data
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{stk_cd}] 수정주가 DB 직접 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"수정주가 조회 실패: {e}")