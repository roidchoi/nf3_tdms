# repositories/financial_repo.py

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional
from p1_shared.db.connection import DbConnectionPool

KST = ZoneInfo("Asia/Seoul")
HISTORICAL_CUTOFF = datetime(2025, 11, 8, 0, 0, tzinfo=KST)

class FinancialRepo:
    """financial_statements 및 financial_ratios 테이블 관리를 위한 Point-in-Time 저장소 클래스."""

    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def _row_to_dict(self, cursor, row) -> Optional[Dict[str, Any]]:
        """DB 튜플 결과를 컬럼명 기반 딕셔너리로 변환합니다."""
        if row is None:
            return None
        return {desc[0]: val for desc, val in zip(cursor.description, row)}

    def get_latest_statement(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]:
        """
        stk_cd, stac_yymm, div_cls_code 기준 DB에 가장 최근(retrieved_at DESC) 저장된 재무제표 레코드를 반환합니다.
        """
        query = """
            SELECT * FROM financial_statements
            WHERE stk_cd = %s AND stac_yymm = %s AND div_cls_code = %s
            ORDER BY retrieved_at DESC
            LIMIT 1;
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, stac_yymm, div_cls_code))
            row = cursor.fetchone()
            return self._row_to_dict(cursor, row)

    def get_latest_ratio(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]:
        """
        stk_cd, stac_yymm, div_cls_code 기준 DB에 가장 최근(retrieved_at DESC) 저장된 재무비율 레코드를 반환합니다.
        """
        query = """
            SELECT * FROM financial_ratios
            WHERE stk_cd = %s AND stac_yymm = %s AND div_cls_code = %s
            ORDER BY retrieved_at DESC
            LIMIT 1;
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, stac_yymm, div_cls_code))
            row = cursor.fetchone()
            return self._row_to_dict(cursor, row)

    def insert_statements(self, statements: List[Dict[str, Any]]) -> int:
        """
        financial_statements 테이블에 PIT 버전 데이터를 일괄 INSERT합니다.
        """
        if not statements:
            return 0

        columns = [
            'stk_cd', 'stac_yymm', 'div_cls_code', 'cras', 'fxas', 'total_aset', 
            'flow_lblt', 'fix_lblt', 'total_lblt', 'cpfn', 'total_cptl', 
            'sale_account', 'sale_cost', 'sale_totl_prfi', 'bsop_prti', 'op_prfi', 'thtr_ntin'
        ]
        
        query = f"""
            INSERT INTO financial_statements ({', '.join(columns)}) 
            VALUES ({', '.join(['%s'] * len(columns))})
        """
        
        data = [
            tuple(item.get(col) for col in columns)
            for item in statements
        ]

        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)
            return cursor.rowcount

    def insert_ratios(self, ratios: List[Dict[str, Any]]) -> int:
        """
        financial_ratios 테이블에 PIT 버전 데이터를 일괄 INSERT합니다.
        """
        if not ratios:
            return 0

        columns = [
            'stk_cd', 'stac_yymm', 'div_cls_code', 'grs', 'bsop_prfi_inrt', 
            'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps', 'rsrv_rate', 'lblt_rate', 
            'cptl_ntin_rate', 'self_cptl_ntin_inrt', 'sale_ntin_rate', 'sale_totl_rate', 
            'eva', 'ebitda', 'ev_ebitda', 'bram_depn', 'crnt_rate', 'quck_rate', 
            'equt_inrt', 'totl_aset_inrt'
        ]

        query = f"""
            INSERT INTO financial_ratios ({', '.join(columns)}) 
            VALUES ({', '.join(['%s'] * len(columns))})
        """

        data = [
            tuple(item.get(col) for col in columns)
            for item in ratios
        ]

        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)
            return cursor.rowcount

    def get_statements_as_of(self, stk_cd: str, div_cls_code: str, as_of_date: datetime) -> List[Dict[str, Any]]:
        """
        특정 시점(as_of_date) 기준으로 유효한 재무제표 스냅샷 데이터를 
        각 결산년월(stac_yymm) 별로 가장 최신 버전을 선택하여 내림차순(stac_yymm DESC)으로 반환합니다.
        
        과거 대량 수집일(2025-11-08) 이전 시점에 대해서는 retrieved_at 필터링을 우회하여 
        데이터 누락을 방지합니다.
        """
        # 시간대 처리 보정 (timezone naive일 경우 KST 부여)
        if as_of_date.tzinfo is None:
            as_of_date = as_of_date.replace(tzinfo=KST)

        # 2025년 11월 8일 이전 시점인 경우, retrieved_at 필터를 무력화
        if as_of_date < HISTORICAL_CUTOFF:
            query = """
                SELECT DISTINCT ON (stac_yymm) *
                FROM financial_statements
                WHERE stk_cd = %(stk_cd)s AND div_cls_code = %(div_cls_code)s
                ORDER BY stac_yymm DESC, retrieved_at DESC;
            """
            params = {
                "stk_cd": stk_cd,
                "div_cls_code": div_cls_code
            }
        else:
            query = """
                SELECT DISTINCT ON (stac_yymm) *
                FROM financial_statements
                WHERE stk_cd = %(stk_cd)s AND div_cls_code = %(div_cls_code)s AND retrieved_at <= %(as_of_date)s
                ORDER BY stac_yymm DESC, retrieved_at DESC;
            """
            params = {
                "stk_cd": stk_cd,
                "div_cls_code": div_cls_code,
                "as_of_date": as_of_date
            }

        with self.pool.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_dict(cursor, r) for r in rows]

    def get_ratios_as_of(self, stk_cd: str, div_cls_code: str, as_of_date: datetime) -> List[Dict[str, Any]]:
        """
        특정 시점(as_of_date) 기준으로 유효한 재무비율 스냅샷 데이터를
        각 결산년월(stac_yymm) 별로 가장 최신 버전을 선택하여 내림차순(stac_yymm DESC)으로 반환합니다.
        """
        if as_of_date.tzinfo is None:
            as_of_date = as_of_date.replace(tzinfo=KST)

        if as_of_date < HISTORICAL_CUTOFF:
            query = """
                SELECT DISTINCT ON (stac_yymm) *
                FROM financial_ratios
                WHERE stk_cd = %(stk_cd)s AND div_cls_code = %(div_cls_code)s
                ORDER BY stac_yymm DESC, retrieved_at DESC;
            """
            params = {
                "stk_cd": stk_cd,
                "div_cls_code": div_cls_code
            }
        else:
            query = """
                SELECT DISTINCT ON (stac_yymm) *
                FROM financial_ratios
                WHERE stk_cd = %(stk_cd)s AND div_cls_code = %(div_cls_code)s AND retrieved_at <= %(as_of_date)s
                ORDER BY stac_yymm DESC, retrieved_at DESC;
            """
            params = {
                "stk_cd": stk_cd,
                "div_cls_code": div_cls_code,
                "as_of_date": as_of_date
            }

        with self.pool.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_dict(cursor, r) for r in rows]


ALLOWED_SCREENING_FIELDS = {
    'grs', 'bsop_prfi_inrt', 'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps',
    'rsrv_rate', 'lblt_rate', 'cptl_ntin_rate', 'self_cptl_ntin_inrt',
    'sale_ntin_rate', 'sale_totl_rate', 'eva', 'ebitda', 'ev_ebitda',
    'bram_depn', 'crnt_rate', 'quck_rate', 'equt_inrt', 'totl_aset_inrt'
}

ALLOWED_OPERATORS = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "="
}


def screen_stocks_method(
    self,
    stac_yymm: str,
    div_cls_code: str,
    as_of_date: datetime,
    filters: List[Dict[str, Any]],
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    DB 레벨 동적 SQL(CTE + WHERE + LIMIT)을 통해 재무 비율 기준 종목들을 스크리닝합니다.
    """
    if as_of_date.tzinfo is None:
        as_of_date = as_of_date.replace(tzinfo=KST)

    if as_of_date < HISTORICAL_CUTOFF:
        cte_query = """
            SELECT DISTINCT ON (fr.stk_cd) fr.*, si.stk_nm
            FROM financial_ratios fr
            JOIN stock_info si ON fr.stk_cd = si.stk_cd
            WHERE fr.stac_yymm = %(stac_yymm)s AND fr.div_cls_code = %(div_cls_code)s
            ORDER BY fr.stk_cd, fr.retrieved_at DESC
        """
        params = {
            "stac_yymm": stac_yymm,
            "div_cls_code": div_cls_code
        }
    else:
        cte_query = """
            SELECT DISTINCT ON (fr.stk_cd) fr.*, si.stk_nm
            FROM financial_ratios fr
            JOIN stock_info si ON fr.stk_cd = si.stk_cd
            WHERE fr.stac_yymm = %(stac_yymm)s AND fr.div_cls_code = %(div_cls_code)s AND fr.retrieved_at <= %(as_of_date)s
            ORDER BY fr.stk_cd, fr.retrieved_at DESC
        """
        params = {
            "stac_yymm": stac_yymm,
            "div_cls_code": div_cls_code,
            "as_of_date": as_of_date
        }

    where_clauses = []
    for i, f in enumerate(filters):
        field = f.get("field")
        op = f.get("operator")
        val = f.get("value")
        
        if field not in ALLOWED_SCREENING_FIELDS:
            raise ValueError(f"Disallowed screening field: {field}")
        if op not in ALLOWED_OPERATORS:
            raise ValueError(f"Disallowed screening operator: {op}")
        
        param_key = f"val_{i}"
        db_op = ALLOWED_OPERATORS[op]
        where_clauses.append(f"{field} {db_op} %({param_key})s")
        params[param_key] = val

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        WITH latest_ratios AS (
            {cte_query}
        )
        SELECT * FROM latest_ratios
        {where_str}
        ORDER BY stk_cd ASC
        LIMIT %(limit)s;
    """
    params["limit"] = limit

    with self.pool.get_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [self._row_to_dict(cursor, r) for r in rows]

# 클래스에 바인딩
FinancialRepo.screen_stocks = screen_stocks_method

