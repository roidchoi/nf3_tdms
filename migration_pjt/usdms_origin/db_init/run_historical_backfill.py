import sys
import os
import time
import gc
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.market_data_loader import MarketDataLoader
from backend.collectors.db_manager import DatabaseManager

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HistBackfill")

REPORT_PATH = "db_init/backfill_history_report.json"
CRITICAL_TICKERS = ['IPG', 'VRNT', 'INFA']
BACKFILL_END_DATE = "20251219" # Fixed End Date to prevent intraday noise

class HistoricalBackfillManager:
    def __init__(self):
        # Initial DB Connection for target identification
        self.db = DatabaseManager()
        self.loader = None # Lazy init per cycle
        
    def get_targets(self):
        """
        Identify Active collected targets with ZERO price data.
        """
        logger.info(">>> identifying Backfill Targets...")
        with self.db.get_cursor() as cur:
            # Efficient NOT EXISTS
            q = """
                SELECT m.cik, m.latest_ticker, m.exchange
                FROM us_ticker_master m
                WHERE m.is_active = TRUE 
                  AND m.is_collect_target = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM us_daily_price p WHERE p.cik = m.cik
                  )
            """
            cur.execute(q)
            targets = cur.fetchall()
            
        logger.info(f"    - Found {len(targets)} targets needing full backfill.")
        return targets

    def run(self):
        targets = self.get_targets()
        
        if not targets:
            logger.info("No targets found. utilization complete.")
            return

        success_count = 0
        failures = []
        
        # Connection Cycling Logic
        CYCLE_LIMIT = 50
        
        # Initialize first loader
        self.init_loader()
        
        logger.info(f"Starting Backfill Execution. Range: 1980-01-01 ~ {BACKFILL_END_DATE}")
        
        try:
            for i, target in enumerate(targets):
                cik = target['cik']
                ticker = target['latest_ticker']
                
                # Critical Sample Monitoring
                is_critical = ticker in CRITICAL_TICKERS
                if is_critical:
                    logger.info(f"*** STARTING CRITICAL BACKFILL: {ticker} ({cik}) ***")
                
                try:
                    # Rate Limit
                    time.sleep(0.15)
                    
                    # Full Range Collection (1980 ~ BACKFILL_END_DATE)
                    # process_ticker handles Fetch -> Save -> Factor Calc
                    result = self.loader.process_ticker(cik, ticker, start_date=None, end_date=BACKFILL_END_DATE)
                    
                    if result:
                        success_count += 1
                        if is_critical:
                             logger.info(f"*** SUCCESS CRITICAL BACKFILL: {ticker} ***")
                    else:
                        failures.append({'cik': cik, 'ticker': ticker, 'reason': 'No Data Returned'})
                        if is_critical:
                             logger.warning(f"*** FAILED CRITICAL BACKFILL: {ticker} ***")
                        
                except Exception as e:
                    logger.error(f"[{ticker}] Backfill Error: {e}")
                    failures.append({'cik': cik, 'ticker': ticker, 'reason': str(e)})
                    
                # Garbage Collection
                gc.collect()
                
                # Connection Cycling
                if (i + 1) % CYCLE_LIMIT == 0:
                    logger.info(f"--- Cycling DB Connection (Processed {i+1}/{len(targets)}) ---")
                    self.idling_cycle()
                    
        finally:
            self.close_loader()
            self.db.close() # Close initial DB
            
        # Report
        report = {
            "timestamp": datetime.now().isoformat(),
            "params": {"mode": "Full Historical", "targets": len(targets)},
            "stats": {
                "success": success_count,
                "failed": len(failures)
            },
            "failures": failures
        }
        
        with open(REPORT_PATH, 'w') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Backfill Complete. Success: {success_count}/{len(targets)}. Report: {REPORT_PATH}")

    def init_loader(self):
        """Init MarketDataLoader (creates fresh DB connection)"""
        if self.loader:
            try:
                self.loader.db.close()
            except: 
                pass
        self.loader = MarketDataLoader()
        
    def close_loader(self):
        if self.loader:
            try:
                self.loader.db.close()
            except:
                pass
            self.loader = None

    def idling_cycle(self):
        """Destroy and recreate loader to free DB resources"""
        self.close_loader()
        gc.collect()
        time.sleep(1) # Cool down
        self.init_loader()

if __name__ == "__main__":
    manager = HistoricalBackfillManager()
    manager.run()
