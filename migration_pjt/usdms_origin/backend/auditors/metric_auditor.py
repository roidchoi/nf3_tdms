import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from backend.collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class MetricVerifier:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def verify_roe_logic(self, sample_limit=500) -> List[Dict]:
        """
        Reverse calc ROE: Metrics.ROE approx (Standard.NetIncome / Standard.TotalEquity).
        Note: Metrics ROE might use TTM Net Income or just annualized. 
        Our MetricCalculator uses simple division of stored values currently (row-wise).
        Formula used in MetricCalculator:
          df['roe'] = safe_div(df['net_income'], df['total_equity'])
        So checking direct match is valid.
        """
        # Join us_financial_metrics and us_standard_financials
        query = """
            SELECT m.cik, m.report_period, m.roe, s.net_income, s.total_equity
            FROM us_financial_metrics m
            JOIN us_standard_financials s 
              ON m.cik = s.cik AND m.report_period = s.report_period AND m.filed_dt = s.filed_dt
            WHERE m.roe IS NOT NULL
            LIMIT %s
        """
        failed_samples = []
        with self.db.get_cursor() as cur:
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            metrics_roe = r['roe']
            ni = r['net_income']
            equity = r['total_equity']
            
            if not equity or equity == 0: continue
            
            calc_roe = ni / equity
            
            # Tolerance 1% (0.01)
            if abs(metrics_roe - calc_roe) > 0.01:
                failed_samples.append({
                    "cik": r['cik'],
                    "period": str(r['report_period']),
                    "metrics_roe": metrics_roe,
                    "calc_roe": calc_roe,
                    "diff": abs(metrics_roe - calc_roe)
                })
        return failed_samples

    def verify_valuation_logic(self, sample_limit=500) -> List[Dict]:
        """
        Reverse calc Market Cap: Val.MktCap approx Price * Shares.
        Price comes from us_daily_price, Shares from us_share_history used at that calculation time.
        Querying logic is complex (PIT). So we do a 'Range/Sanity Check' instead, 
        or check consistency with latest available price/shares if we can join easily.
        
        Let's do Range Check & Consistency check for Mkt Cap > 0.
        """
        query = """
            SELECT dt, cik, mkt_cap, pe, pb
            FROM us_daily_valuation
            WHERE mkt_cap IS NOT NULL
            LIMIT %s
        """
        failed_samples = []
        with self.db.get_cursor() as cur:
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            mkt_cap = r['mkt_cap']
            if mkt_cap <= 0:
                failed_samples.append({
                    "cik": r['cik'],
                    "dt": str(r['dt']),
                    "issue": "Negative Market Cap",
                    "val": mkt_cap
                })
                
            # PE Ratio Outlier
            pe = r['pe']
            if pe and (pe > 10000 or pe < -10000):
                failed_samples.append({
                    "cik": r['cik'],
                    "dt": str(r['dt']),
                    "issue": "Extreme PE",
                    "val": pe
                })
                
        return failed_samples
