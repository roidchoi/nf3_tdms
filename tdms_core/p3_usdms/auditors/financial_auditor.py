# tdms_core/p3_usdms/auditors/financial_auditor.py
import logging
from contextlib import contextmanager
from typing import List, Dict, Any
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class FinancialDiagnostic:
    def __init__(self, pool):
        self.pool = pool

    @contextmanager
    def get_dict_cursor(self):
        """DbConnectionPool에서 RealDictCursor를 제공하는 컨텍스트 매니저"""
        if not self.pool:
            # pool이 없을 때 (예: 단위 테스트 Mocking 시)
            yield None
            return
        conn = self.pool.get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Financial Auditor DB Query failed: {e}")
            raise e
        finally:
            self.pool.put_conn(conn)

    def check_accounting_identity(self, sample_limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Assets = Liabilities + Equity 항등식 검증 (허용 오차 0.1% 초과 시 실패)
        """
        query = """
            SELECT cik, report_period, filed_dt,
                   total_assets, total_liabilities, total_equity
            FROM us_standard_financials
            WHERE total_assets IS NOT NULL 
              AND total_liabilities IS NOT NULL 
              AND total_equity IS NOT NULL
            LIMIT %s
        """
        failed_samples = []
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            assets = float(r['total_assets'])
            liab_equity = float(r['total_liabilities']) + float(r['total_equity'])
            
            # Tolerance: 0.1%
            if assets == 0:
                continue
            
            diff_pct = abs(assets - liab_equity) / abs(assets) * 100
            if diff_pct > 0.1:
                failed_samples.append({
                    "cik": r['cik'],
                    "report_period": str(r['report_period']),
                    "assets": assets,
                    "liab_equity": liab_equity,
                    "diff_pct": round(diff_pct, 4)
                })
        
        return failed_samples

    def check_critical_nulls(self) -> List[Dict[str, Any]]:
        """
        total_assets (임계치 5%), revenue (임계치 10%), net_income (임계치 5%)의 NULL 발생 비율 검사
        """
        query = """
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN total_assets IS NULL THEN 1 END) as null_assets,
                COUNT(CASE WHEN revenue IS NULL THEN 1 END) as null_revenue,
                COUNT(CASE WHEN net_income IS NULL THEN 1 END) as null_income
            FROM us_standard_financials
        """
        failed_samples = []
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query)
            res = cur.fetchone()
            
        total = res['total']
        if total == 0:
            return []
        
        null_assets_pct = (res['null_assets'] / total) * 100
        null_revenue_pct = (res['null_revenue'] / total) * 100
        null_income_pct = (res['null_income'] / total) * 100
        
        if null_assets_pct > 5.0:
            failed_samples.append({"field": "total_assets", "null_pct": round(null_assets_pct, 2)})
        if null_revenue_pct > 10.0:
            failed_samples.append({"field": "revenue", "null_pct": round(null_revenue_pct, 2)})
        if null_income_pct > 5.0:
            failed_samples.append({"field": "net_income", "null_pct": round(null_income_pct, 2)})
            
        return failed_samples

    def check_historical_leakage(self) -> List[Dict[str, Any]]:
        """
        공시연도(report_period.year)와 회계연도(fiscal_year) 차이가 2년을 초과하는지 검사
        """
        query = """
            SELECT cik, report_period, fiscal_year, fiscal_period
            FROM us_standard_financials
            WHERE fiscal_year IS NOT NULL
        """
        failed_samples = []
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query)
            rows = cur.fetchall()
            
        for r in rows:
            # report_period가 str일 수 있으므로 날짜 변환/추출 처리 안전화
            report_period = r['report_period']
            if isinstance(report_period, str):
                from datetime import datetime
                try:
                    report_year = datetime.strptime(report_period[:10], "%Y-%m-%d").year
                except ValueError:
                    continue
            else:
                report_year = report_period.year
                
            fiscal_year = int(r['fiscal_year'])
            
            if abs(report_year - fiscal_year) > 2:
                failed_samples.append({
                    "cik": r['cik'],
                    "report_period": str(r['report_period']),
                    "fiscal_year": fiscal_year,
                    "diff": abs(report_year - fiscal_year)
                })
        
        return failed_samples[:20]
