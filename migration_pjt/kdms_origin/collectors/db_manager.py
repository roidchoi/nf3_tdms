# collectors/db_manager.py

import os
import psycopg2
import logging
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from psycopg2.extras import execute_values, RealDictCursor
from rich import print
from rich.logging import RichHandler
import pandas as pd
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from psycopg2.pool import ThreadedConnectionPool # [수정] PRD 8.2.2

# .env 파일에서 환경 변수 로드
load_dotenv()

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[])
logging.getLogger().addHandler(RichHandler(rich_tracebacks=True))

class DatabaseManager:
    """
    TimescaleDB (PostgreSQL) 데이터베이스 연결 및 관리를 위한 클래스
    [수정] PRD 8.2.2에 따라 ThreadedConnectionPool을 사용
    """

    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = os.getenv("POSTGRES_PORT", 5432)
        self.dbname = os.getenv("POSTGRES_DB")
        self.user = os.getenv("POSTGRES_USER")
        self.password = os.getenv("POSTGRES_PASSWORD")
        if not all([self.dbname, self.user, self.password]):
            raise ValueError(".env 파일에 DB 관련 환경 변수가 올바르게 설정되지 않았습니다.")
        
        # --- [수정] PRD 8.2.2 커넥션 풀 생성 ---
        self.pool = None
        try:
            logging.info(f"DatabaseManager: {self.user}@{self.host} DB 커넥션 풀 생성 중...")
            self.pool = ThreadedConnectionPool(
                minconn=5,  # PRD 8.2.2 예시
                maxconn=20, # PRD 8.2.2 예시
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
            logging.info("✅ DB 커넥션 풀 생성 완료.")
        except psycopg2.OperationalError as e:
            logging.error(f"데이터베이스 커넥션 풀 생성에 실패했습니다: {e}")
            raise

    def _get_connection(self):
        """ [수정] PRD 8.2.2 풀에서 연결을 가져옵니다. """
        try:
            return self.pool.getconn()
        except Exception as e:
            logging.error(f"DB 커넥션 풀에서 연결을 가져오는 데 실패했습니다: {e}")
            raise

    def _release_connection(self, conn):
        """ [수정] PRD 8.2.2 풀에 연결을 반환합니다. """
        if conn:
            try:
                self.pool.putconn(conn)
            except psycopg2.InterfaceError:
                # 연결이 이미 닫혔거나 유효하지 않은 경우 무시
                pass 
            except Exception as e:
                logging.warning(f"DB 커넥션 풀 반환 중 오류: {e}")

    def _execute_query(self, query: str, params=None, fetch=None):
        """ 
        [수정] 쿼리 실행기 (커넥션 풀 사용)
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            if fetch == 'one':
                result = cursor.fetchone()
            elif fetch == 'all':
                result = cursor.fetchall()
            else:
                conn.commit()
                result = None
            cursor.close()
            return result
        except Exception as e:
            logging.error(f"쿼리 실행 중 에러 발생: {e}")
            if conn: conn.rollback()
            raise
        finally:
            # [수정] conn.close() -> _release_connection(conn)
            self._release_connection(conn)

    def _truncate_table_for_testing(self, table_name: str):
        """ [테스트 전용] 테이블 데이터를 비웁니다. (_execute_query 사용으로 안전) """
        query = f"TRUNCATE TABLE {table_name} RESTART IDENTITY;"
        self._execute_query(query)
        logging.warning(f"🧹 [테스트] '{table_name}' 테이블의 모든 데이터가 삭제되었습니다.")

    def delete_data_for_symbols(self, symbols: list[str]):
        """ 
        주어진 종목 코드 리스트에 해당하는 모든 데이터를 관련 테이블에서 삭제합니다.
        (stock_info, daily_ohlcv, minute_ohlcv)  
        """
        if not symbols:
            logging.warning("삭제할 종목 코드가 제공되지 않았습니다.")
            return

        tables_to_delete_from = ['minute_ohlcv', 'daily_ohlcv', 'stock_info']
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor() as cur:
                for table in tables_to_delete_from:
                    query = f"DELETE FROM {table} WHERE stk_cd = ANY(%s);"
                    cur.execute(query, (symbols,))
                    logging.info(f"테이블 '{table}'에서 {cur.rowcount}개 종목의 데이터를 삭제했습니다.")
            conn.commit()
            logging.info(f"총 {len(symbols)}개 테스트 종목에 대한 데이터 삭제가 완료되었습니다.")
        except Exception as e:
            logging.error(f"테스트 데이터 삭제 중 에러 발생: {e}", exc_info=True)
            if conn: conn.rollback() # [수정]
            raise
        finally:
            self._release_connection(conn) # [수정]

    def set_milestone(self, name: str, dt: date, desc: str):
        """
        시스템 신뢰도 마일스톤을 설정(INSERT or UPDATE)합니다.

        [작명 규칙 (Hierarchical Naming Convention)]
        - 구조: `대분류:중분류:상세내용_버전` (예: `LOGIC:TARGET_SELECTION:V1`)
        - 문자: 영문 대문자, 숫자, 언더스코어(_)만 사용
        - 구분자: 콜론(:)

        :param name: 마일스톤 이름 (작명 규칙 준수)
        :param dt: 마일스톤 기준 날짜 (datetime.date 객체)
        :param desc: 마일스톤에 대한 상세 설명
        """
        query = """
            INSERT INTO system_milestones (milestone_name, milestone_date, description, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (milestone_name) DO UPDATE SET
                milestone_date = EXCLUDED.milestone_date,
                description = EXCLUDED.description,
                updated_at = NOW();
        """
        self._execute_query(query, (name, dt, desc))
        logging.info(f"✅ 마일스톤 '{name}'이(가) 날짜 '{dt}'로 설정/업데이트되었습니다.")

    def upsert_stock_info(self, stock_data: list[dict], table_name: str = 'stock_info'):
        """ 종목 정보를 stock_info 테이블에 UPSERT 합니다. """
        if not stock_data: return
        query = f"""
            INSERT INTO {table_name} (stk_cd, stk_nm, market_type, list_dt, status, update_dt)
            VALUES %s
            ON CONFLICT (stk_cd) DO UPDATE SET
                stk_nm = EXCLUDED.stk_nm,
                market_type = EXCLUDED.market_type,
                list_dt = EXCLUDED.list_dt,
                status = EXCLUDED.status,
                update_dt = EXCLUDED.update_dt;
        """
        values = [
            (
                item.get('stk_cd'), item.get('stk_nm'), item.get('market_type'),
                item.get('list_dt'), item.get('status', 'listed'), date.today()
            ) for item in stock_data
        ]
        
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            cursor = conn.cursor()
            execute_values(cursor, query, values)
            conn.commit()
            logging.info(f"✅ 총 {len(stock_data)}건의 종목 정보가 '{table_name}'에 성공적으로 UPSERT 되었습니다.")
        except Exception as e:
            logging.error(f"종목 정보 UPSERT 중 에러 발생: {e}")
            if conn: conn.rollback() # [수정]
            raise
        finally:
            self._release_connection(conn) # [수정]

    def upsert_ohlcv_data(self, table_name: str, data: list[dict]):
        """
        3개 테이블(daily, minute, adjusted)을 모두 지원하는 동적 UPSERT 함수.
        테이블별로 다른 PK와 컬럼 구조를 자동으로 처리하며, 명시적 롤백을 보장합니다.
        """
        if not data: return
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                columns = data[0].keys()
                if 'minute_ohlcv' in table_name:
                    conflict_keys = ['dt_tm', 'stk_cd']
                elif 'daily_ohlcv' in table_name:
                    conflict_keys = ['dt', 'stk_cd']
                else:
                    raise ValueError(f"지원하지 않는 테이블 이름입니다: {table_name}")
                
                update_columns = [col for col in columns if col not in conflict_keys]
                update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
                query = f"""
                    INSERT INTO {table_name} ({', '.join(columns)})
                    VALUES %s
                    ON CONFLICT ({', '.join(conflict_keys)}) DO UPDATE SET
                        {update_clause};
                """
                values = [[item.get(col) for col in columns] for item in data]
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"✅ 총 {len(data)}건의 데이터가 '{table_name}'에 성공적으로 UPSERT 되었습니다.")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"'{table_name}' 데이터 UPSERT 중 에러 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    def get_all_stock_codes(self, active_only: bool = True, table_name: str = 'stock_info') -> list[str]:
        """
        지정된 stock_master 테이블에서 종목 코드 리스트를 조회합니다.
        
        :param active_only: 활성 종목(is_active=True)만 조회할지 여부
        :param table_name: 조회할 테이블명 (기본값: 'stock_info')
        :return: 종목 코드 문자열 리스트
        """
        query = f"SELECT stk_cd FROM {table_name}"
        if active_only:
            query += " WHERE status = 'listed'"
        query += " ORDER BY stk_cd;"
        
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor() as cur:
                cur.execute(query)
                results = cur.fetchall()
            return [row[0] for row in results]
        except Exception as e:
            logging.error(f"테이블 '{table_name}' 조회 중 오류: {e}", exc_info=True)
            return []
        finally:
            self._release_connection(conn) # [수정]

    def get_ohlcv_data(self, table_name: str, start_date: date, end_date: date,
                       symbols: list[str] = None, market_type: str = None,
                       stock_info_table: str = 'stock_info') -> list[dict]:
        """
        3개 테이블(daily, minute, adjusted) 모두에서 OHLCV 데이터를 조회합니다.
        테이블별로 다른 날짜/시간 컬럼(dt, dt_tm)을 자동으로 처리합니다.
        """
        if 'minute_ohlcv' in table_name:
            date_filter_clause = "dt_tm::date BETWEEN %s AND %s"
            order_by_column = 'dt_tm'
        elif 'daily_ohlcv' in table_name:
            date_filter_clause = "dt BETWEEN %s AND %s"
            order_by_column = 'dt'
        else:
            raise ValueError(f"지원하지 않는 테이블 이름입니다: {table_name}")

        base_query = f"""
            SELECT * FROM {table_name} t
            JOIN {stock_info_table} si ON t.stk_cd = si.stk_cd
            WHERE {date_filter_clause}
        """
        params = [start_date, end_date]

        if symbols:
            base_query += " AND t.stk_cd = ANY(%s)"
            params.append(symbols)
        elif market_type:
            base_query += " AND si.market_type = %s"
            params.append(market_type)
        
        order_by_column = 'dt_tm' if 'minute_ohlcv' in table_name else 'dt'
        base_query += f" ORDER BY t.stk_cd, t.{order_by_column} ASC;"

        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(base_query, tuple(params))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"{table_name} 조회 중 에러 발생: {e}", exc_info=True)
            return []
        finally:
            self._release_connection(conn) # [수정]

    # --- (신규) PRD 8.2.1 Anti-Pandas SQL 함수 ---
    
    def get_adjusted_ohlcv_data(self, stk_cd: str, start_date: date, end_date: date) -> List[Dict]:
        """
        [신규] 'pandas' 연산 없이 DB(SQL)에서 직접 수정주가를 계산합니다.
        PRD 8.2.1(쿼리 최적화) 및 모든 논리 오류(이벤트 당일 등)를 수정한 버전입니다.
        (_execute_query 사용으로 커넥션 풀 자동 적용)
        """
        sql_query = """
        WITH best_source AS (
            -- [신규] 종목별 단일 소스 선택 (KIS 우선)
            SELECT price_source
            FROM price_adjustment_factors
            WHERE stk_cd = %(stk_cd)s
            ORDER BY CASE WHEN price_source = 'KIS' THEN 1 ELSE 2 END
            LIMIT 1
        ),
        factors AS (
            -- 1. 해당 종목의 팩터 조회 (단일 소스)
            SELECT 
                event_dt, 
                -- KIWOOM 시절 팩터는 나눗셈용(>1)이므로 역수로 변환, KIS는 이미 곱셈용(<1)
                CASE WHEN price_source = 'KIWOOM' THEN 1.0 / NULLIF(price_ratio, 0) 
                     ELSE price_ratio END AS price_ratio
            FROM price_adjustment_factors
            WHERE stk_cd = %(stk_cd)s
              AND price_source = (SELECT price_source FROM best_source)
        ),
        cum_factors AS (
            -- 2. 팩터를 '내림차순'(최신순)으로 정렬하고 '누적 곱'(adj_factor)을 계산
            SELECT
                event_dt,
                EXP(SUM(LN(price_ratio)) OVER (ORDER BY event_dt DESC)) AS adj_factor
            FROM factors
        ),
        raw_prices AS (
            -- 3. 요청 기간의 '원본' 시세를 가져옴
            SELECT
                dt, stk_nm, open_prc, high_prc, low_prc, cls_prc,
                vol, amt, turn_rt
            FROM daily_ohlcv
            JOIN stock_info USING(stk_cd)
            WHERE
                stk_cd = %(stk_cd)s
                AND dt BETWEEN %(start_date)s AND %(end_date)s
        ),
        mapped_prices AS (
            -- 4. (핵심) 원본 시세(p)에 '미래'의 팩터(f)를 매핑
            SELECT
                p.*,
                (
                    SELECT f.adj_factor
                    FROM cum_factors f
                    WHERE p.dt < f.event_dt -- 주가 날짜 < 이벤트 날짜
                    ORDER BY f.event_dt ASC -- 가장 이른 미래 이벤트
                    LIMIT 1
                ) AS adj_factor
            FROM raw_prices p
        )
        -- 5. 최종 계산
        SELECT
            dt,
            stk_nm,
            -- [곱셈 방식] price_ratio = 1/old_ratio (< 1 저장)
            -- adj_price = raw_price * adj_factor
            COALESCE(adj_factor, 1.0) AS factor, 
            ROUND((open_prc * COALESCE(adj_factor, 1.0))::numeric, 2) AS open_prc,
            ROUND((high_prc * COALESCE(adj_factor, 1.0))::numeric, 2) AS high_prc,
            ROUND((low_prc  * COALESCE(adj_factor, 1.0))::numeric, 2) AS low_prc,
            ROUND((cls_prc  * COALESCE(adj_factor, 1.0))::numeric, 2) AS cls_prc,
            ROUND((vol      / COALESCE(adj_factor, 1.0))::numeric, 0) AS vol,
            amt,
            turn_rt
        FROM
            mapped_prices
        ORDER BY
            dt ASC;
        """
        
        params = {
            "stk_cd": stk_cd,
            "start_date": start_date,
            "end_date": end_date
        }
        
        return self._execute_query(sql_query, params, fetch='all')
    
    def get_adjusted_minute_ohlcv_data(self, stk_cd: str, start_date: date, end_date: date) -> List[Dict]:
        """
        [신규] 'pandas' 연산 없이 DB(SQL)에서 직접 '분봉' 수정주가를 계산합니다.
        모델 학습 왜곡을 방지하기 위해 수정주가를 지원합니다.
        """
        sql_query = """
        WITH best_source AS (
            SELECT price_source
            FROM price_adjustment_factors
            WHERE stk_cd = %(stk_cd)s
            ORDER BY CASE WHEN price_source = 'KIS' THEN 1 ELSE 2 END
            LIMIT 1
        ),
        factors AS (
            -- 1. 해당 종목의 팩터 조회 (단일 소스)
            SELECT 
                event_dt, 
                CASE WHEN price_source = 'KIWOOM' THEN 1.0 / NULLIF(price_ratio, 0) 
                     ELSE price_ratio END AS price_ratio
            FROM price_adjustment_factors
            WHERE stk_cd = %(stk_cd)s
              AND price_source = (SELECT price_source FROM best_source)
        ),
        cum_factors AS (
            -- 2. 팩터를 '내림차순'(최신순)으로 정렬하고 '누적 곱'(adj_factor)을 계산
            SELECT
                event_dt,
                EXP(SUM(LN(price_ratio)) OVER (ORDER BY event_dt DESC)) AS adj_factor
            FROM factors
        ),
        raw_prices AS (
            -- 3. 요청 기간의 '원본' 분봉 시세를 가져옴
            SELECT
                dt_tm, -- (수정) dt -> dt_tm
                stk_nm, open_prc, high_prc, low_prc, cls_prc, vol
            FROM
                minute_ohlcv
            JOIN stock_info USING(stk_cd)
            WHERE
                stk_cd = %(stk_cd)s
                -- (수정) dt_tm::date로 기간 필터링
                AND dt_tm::date BETWEEN %(start_date)s AND %(end_date)s
        ),
        mapped_prices AS (
            -- 4. (핵심) 원본 시세(p)에 '미래'의 팩터(f)를 매핑
            SELECT
                p.*,
                (
                    SELECT f.adj_factor
                    FROM cum_factors f
                    -- (수정) p.dt_tm::date < f.event_dt
                    WHERE p.dt_tm::date < f.event_dt 
                    ORDER BY f.event_dt ASC
                    LIMIT 1
                ) AS adj_factor
            FROM raw_prices p
        )
        -- 5. 최종 계산
        SELECT
            dt_tm, -- (수정) dt -> dt_tm
            stk_nm,
            -- [곱셈 방식] price_ratio = 1/old_ratio (< 1 저장)
            -- adj_price = raw_price * adj_factor
            COALESCE(adj_factor, 1.0) AS factor, 
            ROUND((open_prc * COALESCE(adj_factor, 1.0))::numeric, 2) AS open_prc,
            ROUND((high_prc * COALESCE(adj_factor, 1.0))::numeric, 2) AS high_prc,
            ROUND((low_prc  * COALESCE(adj_factor, 1.0))::numeric, 2) AS low_prc,
            ROUND((cls_prc  * COALESCE(adj_factor, 1.0))::numeric, 2) AS cls_prc,
            ROUND((vol      / COALESCE(adj_factor, 1.0))::numeric, 0) AS vol
        FROM
            mapped_prices
        ORDER BY
            dt_tm ASC; -- (수정) dt -> dt_tm
        """
        
        params = {
            "stk_cd": stk_cd,
            "start_date": start_date,
            "end_date": end_date
        }
        
        return self._execute_query(sql_query, params, fetch='all')

    # --- [신규] Phase KIS-1: daily_ohlcv_adjusted 관련 메서드 ---

    def upsert_adjusted_ohlcv(self, data: List[Dict[str, Any]],
                               table_name: str = 'daily_ohlcv_adjusted') -> int:
        """
        [신규] 수정주가 일봉 데이터를 daily_ohlcv_adjusted 테이블에 일괄 UPSERT합니다.
        get_adjusted_ohlcv_data() 또는 refresh_adjusted_ohlcv_batch()의 결과를 저장할 때 사용합니다.

        :param data: {'dt', 'stk_cd', 'open_prc', 'high_prc', 'low_prc', 'cls_prc', 'vol', 'factor'} 리스트
        :param table_name: 저장 대상 테이블명 (기본값: daily_ohlcv_adjusted)
        :return: UPSERT된 레코드 수
        """
        if not data:
            return 0

        query = f"""
            INSERT INTO {table_name} (dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol, adj_factor, updated_at)
            VALUES %s
            ON CONFLICT (dt, stk_cd) DO UPDATE SET
                open_prc   = EXCLUDED.open_prc,
                high_prc   = EXCLUDED.high_prc,
                low_prc    = EXCLUDED.low_prc,
                cls_prc    = EXCLUDED.cls_prc,
                vol        = EXCLUDED.vol,
                adj_factor = EXCLUDED.adj_factor,
                updated_at = EXCLUDED.updated_at;
        """
        values = [
            (
                item.get('dt'),
                item.get('stk_cd'),
                item.get('open_prc'),
                item.get('high_prc'),
                item.get('low_prc'),
                item.get('cls_prc'),
                item.get('vol'),
                item.get('factor', item.get('adj_factor', 1.0)),  # 필드명 유연 처리
                datetime.now(ZoneInfo("Asia/Seoul"))
            )
            for item in data
        ]

        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"✅ [{table_name}] 수정주가 일봉 {len(values)}건 UPSERT 완료.")
            return len(values)
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"[{table_name}] 수정주가 일봉 UPSERT 오류: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn)

    def refresh_adjusted_ohlcv_batch(self, start_date: date, end_date: date,
                                      src_table: str = 'daily_ohlcv',
                                      factor_table: str = 'price_adjustment_factors',
                                      dst_table: str = 'daily_ohlcv_adjusted') -> int:
        """
        [신규] 지정 기간의 전 종목 수정주가를 SQL CTE로 일괄 계산하여 daily_ohlcv_adjusted에 저장합니다.
        get_adjusted_ohlcv_data()의 동일 로직을 전 종목 배치로 확장한 버전입니다.
        (pandas 미사용, DB 레벨에서 완전 처리)

        :param start_date: 조회 시작일
        :param end_date:   조회 종료일
        :param src_table:  원본 시세 테이블 (기본값: daily_ohlcv)
        :param factor_table: 팩터 테이블 (기본값: price_adjustment_factors)
        :param dst_table:  저장 대상 테이블 (기본값: daily_ohlcv_adjusted)
        :return: UPSERT된 레코드 수
        """
        sql = f"""
        WITH best_source AS (
            -- 종목별 최우선 소스 결정 (KIS > 일반)
            SELECT DISTINCT ON (stk_cd) stk_cd, price_source
            FROM {factor_table}
            ORDER BY stk_cd ASC, CASE WHEN price_source = 'KIS' THEN 1 ELSE 2 END
        ),
        factors AS (
            -- 1. 전 종목 팩터 조회 (단일 우선 소스 적용 & KIWOOM 역수 변환)
            SELECT 
                f.stk_cd, 
                f.event_dt, 
                CASE WHEN f.price_source = 'KIWOOM' THEN 1.0 / NULLIF(f.price_ratio, 0) 
                     ELSE f.price_ratio END AS price_ratio
            FROM {factor_table} f
            JOIN best_source b ON f.stk_cd = b.stk_cd AND f.price_source = b.price_source
        ),
        cum_factors AS (
            -- 2. 종목별 누적 수정계수 계산 (내림차순 누적곱)
            SELECT
                stk_cd,
                event_dt,
                EXP(SUM(LN(price_ratio)) OVER (
                    PARTITION BY stk_cd
                    ORDER BY event_dt DESC
                )) AS adj_factor
            FROM factors
        ),
        raw_prices AS (
            -- 3. 대상 기간의 원본 시세 조회
            SELECT dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol
            FROM {src_table}
            WHERE dt BETWEEN %(start_date)s AND %(end_date)s
        ),
        mapped_prices AS (
            -- 4. 원본 시세에 미래 팩터 매핑 (이벤트 당일 이전 날짜에 팩터 적용)
            SELECT
                p.*,
                (
                    SELECT f.adj_factor
                    FROM cum_factors f
                    WHERE f.stk_cd = p.stk_cd
                      AND p.dt < f.event_dt
                    ORDER BY f.event_dt ASC
                    LIMIT 1
                ) AS adj_factor
            FROM raw_prices p
        )
        INSERT INTO {dst_table} (dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol, adj_factor, updated_at)
        SELECT
            dt,
            stk_cd,
            -- [곱셈 방식] price_ratio = 1/old_ratio (< 1 저장)
            -- adj_price = raw_price * adj_factor
            ROUND((open_prc * COALESCE(adj_factor, 1.0))::numeric, 2),
            ROUND((high_prc * COALESCE(adj_factor, 1.0))::numeric, 2),
            ROUND((low_prc  * COALESCE(adj_factor, 1.0))::numeric, 2),
            ROUND((cls_prc  * COALESCE(adj_factor, 1.0))::numeric, 2),
            ROUND((vol      / COALESCE(adj_factor, 1.0))::numeric, 0)::BIGINT,
            COALESCE(adj_factor, 1.0),
            NOW()
        FROM mapped_prices
        ON CONFLICT (dt, stk_cd) DO UPDATE SET
            open_prc   = EXCLUDED.open_prc,
            high_prc   = EXCLUDED.high_prc,
            low_prc    = EXCLUDED.low_prc,
            cls_prc    = EXCLUDED.cls_prc,
            vol        = EXCLUDED.vol,
            adj_factor = EXCLUDED.adj_factor,
            updated_at = EXCLUDED.updated_at;
        """
        params = {"start_date": start_date, "end_date": end_date}

        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected = cur.rowcount
            conn.commit()
            logging.info(
                f"✅ [{dst_table}] 배치 수정주가 {start_date}~{end_date} 구간 {affected}건 UPSERT 완료."
            )
            return affected
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"[{dst_table}] 배치 수정주가 UPSERT 오류: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn)

    # ----------------------------------------------------------

    def get_stock_info_by_symbols(self, symbols: list[str]) -> list[dict]:

        """ stk_cd 리스트를 받아 해당하는 종목의 마스터 정보를 조회합니다. """
        query = """
            SELECT stk_cd, stk_nm, market_type, list_dt, status
            FROM stock_info WHERE stk_cd = ANY(%s) ORDER BY stk_cd;
        """
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (symbols,))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"특정 종목 정보 조회 중 에러 발생: {e}", exc_info=True)
            return []
        finally:
            self._release_connection(conn) # [수정]

    def get_minute_target_history(self, quarter: str, market: str,
                                  table_name: str = 'minute_target_history') -> list[dict]:
        """ 지정된 minute_target_history 테이블에서 특정 분기/시장의 대상 종목을 조회합니다 """
        query = f"""
            SELECT quarter, market, symbol, avg_trade_value, rank
            FROM {table_name}
            WHERE quarter = %s AND market = %s
            ORDER BY rank ASC;
        """
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (quarter, market))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"분기별 대상 종목 조회 중 에러 발생: {e}", exc_info=True)
            return []
        finally:
            self._release_connection(conn) # [수정]

    def upsert_minute_target_history(self, targets: list[dict],
                                     table_name: str = 'minute_target_history'):
        """ target_selector 결과를 지정된 minute_target_history 테이블에 저장합니다. """
        query = f"""
            INSERT INTO {table_name} (quarter, market, symbol, avg_trade_value, rank)
            VALUES %s
            ON CONFLICT (quarter, market, symbol) DO UPDATE SET
                avg_trade_value = EXCLUDED.avg_trade_value,
                rank = EXCLUDED.rank;
        """
        values = [ (t['quarter'], t['market'], t['symbol'], t['avg_trade_value'], t['rank']) for t in targets ]
        
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"{len(targets)}개의 분기 대상 종목 정보를 '{table_name}'에 성공적으로 저장했습니다.")
        except Exception as e:
            if conn: conn.rollback() # [수정]
            logging.error(f"분기 대상 종목 저장 중 에러 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    def fetch_ohlcv_for_factor_calc(self, stk_cd: str,
                                    table_name_raw: str = 'daily_ohlcv',
                                    table_name_adj: str = 'daily_ohlcv_adjusted_legacy',
                                    stock_info_table: str = 'stock_info') -> pd.DataFrame:
        """
        수정계수 역산을 위해 특정 종목의 원본 및 수정 일봉 시세를 조회하고
        두 데이터가 모두 존재하는 날짜(교집합)를 기준으로 병합하여 반환합니다.
        
        :param stk_cd: 조회할 종목 코드
        :param table_name_raw: 원본 주가 테이블명
        :param table_name_adj: 수정 주가 테이블명
        :return: 'dt', 'adj_close', 'raw_close' 컬럼을 가진 DataFrame
        """
        logging.info(f"[{stk_cd}] 시세 데이터 조회 ({table_name_raw}, {table_name_adj})...")
        wide_start_date = date(1980, 1, 1)
        wide_end_date = date.today()
        try:
            raw_data = self.get_ohlcv_data(
                table_name=table_name_raw, start_date=wide_start_date, end_date=wide_end_date,
                symbols=[stk_cd], stock_info_table=stock_info_table
            )
            if not raw_data:
                logging.warning(f"[{stk_cd}] 원본 주가({table_name_raw}) 데이터가 없습니다.")
                return pd.DataFrame(columns=['dt', 'adj_close', 'raw_close'])
            raw_df = pd.DataFrame(raw_data)[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})

            adj_data = self.get_ohlcv_data(
                table_name=table_name_adj, start_date=wide_start_date, end_date=wide_end_date,
                symbols=[stk_cd], stock_info_table=stock_info_table
            )
            if not adj_data:
                logging.warning(f"[{stk_cd}] 수정 주가({table_name_adj}) 데이터가 없습니다.")
                return pd.DataFrame(columns=['dt', 'adj_close', 'raw_close'])
            adj_df = pd.DataFrame(adj_data)[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})

            df = pd.merge(adj_df, raw_df, on='dt', how='inner')
            df = df.sort_values(by='dt', ascending=True).reset_index(drop=True)
            logging.info(f"[{stk_cd}] {len(df)}일치 시세 데이터 병합 완료.")
            return df
        except Exception as e:
            logging.error(f"[{stk_cd}] 시세 데이터 병합 중 오류 발생: {e}")
            raise

    def upsert_adjustment_factors(self, factors_data: List[Dict[str, Any]],
                                  table_name: str = 'price_adjustment_factors'):
        """
        계산된 수정계수 팩터 목록을 지정된 테이블에 일괄 UPSERT합니다.
        (stk_cd, event_dt, price_source) 충돌 시 업데이트합니다.

        :param factors_data: factor_calculator가 생성한 딕셔너리 리스트
        :param table_name: 데이터를 저장할 테이블명
        """
        if not factors_data: return
        query = f"""
            INSERT INTO {table_name} (
                stk_cd, event_dt, price_ratio, volume_ratio,
                price_source, details, effective_dt
            ) VALUES %s
            ON CONFLICT (stk_cd, event_dt, price_source)
            DO UPDATE SET
                price_ratio = EXCLUDED.price_ratio,
                volume_ratio = EXCLUDED.volume_ratio,
                details = EXCLUDED.details,
                effective_dt = NOW();
        """
        kst = ZoneInfo("Asia/Seoul")
        values = [
            (
                item['stk_cd'], item['event_dt'], item['price_ratio'],
                item['volume_ratio'], item['price_source'], item['details'],
                datetime.now(kst)
            ) for item in factors_data
        ]
        
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"테이블 '{table_name}'에 수정계수 {len(values)}건 UPSERT 완료.")
        except Exception as e:
            if conn: conn.rollback() # [수정]
            logging.error(f"수정계수 UPSERT 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    def get_factors_by_date_range(self, stk_cd: str, start_date: date, end_date: date,
                                  table_name: str = 'price_adjustment_factors') -> List[Dict]:
        """
        지정된 팩터 테이블에서 특정 종목의 특정 기간 팩터 목록을 조회합니다.

        :param stk_cd: 종목 코드
        :param start_date: 조회 시작일
        :param end_date: 조회 종료일
        :param table_name: 조회할 팩터 테이블명
        :return: 팩터 딕셔너리 리스트
        """
        query = f"""
            SELECT event_dt, price_ratio, volume_ratio
            FROM {table_name}
            WHERE stk_cd = %s AND event_dt BETWEEN %s AND %s
            ORDER BY event_dt;
        """
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (stk_cd, start_date, end_date))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"[{stk_cd}] 기간별 팩터 조회({table_name}) 중 오류 발생: {e}", exc_info=True)
            return []
        finally:
            self._release_connection(conn) # [수정]

    def delete_adjustment_factors(self, stk_cd: str, obsolete_event_dates: List[date],
                                  table_name: str = 'price_adjustment_factors'):
        """
        지정된 팩터 테이블에서 더 이상 유효하지 않은 팩터들을 일괄 삭제합니다.

        :param stk_cd: 종목 코드
        :param obsolete_event_dates: 삭제할 event_dt의 리스트
        :param table_name: 삭제할 팩터 테이블명
        """
        if not obsolete_event_dates: return
        query = f"""
            DELETE FROM {table_name}
            WHERE stk_cd = %s AND event_dt = ANY(%s);
        """
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor() as cur:
                cur.execute(query, (stk_cd, obsolete_event_dates))
            conn.commit()
            logging.warning(f"[{stk_cd}] {table_name} 테이블에서 {len(obsolete_event_dates)}개의 오래된 팩터를 삭제했습니다.")
        except Exception as e:
            if conn: conn.rollback() # [수정]
            logging.error(f"[{stk_cd}] 오래된 팩터 삭제({table_name}) 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    def get_recent_event_stocks_map(self, days: int,
                                    table_name: str = 'price_adjustment_factors') -> Dict[str, List[date]]:
        """
        지정된 팩터 테이블에서 최근 N일 이내 'event_dt'가 기록된 종목 맵을 반환합니다.

        :param days: 조회할 최근 일수 (예: 10)
        :param table_name: 조회할 팩터 테이블명
        :return: {'005930': [date(2025, 10, 30)], ...} 형태의 딕셔너리
        """
        start_date = date.today() - timedelta(days=days)
        query = f"""
            SELECT stk_cd, event_dt
            FROM {table_name}
            WHERE event_dt >= %s
            ORDER BY stk_cd, event_dt;
        """
        event_map = {}
        conn = None # [수정]
        try:
            conn = self._get_connection() # [수정]
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (start_date,))
                results = cur.fetchall()
            for row in results:
                stk_cd = row['stk_cd']
                event_dt = row['event_dt']
                if stk_cd not in event_map:
                    event_map[stk_cd] = []
                event_map[stk_cd].append(event_dt)
            logging.info(f"{table_name} 테이블에서 최근 {days}일 이내 이벤트가 발생한 종목 {len(event_map)}개를 조회했습니다.")
            return event_map
        except Exception as e:
            logging.error(f"최근 이벤트 종목 조회({table_name}) 중 오류 발생: {e}", exc_info=True)
            return {}
        finally:
            self._release_connection(conn) # [수정]

    # ... (setup_test_tables, cleanup_test_tables - 커넥션 풀 수정) ...

    PRODUCTION_TABLES = [
        'stock_info',
        'daily_ohlcv',
        'daily_ohlcv_adjusted_legacy',
        'price_adjustment_factors',
        'minute_target_history',
        'minute_ohlcv',
        'trading_calendar'
    ]

    def setup_test_tables(self, suffix: str = '_test'):
        """
        테스트 모드용 임시 테이블을 생성합니다.
        프로덕션 테이블과 동일한 스키마를 복제합니다.

        :param suffix: 테스트 테이블에 붙일 접미사 (예: '_test')
        """
        logging.info(f"테스트용 임시 테이블 (접미사: {suffix}) 생성을 시작합니다...")
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                for table in self.PRODUCTION_TABLES:
                    test_table = f"{table}{suffix}"
                    query = f"CREATE TABLE IF NOT EXISTS {test_table} (LIKE {table} INCLUDING ALL);"
                    cur.execute(query)
                    logging.info(f"테이블 생성 완료: {test_table}")
            conn.commit()
            logging.info("모든 테스트 테이블이 준비되었습니다.")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"테스트 테이블 생성 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    def cleanup_test_tables(self, suffix: str = '_test'):
        """
        테스트 모드용 임시 테이블을 일괄 삭제합니다.

        :param suffix: 삭제할 테스트 테이블의 접미사
        """
        logging.info(f"테스트용 임시 테이블 (접미사: {suffix}) 삭제를 시작합니다...")
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                for table in reversed(self.PRODUCTION_TABLES):
                    test_table = f"{table}{suffix}"
                    query = f"DROP TABLE IF EXISTS {test_table};"
                    cur.execute(query)
                    logging.info(f"테이블 삭제 완료: {test_table}")
            conn.commit()
            logging.info("모든 테스트 테이블을 삭제했습니다.")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"테스트 테이블 삭제 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn) # [수정]

    
    # kis 재무정보 수집 관련 메소드

    def insert_financial_statements(self, data: list[dict]):
        """
        [Phase 4-B] financial_statements 테이블에 PIT 버전 데이터를 일괄 INSERT.
        (ON CONFLICT를 사용하지 않고 모든 버전을 적재)
        """
        if not data: return
        columns = [
            'stk_cd', 'stac_yymm', 'div_cls_code', 'cras', 'fxas', 'total_aset', 
            'flow_lblt', 'fix_lblt', 'total_lblt', 'cpfn', 'total_cptl', 
            'sale_account', 'sale_cost', 'sale_totl_prfi', 'bsop_prti', 'op_prfi', 'thtr_ntin'
        ]
        query = f"INSERT INTO financial_statements ({', '.join(columns)}) VALUES %s"
        values = [ tuple(item.get(col) for col in columns) for item in data ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"✅ financial_statements {len(values)}건 INSERT 완료.")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"❌ financial_statements INSERT 실패: {e}")
            raise
        finally:
            self._release_connection(conn) # [수정]

    def insert_financial_ratios(self, data: list[dict]):
        """
        [Phase 4-B] financial_ratios 테이블에 PIT 버전 데이터를 일괄 INSERT.
        (ON CONFLICT를 사용하지 않고 모든 버전을 적재)
        """
        if not data: return
        columns = [
            'stk_cd', 'stac_yymm', 'div_cls_code', 'grs', 'bsop_prfi_inrt', 
            'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps', 'rsrv_rate', 'lblt_rate', 
            'cptl_ntin_rate', 'self_cptl_ntin_inrt', 'sale_ntin_rate', 'sale_totl_rate', 
            'eva', 'ebitda', 'ev_ebitda', 'bram_depn', 'crnt_rate', 'quck_rate', 
            'equt_inrt', 'totl_aset_inrt'
        ]
        query = f"INSERT INTO financial_ratios ({', '.join(columns)}) VALUES %s"
        values = [ tuple(item.get(col) for col in columns) for item in data ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logging.info(f"✅ financial_ratios {len(values)}건 INSERT 완료.")
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"❌ financial_ratios INSERT 실패: {e}")
            raise
        finally:
            self._release_connection(conn) # [수정]

    def get_latest_financial_statement(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[dict]:
        """ [Phase 4-B] 특정 재무제표의 가장 최신 버전을 조회합니다. (변경 감지용) """
        query = """
            SELECT * FROM financial_statements
            WHERE stk_cd = %s AND stac_yymm = %s AND div_cls_code = %s
            ORDER BY retrieved_at DESC LIMIT 1;
        """
        return self._execute_query(query, (stk_cd, stac_yymm, div_cls_code), fetch='one')

    def get_latest_financial_ratio(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[dict]:
        """ [Phase 4-B] 특정 재무비율의 가장 최신 버전을 조회합니다. (변경 감지용) """
        query = """
            SELECT * FROM financial_ratios
            WHERE stk_cd = %s AND stac_yymm = %s AND div_cls_code = %s
            ORDER BY retrieved_at DESC LIMIT 1;
        """
        return self._execute_query(query, (stk_cd, stac_yymm, div_cls_code), fetch='one')

    # =================================================================
    # KRX 시가총액 데이터 관련 메소드 (pykrx)
    # =================================================================

    def upsert_daily_market_cap(self, data: List[Dict[str, Any]]) -> int:
        """
        시가총액 데이터 Upsert (ON CONFLICT DO UPDATE)

        :param data: List of Dict (dt, stk_cd, cls_prc, mkt_cap, vol, amt, listed_shares)
        :return: 삽입/업데이트된 레코드 수
        """
        if not data:
            logging.warning("시가총액 데이터가 비어있습니다.")
            return 0

        query = """
            INSERT INTO daily_market_cap
            (dt, stk_cd, cls_prc, mkt_cap, vol, amt, listed_shares)
            VALUES %s
            ON CONFLICT (dt, stk_cd) DO UPDATE SET
                cls_prc = EXCLUDED.cls_prc,
                mkt_cap = EXCLUDED.mkt_cap,
                vol = EXCLUDED.vol,
                amt = EXCLUDED.amt,
                listed_shares = EXCLUDED.listed_shares
        """

        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            values = [
                (d['dt'], d['stk_cd'], d['cls_prc'], d['mkt_cap'],
                 d['vol'], d['amt'], d['listed_shares'])
                for d in data
            ]

            # [디버깅] 요청 건수 로깅
            logging.info(f"[DB] 시가총액 Upsert 요청: {len(values)}건")

            execute_values(cursor, query, values)
            conn.commit()
            count = cursor.rowcount
            cursor.close()

            # [개선] 요청 vs 실제 처리 건수 명시
            # 참고: ON CONFLICT DO UPDATE에서 rowcount는 실제로 INSERT되거나 값이 변경된 UPDATE만 집계
            #       값이 동일하면 UPDATE로 처리되어도 rowcount에 포함되지 않을 수 있음
            logging.info(
                f"✅ 시가총액 데이터 Upsert 완료 - "
                f"요청: {len(values)}건, 실제 변경: {count}건"
            )
            return count

        except Exception as e:
            logging.error(f"시가총액 데이터 삽입 실패: {e}", exc_info=True)
            if conn:
                conn.rollback()
            raise
        finally:
            self._release_connection(conn)

    def get_market_cap_date_range(self) -> Dict[str, Optional[date]]:
        """
        daily_market_cap 테이블의 MIN(dt), MAX(dt)를 조회

        :return: {'min_date': date, 'max_date': date} or {'min_date': None, 'max_date': None}
        """
        query = "SELECT MIN(dt) as min_date, MAX(dt) as max_date FROM daily_market_cap"
        result = self._execute_query(query, fetch='one')

        if result:
            return {
                'min_date': result.get('min_date'),
                'max_date': result.get('max_date')
            }
        else:
            return {'min_date': None, 'max_date': None}

    def get_market_cap_missing_dates(self, start_date: date, end_date: date) -> List[date]:
        """
        주어진 기간 내에서 daily_market_cap 테이블에 누락된 날짜 목록을 반환

        :param start_date: 검사 시작일
        :param end_date: 검사 종료일
        :return: 누락된 날짜 목록 (List[date])
        """
        query = """
            SELECT DISTINCT dt
            FROM daily_market_cap
            WHERE dt BETWEEN %s AND %s
            ORDER BY dt
        """
        results = self._execute_query(query, (start_date, end_date), fetch='all')

        if not results:
            # 기간 내 데이터가 전혀 없으면 모든 영업일이 누락
            collected_dates = set()
        else:
            collected_dates = {row['dt'] for row in results}

        # pandas.bdate_range로 영업일 생성
        business_days = pd.bdate_range(start=start_date, end=end_date)
        business_dates = {d.date() for d in business_days}

        # Set Difference로 누락일 계산
        missing_dates = sorted(business_dates - collected_dates)

        return missing_dates

# =================================================================
# 테스트 코드 (단순화)
# =================================================================
if __name__ == '__main__':
    try:
        logging.info("--- [1/2] DB 매니저(커넥션 풀) 초기화 테스트 ---")
        db_manager = DatabaseManager()
        logging.info("✅ DB 매니저 생성 완료.")
        
        logging.info("--- [2/2] _execute_query (SELECT 1) 테스트 ---")
        result = db_manager._execute_query("SELECT 1 as test;", fetch='one')
        print("[bold green]쿼리 결과:[/bold green]", result)
        if result['test'] == 1:
            logging.info("✅ _execute_query 및 커넥션 풀 작동 확인 완료.")
        else:
            logging.error("❌ _execute_query 테스트 실패.")
            
    except Exception as e:
        logging.error(f"DB 매니저 테스트 중 치명적 오류 발생: {e}", exc_info=True)