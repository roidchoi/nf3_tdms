from datetime import date
from p1_shared.db.connection import DbConnectionPool

class OhlcvRepo:
    """daily_ohlcv 및 daily_ohlcv_gap 테이블 관리를 위한 저장소 클래스."""

    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def upsert_daily_ohlcv(self, records: list[dict]) -> int:
        """
        daily_ohlcv에 여러 OHLCV 레코드를 UPSERT. ON CONFLICT (stk_cd, dt) DO UPDATE.

        Args:
            records: [{"stk_cd", "dt", "open", "high", "low", "close", "volume"}, ...]
        Returns:
            int: 처리된 행 수 (cursor.rowcount)
        """
        if not records:
            return 0

        query = """
            INSERT INTO daily_ohlcv (stk_cd, dt, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stk_cd, dt) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """
        
        data = [
            (
                r["stk_cd"],
                r["dt"],
                r["open"],
                r["high"],
                r["low"],
                r["close"],
                r["volume"]
            )
            for r in records
        ]

        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)
            return cursor.rowcount

    def get_latest_date(self, stk_cd: str) -> date | None:
        """
        특정 종목의 가장 최근 수집된 일봉 날짜를 반환.

        Args:
            stk_cd: 종목코드
        Returns:
            date 또는 None
        """
        query = "SELECT MAX(dt) FROM daily_ohlcv WHERE stk_cd = %s"
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                return row[0]
            return None

    def record_gap(self, stk_cd: str, target_date: date, reason: str) -> None:
        """
        수집 실패 종목을 daily_ohlcv_gap 테이블에 기록. ON CONFLICT (stk_cd, dt) DO UPDATE.

        Args:
            stk_cd: 종목코드
            target_date: 수집일자
            reason: 실패 사유
        """
        query = """
            INSERT INTO daily_ohlcv_gap (stk_cd, dt, reason, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (stk_cd, dt) DO UPDATE SET
                reason = EXCLUDED.reason,
                updated_at = CURRENT_TIMESTAMP
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, target_date, reason))
