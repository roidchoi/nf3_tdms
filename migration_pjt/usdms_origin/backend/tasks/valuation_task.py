import logging
import pandas as pd
import numpy as np
from typing import List
from ..collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class ValuationTask:
    def __init__(self):
        self.db_manager = DatabaseManager()

    def run(self, batch_size: int = 50):
        """
        Run valuation calculation for all active tickers in batches.
        """
        logger.info("Starting Valuation Task...")
        
        # 1. Get Active CIKs
        ciks = self._get_active_ciks()
        logger.info(f"Found {len(ciks)} active CIKs.")
        
        # 2. Process in Batches
        for i in range(0, len(ciks), batch_size):
            batch_ciks = ciks[i:i + batch_size]
            logger.info(f"Processing batch {i} to {i + batch_size}...")
            try:
                self.process_batch(batch_ciks)
            except Exception as e:
                logger.error(f"Failed to process batch {i}: {e}", exc_info=True)
                
        logger.info("Valuation Task Complete.")

    def _get_active_ciks(self) -> List[str]:
        with self.db_manager.get_cursor() as cur:
            cur.execute("SELECT cik FROM us_ticker_master WHERE is_active = TRUE")
            rows = cur.fetchall()
            return [r['cik'] for r in rows]

    def process_batch(self, ciks: List[str]):
        # 1. Fetch Data for Batch
        # We need Price History and Financial History for these CIKs.
        # Fetching all history might be heavy, but for 50 CIKs it's manageable.
        
        price_df = self._fetch_prices(ciks)
        financial_df = self._fetch_financials(ciks)
        
        if price_df.empty:
            logger.warning("No price data for this batch.")
            return

        # 2. Process per CIK (Vectorization across CIKs is hard due to merge_asof by group)
        # merge_asof 'by' argument supports grouping.
        
        # Ensure types
        price_df['dt'] = pd.to_datetime(price_df['dt'])
        price_df = price_df.sort_values('dt')
        
        if not financial_df.empty:
            financial_df['filed_dt'] = pd.to_datetime(financial_df['filed_dt'])
            financial_df['report_period'] = pd.to_datetime(financial_df['report_period'])
            financial_df = financial_df.sort_values('filed_dt')
            
            # Calculate TTM for Financials
            # TTM = Rolling sum of last 4 quarters.
            # We must group by CIK and sort by report_period (not filed_dt for TTM calc, but report_period is logical sequence)
            # However, filed_dt is when it becomes available.
            # TTM calculation should be based on logical sequence of quarters.
            
            # Sort by CIK, Report Period
            financial_df = financial_df.sort_values(['cik', 'report_period'])
            
            # Calculate TTM columns
            ttm_cols = ['net_income', 'ebitda', 'fcf', 'gross_profit', 'revenue', 'ocf']
            # Balance Sheet items (Assets, Debt, Equity) are Point-in-Time (Instant), so we take the Latest, not Sum.
            # But Income/CF are Duration, so we Sum.
            
            # Group by CIK and apply rolling
            # Strict TTM: min_periods=4
            
            for col in ttm_cols:
                if col in financial_df.columns:
                    financial_df[f'{col}_ttm'] = financial_df.groupby('cik')[col].transform(
                        lambda x: x.rolling(window=4, min_periods=4).sum()
                    )
            
            # Now we have TTM values attached to each financial record.
            # We need to join this with Price based on filed_dt.
            # Sort by filed_dt for merge_asof
            financial_df = financial_df.sort_values('filed_dt')
            
            # 3. Merge Price and Financials (PIT)
            # merge_asof: left=Price, right=Financials, on=dt/filed_dt, by=cik
            # direction='backward' (Price uses latest past Financial)
            
            merged_df = pd.merge_asof(
                price_df,
                financial_df,
                left_on='dt',
                right_on='filed_dt',
                by='cik',
                direction='backward'
            )
            
            # 4. Calculate Ratios
            # merged_df has price columns and financial columns (latest available)
            
            results = []
            
            # Vectorized calculation
            # Handle missing values safely
            
            # Market Cap
            # shares_outstanding is from financials (latest). 
            # Ideally shares should be from separate source or latest filing.
            # Using latest filing shares is standard for historical PIT.
            
            merged_df['mkt_cap'] = merged_df['cls_prc'] * merged_df['shares_outstanding']
            
            # PER = Market Cap / Net Income TTM
            merged_df['pe_ratio'] = merged_df['mkt_cap'] / merged_df['net_income_ttm']
            
            # EV = Market Cap + Total Debt - Cash
            # Debt/Cash are BS items, so we use the value from the record (Latest Instant)
            merged_df['ev'] = merged_df['mkt_cap'] + merged_df['total_debt'].fillna(0) - merged_df['cash_and_equiv'].fillna(0)
            
            # EV/EBITDA
            merged_df['ev_ebitda'] = merged_df['ev'] / merged_df['ebitda_ttm']
            
            # P/FCF
            merged_df['pfcf_ratio'] = merged_df['mkt_cap'] / merged_df['fcf_ttm']
            
            # GP/A (Gross Profit TTM / Total Assets)
            merged_df['gp_a_ratio'] = merged_df['gross_profit_ttm'] / merged_df['total_assets']
            
            # PSR (Price to Sales)
            merged_df['ps_ratio'] = merged_df['mkt_cap'] / merged_df['revenue_ttm']
            
            # PBR (Price to Book)
            merged_df['pb_ratio'] = merged_df['mkt_cap'] / merged_df['total_equity']
            
            # PCR (Price to Cash) - Optional
            merged_df['pcr_ratio'] = merged_df['mkt_cap'] / merged_df['ocf_ttm']

            # Prepare for DB
            # Filter rows where we have at least some valuation (or just save all?)
            # Saving all allows seeing price history even if financials missing.
            # But table is us_valuation_ratios.
            # Let's save where we have Market Cap at least?
            
            # Replace inf/nan with None
            merged_df = merged_df.replace([np.inf, -np.inf], np.nan)
            
            # Select columns
            target_cols = ['dt', 'cik', 'mkt_cap', 'pe_ratio', 'pb_ratio', 'ps_ratio', 'pcr_ratio', 'ev_ebitda', 'pfcf_ratio', 'gp_a_ratio']
            
            # Convert to dict list
            # dropna subset? No, we want to update what we can.
            
            records = merged_df[target_cols].to_dict('records')
            
            # Clean NaNs to None for SQL
            clean_records = []
            for r in records:
                clean_r = {k: (None if pd.isna(v) else v) for k, v in r.items()}
                # Ensure dt is date
                if isinstance(clean_r['dt'], pd.Timestamp):
                    clean_r['dt'] = clean_r['dt'].date()
                clean_records.append(clean_r)
                
            # Upsert
            self.db_manager.upsert_valuation_ratios(clean_records)
            
        else:
            logger.warning("No financial data for this batch.")

    def _fetch_prices(self, ciks: List[str]) -> pd.DataFrame:
        if not ciks: return pd.DataFrame()
        with self.db_manager.get_cursor() as cur:
            # Fetch all history for these CIKs
            # In production, might limit to recent window if updating incrementally.
            # For Phase 4, we reload all.
            query = "SELECT dt, cik, cls_prc FROM us_daily_price WHERE cik = ANY(%s)"
            cur.execute(query, (ciks,))
            rows = cur.fetchall()
            return pd.DataFrame(rows)

    def _fetch_financials(self, ciks: List[str]) -> pd.DataFrame:
        if not ciks: return pd.DataFrame()
        with self.db_manager.get_cursor() as cur:
            # Fetch standard financials
            query = "SELECT * FROM us_standard_financials WHERE cik = ANY(%s)"
            cur.execute(query, (ciks,))
            rows = cur.fetchall()
            return pd.DataFrame(rows)
