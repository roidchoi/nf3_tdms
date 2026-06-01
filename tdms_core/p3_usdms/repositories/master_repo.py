from typing import Optional
from p3_usdms.repositories.base import BaseRepository

class MasterRepo(BaseRepository):
    """
    us_ticker_master 및 us_ticker_history 테이블에 접근하는 리포지토리 클래스
    """
    def get_active_tickers(self) -> list[dict]:
        """us_ticker_master에서 is_active = TRUE인 티커 목록 조회"""
        query = """
            SELECT cik, latest_ticker, latest_name, exchange, sector, industry, country, quote_type, market_cap, current_price, is_active, is_collect_target
            FROM us_ticker_master
            WHERE is_active = TRUE
        """
        with self.get_cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def get_collect_targets(self) -> list[dict]:
        """is_collect_target = TRUE인 종목 목록 조회"""
        query = """
            SELECT cik, latest_ticker, latest_name, exchange, sector, industry, country, quote_type, market_cap, current_price, is_active, is_collect_target
            FROM us_ticker_master
            WHERE is_collect_target = TRUE
        """
        with self.get_cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def get_ticker_history(self, cik: str) -> list[dict]:
        """특정 CIK의 티커 변경 이력 조회"""
        query = """
            SELECT cik, ticker, start_dt, end_dt
            FROM us_ticker_history
            WHERE cik = %s
            ORDER BY start_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (str(cik).zfill(10),))
            return cur.fetchall()

    def get_cik_by_ticker(self, ticker: str) -> Optional[str]:
        """특정 티커의 CIK 값을 조회합니다."""
        query = "SELECT cik FROM us_ticker_master WHERE latest_ticker = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (ticker,))
            res = cur.fetchone()
            if res:
                return res['cik']
            return None
