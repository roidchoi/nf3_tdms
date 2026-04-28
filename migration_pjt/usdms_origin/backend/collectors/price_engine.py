import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class PriceEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def calculate_factors_from_ratio(self, cik: str, df: pd.DataFrame):
        """
        Detect price adjustment factors using the Ratio method (Price Engine v2).
        Formula: Factor = Ratio_t-1 / Ratio_t
        Where Ratio = Adj Close / Raw Close
        
        df: DataFrame with 'Close' (Raw) and 'Adj Close'
        """
        if 'Adj Close' not in df.columns or 'Close' not in df.columns:
            logger.warning(f"[{cik}] Missing Close or Adj Close for factor calc")
            return

        # Sort by date ascending (Past -> Future)
        df = df.sort_index()
        
        # 1. Calculate Ratio
        # Fill zero closes with NaN to avoid Inf
        raw_close = df['Close'].replace(0, np.nan)
        ratio = df['Adj Close'] / raw_close
        
        # 2. Compare with Previous Ratio
        prev_ratio = ratio.shift(1)
        
        # 3. Detect Change
        # Delta = |Ratio - Prev_Ratio|
        delta = (ratio - prev_ratio).abs()
        
        # Threshold 1e-5 (User Requirement)
        # Note: We look for events at index T where ratio changed from T-1.
        events = df[delta >= 1e-5].copy()
        
        if events.empty:
            return

        factors = []
        for dt, row in events.iterrows():
            curr_r = ratio.loc[dt]
            prev_r = prev_ratio.loc[dt]
            
            # Factor to apply to PAST prices = Prev_Ratio / Curr_Ratio
            # e.g., Split 2:1. Prev=0.5, Curr=1.0. Factor=0.5.
            # e.g., Div. Prev=0.9, Curr=1.0. Factor=0.9.
            
            if curr_r == 0:
                continue
                
            factor_val = prev_r / curr_r
            
            factors.append({
                'cik': cik,
                'event_dt': dt.date(),
                'factor_val': float(factor_val),
                'event_type': 'ADJUSTMENT', # Generic type as we rely on pure math
                'matched_info': f"Ratio Change: {prev_r:.4f} -> {curr_r:.4f}"
            })
            
        # 4. Insert Factors
        if factors:
            # Deduplicate
            unique_factors = {}
            for f in factors:
                key = (f['cik'], f['event_dt'], f['event_type'])
                unique_factors[key] = f
            
            clean_factors = list(unique_factors.values())
            self.db_manager.upsert_price_factors(clean_factors)
            logger.info(f"[{cik}] Calculated {len(clean_factors)} adjustment factors.")

