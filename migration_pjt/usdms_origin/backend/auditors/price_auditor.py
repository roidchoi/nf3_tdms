import logging
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, date
from typing import List, Dict, Any, Tuple
from tqdm import tqdm
from dotenv import load_dotenv

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../backend/utils
parent_dir = os.path.dirname(current_dir) # .../backend
project_root = os.path.dirname(parent_dir) # .../01_usdms
sys.path.append(project_root)

from backend.collectors.db_manager import DatabaseManager
from backend.collectors.kis_us_wrapper import KisUSREST

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Known exceptions for historical floating point drifts or source mismatches
KNOWN_EXCEPTIONS = {
    "NVDA": {"threshold": 2.0, "reason": "Historical drift since 2007"},
}
DEFAULT_THRESHOLD = 0.1

class PriceReproducer:
    def __init__(self):
        self.db = DatabaseManager()
        self.kis = KisUSREST(mock=False, log_level=2) # log_level 2 for less noise

    def verify_ticker(self, ticker: str, start_dt: str = None, end_dt: str = None) -> Dict[str, Any]:
        """
        Verify Price Reproduction for a single ticker.
        1. Fetch Local Raw Prices & Factors.
        2. Fetch KIS Adj Close (Truth).
        3. Calculate Local Adj = Raw * Product(Factors).
        4. Compare.
        """
        cik = self.db.get_cik_by_ticker(ticker)
        if not cik:
            return {"status": "FAIL", "msg": "CIK not found"}

        # 1. Fetch Local Data
        raw_df = self._fetch_local_prices(cik, start_dt, end_dt)
        factors = self._fetch_local_factors(cik)
        
        if raw_df.empty:
            return {"status": "SKIP", "msg": "No local price data"}

        # 2. Fetch KIS Data (Truth)
        # Note: KIS API limits. Running this in loop needs care.
        try:
            kis_df = self.kis.get_ohlcv(ticker, start_date=start_dt, end_date=end_dt, add_adjusted=True)
        except Exception as e:
            return {"status": "ERROR", "msg": f"KIS API Error: {e}"}

        if kis_df.empty or 'Adj Close' not in kis_df.columns:
            return {"status": "SKIP", "msg": "No KIS data or Adj Close missing"}

        # 3. Align Data
        # Ensure indices match
        raw_df.index = pd.to_datetime(raw_df.index)
        kis_df.index = pd.to_datetime(kis_df.index)
        
        # Merge on Date
        merged = raw_df[['cls_prc']].join(kis_df[['Adj Close']], how='inner')
        if merged.empty:
             return {"status": "FAIL", "msg": "No overlapping dates"}
             
        # 4. Calculate Local Adj Close
        # Logic:
        # For each date D, Adjusted Price = Raw Price(D) * Product(Factors where EventDate > D)
        # Because events (Split/Div) usually adjust PAST prices.
        
        # Optimization: Pre-calculate Cumulative Factor Series
        # Create a Series of Factors indexed by EventDate
        # 1.0 initially.
        # Multiply by factor at EventDate.
        # Then CumProd backwards?
        
        # Let's do vectorized approach:
        # Create a Factor Series for all trading days (default 1.0).
        # Populate it with factors at Event Dates.
        # Cumulative Product Backwards (shift=-1)
        
        # Map Factors to Dates
        # Valid factors: factors that are in the date range of our data.
        # Warning: If a factor is OUTSIDE our data range (future), it still affects us?
        # Yes, if we have recent data and a future split happens... wait, DB usually has past data.
        # If we are verifying PAST data, we need all factors that happened AFTER the data point.
        
        dates = merged.index.sort_values()
        adj_close_calc = []
        
        # Convert factors to a list of (date, val)
        # Filter factors strictly > date
        # Sorting factors by date descending helps
        sorted_factors = sorted(factors, key=lambda x: x['event_dt'], reverse=True)
        
        # Naive Loop Implementation (Safe)
        # For each row, apply all factors happening AFTER this row's date.
        # Complexity: O(N * M) where N=days, M=factors. M is usually small (<100). N ~ 5000. 500k ops is fine.
        
        raw_prices = merged['cls_prc'].values
        truth_prices = merged['Adj Close'].values
        idx_dates = merged.index.date
        
        local_adj = []
        
        # Optimize: Iterate backwards from latest date
        # Maintain a running 'cumulative_factor'.
        # If we encounter an event date (going backwards), we update the cumulative factor.
        # Wait. 
        # T (Latest): Factor applies if EventDate > T. (None).
        # T-1: Factor applies if EventDate > T-1. (Event at T).
        # So we scan BACKWARDS from Latest.
        # Keep `current_cum_factor` initialized to 1.0.
        # When moving from T to T-1, did we cross an Ex-Date?
        # If T is an Ex-Date, then for T-1, we must apply the factor of T.
        # So: if date T is an event date with factor F, then for all dates < T, we multiply by F.
        
        # Dictionary of factors: Date -> Factor Product (if multiple on same day)
        factor_map = {}
        for f in sorted_factors:
            ed = f['event_dt']
            val = f['factor_val']
            factor_map[ed] = factor_map.get(ed, 1.0) * val
            
        cum_factor = 1.0
        
        # Iterate backwards
        calc_prices = np.zeros(len(raw_prices))
        
        # We need to iterate dates in descending order
        # merged is sorted by date ascending usually?
        # sort explicitly
        merged = merged.sort_index(ascending=True) # Old -> New
        dates_asc = merged.index.date
        raw_asc = merged['cls_prc'].values
        
        # Reverse to iterate New -> Old
        dates_desc = dates_asc[::-1]
        raw_desc = raw_asc[::-1]
        calc_desc = []
        
        # Find factors that are strictly AFTER the last date?
        # Usually we only care about factors up to "Now".
        # If there are factors in the future (rare), we ignore or apply? 
        # Usually KIS Adj Close reflects known future? No, usually reflects up to query time.
        # We assume factor_map contains historic events.
        
        # Need to handle "Event Date" carefully.
        # Event Date is Ex-Date.
        # On Ex-Date, price is already adjusted (Raw drops).
        # Past prices (pre Ex-Date) need to be adjusted down to match.
        # So for any date D < ExDate, apply factor.
        
        # Loop D from New to Old.
        # Check if D is in factor_map?
        # If D is in factor_map, it means D is the Ex-Date.
        # All prices BEFORE D (which we are about to visit next) should get this factor.
        # So update cum_factor AFTER processing D, but BEFORE processing D-1.
        
        for i, dt in enumerate(dates_desc):
            # 1. Calc Price for D (using cum_factor accumulated from Future)
            # Current D is not affected by event ON D. It is already post-event (or AT event).
            # Wait. If D is Ex-Date, raw price is Low. Adj Price is Low.
            # D-1 is Pre-Ex. Raw is High. Adj Price should be Low * Factor? No.
            # Adj Price (D-1) ~= Raw (D-1) * Factor.
            # So, cum_factor applies to D-1.
            # So we apply current cum_factor to D.
            
            calc_desc.append(raw_desc[i] * cum_factor)
            
            # 2. Update cum_factor for dates < D (next iterations)
            if dt in factor_map:
                cum_factor *= factor_map[dt]
                
        # Reverse back
        local_adj = np.array(calc_desc[::-1])
        
        merged['Local_Adj'] = local_adj
        
        merged['Error_Pct'] = (abs(merged['Local_Adj'] - merged['Adj Close']) / merged['Adj Close']) * 100
        
        # DEBUG: Inspect Factors
        print("\n[DEBUG] Factors Loaded:")
        for f in sorted_factors:
            print(f" - {f['event_dt']} : {f['factor_val']}")
            
        # DEBUG: Inspect Failing Row Neighborhood
        failed_mask = merged['Error_Pct'] > 0.1
        if failed_mask.any():
            fail_idx = merged[failed_mask].index[0]
            # Get +/- 2 days
            loc_idx = merged.index.get_loc(fail_idx)
            start_loc = max(0, loc_idx - 2)
            end_loc = min(len(merged), loc_idx + 3)
            print(f"\n[DEBUG] Neighborhood of failure ({fail_idx.date()}):")
            print(merged.iloc[start_loc:end_loc][['cls_prc', 'Adj Close', 'Local_Adj', 'Error_Pct']])
            
        max_err = merged['Error_Pct'].max()
        mean_err = merged['Error_Pct'].mean()
        
        # Determine Threshold
        exception_info = KNOWN_EXCEPTIONS.get(ticker)
        threshold = exception_info['threshold'] if exception_info else DEFAULT_THRESHOLD
        
        # Check Fail Condition
        failed_rows = merged[merged['Error_Pct'] > threshold]
        
        # Determine Status
        if max_err < threshold or (max_err < threshold and failed_rows.empty): 
            # Logic: If max_err < threshold, then failed_rows is empty naturally.
            status = "PASS"
            if exception_info:
                status += " (Exception Applied)"
        else:
            status = "FAIL"
            
        # Serialize failed samples (Only those above threshold)
        failed_list = []
        for idx, row in failed_rows.head(5).iterrows():
            failed_list.append({
                "dt": idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx),
                "cls_prc": row['cls_prc'],
                "Adj Close": row['Adj Close'],
                "Local_Adj": row['Local_Adj'],
                "Error_Pct": row['Error_Pct']
            })

        result = {
            "status": status,
            "max_error": round(max_err, 4),
            "mean_error": round(mean_err, 4),
            "sample_count": len(merged),
            "failed_count": len(failed_rows),
            "failed_samples": failed_list,
            "threshold_used": threshold
        }
        
        return result

    def _fetch_local_prices(self, cik: str, start_dt: str, end_dt: str) -> pd.DataFrame:
        query = """
            SELECT dt, cls_prc 
            FROM us_daily_price 
            WHERE cik = %s 
        """
        params = [cik]
        if start_dt:
            query += " AND dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND dt <= %s"
            params.append(end_dt)
        query += " ORDER BY dt ASC"
        
        with self.db.get_cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        df = df.set_index('dt')
        return df

    def _fetch_local_factors(self, cik: str) -> List[Dict]:
        query = "SELECT event_dt, factor_val FROM us_price_adjustment_factors WHERE cik = %s"
        with self.db.get_cursor() as cur:
            cur.execute(query, (cik,))
            return cur.fetchall()

if __name__ == "__main__":
    # Test Mode
    reproducer = PriceReproducer()
    
    # Test with AAPL (Should be normal PASS or FAIL)
    print("\nVerifying AAPL...")
    res_aapl = reproducer.verify_ticker('AAPL')
    print(res_aapl)

    # Test with NVDA (Should be PASS (Exception Applied))
    print("\nVerifying NVDA...")
    res_nvda = reproducer.verify_ticker('NVDA')
    print(res_nvda)
