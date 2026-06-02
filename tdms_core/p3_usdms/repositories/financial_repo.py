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
                total_assets, total_debt, shares_outstanding, revenue, gross_profit, 
                op_income, rnd_expense, interest_expense, net_income, ebitda, 
                ocf, capex, fcf
            )
            VALUES %s
            ON CONFLICT (cik, report_period, filed_dt) DO UPDATE SET
                fiscal_year = EXCLUDED.fiscal_year,
                fiscal_period = EXCLUDED.fiscal_period,
                total_assets = EXCLUDED.total_assets,
                total_debt = EXCLUDED.total_debt,
                shares_outstanding = EXCLUDED.shares_outstanding,
                revenue = EXCLUDED.revenue,
                gross_profit = EXCLUDED.gross_profit,
                op_income = EXCLUDED.op_income,
                rnd_expense = EXCLUDED.rnd_expense,
                interest_expense = EXCLUDED.interest_expense,
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
                r.get('total_debt'),
                r.get('shares_outstanding'),
                r.get('revenue'),
                r.get('gross_profit'),
                r.get('op_income'),
                r.get('rnd_expense'),
                r.get('interest_expense'),
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
