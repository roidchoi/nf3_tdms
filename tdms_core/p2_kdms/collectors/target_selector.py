import logging
from datetime import date
from typing import List, Dict, Optional
from p1_shared.db.connection import DbConnectionPool

logger = logging.getLogger(__name__)

class TargetSelector:
    """
    직전 분기 평균 거래대금(종가 * 거래량) 기준 상위 N개 종목을 선출하고 
    minute_target_history 테이블에 기록 및 관리하는 모듈.
    """

    def __init__(self, db_manager) -> None:
        """
        :param db_manager: DatabaseManager 객체 (또는 _execute_query와 Connection 관리 기능을 지닌 인스턴스)
        """
        self.db = db_manager

    def _get_quarter_date_range(self, quarter: str) -> tuple[date, date]:
        """
        분기 문자열 (예: '2026Q1')을 시작일과 종료일 날짜 객체로 변환합니다.
        """
        try:
            year_str = quarter[:4]
            q_str = quarter[4:]
            year = int(year_str)
            
            if q_str == "Q1":
                return date(year, 1, 1), date(year, 3, 31)
            elif q_str == "Q2":
                return date(year, 4, 1), date(year, 6, 30)
            elif q_str == "Q3":
                return date(year, 7, 1), date(year, 9, 30)
            elif q_str == "Q4":
                return date(year, 10, 1), date(year, 12, 31)
            else:
                raise ValueError("올바르지 않은 분기 구분자입니다 (Q1~Q4 필요).")
        except Exception as e:
            raise ValueError(f"분기 파싱 실패 ('{quarter}'): {e}")

    def select_top_n_stocks(self, quarter: str, top_n: int = 200) -> List[str]:
        """
        지정된 분기의 평균 거래대금(close * volume) 기준 상위 N개 종목 코드를 추출합니다.
        """
        start_date, end_date = self._get_quarter_date_range(quarter)
        logger.info(f"Target 선정 대상 기간: {start_date} ~ {end_date} (분기: {quarter}, 상위 {top_n}개)")

        query = """
            SELECT stk_cd as symbol, AVG(close * volume) as avg_amount
            FROM daily_ohlcv
            WHERE dt BETWEEN %s AND %s
            GROUP BY stk_cd
            ORDER BY avg_amount DESC
            LIMIT %s;
        """
        try:
            results = self.db._execute_query(query, (start_date, end_date, top_n), fetch='all')
            if not results:
                logger.warning(f"해당 분기({quarter})에 조회된 daily_ohlcv 데이터가 없습니다.")
                return []
            
            # 테스트 시 mock 데이터는 딕셔너리 리스트 형식이므로 이를 안전하게 처리
            symbols = []
            for row in results:
                if isinstance(row, dict):
                    symbols.append(row.get('symbol'))
                else:
                    # tuple 형식일 경우 대비
                    symbols.append(row[0])
            
            # 이중 안전장치: 상위 top_n개로 슬라이싱 처리
            sliced_symbols = symbols[:top_n]
            logger.info(f"성공적으로 상위 {len(sliced_symbols)}개 종목을 선정했습니다.")
            return sliced_symbols
        except Exception as e:
            logger.error(f"거래대금 기반 Target 종목 선정 쿼리 실행 실패: {e}")
            raise

    def save_target_stocks(self, quarter: str, symbols: List[str], market: str = 'KOSPI') -> int:
        """
        선출된 대상 종목을 minute_target_history 테이블에 적재합니다.
        
        :param quarter: 분기 문자열
        :param symbols: 종목 코드 리스트
        :param market: 시장 구분 (기본값: KOSPI)
        :return: 저장된 건수
        """
        if not symbols:
            return 0

        query = """
            INSERT INTO minute_target_history (quarter, symbol, market)
            VALUES (%s, %s, %s)
            ON CONFLICT (quarter, symbol) DO NOTHING;
        """
        
        conn = None
        inserted_count = 0
        try:
            # db_manager의 connection 풀을 이용하여 저장 수행
            conn = self.db._get_connection()
            with conn.cursor() as cur:
                for symbol in symbols:
                    cur.execute(query, (quarter, symbol, market))
                inserted_count = len(symbols)  # execute_values 또는 simple execute
            conn.commit()
            logger.info(f"minute_target_history에 {inserted_count}건의 종목 저장 완료 (분기: {quarter})")
            return inserted_count
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Target 종목 DB 적재 실패: {e}")
            raise
        finally:
            if conn:
                self.db._release_connection(conn)
