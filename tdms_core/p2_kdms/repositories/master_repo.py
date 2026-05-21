# repositories/master_repo.py

from typing import List, Dict, Any
from p1_shared.db.connection import DbConnectionPool

class MasterRepo:
    """
    stock_info 테이블의 CRUD 및 조회를 담당하는 리포지토리 클래스.
    """

    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def upsert_stock_info(self, records: List[Dict[str, Any]]) -> int:
        """
        종목 마스터 정보를 stock_info 테이블에 벌크 업서트합니다.
        ON CONFLICT (stk_cd) DO UPDATE SET.
        """
        if not records:
            return 0

        query = """
            INSERT INTO stock_info (stk_cd, stk_nm, market, is_active, listed_dt, listed_shares, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (stk_cd) DO UPDATE SET
                stk_nm = EXCLUDED.stk_nm,
                market = EXCLUDED.market,
                is_active = EXCLUDED.is_active,
                listed_dt = EXCLUDED.listed_dt,
                listed_shares = EXCLUDED.listed_shares,
                updated_at = CURRENT_TIMESTAMP
        """
        
        data = [
            (
                r.get("stk_cd"),
                r.get("stk_nm"),
                r.get("market"),
                r.get("is_active", True),
                r.get("listed_dt"),
                r.get("listed_shares")
            )
            for r in records
        ]

        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)
            return cursor.rowcount

    def get_all_active_stocks(self) -> List[Dict[str, Any]]:
        """
        is_active=True인 활성 종목 리스트를 반환합니다.
        테스트와 실제 DB 컬럼 차이를 흡수하기 위해 가변 컬럼 매핑을 사용합니다.
        """
        query = """
            SELECT stk_cd, stk_nm, market, is_active, listed_dt, listed_shares 
            FROM stock_info 
            WHERE is_active = TRUE
        """
        
        columns = ["stk_cd", "stk_nm", "market", "is_active", "listed_dt", "listed_shares"]
        
        with self.pool.get_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                stock_dict = {}
                for i, col in enumerate(columns):
                    if i < len(row):
                        stock_dict[col] = row[i]
                results.append(stock_dict)
            return results

