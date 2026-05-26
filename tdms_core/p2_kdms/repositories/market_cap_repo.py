import logging
from datetime import date
from typing import List, Dict, Any
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

class MarketCapRepo:
    """
    daily_market_cap 테이블 데이터베이스 저장소
    """
    
    def __init__(self, pool) -> None:
        """
        pool: DB 커넥션 풀 (DbConnectionPool 또는 어댑터 풀)
        """
        self.pool = pool

    def _get_connection(self):
        if hasattr(self.pool, "get_conn"):
            return self.pool.get_conn()
        elif hasattr(self.pool, "_pool") and hasattr(self.pool._pool, "getconn"):
            return self.pool._pool.getconn()
        elif hasattr(self.pool, "connection"):
            return self.pool.connection()
        raise AttributeError("Provided database pool has no connection retrieval method.")

    def _release_connection(self, conn):
        if hasattr(self.pool, "put_conn"):
            self.pool.put_conn(conn)
        elif hasattr(self.pool, "_pool") and hasattr(self.pool._pool, "putconn"):
            self.pool._pool.putconn(conn)
        else:
            conn.close()

    def upsert_daily_market_cap(self, data: List[Dict[str, Any]]) -> int:
        """
        시가총액 데이터 리스트를 벌크 UPSERT 합니다.
        
        :param data: 정형화된 시총 데이터 딕셔너리 리스트
        :return: 저장된 레코드 개수
        """
        if not data:
            return 0
            
        columns = ["dt", "stk_cd", "cls_prc", "mkt_cap", "vol", "amt", "listed_shares"]
        query = """
            INSERT INTO daily_market_cap (dt, stk_cd, cls_prc, mkt_cap, vol, amt, listed_shares)
            VALUES %s
            ON CONFLICT (dt, stk_cd) DO UPDATE SET
                cls_prc = EXCLUDED.cls_prc,
                mkt_cap = EXCLUDED.mkt_cap,
                vol = EXCLUDED.vol,
                amt = EXCLUDED.amt,
                listed_shares = EXCLUDED.listed_shares;
        """
        
        values = [
            [
                item.get("dt"),
                item.get("stk_cd"),
                item.get("cls_prc"),
                item.get("mkt_cap"),
                item.get("vol"),
                item.get("amt"),
                item.get("listed_shares")
            ]
            for item in data
        ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logger.info(f"✅ daily_market_cap 테이블 벌크 UPSERT 완료: {len(data)}건")
            return len(data)
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"daily_market_cap 벌크 UPSERT 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            if conn:
                self._release_connection(conn)

    def get_market_cap_missing_dates(self, start_date: date, end_date: date) -> List[date]:
        """
        주어진 기간 동안 trading_calendar 기준 개장일이나 daily_market_cap에 없는 누락 영업일 목록을 반환합니다.
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: 누락된 날짜 리스트 (오름차순)
        """
        query = """
            SELECT tc.dt
            FROM trading_calendar tc
            LEFT JOIN (
                SELECT DISTINCT dt FROM daily_market_cap
            ) dmc ON tc.dt = dmc.dt
            WHERE tc.opnd_yn = 'Y'
              AND tc.dt BETWEEN %s AND %s
              AND dmc.dt IS NULL
            ORDER BY tc.dt;
        """
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(query, (start_date, end_date))
                rows = cur.fetchall()
                missing_dates = [row[0] for row in rows]
            logger.info(f"누락 영업일 탐지 완료: {len(missing_dates)}일 (기간: {start_date} ~ {end_date})")
            return missing_dates
        except Exception as e:
            logger.error(f"누락 영업일 조회 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            if conn:
                self._release_connection(conn)

