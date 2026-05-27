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
            INSERT INTO stock_info (stk_cd, stk_nm, market_type, status, delist_dt, list_dt, m_vol, update_dt)
            VALUES (%s, %s, %s, %s, NULL, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (stk_cd) DO UPDATE SET
                stk_nm = EXCLUDED.stk_nm,
                market_type = EXCLUDED.market_type,
                status = EXCLUDED.status,
                list_dt = EXCLUDED.list_dt,
                m_vol = EXCLUDED.m_vol,
                update_dt = CURRENT_TIMESTAMP
        """
        
        data = [
            (
                r.get("stk_cd"),
                r.get("stk_nm"),
                r.get("market"),
                'listed' if r.get("is_active", True) else 'delisted',
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
        상장(listed) 상태이고 상장폐지일이 없는 활성 종목 리스트를 반환합니다.
        물리 스키마(status, delist_dt, market_type, list_dt, m_vol)를 
        상위 레이어 인터페이스 형식(market, is_active, listed_dt, listed_shares)으로 변환하여 반환합니다.
        """
        query = """
            SELECT stk_cd, stk_nm, market_type as market, 
                   TRUE as is_active, 
                   list_dt as listed_dt, 
                   m_vol as listed_shares 
            FROM stock_info 
            WHERE status = 'listed' AND (delist_dt IS NULL OR delist_dt > CURRENT_DATE);
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

    def get_ipo_dates(self) -> Dict[str, Any]:
        """모든 종목의 종목코드별 상장일(list_dt) 딕셔너리를 반환합니다."""
        query = "SELECT stk_cd, list_dt FROM stock_info WHERE list_dt IS NOT NULL"
        with self.pool.get_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}



