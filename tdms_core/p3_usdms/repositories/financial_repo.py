import logging
from typing import List, Dict, Any
from psycopg2.extras import execute_values
from p3_usdms.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

class FinancialRepo(BaseRepository):
    def delete_raw_facts_by_cik(self, cik: str) -> None:
        """
        특정 CIK의 모든 raw financial facts 데이터를 일괄 삭제합니다.
        EAV 특성상 히스토리가 길어 덮어쓰기 전 안전하게 전체 삭제를 수행합니다.
        """
        query = "DELETE FROM us_financial_facts WHERE cik = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))

    def insert_financial_facts(self, records: List[Dict[str, Any]]) -> None:
        """
        us_financial_facts EAV 데이터를 bulk insert 합니다.
        """
        if not records:
            return

        query = """
            INSERT INTO us_financial_facts (cik, tag, val, period_start, period_end, filed_dt, frame, fy, fp, form)
            VALUES %s
        """
        values = [
            (
                r['cik'],
                r['tag'],
                r['val'],
                r.get('period_start'),
                r.get('period_end'),
                r['filed_dt'],
                r.get('frame'),
                r.get('fy'),
                r.get('fp'),
                r.get('form')
            )
            for r in records
        ]
        with self.get_cursor() as cur:
            execute_values(cur, query, values)

    def upsert_standard_financials(self, records: List[Dict[str, Any]]) -> None:
        """
        us_standard_financials 테이블에 표준 재무 데이터를 upsert 합니다.
        Conflict Target: (cik, report_period, filed_dt)
        """
        if not records:
            return

        query = """
            INSERT INTO us_standard_financials (
                cik, report_period, filed_dt, fiscal_year, fiscal_period, 
                total_assets, current_assets, cash_and_equiv, inventory, account_receivable,
                total_equity, retained_earnings, total_liabilities, current_liabilities, total_debt, 
                shares_outstanding, revenue, cogs, gross_profit, sgna_expense,
                rnd_expense, op_income, interest_expense, tax_provision, net_income, 
                ebitda, ocf, capex, fcf
            )
            VALUES %s
            ON CONFLICT (cik, report_period, filed_dt) DO UPDATE SET
                fiscal_year = EXCLUDED.fiscal_year,
                fiscal_period = EXCLUDED.fiscal_period,
                total_assets = EXCLUDED.total_assets,
                current_assets = EXCLUDED.current_assets,
                cash_and_equiv = EXCLUDED.cash_and_equiv,
                inventory = EXCLUDED.inventory,
                account_receivable = EXCLUDED.account_receivable,
                total_equity = EXCLUDED.total_equity,
                retained_earnings = EXCLUDED.retained_earnings,
                total_liabilities = EXCLUDED.total_liabilities,
                current_liabilities = EXCLUDED.current_liabilities,
                total_debt = EXCLUDED.total_debt,
                shares_outstanding = EXCLUDED.shares_outstanding,
                revenue = EXCLUDED.revenue,
                cogs = EXCLUDED.cogs,
                gross_profit = EXCLUDED.gross_profit,
                sgna_expense = EXCLUDED.sgna_expense,
                rnd_expense = EXCLUDED.rnd_expense,
                op_income = EXCLUDED.op_income,
                interest_expense = EXCLUDED.interest_expense,
                tax_provision = EXCLUDED.tax_provision,
                net_income = EXCLUDED.net_income,
                ebitda = EXCLUDED.ebitda,
                ocf = EXCLUDED.ocf,
                capex = EXCLUDED.capex,
                fcf = EXCLUDED.fcf
        """
        values = [
            (
                r['cik'],
                r['report_period'],
                r['filed_dt'],
                r['fiscal_year'],
                r['fiscal_period'],
                r.get('total_assets'),
                r.get('current_assets'),
                r.get('cash_and_equiv'),
                r.get('inventory'),
                r.get('account_receivable'),
                r.get('total_equity'),
                r.get('retained_earnings'),
                r.get('total_liabilities'),
                r.get('current_liabilities'),
                r.get('total_debt'),
                r.get('shares_outstanding'),
                r.get('revenue'),
                r.get('cogs'),
                r.get('gross_profit'),
                r.get('sgna_expense'),
                r.get('rnd_expense'),
                r.get('op_income'),
                r.get('interest_expense'),
                r.get('tax_provision'),
                r.get('net_income'),
                r.get('ebitda'),
                r.get('ocf'),
                r.get('capex'),
                r.get('fcf')
            )
            for r in records
        ]
        with self.get_cursor() as cur:
            execute_values(cur, query, values)

    def upsert_share_history(self, records: List[Dict[str, Any]]) -> None:
        """
        us_share_history 테이블에 주식 수 이력을 upsert 합니다.
        Conflict Target: (cik, filed_dt)
        """
        if not records:
            return

        query = """
            INSERT INTO us_share_history (cik, filed_dt, val)
            VALUES %s
            ON CONFLICT (cik, filed_dt) DO UPDATE SET
                val = EXCLUDED.val
        """
        values = [
            (
                r['cik'],
                r['filed_dt'],
                r['val']
            )
            for r in records
        ]
        with self.get_cursor() as cur:
            execute_values(cur, query, values)

    def get_standard_financials_range(self, cik: str, start_dt: str = None, end_dt: str = None) -> list[dict]:
        """특정 CIK의 표준화 재무 정보를 범위로 조회 (날짜순 정렬)"""
        query = """
            SELECT 
                cik, report_period, filed_dt, fiscal_year, fiscal_period,
                total_assets, total_debt, shares_outstanding, revenue, gross_profit,
                op_income, rnd_expense, interest_expense, net_income, ebitda,
                ocf, capex, fcf
            FROM us_standard_financials
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

    def get_standard_financials_pit(self, cik: str, as_of_date: Any) -> list[dict]:
        """특정 시점(as_of_date) 기준으로 최신 공시된(filed_dt <= as_of) Point-in-Time 표준화 재무 정보 조회"""
        query = """
            SELECT DISTINCT ON (report_period)
                cik, report_period, filed_dt, fiscal_year, fiscal_period,
                total_assets, total_debt, shares_outstanding, revenue, gross_profit,
                op_income, rnd_expense, interest_expense, net_income, ebitda,
                ocf, capex, fcf
            FROM us_standard_financials
            WHERE cik = %s AND filed_dt <= %s
            ORDER BY report_period DESC, filed_dt DESC
        """
        with self.get_cursor() as cur:
            cur.execute(query, (str(cik).zfill(10), as_of_date))
            rows = cur.fetchall()
            # report_period 기준 오름차순 정렬 반환
            rows.sort(key=lambda x: x['report_period'])
            return rows

