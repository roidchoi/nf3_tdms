import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from backend.collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class FinancialDiagnostic:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def check_accounting_identity(self, sample_limit=1000) -> List[Dict]:
        """
        Check Balance Sheet Identity: Assets = Liabilities + Equity
        Returns list of failed samples.
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
        with self.db.get_cursor() as cur:
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            assets = r['total_assets']
            liab_equity = r['total_liabilities'] + r['total_equity']
            
            # Tolerance: 0.1%
            if assets == 0: continue
            
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

    def check_critical_nulls(self) -> List[Dict]:
        """
        Check for critical fields being NULL (Assets, Revenue, Net Income).
        Returns failure stats if threshold exceeded.
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
        with self.db.get_cursor() as cur:
            cur.execute(query)
            res = cur.fetchone()
            
        total = res['total']
        if total == 0: return []
        
        null_assets_pct = (res['null_assets'] / total) * 100
        null_revenue_pct = (res['null_revenue'] / total) * 100
        null_income_pct = (res['null_income'] / total) * 100
        
        # Threshold: 5% (flexible for revenue/income as some companies might not report yet or distinct forms)
        # But for 'standard' financials, high null rate is bad.
        
        if null_assets_pct > 5.0:
            failed_samples.append({"field": "total_assets", "null_pct": round(null_assets_pct, 2)})
        if null_revenue_pct > 10.0: # Revenue might be null for some holding cos?
            failed_samples.append({"field": "revenue", "null_pct": round(null_revenue_pct, 2)})
        if null_income_pct > 5.0:
            failed_samples.append({"field": "net_income", "null_pct": round(null_income_pct, 2)})
            
        return failed_samples

    def check_historical_leakage(self) -> List[Dict]:
        """
        Check if fiscal_year matches report_period year (within reasonable range).
        Prevents historical data being mapped to wrong recent years.
        """
        query = """
            SELECT cik, report_period, fiscal_year, fiscal_period
            FROM us_standard_financials
            WHERE fiscal_year IS NOT NULL
        """
        failed_samples = []
        with self.db.get_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
        for r in rows:
            report_year = r['report_period'].year
            fiscal_year = r['fiscal_year']
            
            # Allow 1-2 year difference (Fiscal year ending in Jan 2024 is FY2023 usually, or FY2024 depending on company convention)
            # Drift > 2 years is suspicious.
            if abs(report_year - fiscal_year) > 2:
                failed_samples.append({
                    "cik": r['cik'],
                    "report_period": str(r['report_period']),
                    "fiscal_year": fiscal_year,
                    "diff": abs(report_year - fiscal_year)
                })
        
        # Limit samples
        return failed_samples[:20]
