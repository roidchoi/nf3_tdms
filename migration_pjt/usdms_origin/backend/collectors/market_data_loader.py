import asyncio
import logging
import random
import pandas as pd
import numpy as np
import gc
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .db_manager import DatabaseManager
from .price_engine import PriceEngine
from .kis_us_wrapper import KisUSREST

logger = logging.getLogger(__name__)

class MarketDataLoader:
    def __init__(self):
        self.db = DatabaseManager()
        self.price_engine = PriceEngine(self.db)
        # KIS API Wrapper
        self.kis = KisUSREST(mock=False, log_level=1)

    def collect_batch(self, limit: int = 50):
        """
        Identify pending targets and collect data for them.
        """
        logger.info(f"Identifying pending targets (Limit: {limit})...")
        
        # 1. Get All Active Tickers
        # We assume us_ticker_master has the universe.
        query_all = "SELECT cik, latest_ticker FROM us_ticker_master WHERE is_collect_target = true"
        with self.db.get_cursor() as cur:
            cur.execute(query_all)
            all_tickers = cur.fetchall() # List of RealDictRow
            
        if not all_tickers:
            logger.info("No active tickers found in master.")
            return

        # 2. Get Collected Tickers
        # Check distinct tickers in us_daily_price
        query_done = "SELECT DISTINCT ticker FROM us_daily_price"
        with self.db.get_cursor() as cur:
            cur.execute(query_done)
            done_rows = cur.fetchall()
            done_tickers = {r['ticker'] for r in done_rows}
            
        # 3. Filter Pending
        pending = [t for t in all_tickers if t['latest_ticker'] not in done_tickers]
        
        if not pending:
            logger.info("All targets collected.")
            return

        targets = pending[:limit]
        logger.info(f"Starting batch collection for {len(targets)} tickers...")
        
        # 4. Process
        success_count = 0
        for t in targets:
            try:
                # Synchronous call because KIS Wrapper is sync/requests based
                # If we need async, we'd need to wrap it, but for now linear is fine for stability or use run_in_executor if needed.
                # Given strict rate limits (20/s), linear or controlled concurrency is needed.
                # KisREST handles rate limiting internally.
                if self.process_ticker(t['cik'], t['latest_ticker']):
                    success_count += 1
            except Exception as e:
                logger.error(f"[{t['latest_ticker']}] Batch Process Error: {e}")
                
        logger.info(f"Batch Complete. Success: {success_count}/{len(targets)}")

    def collect_daily_updates(self, lookback_days: int = 10, ciks: List[str] = None):
        """
        Incremental update for all active tickers (or specific list).
        1. Lookback 10 days to handle provisional data correction.
        2. Upsert Prices.
        3. Trigger Factor Calculation.
        """
        logger.info(f"Starting Daily Update (Lookback: {lookback_days}d)...")
        
        # 1. Get Active Tickers
        if ciks:
            query = "SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)"
            params = (ciks,)
        else:
            query = "SELECT cik, latest_ticker FROM us_ticker_master WHERE is_collect_target = true"
            params = ()
            
        with self.db.get_cursor() as cur:
            cur.execute(query, params)
            targets = cur.fetchall()
            
        if not targets:
            logger.info("No active targets found.")
            return

        logger.info(f"Updating {len(targets)} tickers...")
        
        # 2. Define Date Range
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days)
        start_str = start_dt.strftime('%Y%m%d')
        end_str = end_dt.strftime('%Y%m%d')
        
        success_count = 0
        
        from tqdm import tqdm
        for i, t in enumerate(pd.Series(targets)): # Use enumerate for index
            try:
                if self.process_ticker(t['cik'], t['latest_ticker'], start_date=start_str, end_date=end_str):
                    success_count += 1
            except Exception as e:
                logger.error(f"[{t['latest_ticker']}] Update Error: {e}")

            if (i + 1) % 50 == 0:
                percent = int(((i + 1) / len(targets)) * 100)
                logger.info(f"Market Data Progress: {i + 1}/{len(targets)} ({percent}%)")
                
        logger.info(f"Daily Update Complete. Success: {success_count}/{len(targets)}")

    def process_ticker(self, cik: str, ticker: str, start_date: str = None, end_date: str = None) -> bool:
        """
        Fetch from KIS and Save.
        """
        try:
            # 1. Fetch Data
            # add_adjusted=True to get 'Adj Close' for PriceEngine
            df = self.kis.get_ohlcv(ticker, start_date=start_date, end_date=end_date, add_adjusted=True)
            
            if df.empty:
                # logger.warning(f"[{ticker}] No data returned from KIS.") # Quiet for updates
                return False
                
            # 2. Save Data & Process Factors
            self._save_data(cik, ticker, df)
            return True
            
        except Exception as e:
            logger.error(f"[{ticker}] Process Error: {e}")
            return False

    def _save_data(self, cik: str, ticker: str, df: pd.DataFrame):
        """
        Save OHLCV to DB and trigger PriceEngine.
        """
        try:
            # Keep copy for PriceEngine (needs Close and Adj Close)
            df_for_engine = df.copy()
            
            # 1. Prepare OHLCV for DB
            # KIS returns Index as Date
            df = df.reset_index()
            
            # Map columns KIS (Date, Open, High, Low, Close, Adj Close, Volume) -> DB
            # DB Schema: open_prc, high_prc, low_prc, cls_prc (Raw), vol
            
            rename_map = {
                'Date': 'dt',
                'Open': 'open_prc',
                'High': 'high_prc', 
                'Low': 'low_prc', 
                'Close': 'cls_prc', 
                'Volume': 'vol'
            }
            
            # Check required columns
            if not all(c in df.columns for c in rename_map.keys()):
                logger.error(f"[{ticker}] Missing columns: {df.columns}")
                return

            df = df.rename(columns=rename_map)
            
            # Add identifiers
            df['cik'] = cik
            df['ticker'] = ticker
            df['amt'] = 0.0 # KIS US stock might not provide amt in daily chart easily, defaulting
            
            # Type Conversion
            df['dt'] = pd.to_datetime(df['dt']).dt.date
            df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0).astype(int)
            
            # Select columns for insert
            db_cols = ['dt', 'cik', 'ticker', 'open_prc', 'high_prc', 'low_prc', 'cls_prc', 'vol', 'amt']
            price_records = df[db_cols].to_dict('records')
            
            # Clean numpy types
            clean_prices = []
            for r in price_records:
                clean_r = {k: (v.item() if isinstance(v, (np.generic)) else v) for k, v in r.items()}
                clean_prices.append(clean_r)
                
            # Insert Prices
            self.db.insert_daily_price(clean_prices)
            
            # 2. Process Factors
            # df_for_engine has 'Close' (Raw) and 'Adj Close'
            try:
                self.price_engine.calculate_factors_from_ratio(cik, df_for_engine)
            except Exception as e:
                logger.error(f"[{ticker}] Factor Calculation Error: {e}")

        except Exception as e:
            logger.error(f"[{ticker}] Save Error: {e}")
            raise e
        finally:
            del df
            gc.collect()

