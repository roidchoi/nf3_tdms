# tdms_core/p3_usdms/routers/data.py
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.price_repo import PriceRepo
from p3_usdms.repositories.financial_repo import FinancialRepo
from p3_usdms.repositories.valuation_repo import ValuationRepo

router = APIRouter(prefix="/api/data", tags=["data"])

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

def get_financial_repo(pool = Depends(get_db_pool)) -> FinancialRepo:
    return FinancialRepo(pool)

def get_valuation_repo(pool = Depends(get_db_pool)) -> ValuationRepo:
    return ValuationRepo(pool)

# =================================================================
# 2. Apache Arrow 스트리밍 직렬화 헬퍼
# =================================================================
def _format_response_arrow_or_json(data: list[dict], accept_header: str | None, json_payload):
    """Accept 헤더 기반으로 Apache Arrow 또는 JSON 반환"""
    if accept_header and "arrow" in accept_header.lower():
        try:
            import pyarrow as pa
            import pyarrow.ipc as ipc
            import io
            sink = io.BytesIO()
            if data:
                normalized_data = []
                for r in data:
                    normalized_row = {}
                    for k, v in r.items():
                        if isinstance(v, (date, datetime)):
                            normalized_row[k] = v.isoformat()
                        else:
                            normalized_row[k] = v
                        # NaN/Inf 값 None 변환
                        if type(normalized_row[k]) is float and (
                            normalized_row[k] != normalized_row[k]
                            or normalized_row[k] == float('inf')
                            or normalized_row[k] == float('-inf')
                        ):
                            normalized_row[k] = None
                    normalized_data.append(normalized_row)
                
                table = pa.Table.from_pydict({k: [r[k] for r in normalized_data] for k in normalized_data[0]})
            else:
                table = pa.table({})
            writer = ipc.new_stream(sink, table.schema)
            writer.write_table(table)
            writer.close()
            sink.seek(0)
            return StreamingResponse(sink, media_type="application/vnd.apache.arrow.stream")
        except ImportError:
            # pyarrow 패키지 미설치 시 JSON으로 Fallback
            pass
    return json_payload

# =================================================================
# 3. 날짜 파싱 및 검증 헬퍼
# =================================================================
def _parse_date_range(
    start_dt: Optional[str], 
    end_dt: Optional[str], 
    default_days: int = 365,
    max_years: int = 15
) -> tuple[str, str]:
    """
    start_dt, end_dt 파싱 및 기본값 대입, 기간 Throttling 적용.
    미입력 시 기본 최근 1년(365일) 범위 지정.
    최대 max_years(15년) 초과 시 400 HTTPException 발생.
    """
    today = date.today()
    
    if not start_dt and not end_dt:
        # 둘 다 없으면 기본 최근 default_days(1년)
        start_date = today - timedelta(days=default_days)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_dt, "%Y-%m-%d").date() if start_dt else today - timedelta(days=default_days)
            end_date = datetime.strptime(end_dt, "%Y-%m-%d").date() if end_dt else today
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
            
    if (end_date - start_date) > timedelta(days=365 * max_years):
        raise HTTPException(status_code=400, detail=f"Query date range cannot exceed {max_years} years.")
        
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

# =================================================================
# 4. API 엔드포인트 구현
# =================================================================

@router.get("/tickers")
def get_tickers(
    exchange: Optional[str] = Query(None, description="Filter by exchange (e.g. NASDAQ, NYSE)"),
    is_collect_target: Optional[bool] = Query(None, description="Filter by collection target status"),
    repo: MasterRepo = Depends(get_master_repo)
) -> List[Dict[str, Any]]:
    """
    미국 주식 마스터 종목 조회 엔드포인트.
    필터 조건(exchange, is_collect_target)이 제공될 경우 필터링을 수행하며,
    미제공 시 활성화된 모든 종목(is_active=True)을 반환하여 하위 호환성을 유지합니다.
    """
    try:
        # 하위 호환성 대응: 기존 쿼리 파라미터 collect_only 지원
        return repo.get_tickers_filtered(exchange=exchange, is_collect_target=is_collect_target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve tickers: {str(e)}")

@router.get("/price/daily")
def get_daily_prices(
    request: Request,
    cik: str = Query(..., description="SEC CIK of the target company"),
    start_dt: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_dt: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    adjusted: bool = Query(False, description="Whether to apply on-the-fly stock price adjustments"),
    repo: PriceRepo = Depends(get_price_repo)
):
    """
    특정 기간의 미국 주식 일일 가격을 조회합니다.
    - adjusted=True 이면 수정계수 이력을 결합하여 온더플라이(On-the-fly) 역순 누적곱 연산을 수행합니다.
    - Throttling: 기간 미지정 시 최근 1년 범위 기본 지정, 최대 15년 조회 범위 제한.
    """
    # 1. 날짜 범위 캡 및 파싱
    parsed_start, parsed_end = _parse_date_range(start_dt, end_dt)
    
    try:
        # 2. Raw 가격 데이터 조회
        prices = repo.get_daily_prices(cik, parsed_start, parsed_end)
        
        # 3. 조정 여부에 따라 연산 수행
        if adjusted:
            factors = repo.get_price_factors(cik)
            
            # event_dt별 수정계수 맵 작성 (동일 날짜 중복 처리)
            factor_map = {}
            for f in factors:
                ed = f['event_dt']
                val = f['factor_val']
                # date 객체 타입 호환 처리
                if isinstance(ed, str):
                    ed = datetime.strptime(ed, "%Y-%m-%d").date()
                factor_map[ed] = factor_map.get(ed, 1.0) * val
                
            cum_factor = 1.0
            adjusted_records = []
            
            # 최신 날짜(Future)부터 과거 날짜(Past)로 역순 순회
            for row in reversed(prices):
                dt_val = row['dt']
                if isinstance(dt_val, str):
                    dt_val = datetime.strptime(dt_val, "%Y-%m-%d").date()
                
                # 역순 순회 중 현재 일자 가격에 cum_factor를 먼저 반영 (Ex-Date 당일/이후 가격은 보정 제외)
                adjusted_records.append({
                    "dt": dt_val.strftime("%Y-%m-%d"),
                    "cik": row['cik'],
                    "ticker": row.get('ticker', ''),
                    "open_prc": float(row.get('open_prc', 0.0) * cum_factor),
                    "high_prc": float(row.get('high_prc', 0.0) * cum_factor),
                    "low_prc": float(row.get('low_prc', 0.0) * cum_factor),
                    "cls_prc": float(row.get('cls_prc', 0.0) * cum_factor),
                    "vol": int(row.get('vol', 0)),
                    "amt": float(row.get('amt', 0.0))
                })
                
                # 현재 날짜가 Ex-Date(수정이벤트 발생일)인 경우, 이후 과거 가격 보정을 위해 cum_factor 누적 갱신
                if dt_val in factor_map:
                    cum_factor *= factor_map[dt_val]
                    
            # 다시 시간순 정렬로 원복
            adjusted_records.reverse()
            final_records = adjusted_records
        else:
            final_records = []
            for row in prices:
                item = dict(row)
                dt_val = item.get('dt')
                if dt_val:
                    item['dt'] = dt_val.strftime("%Y-%m-%d") if hasattr(dt_val, "strftime") else str(dt_val)
                for prc_col in ['open_prc', 'high_prc', 'low_prc', 'cls_prc', 'amt']:
                    if prc_col in item and item[prc_col] is not None:
                        item[prc_col] = float(item[prc_col])
                if 'vol' in item and item['vol'] is not None:
                    item['vol'] = int(item['vol'])
                final_records.append(item)
                
        # Apache Arrow 직렬화 적용 확인
        accept_header = request.headers.get("accept")
        return _format_response_arrow_or_json(prices, accept_header, final_records)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve daily prices: {str(e)}")

@router.get("/price/factors")
def get_price_factors(
    cik: str = Query(..., description="SEC CIK of the target company"),
    repo: PriceRepo = Depends(get_price_repo)
) -> List[Dict[str, Any]]:
    """
    특정 종목의 전체 가격 수정계수(Adjustment Factors) 이력을 조회합니다.
    """
    try:
        factors = repo.get_price_factors(cik)
        normalized = []
        for f in factors:
            ed_val = f['event_dt']
            ed_str = ed_val.strftime("%Y-%m-%d") if hasattr(ed_val, "strftime") else str(ed_val)
            item = {
                "cik": f["cik"],
                "event_dt": ed_str,
                "factor_val": float(f["factor_val"]),
                "event_type": f["event_type"]
            }
            if "matched_info" in f:
                item["matched_info"] = f["matched_info"]
            normalized.append(item)
        return normalized
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve price factors: {str(e)}")

@router.get("/financials")
def get_financials(
    cik: str = Query(..., description="SEC CIK of the target company"),
    pit: bool = Query(True, description="Whether to fetch Point-in-Time financials"),
    as_of: Optional[str] = Query(None, alias="as_of_date", description="Target PIT query timestamp (ISO format or YYYY-MM-DD)"),
    start_dt: Optional[str] = Query(None, description="Start date for range query (YYYY-MM-DD)"),
    end_dt: Optional[str] = Query(None, description="End date for range query (YYYY-MM-DD)"),
    repo: FinancialRepo = Depends(get_financial_repo)
):
    """
    특정 CIK의 표준화 재무 정보를 조회합니다.
    - pit=True 이면 as_of 시점 기준의 Point-in-Time 정보를 조회합니다 (기본값: 현재시각).
    - pit=False 이면 공시일(filed_dt) 기준 범위(start_dt ~ end_dt) 조회를 수행합니다.
    """
    try:
        if pit:
            # PIT 시점 파싱
            if as_of:
                try:
                    as_of_dt = datetime.fromisoformat(as_of)
                except ValueError:
                    try:
                        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d")
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid as_of date format. Use ISO format or YYYY-MM-DD.")
            else:
                as_of_dt = datetime.utcnow()
                
            statements = repo.get_standard_financials_pit(cik, as_of_dt)
        else:
            statements = repo.get_standard_financials_range(cik, start_dt, end_dt)
            
        # JSON 직렬화에 적합하게 date/datetime 필드 문자열 변환
        normalized = []
        for s in statements:
            row = dict(s)
            for k, v in row.items():
                if isinstance(v, (date, datetime)):
                    row[k] = v.isoformat()
                elif v is not None and type(v) is float and (v != v or v == float('inf') or v == float('-inf')):
                    row[k] = None
            normalized.append(row)
            
        return normalized
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve financials: {str(e)}")

@router.get("/valuation")
def get_valuation(
    request: Request,
    cik: str = Query(..., description="SEC CIK of the target company"),
    start_dt: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_dt: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    repo: ValuationRepo = Depends(get_valuation_repo)
):
    """
    특정 CIK의 일별 가치평가(PE, PB, PS, PCR, EV/EBITDA 등) 정보를 조회합니다.
    - Throttling: 기간 미지정 시 최근 1년 범위 기본 지정, 최대 15년 조회 범위 제한.
    """
    parsed_start, parsed_end = _parse_date_range(start_dt, end_dt)
    
    try:
        data = repo.get_valuations(cik, parsed_start, parsed_end)
        
        normalized = []
        for r in data:
            row = dict(r)
            for k, v in row.items():
                if isinstance(v, (date, datetime)):
                    row[k] = v.isoformat()
                elif v is not None and type(v) is float and (v != v or v == float('inf') or v == float('-inf')):
                    row[k] = None
            normalized.append(row)
            
        accept_header = request.headers.get("accept")
        return _format_response_arrow_or_json(data, accept_header, normalized)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve valuation data: {str(e)}")

@router.get("/metrics")
def get_metrics(
    request: Request,
    cik: str = Query(..., description="SEC CIK of the target company"),
    start_dt: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_dt: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    repo: ValuationRepo = Depends(get_valuation_repo)
):
    """
    특정 CIK의 재무비율(ROE, ROA, ROIC, 마진율, 부채비율, 성장률 등) 정보를 조회합니다.
    - Throttling: 기간 미지정 시 최근 1년 범위 기본 지정, 최대 15년 조회 범위 제한.
    """
    parsed_start, parsed_end = _parse_date_range(start_dt, end_dt)
    
    try:
        data = repo.get_metrics(cik, parsed_start, parsed_end)
        
        normalized = []
        for r in data:
            row = dict(r)
            for k, v in row.items():
                if isinstance(v, (date, datetime)):
                    row[k] = v.isoformat()
                elif v is not None and type(v) is float and (v != v or v == float('inf') or v == float('-inf')):
                    row[k] = None
            normalized.append(row)
            
        accept_header = request.headers.get("accept")
        return _format_response_arrow_or_json(data, accept_header, normalized)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve financial metrics: {str(e)}")


# =================================================================
# 5. 테이블 미리보기 (Preview) API 구현
# =================================================================
ALLOWED_TABLES = {
    "us_ticker_master", "us_ticker_history", "us_collection_blacklist",
    "us_financial_facts", "us_standard_financials", "us_share_history",
    "us_daily_price", "us_price_adjustment_factors", "us_daily_valuation",
    "us_financial_metrics"
}

TABLE_DATE_COLUMNS = {
    "us_daily_price": "dt",
    "us_daily_valuation": "dt",
    "us_price_adjustment_factors": "event_dt",
    "us_ticker_history": "start_dt",
    "us_financial_facts": "filed_dt",
    "us_standard_financials": "filed_dt",
    "us_share_history": "filed_dt",
    "us_financial_metrics": "filed_dt"
}

@router.get("/preview/{table}")
def get_preview_table(
    table: str,
    limit: int = Query(50, ge=1, description="Limit of rows to retrieve"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    stk_cd: Optional[str] = Query(None, description="Target stock ticker/symbol filter"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    pool = Depends(get_db_pool)
):
    """
    [T-006] 허용된 테이블에 한해 데이터 미리보기 및 페이징 조회를 제공합니다.
    - SQL Injection 방지: 테이블명 검증 및 바인딩 파라미터 적용
    - limit는 최대 1000으로 강제 제한(cap)
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not allowed for preview.")

    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")

    # 1. limit 최대 1000 Cap 설정
    limit = min(limit, 1000)

    where_clauses = []
    params = []

    # 종목 코드/CIK 필터링 (미국 주식은 테이블에 따라 ticker 또는 cik 컬럼을 가짐)
    if stk_cd:
        # us_ticker_master 등에는 latest_ticker 필드, 시세 등에는 ticker 필드나 cik 필드를 쓸 수 있음
        # 심플하게 ticker 또는 latest_ticker 등 테이블 형태에 따라 matching 처리
        if table in ["us_ticker_master"]:
            where_clauses.append("latest_ticker = %s")
        elif table in ["us_daily_price"]:
            where_clauses.append("ticker = %s")
        else:
            # 다른 테이블은 ticker가 없으므로 cik에 대한 맵핑 시도로 간주
            where_clauses.append("cik = %s")
        params.append(stk_cd)

    # 날짜 필터링
    date_col = TABLE_DATE_COLUMNS.get(table)
    if date_col:
        if start_date:
            where_clauses.append(f"{date_col} >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append(f"{date_col} <= %s")
            params.append(end_date)

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    # 정렬 방식 결정
    order_clause = ""
    if date_col:
        order_clause = f"ORDER BY {date_col} DESC"
    elif table == "us_ticker_master":
        order_clause = "ORDER BY cik ASC"

    count_query = f"SELECT COUNT(*) FROM {table} {where_str}"
    select_query = f"SELECT * FROM {table} {where_str} {order_clause} LIMIT %s OFFSET %s"

    try:
        with pool.get_cursor() as cursor:
            # 전체 개수 count 실행
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()[0]

            # 데이터 fetch 실행
            select_params = params + [limit, offset]
            cursor.execute(select_query, tuple(select_params))
            rows = cursor.fetchall()
            
            desc = cursor.description
            data = []
            for r in rows:
                row_dict = {}
                for d, val in zip(desc, r):
                    col_name = d[0]
                    if isinstance(val, (date, datetime)):
                        row_dict[col_name] = val.isoformat()
                    elif val is not None and type(val) is float and (val != val or val == float('inf') or val == float('-inf')):
                        row_dict[col_name] = None
                    else:
                        row_dict[col_name] = val
                data.append(row_dict)

            return {
                "table": table,
                "count": total_count,
                "data": data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
