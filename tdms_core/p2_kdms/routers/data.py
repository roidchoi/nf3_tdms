# routers/data.py

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

from repositories.master_repo import MasterRepo
from repositories.factor_repo import FactorRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.financial_repo import FinancialRepo
from repositories.market_cap_repo import MarketCapRepo
from repositories.investor_trade_repo import InvestorTradeRepo
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

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

def get_market_cap_repo(pool = Depends(get_db_pool)) -> MarketCapRepo:
    return MarketCapRepo(pool)

def get_investor_trade_repo(pool = Depends(get_db_pool)) -> InvestorTradeRepo:
    return InvestorTradeRepo(pool)


class ScreeningFilter(BaseModel):
    field: str
    operator: str
    value: float

class ScreeningParams(BaseModel):
    stac_yymm: str
    div_cls_code: str = "1"
    as_of_date: str | None = None
    filters: List[ScreeningFilter] = Field(default_factory=list)
    limit: int = 50


def _format_response_arrow_or_json(data: list[dict], accept_header: str | None, json_payload):
    """Accept 헤더 기반으로 Apache Arrow 또는 JSON 반환"""
    if accept_header and "arrow" in accept_header.lower():
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
                    # float 값 직렬화 시 pyarrow 에러 방지 위해 float 처리
                    if type(normalized_row[k]) is float and (normalized_row[k] != normalized_row[k] or normalized_row[k] == float('inf') or normalized_row[k] == float('-inf')):
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
    return json_payload



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
    as_of: str = Query(None, alias="as_of_date", description="특정 PIT 조회 시점 (ISO 형식: YYYY-MM-DDTHH:MM:SS+TZ 또는 YYYY-MM-DD)"),
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


@router.get("/ohlcv/daily")
def get_ohlcv_daily(
    stk_cd: str = Query(..., description="종목 코드"),
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    adjusted: bool = Query(False, description="수정주가 여부"),
    price_source: str = Query("KIS", description="시세 출처"),
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo),
    factor_repo: FactorRepo = Depends(get_factor_repo)
):
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if adjusted:
        return get_adjusted_ohlcv_daily(stk_cd, start_date, end_date, price_source, ohlcv_repo, factor_repo)
    else:
        try:
            records = ohlcv_repo.get_daily_ohlcv(stk_cd, start_dt, end_dt)
            for r in records:
                if hasattr(r["dt"], "strftime"):
                    r["dt"] = r["dt"].strftime("%Y-%m-%d")
                else:
                    r["dt"] = str(r["dt"])
            return records
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve daily ohlcv: {str(e)}")


@router.get("/ohlcv/minute")
def get_ohlcv_minute(
    request: Request,
    stk_cd: str = Query(..., description="종목 코드"),
    start_dt: str = Query(..., description="시작 일시 (ISO 형식 또는 YYYY-MM-DD)"),
    end_dt: str = Query(..., description="종료 일시 (ISO 형식 또는 YYYY-MM-DD)"),
    ohlcv_repo: OhlcvRepo = Depends(get_ohlcv_repo)
):
    try:
        try:
            start = datetime.fromisoformat(start_dt)
            end = datetime.fromisoformat(end_dt)
        except ValueError:
            from zoneinfo import ZoneInfo
            kst = ZoneInfo("Asia/Seoul")
            start = datetime.strptime(start_dt, "%Y-%m-%d").replace(tzinfo=kst)
            end = datetime.strptime(end_dt, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=kst)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO format or YYYY-MM-DD.")

    if end - start > timedelta(days=30):
        raise HTTPException(status_code=400, detail="분봉 조회는 최대 30일 범위까지 가능합니다")

    try:
        data = ohlcv_repo.get_minute_ohlcv(stk_cd, start, end)
        
        json_data = []
        for r in data:
            row = dict(r)
            if hasattr(row["dt_tm"], "isoformat"):
                row["dt_tm"] = row["dt_tm"].isoformat()
            else:
                row["dt_tm"] = str(row["dt_tm"])
            json_data.append(row)
            
        accept_header = request.headers.get("accept")
        return _format_response_arrow_or_json(data, accept_header, json_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve minute ohlcv: {str(e)}")


@router.get("/market-cap")
def get_market_cap(
    stk_cd: str = Query(..., description="종목 코드"),
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    market_cap_repo: MarketCapRepo = Depends(get_market_cap_repo)
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        records = market_cap_repo.get_daily_market_cap(stk_cd, start, end)
        for r in records:
            if hasattr(r["dt"], "strftime"):
                r["dt"] = r["dt"].strftime("%Y-%m-%d")
            else:
                r["dt"] = str(r["dt"])
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve market cap: {str(e)}")


@router.get("/investor-trade/daily")
def get_investor_trade_daily(
    request: Request,
    stk_cd: str = Query(..., description="종목 코드"),
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    investor_trade_repo: InvestorTradeRepo = Depends(get_investor_trade_repo)
):
    """
    한국 주식 특정 종목의 지정 기간 내 일별 투자자 매매동향(수급) 데이터를 오름차순으로 반환합니다.
    헤더의 Accept: application/vnd.apache.arrow.stream 지정 시 Apache Arrow 스트리밍 응답을 제공합니다.
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        records = investor_trade_repo.get_daily_investor_trade(stk_cd, start, end)
        
        json_data = []
        for r in records:
            row = dict(r)
            if hasattr(row["dt"], "strftime"):
                row["dt"] = row["dt"].strftime("%Y-%m-%d")
            else:
                row["dt"] = str(row["dt"])
            json_data.append(row)
            
        accept_header = request.headers.get("accept")
        return _format_response_arrow_or_json(records, accept_header, json_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve daily investor trade: {str(e)}")


@router.post("/screening")
def post_screening(
    params: ScreeningParams,
    financial_repo: FinancialRepo = Depends(get_financial_repo)
):
    limit = min(params.limit, 500)
    
    from zoneinfo import ZoneInfo
    kst = ZoneInfo("Asia/Seoul")
    if params.as_of_date:
        try:
            try:
                as_of_dt = datetime.fromisoformat(params.as_of_date)
            except ValueError:
                as_of_dt = datetime.strptime(params.as_of_date, "%Y-%m-%d").replace(tzinfo=kst)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid as_of_date format. Use ISO format or YYYY-MM-DD.")
    else:
        as_of_dt = datetime.now(kst)

    filters_dict = [f.model_dump() for f in params.filters]

    try:
        records = financial_repo.screen_stocks(
            stac_yymm=params.stac_yymm,
            div_cls_code=params.div_cls_code,
            as_of_date=as_of_dt,
            filters=filters_dict,
            limit=limit
        )
        for r in records:
            if r.get("retrieved_at") and hasattr(r["retrieved_at"], "isoformat"):
                r["retrieved_at"] = r["retrieved_at"].isoformat()
        return records
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screening execution failed: {str(e)}")


ALLOWED_TABLES = {
    "daily_ohlcv", "daily_ohlcv_adjusted", "daily_market_cap", "minute_ohlcv",
    "financial_statements", "financial_ratios", "price_adjustment_factors",
    "stock_info", "system_milestones", "trading_calendar", "minute_target_history",
    "daily_investor_trade"
}

TABLE_DATE_COLUMNS = {
    "daily_ohlcv": "dt",
    "daily_ohlcv_adjusted": "dt",
    "minute_ohlcv": "dt_tm",
    "daily_market_cap": "dt",
    "price_adjustment_factors": "event_dt",
    "system_milestones": "milestone_date",
    "daily_investor_trade": "dt"
}

TABLE_FILTER_COLUMNS = {
    "minute_target_history": {
        "stk_cd": "symbol",
        "quarter": "quarter",
        "market": "market"
    },
    "stock_info": {
        "stk_cd": "stk_cd",
        "market": "market_type"
    },
    "daily_ohlcv": {
        "stk_cd": "stk_cd"
    },
    "daily_ohlcv_adjusted": {
        "stk_cd": "stk_cd"
    },
    "daily_market_cap": {
        "stk_cd": "stk_cd"
    },
    "minute_ohlcv": {
        "stk_cd": "stk_cd"
    },
    "financial_statements": {
        "stk_cd": "stk_cd",
        "quarter": "stac_yymm"
    },
    "financial_ratios": {
        "stk_cd": "stk_cd",
        "quarter": "stac_yymm"
    },
    "price_adjustment_factors": {
        "stk_cd": "stk_cd"
    },
    "daily_investor_trade": {
        "stk_cd": "stk_cd"
    }
}

@router.get("/preview/{table}")
def get_preview_table(
    table: str,
    limit: int = Query(50, ge=1, description="조회 레코드 제한"),
    offset: int = Query(0, ge=0, description="페이지네이션 오프셋"),
    stk_cd: str | None = Query(None, description="종목 코드 필터"),
    start_date: str | None = Query(None, description="시작 날짜 필터 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="종료 날짜 필터 (YYYY-MM-DD)"),
    quarter: str | None = Query(None, description="분기/결산연월 필터"),
    market: str | None = Query(None, description="시장 구분 필터"),
    keyword: str | None = Query(None, description="종목명/종목코드 검색 키워드"),
    match_type: str = Query("contains", description="검색 매칭 방식 (contains | exact)"),
    search_field: str = Query("all", description="검색 대상 필드 (all | code | name)"),
    pool = Depends(get_db_pool)
):
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not allowed for preview.")

    if not pool:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")

    limit = min(limit, 1000)

    where_clauses = []
    params = []

    applied_quarter = None
    if table == "minute_target_history":
        # 사용자가 stk_cd를 명시적으로 검색하고, quarter를 입력하지 않은 경우에는
        # 전체 분기를 다 조회할 수 있도록 quarter 조건을 생략한다.
        if stk_cd and not quarter:
            pass
        else:
            if not quarter:
                try:
                    with pool.get_cursor() as cursor:
                        cursor.execute("SELECT MAX(quarter) FROM minute_target_history")
                        row = cursor.fetchone()
                        if row and row[0]:
                            applied_quarter = row[0]
                except Exception:
                    pass
                
                if applied_quarter:
                    where_clauses.append("quarter = %s")
                    params.append(applied_quarter)
            else:
                applied_quarter = quarter
                where_clauses.append("quarter = %s")
                params.append(quarter)

    # 키워드 검색 (stock_info 테이블인 경우)
    if table == "stock_info" and keyword:
        kw_pattern = keyword if match_type == "exact" else f"%{keyword}%"
        operator = "=" if match_type == "exact" else "LIKE"
        
        if search_field == "code":
            where_clauses.append(f"stk_cd {operator} %s")
            params.append(kw_pattern)
        elif search_field == "name":
            where_clauses.append(f"stk_nm {operator} %s")
            params.append(kw_pattern)
        else: # all
            where_clauses.append(f"(stk_cd {operator} %s OR stk_nm {operator} %s)")
            params.extend([kw_pattern, kw_pattern])

    filters = TABLE_FILTER_COLUMNS.get(table, {})
    for filter_param, col_name in filters.items():
        if table == "minute_target_history" and filter_param == "quarter":
            continue
        
        if filter_param == "stk_cd" and stk_cd:
            where_clauses.append(f"{col_name} = %s")
            params.append(stk_cd)
        elif filter_param == "quarter" and quarter:
            where_clauses.append(f"{col_name} = %s")
            params.append(quarter)
        elif filter_param == "market" and market:
            where_clauses.append(f"{col_name} = %s")
            params.append(market)

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

    order_clause = ""
    if table == "minute_target_history":
        order_clause = "ORDER BY quarter DESC, market DESC, rank DESC"
    elif date_col:
        order_clause = f"ORDER BY {date_col} DESC"
    elif table == "stock_info":
        order_clause = "ORDER BY stk_cd ASC"

    count_query = f"SELECT COUNT(*) FROM {table} {where_str}"
    select_query = f"SELECT * FROM {table} {where_str} {order_clause} LIMIT %s OFFSET %s"

    try:
        with pool.get_cursor() as cursor:
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            select_params = params + [limit, offset]
            cursor.execute(select_query, select_params)
            rows = cursor.fetchall()
            
            desc = cursor.description
            data = []
            for r in rows:
                row_dict = {}
                for d, val in zip(desc, r):
                    col_name = d[0]
                    if isinstance(val, (date, datetime)):
                        row_dict[col_name] = val.isoformat()
                    else:
                        row_dict[col_name] = val
                data.append(row_dict)

            resp_obj = {
                "table": table,
                "count": total_count,
                "data": data
            }
            if applied_quarter is not None:
                resp_obj["applied_quarter"] = applied_quarter
            return resp_obj
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


