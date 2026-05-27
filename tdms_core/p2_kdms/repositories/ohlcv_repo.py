from datetime import date, datetime
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
            INSERT INTO daily_ohlcv (stk_cd, dt, open_prc, high_prc, low_prc, cls_prc, vol)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stk_cd, dt) DO UPDATE SET
                open_prc = EXCLUDED.open_prc,
                high_prc = EXCLUDED.high_prc,
                low_prc = EXCLUDED.low_prc,
                cls_prc = EXCLUDED.cls_prc,
                vol = EXCLUDED.vol
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

    def refresh_adjusted_ohlcv_batch(self, start_date: date, end_date: date, price_source: str = 'KIS') -> int:
        """
        수정계수를 기반으로 누적곱 계산을 처리하는 SQL CTE를 활용해
        daily_ohlcv_adjusted 물리 테이블을 일괄 갱신합니다.
        
        Args:
            start_date: 갱신 시작일
            end_date: 갱신 종료일
            price_source: 수정계수 출처
        Returns:
            int: 갱신(UPSERT) 처리된 행 수
        """
        query = """
            WITH raw_data AS (
                SELECT dt, stk_cd, open_prc as open, high_prc as high, low_prc as low, cls_prc as close, vol as volume
                FROM daily_ohlcv
                WHERE dt BETWEEN %s AND %s
            ),
            calculated_factors AS (
                SELECT 
                    r.dt,
                    r.stk_cd,
                    r.open as open_prc,
                    r.high as high_prc,
                    r.low as low_prc,
                    r.close as cls_prc,
                    r.volume as vol,
                    COALESCE(
                        (SELECT EXP(SUM(LN(f.price_ratio))) 
                         FROM price_adjustment_factors f 
                         WHERE f.stk_cd = r.stk_cd 
                           AND f.price_source = %s 
                           AND f.event_dt > r.dt), 
                        1.0
                    ) as cum_price_factor,
                    COALESCE(
                        (SELECT EXP(SUM(LN(f.volume_ratio))) 
                         FROM price_adjustment_factors f 
                         WHERE f.stk_cd = r.stk_cd 
                           AND f.price_source = %s 
                           AND f.event_dt > r.dt), 
                        1.0
                    ) as cum_volume_factor
                FROM raw_data r
            )
            INSERT INTO daily_ohlcv_adjusted (dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol, adj_factor, updated_at)
            SELECT 
                dt,
                stk_cd,
                ROUND(open_prc * cum_price_factor)::INTEGER,
                ROUND(high_prc * cum_price_factor)::INTEGER,
                ROUND(low_prc * cum_price_factor)::INTEGER,
                ROUND(cls_prc * cum_price_factor)::INTEGER,
                ROUND(vol * cum_volume_factor)::BIGINT,
                cum_price_factor,
                CURRENT_TIMESTAMP
            FROM calculated_factors
            ON CONFLICT (dt, stk_cd) DO UPDATE SET
                open_prc = EXCLUDED.open_prc,
                high_prc = EXCLUDED.high_prc,
                low_prc = EXCLUDED.low_prc,
                cls_prc = EXCLUDED.cls_prc,
                vol = EXCLUDED.vol,
                adj_factor = EXCLUDED.adj_factor,
                updated_at = CURRENT_TIMESTAMP
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (start_date, end_date, price_source, price_source))
            return cursor.rowcount

    def get_daily_ohlcv(self, stk_cd: str, start_date: date, end_date: date) -> list[dict]:
        """
        특정 종목의 지정 기간 내 원본 OHLCV 데이터를 오름차순으로 조회합니다.
        """
        query = """
            SELECT stk_cd, dt, open_prc, high_prc, low_prc, cls_prc, vol
            FROM daily_ohlcv
            WHERE stk_cd = %s AND dt BETWEEN %s AND %s
            ORDER BY dt ASC
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, start_date, end_date))
            rows = cursor.fetchall()
            return [
                {
                    "stk_cd": r[0],
                    "dt": r[1],
                    "open": int(r[2]),
                    "high": int(r[3]),
                    "low": int(r[4]),
                    "close": int(r[5]),
                    "volume": int(r[6])
                }
                for r in rows
            ]

    def get_adjusted_ohlcv_direct(self, stk_cd: str, start_date: date, end_date: date) -> list[dict]:
        """
        특정 종목의 지정 기간 내 물리 테이블(daily_ohlcv_adjusted) 수정주가 데이터를 오름차순으로 조회합니다.
        """
        query = """
            SELECT stk_cd, dt, open_prc, high_prc, low_prc, cls_prc, vol, adj_factor
            FROM daily_ohlcv_adjusted
            WHERE stk_cd = %s AND dt BETWEEN %s AND %s
            ORDER BY dt ASC
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, start_date, end_date))
            rows = cursor.fetchall()
            return [
                {
                    "stk_cd": r[0],
                    "dt": r[1],
                    "open": int(r[2]),
                    "high": int(r[3]),
                    "low": int(r[4]),
                    "close": int(r[5]),
                    "volume": int(r[6]),
                    "adj_factor": float(r[7])
                }
                for r in rows
            ]

    def get_minute_target_history(self, quarter: str, market: str, table_name: str = 'minute_target_history') -> list[dict]:
        """지정된 minute_target_history 테이블에서 특정 분기/시장의 대상 종목을 조회합니다."""
        query = f"""
            SELECT quarter, market, symbol, avg_trade_value, rank
            FROM {table_name}
            WHERE quarter = %s AND market = %s
            ORDER BY rank ASC;
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (quarter, market))
            rows = cursor.fetchall()
            return [
                {
                    "quarter": r[0],
                    "market": r[1],
                    "symbol": r[2],
                    "avg_trade_value": float(r[3]) if r[3] is not None else 0.0,
                    "rank": int(r[4]) if r[4] is not None else 0
                }
                for r in rows
            ]

    def upsert_minute_target_history(self, targets: list[dict], table_name: str = 'minute_target_history') -> None:
        """target_selector 결과를 지정된 minute_target_history 테이블에 저장합니다."""
        if not targets:
            return
        query = f"""
            INSERT INTO {table_name} (quarter, market, symbol, avg_trade_value, rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (quarter, market, symbol) DO UPDATE SET
                avg_trade_value = EXCLUDED.avg_trade_value,
                rank = EXCLUDED.rank;
        """
        data = [
            (t['quarter'], t['market'], t['symbol'], t['avg_trade_value'], t['rank'])
            for t in targets
        ]
        with self.pool.get_cursor() as cursor:
            cursor.executemany(query, data)

    def upsert_minute_ohlcv(self, data: list[dict], table_name: str = 'minute_ohlcv') -> int:
        """분봉 데이터를 지정된 minute_ohlcv 테이블에 일괄 UPSERT합니다."""
        if not data:
            return 0
        from psycopg2.extras import execute_values
        columns = list(data[0].keys())
        conflict_keys = ['dt_tm', 'stk_cd']
        update_columns = [col for col in columns if col not in conflict_keys]
        update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
        query = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES %s
            ON CONFLICT ({', '.join(conflict_keys)}) DO UPDATE SET
                {update_clause};
        """
        values = [[item.get(col) for col in columns] for item in data]
        with self.pool.get_cursor() as cursor:
            execute_values(cursor, query, values)
            return cursor.rowcount

    def fetch_ohlcv_for_factor_calc(self, stk_cd: str, table_name_raw: str = 'daily_ohlcv', table_name_adj: str = 'daily_ohlcv_adjusted') -> 'pd.DataFrame':
        """
        수정계수 역산을 위해 특정 종목의 원본 및 수정 일봉 시세를 조회하고
        두 데이터가 모두 존재하는 날짜(교집합)를 기준으로 병합하여 반환합니다.
        """
        import pandas as pd
        raw_query = f"SELECT dt, cls_prc FROM {table_name_raw} WHERE stk_cd = %s"
        adj_query = f"SELECT dt, cls_prc FROM {table_name_adj} WHERE stk_cd = %s"
        
        with self.pool.get_cursor() as cursor:
            cursor.execute(raw_query, (stk_cd,))
            raw_rows = cursor.fetchall()
            df_raw = pd.DataFrame(raw_rows, columns=['dt', 'raw_close']) if raw_rows else pd.DataFrame(columns=['dt', 'raw_close'])
            
            cursor.execute(adj_query, (stk_cd,))
            adj_rows = cursor.fetchall()
            df_adj = pd.DataFrame(adj_rows, columns=['dt', 'adj_close']) if adj_rows else pd.DataFrame(columns=['dt', 'adj_close'])
            
        if df_raw.empty or df_adj.empty:
            return pd.DataFrame(columns=['dt', 'adj_close', 'raw_close'])
            
        df = pd.merge(df_adj, df_raw, on='dt', how='inner')
        df = df.sort_values(by='dt', ascending=True).reset_index(drop=True)
        return df

    def get_minute_ohlcv(self, stk_cd: str, start_dt_tm: datetime, end_dt_tm: datetime) -> list[dict]:
        """
        minute_ohlcv 테이블에서 특정 종목의 분봉 데이터를 기간 조회합니다.
        """
        query = """
            SELECT stk_cd, dt_tm, open, high, low, close, volume
            FROM minute_ohlcv
            WHERE stk_cd = %s AND dt_tm BETWEEN %s AND %s
            ORDER BY dt_tm ASC;
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (stk_cd, start_dt_tm, end_dt_tm))
            rows = cursor.fetchall()
            return [
                {
                    "stk_cd": r[0],
                    "dt_tm": r[1],
                    "open": int(r[2]),
                    "high": int(r[3]),
                    "low": int(r[4]),
                    "close": int(r[5]),
                    "volume": int(r[6])
                }
                for r in rows
            ]

    def get_blacklisted_stocks(self, threshold_days: int = 5) -> list[str]:
        """
        daily_ohlcv_gap 테이블을 조회하여 누적 실패(갭) 횟수가 threshold_days 이상인 종목코드 목록을 반환합니다.
        """
        query = """
            SELECT stk_cd
            FROM daily_ohlcv_gap
            GROUP BY stk_cd
            HAVING COUNT(dt) >= %s;
        """
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, (threshold_days,))
            rows = cursor.fetchall()
            return [r[0] for r in rows]




