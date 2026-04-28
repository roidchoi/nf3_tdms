import sys
import os
import gc
import time
import logging
from tqdm import tqdm
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager
from backend.engines.valuation_calculator import ValuationCalculator

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ValRebuild")

def run_valuation_rebuild():
    logger.info(">>> Starting Valuation Rebuild (Memory Optimized) <<<")
    
    db = DatabaseManager()
    
    # 1. Get Targets (Collect Targets only)
    with db.get_cursor() as cur:
        # Only companies marked as targets, but also ensure they have price data?
        # Let 'calculate_and_save' handle empty data gracefully.
        cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE is_collect_target = TRUE")
        rows = cur.fetchall()
        # Sort by CIK for consistent order
        targets = sorted(rows, key=lambda x: x['cik'])
        
    logger.info(f"Target Count: {len(targets)} Tickers")
    db.close()
    
    # 2. Execution Setup
    CYCLE_LIMIT = 50
    success_count = 0
    fail_count = 0
    
    calc = ValuationCalculator()
    
    start_time = time.time()
    
    try:
        for i, target in enumerate(tqdm(targets, desc="Valuation Rebuild")):
            cik = target['cik']
            ticker = target['latest_ticker']
            
            try:
                # Calculate for ALL history (start_date=None)
                calc.calculate_and_save(cik, start_date=None)
                success_count += 1
            except Exception as e:
                logger.error(f"[{ticker}] Failed: {e}")
                # If OOM suspected, force sleep
                if "memory" in str(e).lower():
                    time.sleep(5)
                fail_count += 1
            
            # 3. Memory Safety Cycling
            if (i + 1) % CYCLE_LIMIT == 0:
                progress = (i + 1) / len(targets) * 100
                logger.info(f"Progress: {i + 1}/{len(targets)} ({progress:.1f}%) - Cycling DB & GC")
                
                calc.db.close()
                del calc
                gc.collect()
                time.sleep(0.5)
                calc = ValuationCalculator()
                
    finally:
         if calc:
             calc.db.close()
             
    elapsed = time.time() - start_time
    logger.info(f"Rebuild Complete in {elapsed:.1f}s. Success: {success_count}, Fail: {fail_count}")

if __name__ == "__main__":
    run_valuation_rebuild()
