import logging
from psycopg2.extras import execute_values
from p3_usdms.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

class PriceRepo(BaseRepository):
    def insert_daily_price(self, records: list[dict]) -> None:
        """
        us_daily_price 테이블에 일봉 시세를 bulk insert (ON CONFLICT (dt, cik) DO UPDATE).
        """
        if not records:
            return

        query = """
            INSERT INTO us_daily_price (dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol, amt)
            VALUES %s
            ON CONFLICT (dt, cik) DO UPDATE SET
                ticker = EXCLUDED.ticker,
                open_prc = EXCLUDED.open_prc,
                high_prc = EXCLUDED.high_prc,
                low_prc = EXCLUDED.low_prc,
                cls_prc = EXCLUDED.cls_prc,
                vol = EXCLUDED.vol,
                amt = EXCLUDED.amt
        """
        
        # execute_values용 튜플 리스트 변환
        values = [
            (
                r['dt'],
                r['cik'],
                r['ticker'],
                r['open_prc'],
                r['high_prc'],
                r['low_prc'],
                r['cls_prc'],
                r['vol'],
                r.get('amt', 0.0)
            )
            for r in records
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)

    def upsert_price_factors(self, records: list[dict]) -> None:
        """
        us_price_adjustment_factors 테이블에 수정 계수를 upsert.
        """
        if not records:
            return

        query = """
            INSERT INTO us_price_adjustment_factors (cik, event_dt, factor_val, event_type, matched_info)
            VALUES %s
            ON CONFLICT (cik, event_dt) DO UPDATE SET
                factor_val = EXCLUDED.factor_val,
                event_type = EXCLUDED.event_type,
                matched_info = EXCLUDED.matched_info
        """
        
        values = [
            (
                r['cik'],
                r['event_dt'],
                r['factor_val'],
                r['event_type'],
                r.get('matched_info', '')
            )
            for r in records
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)

    def get_daily_prices(self, cik: str, start_dt: str, end_dt: str) -> list[dict]:
        """특정 기간의 일일 주가(Raw)를 조회"""
        query = """
            SELECT dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol, amt
            FROM us_daily_price
            WHERE cik = %s AND dt >= %s AND dt <= %s
            ORDER BY dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik, start_dt, end_dt))
            return cur.fetchall()

    def get_price_factors(self, cik: str) -> list[dict]:
        """특정 종목의 전체 수정계수 이력을 조회"""
        query = """
            SELECT cik, event_dt, factor_val, event_type, matched_info
            FROM us_price_adjustment_factors
            WHERE cik = %s
            ORDER BY event_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            return cur.fetchall()
