import logging
from typing import List, Dict, Any, Tuple
from psycopg2.extras import execute_values
from p3_usdms.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

class ValuationRepo(BaseRepository):
    def load_prices(self, cik: str, start_date=None) -> List[Dict[str, Any]]:
        """
        특정 CIK의 일별 주가를 dt 오름차순으로 조회합니다.
        start_date가 지정되면 해당 날짜 이후의 가격 정보만 로드합니다.
        """
        if start_date:
            query = """
                SELECT dt, cls_prc 
                FROM us_daily_price 
                WHERE cik = %s AND dt >= %s 
                ORDER BY dt ASC
            """
            params = (cik, start_date)
        else:
            query = """
                SELECT dt, cls_prc 
                FROM us_daily_price 
                WHERE cik = %s 
                ORDER BY dt ASC
            """
            params = (cik,)
            
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def load_shares(self, cik: str) -> List[Dict[str, Any]]:
        """
        특정 CIK의 발행주식수 변동 이력을 filed_dt 오름차순으로 조회합니다.
        """
        query = """
            SELECT filed_dt, val 
            FROM us_share_history 
            WHERE cik = %s 
            ORDER BY filed_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            return cur.fetchall()

    def load_financials(self, cik: str) -> List[Dict[str, Any]]:
        """
        특정 CIK의 표준화 재무 정보를 report_period 및 filed_dt 오름차순으로 조회합니다.
        """
        query = """
            SELECT 
                cik, report_period, filed_dt, fiscal_year, fiscal_period,
                total_assets, current_assets, cash_and_equiv, inventory, account_receivable,
                total_equity, retained_earnings,
                total_liabilities, current_liabilities, total_debt,
                shares_outstanding,
                revenue, cogs, gross_profit,
                sgna_expense, rnd_expense,
                op_income, interest_expense, tax_provision, net_income,
                ebitda, ocf, capex, fcf
            FROM us_standard_financials
            WHERE cik = %s
            ORDER BY report_period ASC, filed_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            return cur.fetchall()

    def get_latest_valuation_date(self, cik: str) -> Any:
        """
        특정 CIK의 가치평가 테이블에서 가장 최신 날짜(dt)를 반환합니다.
        데이터가 없는 경우 None을 반환합니다.
        """
        query = """
            SELECT MAX(dt) as latest_dt 
            FROM us_daily_valuation 
            WHERE cik = %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            row = cur.fetchone()
            if row and row.get('latest_dt'):
                return row['latest_dt']
        return None

    def get_latest_financial_filed_date(self, cik: str) -> Any:
        """
        특정 CIK의 표준화 재무 테이블에서 가장 최신 공시일(filed_dt)을 반환합니다.
        """
        query = """
            SELECT MAX(filed_dt) as latest_filed 
            FROM us_standard_financials 
            WHERE cik = %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            row = cur.fetchone()
            if row and row.get('latest_filed'):
                return row['latest_filed']
        return None

    def get_latest_metric_filed_date(self, cik: str) -> Any:
        """
        특정 CIK의 재무비율 테이블에서 가장 최신 공시일(filed_dt)을 반환합니다.
        """
        query = """
            SELECT MAX(filed_dt) as latest_filed 
            FROM us_financial_metrics 
            WHERE cik = %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            row = cur.fetchone()
            if row and row.get('latest_filed'):
                return row['latest_filed']
        return None

    def get_all_latest_valuation_dates(self, ciks: List[str]) -> Dict[str, Any]:
        """
        주어진 CIK 목록 전체에 대해 가장 최신 가치평가 날짜를 한 번에 조회하여 맵으로 반환합니다.
        """
        if not ciks:
            return {}
        query = """
            SELECT cik, MAX(dt) as latest_dt 
            FROM us_daily_valuation 
            WHERE cik = ANY(%s)
            GROUP BY cik
        """
        with self.get_cursor() as cur:
            cur.execute(query, (ciks,))
            rows = cur.fetchall()
        return {r['cik']: r['latest_dt'] for r in rows}

    def get_all_latest_financial_filed_dates(self, ciks: List[str]) -> Dict[str, Any]:
        """
        주어진 CIK 목록 전체에 대해 가장 최신 표준재무 공시일을 한 번에 조회하여 맵으로 반환합니다.
        """
        if not ciks:
            return {}
        query = """
            SELECT cik, MAX(filed_dt) as latest_filed 
            FROM us_standard_financials 
            WHERE cik = ANY(%s)
            GROUP BY cik
        """
        with self.get_cursor() as cur:
            cur.execute(query, (ciks,))
            rows = cur.fetchall()
        return {r['cik']: r['latest_filed'] for r in rows}

    def get_all_latest_metric_filed_dates(self, ciks: List[str]) -> Dict[str, Any]:
        """
        주어진 CIK 목록 전체에 대해 가장 최신 재무비율 공시일을 한 번에 조회하여 맵으로 반환합니다.
        """
        if not ciks:
            return {}
        query = """
            SELECT cik, MAX(filed_dt) as latest_filed 
            FROM us_financial_metrics 
            WHERE cik = ANY(%s)
            GROUP BY cik
        """
        with self.get_cursor() as cur:
            cur.execute(query, (ciks,))
            rows = cur.fetchall()
        return {r['cik']: r['latest_filed'] for r in rows}

    def save_valuations(self, valuations: List[Tuple]) -> None:
        """
        us_daily_valuation 테이블에 가치평가 지표 목록을 50건 단위 배치로 나누어 Upsert합니다.
        """
        if not valuations:
            return

        query = """
            INSERT INTO us_daily_valuation (
                dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda
            )
            VALUES %s
            ON CONFLICT (dt, cik) DO UPDATE SET
                mkt_cap = EXCLUDED.mkt_cap,
                pe = EXCLUDED.pe,
                pb = EXCLUDED.pb,
                ps = EXCLUDED.ps,
                pcr = EXCLUDED.pcr,
                ev_ebitda = EXCLUDED.ev_ebitda
        """
        
        BATCH_SIZE = 50
        for i in range(0, len(valuations), BATCH_SIZE):
            batch = valuations[i : i + BATCH_SIZE]
            with self.get_cursor() as cur:
                execute_values(cur, query, batch)

    def save_metrics(self, metrics: List[Tuple]) -> None:
        """
        us_financial_metrics 테이블에 재무비율 목록을 Upsert합니다.
        """
        if not metrics:
            return

        query = """
            INSERT INTO us_financial_metrics (
                cik, report_period, filed_dt,
                roe, roa, roic, op_margin, net_margin,
                gp_a_ratio, debt_ratio, current_ratio, interest_coverage,
                rev_growth_yoy, op_growth_yoy, eps_growth_yoy
            )
            VALUES %s
            ON CONFLICT (cik, report_period, filed_dt) DO UPDATE SET
                roe = EXCLUDED.roe,
                roa = EXCLUDED.roa,
                roic = EXCLUDED.roic,
                op_margin = EXCLUDED.op_margin,
                net_margin = EXCLUDED.net_margin,
                gp_a_ratio = EXCLUDED.gp_a_ratio,
                debt_ratio = EXCLUDED.debt_ratio,
                current_ratio = EXCLUDED.current_ratio,
                interest_coverage = EXCLUDED.interest_coverage,
                rev_growth_yoy = EXCLUDED.rev_growth_yoy,
                op_growth_yoy = EXCLUDED.op_growth_yoy,
                eps_growth_yoy = EXCLUDED.eps_growth_yoy,
                created_at = NOW()
        """
        with self.get_cursor() as cur:
            execute_values(cur, query, metrics)

    def get_earliest_valuation_gap_date(self, cik: str, start_date: str = '2026-05-01') -> Any:
        """
        특정 CIK에 대해, 지정한 start_date 이후의 가격 데이터(us_daily_price)는 존재하나 
        가치평가 데이터(us_daily_valuation)가 매칭되지 않고 비어 있는 
        가장 오래된 날짜(MIN dt)를 반환합니다.
        재무 정보 및 발행주식수 이력이 둘 다 없는 종목(ETF/CEF 등)은 
        매번 불필요한 전체 재계산이 유발되지 않도록 gap 감지에서 제외합니다.
        """
        query = """
            SELECT MIN(p.dt) as gap_dt
            FROM us_daily_price p
            LEFT JOIN us_daily_valuation v ON p.dt = v.dt AND p.cik = v.cik
            WHERE p.cik = %s 
              AND p.dt >= %s
              AND v.cik IS NULL
              AND EXISTS (SELECT 1 FROM us_standard_financials f WHERE f.cik = p.cik)
              AND (
                  EXISTS (SELECT 1 FROM us_share_history s WHERE s.cik = p.cik)
                  OR EXISTS (SELECT 1 FROM us_standard_financials f WHERE f.cik = p.cik AND f.shares_outstanding IS NOT NULL)
              )
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik, start_date))
            row = cur.fetchone()
            if row and row.get('gap_dt'):
                return row['gap_dt']
        return None

    def get_valuations(self, cik: str, start_dt: str = None, end_dt: str = None) -> list[dict]:
        """특정 CIK의 일별 가치평가 정보를 조회 (날짜순 정렬)"""
        query = """
            SELECT dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda
            FROM us_daily_valuation
            WHERE cik = %s
        """
        params = [str(cik).zfill(10)]
        if start_dt:
            query += " AND dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND dt <= %s"
            params.append(end_dt)
            
        query += " ORDER BY dt ASC"
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def get_metrics(self, cik: str, start_dt: str = None, end_dt: str = None) -> list[dict]:
        """특정 CIK의 재무비율 정보를 조회 (날짜순 정렬)"""
        query = """
            SELECT 
                cik, report_period, filed_dt,
                roe, roa, roic, op_margin, net_margin,
                gp_a_ratio, debt_ratio, current_ratio, interest_coverage,
                rev_growth_yoy, op_growth_yoy, eps_growth_yoy
            FROM us_financial_metrics
            WHERE cik = %s
        """
        params = [str(cik).zfill(10)]
        if start_dt:
            query += " AND filed_dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND filed_dt <= %s"
            params.append(end_dt)
            
        query += " ORDER BY report_period ASC, filed_dt ASC"
        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def load_prices_bulk(self, ciks: List[str], start_date=None) -> List[Dict[str, Any]]:
        """
        주어진 CIK 목록 전체에 대해 일별 주가를 dt 오름차순으로 조회합니다.
        """
        if not ciks:
            return []
        
        if start_date:
            query = """
                SELECT cik, dt, cls_prc 
                FROM us_daily_price 
                WHERE cik = ANY(%s) AND dt >= %s 
                ORDER BY dt ASC
            """
            params = (ciks, start_date)
        else:
            query = """
                SELECT cik, dt, cls_prc 
                FROM us_daily_price 
                WHERE cik = ANY(%s) 
                ORDER BY dt ASC
            """
            params = (ciks,)
            
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def load_shares_bulk(self, ciks: List[str]) -> List[Dict[str, Any]]:
        """
        주어진 CIK 목록 전체에 대해 발행주식수 변동 이력을 filed_dt 오름차순으로 조회합니다.
        """
        if not ciks:
            return []
            
        query = """
            SELECT cik, filed_dt, val 
            FROM us_share_history 
            WHERE cik = ANY(%s) 
            ORDER BY filed_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (ciks,))
            return cur.fetchall()

    def load_financials_bulk(self, ciks: List[str]) -> List[Dict[str, Any]]:
        """
        주어진 CIK 목록 전체에 대해 표준화 재무 정보를 report_period 및 filed_dt 오름차순으로 조회합니다.
        """
        if not ciks:
            return []
            
        query = """
            SELECT 
                cik, report_period, filed_dt, fiscal_year, fiscal_period,
                total_assets, current_assets, cash_and_equiv, inventory, account_receivable,
                total_equity, retained_earnings,
                total_liabilities, current_liabilities, total_debt,
                shares_outstanding,
                revenue, cogs, gross_profit,
                sgna_expense, rnd_expense,
                op_income, interest_expense, tax_provision, net_income,
                ebitda, ocf, capex, fcf
            FROM us_standard_financials
            WHERE cik = ANY(%s)
            ORDER BY report_period ASC, filed_dt ASC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (ciks,))
            return cur.fetchall()



