# repositories/factor_repo.py

from typing import List, Dict, Any
from datetime import date
from p1_shared.db.connection import DbConnectionPool

class FactorRepo:
    """
    price_adjustment_factors 테이블의 CRUD 및 조회를 담당하는 리포지토리 클래스.
    """

    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def upsert_adjustment_factors(self, factors: List[Dict[str, Any]]) -> int:
        """
        수정계수 이벤트를 price_adjustment_factors 테이블에 벌크 업서트합니다.
        """
        if not factors:
            return 0

        query = """
            INSERT INTO price_adjustment_factors (
                stk_cd, event_dt, price_ratio, volume_ratio, price_source, details, effective_dt
            ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (stk_cd, event_dt, price_source) DO UPDATE SET
                price_ratio = EXCLUDED.price_ratio,
                volume_ratio = EXCLUDED.volume_ratio,
                details = EXCLUDED.details,
                effective_dt = CURRENT_TIMESTAMP
        """
        
        data = [
            (
                f.get("stk_cd"),
                f.get("event_dt"),
                f.get("price_ratio"),
                f.get("volume_ratio"),
                f.get("price_source"),
                f.get("details"),
            )
            for f in factors
        ]

        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)
            return cursor.rowcount

    def delete_adjustment_factors(self, stk_cd: str, price_source: str) -> None:
        """
        특정 종목 및 출처의 수정계수 데이터를 삭제합니다.
        """
        query = """
            DELETE FROM price_adjustment_factors 
            WHERE stk_cd = %s AND price_source = %s
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, price_source))

    def get_factors_for_stock(self, stk_cd: str, price_source: str) -> List[Dict[str, Any]]:
        """
        특정 종목 및 출처의 수정계수 이력을 event_dt 오름차순으로 조회합니다.
        """
        query = """
            SELECT stk_cd, event_dt, price_ratio, volume_ratio, price_source, details
            FROM price_adjustment_factors
            WHERE stk_cd = %s AND price_source = %s
            ORDER BY event_dt ASC
        """
        
        columns = ["stk_cd", "event_dt", "price_ratio", "volume_ratio", "price_source", "details"]
        
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, price_source))
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                factor_dict = {}
                for i, col in enumerate(columns):
                    if i < len(row):
                        # float 타입 캐스팅 처리 (price_ratio, volume_ratio)
                        if col in ["price_ratio", "volume_ratio"] and row[i] is not None:
                            factor_dict[col] = float(row[i])
                        else:
                            factor_dict[col] = row[i]
                results.append(factor_dict)
            return results

    def get_recent_event_stocks_map(self, days: int, price_source: str = 'KIS', table_name: str = 'price_adjustment_factors') -> dict[str, list[date]]:
        """
        최근 N일 이내에 특정 소스의 수정계수 팩터가 발생한 종목 코드 및 이벤트 날짜 매핑 데이터를 조회합니다.
        """
        from datetime import date, timedelta
        start_date = date.today() - timedelta(days=days)
        query = f"""
            SELECT stk_cd, event_dt
            FROM {table_name}
            WHERE event_dt >= %s AND price_source = %s
            ORDER BY stk_cd, event_dt;
        """
        event_map = {}
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (start_date, price_source))
            rows = cursor.fetchall()
            for r in rows:
                stk_cd = r[0]
                event_dt = r[1]
                if stk_cd not in event_map:
                    event_map[stk_cd] = []
                event_map[stk_cd].append(event_dt)
            return event_map

    def delete_adjustment_factors_by_dates(self, stk_cd: str, obsolete_event_dates: list[date], price_source: str = 'KIS', table_name: str = 'price_adjustment_factors') -> None:
        """
        특정 종목에 대해 불필요해진 이벤트 날짜들의 팩터를 일괄 삭제합니다.
        """
        if not obsolete_event_dates:
            return
        query = f"""
            DELETE FROM {table_name}
            WHERE stk_cd = %s AND price_source = %s AND event_dt = ANY(%s)
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, price_source, obsolete_event_dates))

