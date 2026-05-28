import logging
from datetime import date
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TargetSelector:
    """
    직전 분기 평균 거래대금(amt) 기준 상위 N개 종목을 선출하여
    minute_target_history 테이블에 기록 및 관리할 수 있도록 대상을 선정하는 모듈.
    """

    def __init__(self, db) -> None:
        """
        :param db: DatabaseManager, OhlcvRepo 또는 DbConnectionPool 등의 DB 관련 인스턴스
        """
        self.db = db

    def _execute_query(self, query: str, params: tuple = (), fetch: str = None) -> Any:
        """주입된 DB 객체의 종류에 맞춰 쿼리를 유연하게 수행하는 헬퍼 메서드."""
        if hasattr(self.db, '_execute_query'):
            return self.db._execute_query(query, params, fetch=fetch)
        
        pool = getattr(self.db, 'pool', self.db)
        with pool.get_cursor() as cursor:
            cursor.execute(query, params)
            if fetch == 'all':
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            elif fetch == 'one':
                columns = [desc[0] for desc in cursor.description]
                row = cursor.fetchone()
                return dict(zip(columns, row)) if row else None
            return None

    def _get_prev_quarter_info(self, quarter: str) -> tuple[str, date, date]:
        """
        지정된 타겟 분기(예: '2026Q2')의 직전 분기 명칭과 날짜 범위를 반환합니다.
        예: '2026Q2' -> ('2026Q1', date(2026, 1, 1), date(2026, 3, 31))
        """
        try:
            year = int(quarter[:4])
            q_num = int(quarter[5])
            
            if q_num == 1:
                prev_quarter_str = f"{year - 1}Q4"
                start_date = date(year - 1, 10, 1)
                end_date = date(year - 1, 12, 31)
            elif q_num == 2:
                prev_quarter_str = f"{year}Q1"
                start_date = date(year, 1, 1)
                end_date = date(year, 3, 31)
            elif q_num == 3:
                prev_quarter_str = f"{year}Q2"
                start_date = date(year, 4, 1)
                end_date = date(year, 6, 30)
            elif q_num == 4:
                prev_quarter_str = f"{year}Q3"
                start_date = date(year, 7, 1)
                end_date = date(year, 9, 30)
            else:
                raise ValueError("분기 값은 Q1 ~ Q4 중 하나여야 합니다.")
            
            return prev_quarter_str, start_date, end_date
        except Exception as e:
            raise ValueError(f"분기 파싱 및 직전 분기 계산 실패 ('{quarter}'): {e}")

    def select_top_n_stocks(self, quarter: str, top_n: int = 200, market: str = 'KOSPI') -> List[Dict[str, Any]]:
        """
        지정된 타겟 분기의 직전 분기 평균 거래대금(daily_ohlcv의 amt 필드) 기준 상위 N개 종목 정보를 선출합니다.
        데이터가 없는 경우 최대 8분기 전까지 역산하며 데이터를 조회합니다.
        
        :param quarter: 대상 분기 문자열 (예: '2026Q2')
        :param top_n: 선출할 종목 수 (기본값: 200)
        :param market: 시장 구분 ('KOSPI' 또는 'KOSDAQ')
        :return: [{'quarter', 'market', 'symbol', 'avg_trade_value', 'rank'}] 리스트
        """
        current_quarter = quarter
        for attempt in range(8):
            prev_quarter_str, start_date, end_date = self._get_prev_quarter_info(current_quarter)
            logger.info(
                f"Target 선정을 위한 직전 분기 데이터 기간: {start_date} ~ {end_date} "
                f"(기준 분기: {prev_quarter_str}, 타겟 분기: {quarter}, 시장: {market}, 상위 {top_n}개, 시도 {attempt+1}/8)"
            )

            query = """
                SELECT d.stk_cd as symbol, AVG(d.amt) as avg_amount
                FROM daily_ohlcv d
                INNER JOIN stock_info s ON d.stk_cd = s.stk_cd
                WHERE d.dt BETWEEN %s AND %s
                  AND s.market_type = %s
                GROUP BY d.stk_cd
                ORDER BY avg_amount DESC
                LIMIT %s;
            """
            try:
                results = self._execute_query(query, (start_date, end_date, market, top_n), fetch='all')
                if results:
                    top_stocks = []
                    for rank, row in enumerate(results, start=1):
                        symbol = row.get('symbol') if isinstance(row, dict) else row[0]
                        avg_amount = row.get('avg_amount') if isinstance(row, dict) else row[1]
                        top_stocks.append({
                            'quarter': quarter,
                            'market': market,
                            'symbol': symbol,
                            'avg_trade_value': int(round(float(avg_amount))) if avg_amount is not None else 0,
                            'rank': rank
                        })
                    
                    logger.info(f"{market} 시장 대상 상위 {len(top_stocks)}개 종목 선정 완료. (기준 분기: {prev_quarter_str})")
                    return top_stocks[:top_n]
                else:
                    logger.warning(f"기준 분기({prev_quarter_str})에 해당하는 {market} 시장의 daily_ohlcv 데이터가 없습니다. 이전 분기를 탐색합니다.")
                    current_quarter = prev_quarter_str
            except Exception as e:
                logger.error(f"거래대금 기반 Target 종목 선정 쿼리 실행 실패: {e}")
                raise
        
        logger.error(f"최근 8개 분기를 탐색했으나 {market} 시장의 daily_ohlcv 데이터를 찾을 수 없어 대상 종목 선정에 실패했습니다.")
        return []

    def save_target_stocks(self, quarter: str, symbols: List[str], market: str = 'KOSPI') -> int:
        """
        [하위 호환성용 메서드]
        단순 종목 코드 목록을 받아 minute_target_history에 최소 정보(대금, 순위 0)로 임시 저장합니다.
        실제 운영 루틴에서는 select_top_n_stocks의 결과를 ohlcv_repo.upsert_minute_target_history에 전달할 것을 적극 권장합니다.
        """
        if not symbols:
            return 0
        
        targets = [
            {
                'quarter': quarter,
                'market': market,
                'symbol': sym,
                'avg_trade_value': 0,
                'rank': 0
            }
            for sym in symbols
        ]
        
        query = """
            INSERT INTO minute_target_history (quarter, market, symbol, avg_trade_value, rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (quarter, market, symbol) DO UPDATE SET
                avg_trade_value = EXCLUDED.avg_trade_value,
                rank = EXCLUDED.rank;
        """
        
        pool = getattr(self.db, 'pool', self.db)
        inserted_count = 0
        conn = None
        try:
            if hasattr(self.db, '_get_connection'):
                conn = self.db._get_connection()
            else:
                conn = pool.get_conn()
                
            with conn.cursor() as cur:
                for t in targets:
                    cur.execute(query, (t['quarter'], t['market'], t['symbol'], t['avg_trade_value'], t['rank']))
                inserted_count = len(symbols)
            conn.commit()
            return inserted_count
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"save_target_stocks 임시 저장 실패: {e}")
            raise
        finally:
            if conn:
                if hasattr(self.db, '_release_connection'):
                    self.db._release_connection(conn)
                else:
                    pool.put_conn(conn)

