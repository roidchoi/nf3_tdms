import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from backend.collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class MetricCalculator:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager if db_manager else DatabaseManager()

    def calculate_and_save(self, cik: str):
        """
        Load financials, calculate metrics (vectorized), and upsert.
        """
        # 1. Load Data
        df = self._load_financials(cik)
        if df.empty:
            logger.debug(f"[{cik}] No financials found.")
            return

        # 2. Calculate Metrics
        metrics_df = self._compute_metrics(df)
        
        # 3. Upsert
        if not metrics_df.empty:
            self._save_metrics(metrics_df)
            logger.info(f"[{cik}] Calculated & Saved {len(metrics_df)} metric records.")

    def _load_financials(self, cik: str) -> pd.DataFrame:
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
        with self.db.get_cursor() as cur:
            cur.execute(query, (cik,))
            rows = cur.fetchall()
            
        return pd.DataFrame(rows)

    def _compute_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Vectorized Calculation of Metrics.
        """
        # [Fix] Enforce numeric types to prevent TypeError on 'object' columns (containing None)
        # Identify numeric columns (all except cik, fiscal_period, etc.)
        numeric_cols = [
            'total_assets', 'current_assets', 'cash_and_equiv', 'inventory', 'account_receivable',
            'total_equity', 'retained_earnings', 'total_liabilities', 'current_liabilities', 'total_debt',
            'shares_outstanding', 'revenue', 'cogs', 'gross_profit',
            'sgna_expense', 'rnd_expense', 'op_income', 'interest_expense', 'tax_provision', 'net_income',
            'ebitda', 'ocf', 'capex', 'fcf'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Avoid Division by Zero
        def safe_div(a, b):
            # Since inputs are now floats (with NaN), we can strictly check for 0
            # NaN != 0 is True, resulting in NaN/NaN = NaN (Safe)
            # 1/0 is Inf (Safe in numpy unless set to raise)
            return np.where(b != 0, a / b, None)


        # --- Profitability ---
        # ROE = Net Income / Total Equity
        df['roe'] = safe_div(df['net_income'], df['total_equity'])
        # ROA = Net Income / Total Assets
        df['roa'] = safe_div(df['net_income'], df['total_assets'])
        # ROIC = (Op Income * (1 - TaxRate?)) / Invested Capital? 
        # Simplified ROIC: Op Income / (Total Equity + Total Debt)
        df['roic'] = safe_div(df['op_income'], (df['total_equity'] + df['total_debt'].fillna(0)))
        
        # Margins
        df['op_margin'] = safe_div(df['op_income'], df['revenue'])
        df['net_margin'] = safe_div(df['net_income'], df['revenue'])

        # --- Quality & Stability ---
        # GP/A = Gross Profit / Total Assets (Novy-Marx)
        df['gp_a_ratio'] = safe_div(df['gross_profit'], df['total_assets'])
        
        # Debt Ratio = Total Liabilities / Total Assets
        df['debt_ratio'] = safe_div(df['total_liabilities'], df['total_assets'])
        
        # Current Ratio = Current Assets / Current Liabilities
        df['current_ratio'] = safe_div(df['current_assets'], df['current_liabilities'])
        
        # Interest Coverage = Op Income / Interest Expense
        df['interest_coverage'] = safe_div(df['op_income'], df['interest_expense'])

        # --- Growth (YoY) ---
        # Strategy: distinct fiscal_period groups (Q1, Q2, Q3, FY) sorted by fiscal_year.
        # But 'fiscal_period' might be missing or inconsistent.
        # Fallback: Group by 'report_period' month? (e.g. 12, 09, 06, 03)
        # Let's try to use fiscal_period if available.
        
        # We need to handle duplicates (amendments). 
        # We perform calculations on all rows, but for Growth lookback, we should refer to the "Same Period Last Year".
        # This is tricky with multiple rows per period.
        # For simplicity in V1: We compute growth only if we find a matching (FY-1, FP) record.
        
        # Create a lookup key
        # If fiscal_year/period exists:
        if 'fiscal_year' in df.columns and 'fiscal_period' in df.columns:
            # We use a temporary DataFrame to find "Previous Year Value".
            # If multiple versions exist for T-1, generally use the LATEST version known (or earliest?).
            # Usually we compare against the *final* numbers of last year.
            # Let's pick the latest filed_dt for each (fiscal_year, fiscal_period) to build a reference map.
            
            # Filter valid FY/FP
            valid_idx = df['fiscal_year'].notna() & df['fiscal_period'].notna()
            
            # Build Reference (Latest filing for each period)
            ref_df = df[valid_idx].sort_values('filed_dt').drop_duplicates(subset=['fiscal_year', 'fiscal_period'], keep='last')
            ref_df = ref_df.set_index(['fiscal_year', 'fiscal_period'])
            
            # Helper to get prev val
            def get_growth(row, col):
                if pd.isna(row.get('fiscal_year')) or pd.isna(row.get('fiscal_period')):
                    return None
                
                prev_fy = row['fiscal_year'] - 1
                fp = row['fiscal_period']
                
                if (prev_fy, fp) in ref_df.index:
                    prev_val = ref_df.loc[(prev_fy, fp), col]
                    curr_val = row[col]
                    if prev_val and prev_val != 0 and curr_val is not None:
                        return (curr_val - prev_val) / abs(prev_val)
                return None
            
            # Apply (Row-wise is slow but safe for logic. Vectorize if possible)
            # Vectorized approach:
            # Join df with ref_df on (fy-1, fp)
            df['prev_fy'] = df['fiscal_year'] - 1
            
            merged = df.merge(
                ref_df[['revenue', 'op_income', 'net_income', 'shares_outstanding']], 
                left_on=['prev_fy', 'fiscal_period'], 
                right_index=True, 
                how='left', 
                suffixes=('', '_prev')
            )
            
            # Calculate Growth
            df['rev_growth_yoy'] = np.where(merged['revenue_prev'] != 0, (merged['revenue'] - merged['revenue_prev']) / merged['revenue_prev'].abs(), None)
            df['op_growth_yoy'] = np.where(merged['op_income_prev'] != 0, (merged['op_income'] - merged['op_income_prev']) / merged['op_income_prev'].abs(), None)
            
            # EPS Growth
            # Current EPS
            eps = safe_div(merged['net_income'], merged['shares_outstanding'])
            prev_eps = safe_div(merged['net_income_prev'], merged['shares_outstanding_prev'])
            
            # EPS Growth is tricky if EPS is negative/small. But let's follow standard formula.
            # Handle standard pandas nullable.
            eps = eps.astype(float)
            prev_eps = prev_eps.astype(float)
            
            df['eps_growth_yoy'] = np.where((prev_eps != 0) & (~np.isnan(prev_eps)) & (~np.isnan(eps)), 
                                            (eps - prev_eps) / np.abs(prev_eps), None)
                                            
            # Clean up temp cols
            df.drop(columns=['prev_fy'], inplace=True)
            
        else:
            # Fallback (shift by 4 if sorted by quarters?) 
            # Too risky. Just leave None for now if FY/FP missing.
            df['rev_growth_yoy'] = None
            df['op_growth_yoy'] = None
            df['eps_growth_yoy'] = None

        # Clean NaN/Inf
        for col in ['roe', 'roa', 'roic', 'op_margin', 'net_margin', 'gp_a_ratio', 'debt_ratio', 
                    'current_ratio', 'interest_coverage', 
                    'rev_growth_yoy', 'op_growth_yoy', 'eps_growth_yoy']:
             df[col] = df[col].replace([np.inf, -np.inf], None)
             df[col] = df[col].where(pd.notnull(df[col]), None)

        return df

    def _save_metrics(self, df: pd.DataFrame):
        data_list = df.to_dict('records')
        
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
        
        values = [
            (
                d['cik'], d['report_period'], d['filed_dt'],
                d['roe'], d['roa'], d['roic'], d['op_margin'], d['net_margin'],
                d['gp_a_ratio'], d['debt_ratio'], d['current_ratio'], d['interest_coverage'],
                d['rev_growth_yoy'], d['op_growth_yoy'], d['eps_growth_yoy']
            )
            for d in data_list
        ]
        
        with self.db.get_cursor() as cur:
            from psycopg2.extras import execute_values
            execute_values(cur, query, values)
