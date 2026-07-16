import logging
from datetime import date
from typing import List, Dict, Any
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

class InvestorTradeRepo:
    """
    daily_investor_trade 테이블 데이터베이스 저장소
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

    def upsert_daily_investor_trade(self, data: List[Dict[str, Any]]) -> int:
        """
        일별 투자자 매매동향 데이터를 벌크 UPSERT 합니다.
        
        :param data: 정형화된 투자자 매매동향 데이터 딕셔너리 리스트
        :return: 저장된 레코드 개수
        """
        if not data:
            return 0
            
        # 102개 컬럼 전체 나열
        columns = [
            "dt", "stk_cd", "stck_clpr", "prdy_vrss", "prdy_vrss_sign", "prdy_ctrt",
            "acml_vol", "acml_tr_pbmn", "stck_oprc", "stck_hgpr", "stck_lwpr",
            
            "prsn_seln_vol", "prsn_shnu_vol", "prsn_ntby_qty", "prsn_seln_tr_pbmn", "prsn_shnu_tr_pbmn", "prsn_ntby_tr_pbmn",
            "frgn_seln_vol", "frgn_shnu_vol", "frgn_ntby_qty", "frgn_seln_tr_pbmn", "frgn_shnu_tr_pbmn", "frgn_ntby_tr_pbmn",
            "orgn_seln_vol", "orgn_shnu_vol", "orgn_ntby_qty", "orgn_seln_tr_pbmn", "orgn_shnu_tr_pbmn", "orgn_ntby_tr_pbmn",
            "scrt_seln_vol", "scrt_shnu_vol", "scrt_ntby_qty", "scrt_seln_tr_pbmn", "scrt_shnu_tr_pbmn", "scrt_ntby_tr_pbmn",
            "insu_seln_vol", "insu_shnu_vol", "insu_ntby_qty", "insu_seln_tr_pbmn", "insu_shnu_tr_pbmn", "insu_ntby_tr_pbmn",
            "fund_seln_vol", "fund_shnu_vol", "fund_ntby_qty", "fund_seln_tr_pbmn", "fund_shnu_tr_pbmn", "fund_ntby_tr_pbmn",
            "bank_seln_vol", "bank_shnu_vol", "bank_ntby_qty", "bank_seln_tr_pbmn", "bank_shnu_tr_pbmn", "bank_ntby_tr_pbmn",
            "ivtr_seln_vol", "ivtr_shnu_vol", "ivtr_ntby_qty", "ivtr_seln_tr_pbmn", "ivtr_shnu_tr_pbmn", "ivtr_ntby_tr_pbmn",
            "mrbn_seln_vol", "mrbn_shnu_vol", "mrbn_ntby_qty", "mrbn_seln_tr_pbmn", "mrbn_shnu_tr_pbmn", "mrbn_ntby_tr_pbmn",
            "pe_fund_seln_vol", "pe_fund_shnu_vol", "pe_fund_ntby_vol", "pe_fund_seln_tr_pbmn", "pe_fund_shnu_tr_pbmn", "pe_fund_ntby_tr_pbmn",
            "etc_seln_vol", "etc_shnu_vol", "etc_ntby_qty", "etc_seln_tr_pbmn", "etc_shnu_tr_pbmn", "etc_ntby_tr_pbmn",
            "etc_corp_seln_vol", "etc_corp_shnu_vol", "etc_corp_ntby_vol", "etc_corp_seln_tr_pbmn", "etc_corp_shnu_tr_pbmn", "etc_corp_ntby_tr_pbmn",
            "etc_orgt_seln_vol", "etc_orgt_shnu_vol", "etc_orgt_ntby_vol", "etc_orgt_seln_tr_pbmn", "etc_orgt_shnu_tr_pbmn", "etc_orgt_ntby_tr_pbmn",
            
            "frgn_reg_askp_qty", "frgn_reg_bidp_qty", "frgn_reg_ntby_qty", "frgn_reg_askp_pbmn", "frgn_reg_bidp_pbmn", "frgn_reg_ntby_pbmn",
            "frgn_nreg_askp_qty", "frgn_nreg_bidp_qty", "frgn_nreg_ntby_qty", "frgn_nreg_askp_pbmn", "frgn_nreg_bidp_pbmn", "frgn_nreg_ntby_pbmn"
        ]
        
        # Conflict 시 업데이트할 컬럼 (dt, stk_cd 제외한 100개 컬럼)
        update_cols = [col for col in columns if col not in ("dt", "stk_cd")]
        update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
        
        query = f"""
            INSERT INTO daily_investor_trade ({', '.join(columns)})
            VALUES %s
            ON CONFLICT (dt, stk_cd) DO UPDATE SET
                {update_clause};
        """
        
        values = [
            [item.get(col) for col in columns]
            for item in data
        ]
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                execute_values(cur, query, values)
            conn.commit()
            logger.info(f"✅ daily_investor_trade 테이블 벌크 UPSERT 완료: {len(data)}건")
            return len(data)
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"daily_investor_trade 벌크 UPSERT 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            if conn:
                self._release_connection(conn)

    def get_active_symbols_for_date(self, dt: date) -> List[str]:
        """
        주어진 날짜 dt가 포함된 분기(quarter)의 분봉 수집 대상 종목코드 리스트를 반환합니다.
        분기 형식 예: '2025Q1'
        """
        q_num = (dt.month - 1) // 3 + 1
        quarter = f"{dt.year}Q{q_num}"
        
        query = """
            SELECT DISTINCT symbol
            FROM minute_target_history
            WHERE quarter = %s;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(query, (quarter,))
                rows = cur.fetchall()
                symbols = [row[0] for row in rows]
            logger.info(f"[{quarter}] 분봉 수집 대상 종목 조회 완료: {len(symbols)}개")
            return symbols
        except Exception as e:
            logger.error(f"[{quarter}] 분봉 수집 대상 종목 조회 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            if conn:
                self._release_connection(conn)

    def get_daily_investor_trade(self, stk_cd: str, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        특정 종목의 지정 기간 내 일별 투자자 매매동향 데이터를 오름차순으로 조회합니다.
        
        :param stk_cd: 종목코드
        :param start_date: 조회 시작 날짜
        :param end_date: 조회 종료 날짜
        :return: 투자자 매매동향 데이터 리스트
        """
        query = """
            SELECT dt, stk_cd, stck_clpr, prdy_vrss, prdy_vrss_sign, prdy_ctrt, acml_vol, acml_tr_pbmn, stck_oprc, stck_hgpr, stck_lwpr,
                   prsn_seln_vol, prsn_shnu_vol, prsn_ntby_qty, prsn_seln_tr_pbmn, prsn_shnu_tr_pbmn, prsn_ntby_tr_pbmn,
                   frgn_seln_vol, frgn_shnu_vol, frgn_ntby_qty, frgn_seln_tr_pbmn, frgn_shnu_tr_pbmn, frgn_ntby_tr_pbmn,
                   orgn_seln_vol, orgn_shnu_vol, orgn_ntby_qty, orgn_seln_tr_pbmn, orgn_shnu_tr_pbmn, orgn_ntby_tr_pbmn,
                   scrt_seln_vol, scrt_shnu_vol, scrt_ntby_qty, scrt_seln_tr_pbmn, scrt_shnu_tr_pbmn, scrt_ntby_tr_pbmn,
                   insu_seln_vol, insu_shnu_vol, insu_ntby_qty, insu_seln_tr_pbmn, insu_shnu_tr_pbmn, insu_ntby_tr_pbmn,
                   fund_seln_vol, fund_shnu_vol, fund_ntby_qty, fund_seln_tr_pbmn, fund_shnu_tr_pbmn, fund_ntby_tr_pbmn,
                   bank_seln_vol, bank_shnu_vol, bank_ntby_qty, bank_seln_tr_pbmn, bank_shnu_tr_pbmn, bank_ntby_tr_pbmn,
                   ivtr_seln_vol, ivtr_shnu_vol, ivtr_ntby_qty, ivtr_seln_tr_pbmn, ivtr_shnu_tr_pbmn, ivtr_ntby_tr_pbmn,
                   mrbn_seln_vol, mrbn_shnu_vol, mrbn_ntby_qty, mrbn_seln_tr_pbmn, mrbn_shnu_tr_pbmn, mrbn_ntby_tr_pbmn,
                   pe_fund_seln_vol, pe_fund_shnu_vol, pe_fund_ntby_vol, pe_fund_seln_tr_pbmn, pe_fund_shnu_tr_pbmn, pe_fund_ntby_tr_pbmn,
                   etc_seln_vol, etc_shnu_vol, etc_ntby_qty, etc_seln_tr_pbmn, etc_shnu_tr_pbmn, etc_ntby_tr_pbmn,
                   etc_corp_seln_vol, etc_corp_shnu_vol, etc_corp_ntby_vol, etc_corp_seln_tr_pbmn, etc_corp_shnu_tr_pbmn, etc_corp_ntby_tr_pbmn,
                   etc_orgt_seln_vol, etc_orgt_shnu_vol, etc_orgt_ntby_vol, etc_orgt_seln_tr_pbmn, etc_orgt_shnu_tr_pbmn, etc_orgt_ntby_tr_pbmn,
                   frgn_reg_askp_qty, frgn_reg_bidp_qty, frgn_reg_ntby_qty, frgn_reg_askp_pbmn, frgn_reg_bidp_pbmn, frgn_reg_ntby_pbmn,
                   frgn_nreg_askp_qty, frgn_nreg_bidp_qty, frgn_nreg_ntby_qty, frgn_nreg_askp_pbmn, frgn_nreg_bidp_pbmn, frgn_nreg_ntby_pbmn
            FROM daily_investor_trade
            WHERE stk_cd = %s AND dt BETWEEN %s AND %s
            ORDER BY dt ASC;
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(query, (stk_cd, start_date, end_date))
                desc = cur.description
                columns = [d[0] for d in desc]
                rows = cur.fetchall()
                
                results = []
                for row in rows:
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            logger.error(f"Failed to query daily_investor_trade: {e}", exc_info=True)
            raise
        finally:
            if conn:
                self._release_connection(conn)
