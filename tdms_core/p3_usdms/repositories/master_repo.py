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

    def get_missing_enrichment_targets(self, limit: int = 50) -> list[dict]:
        """is_active = TRUE이고 country, sector, industry 중 하나라도 누락된 종목을 최대 limit개 조회합니다."""
        query = """
            SELECT cik, latest_ticker, latest_name, exchange, sector, industry, country, quote_type, market_cap, current_price, is_active, is_collect_target
            FROM us_ticker_master
            WHERE is_active = TRUE
              AND (country IS NULL OR sector IS NULL OR industry IS NULL)
            LIMIT %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (limit,))
            return cur.fetchall()

    def update_metadata(self, cik: str, country: str, sector: str, industry: str, is_collect_target: bool) -> None:
        """단일 종목의 메타데이터 및 수집 대상 지정 여부를 데이터베이스에 반영합니다."""
        query = """
            UPDATE us_ticker_master
            SET country = %s,
                sector = %s,
                industry = %s,
                is_collect_target = %s,
                updated_at = NOW()
            WHERE cik = %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (country, sector, industry, is_collect_target, str(cik).zfill(10)))

    def bulk_update_metadata(self, updates: list[dict]) -> None:
        """여러 종목의 메타데이터를 일괄 배치 업데이트합니다."""
        query = """
            UPDATE us_ticker_master
            SET country = %(country)s,
                sector = %(sector)s,
                industry = %(industry)s,
                is_collect_target = %(is_collect_target)s,
                updated_at = NOW()
            WHERE cik = %(cik)s
        """
        # updates 리스트의 CIK들은 10자리 zero-padding이 보장되도록 함
        for up in updates:
            up['cik'] = str(up['cik']).zfill(10)

        with self.get_cursor() as cur:
            # psycopg2.extras.execute_batch 등을 활용할 수도 있으나, 
            # execute_batch는 DB 연결 환경에 따라 다름. 심플하게 루프로 처리하거나 executemany 사용.
            # safe하고 호환성 있는 executemany를 사용함
            cur.executemany(query, updates)

    def apply_targeting_rules(
        self, 
        min_market_cap_entry: float = 50000000.0, 
        min_price_entry: float = 1.00,
        min_market_cap_exit: float = 35000000.0,
        min_price_exit: float = 0.80
    ) -> dict[str, int]:
        """
        Dynamic Targeting Rules를 SQL 트랜잭션으로 반영합니다.
        - Entry Criteria: 시가총액 >= entry, 가격 >= entry 이면 is_collect_target = TRUE
        - Retention Criteria (Exit): 시가총액 < exit, 가격 < exit 이면 is_collect_target = FALSE
        반환값: {"dropped_count": N, "added_count": M}
        """
        # 1. 탈퇴 기준 (Retention Exit)
        exit_query = """
            UPDATE us_ticker_master
            SET is_collect_target = FALSE,
                updated_at = NOW()
            WHERE is_collect_target = TRUE
              AND (market_cap < %s OR current_price < %s)
        """
        # 2. 진입 기준 (Entry)
        entry_query = """
            UPDATE us_ticker_master
            SET is_collect_target = TRUE,
                updated_at = NOW()
            WHERE is_collect_target = FALSE
              AND is_active = TRUE
              AND market_cap >= %s
              AND current_price >= %s
              -- 블랙리스트 등록된 CIK는 진입 거부
              AND cik NOT IN (SELECT cik FROM us_collection_blacklist WHERE is_blocked = TRUE)
        """
        with self.get_cursor() as cur:
            # exit 실행
            cur.execute(exit_query, (min_market_cap_exit, min_price_exit))
            dropped = cur.rowcount
            
            # entry 실행
            cur.execute(entry_query, (min_market_cap_entry, min_price_entry))
            added = cur.rowcount
            
        return {"dropped_count": dropped, "added_count": added}
