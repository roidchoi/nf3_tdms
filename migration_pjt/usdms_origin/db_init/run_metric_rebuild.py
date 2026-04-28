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
from backend.engines.metric_calculator import MetricCalculator

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MetricRebuild")

def run_metric_rebuild():
    logger.info(">>> Starting Financial Metrics Rebuild <<<")
    
    db = DatabaseManager()
    
    # 1. Get Targets (All CIKs that have financials)
    with db.get_cursor() as cur:
        # Optimization: Only select CIKs that actually have data in standard_financials
        cur.execute("SELECT DISTINCT cik FROM us_standard_financials")
        rows = cur.fetchall()
        
    ciks = sorted([row['cik'] for row in rows])
    logger.info(f"Target Count: {len(ciks)} CIKs")
    
    db.close() # Close mainly to reset before loop
    
    # 2. Execution
    calc = MetricCalculator()
    success_count = 0
    fail_count = 0
    
    start_time = time.time()
    
    for i, cik in enumerate(tqdm(ciks, desc="Metric Rebuild")):
        try:
            calc.calculate_and_save(cik)
            success_count += 1
        except Exception as e:
            logger.error(f"[{cik}] Failed: {e}")
            fail_count += 1
            
        # Basic Resource Mgmt
        if (i + 1) % 1000 == 0:
            gc.collect()
            
    elapsed = time.time() - start_time
    logger.info(f"Rebuild Complete in {elapsed:.1f}s. Success: {success_count}, Fail: {fail_count}")

if __name__ == "__main__":
    run_metric_rebuild()
