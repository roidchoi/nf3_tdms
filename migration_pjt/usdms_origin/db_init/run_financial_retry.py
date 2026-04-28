import sys
import os
import json
import time
import gc
import logging
from tqdm import tqdm
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.financial_parser import FinancialParser

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FinRetry")

REPORT_PATH = "db_init/financial_recovery_report.json"
RETRY_REPORT_PATH = "db_init/financial_retry_report.json"

def run_retry():
    # 1. Load Failures
    if not os.path.exists(REPORT_PATH):
        logger.error(f"Report not found: {REPORT_PATH}")
        return
        
    with open(REPORT_PATH, 'r') as f:
        report = json.load(f)
        
    failures = report.get('failures', [])
    if not failures:
        logger.info("No failures to retry.")
        return
    
    # Target only specific error types or all?
    # User asked for Urgent Patch for ORCL, T, CRM.
    # But we can retry all 267 failures. Many are 404s working as intended, but retrying them won't hurt (just 404 again).
    # However, to save time we might prioritize, but for simplicity let's retry all.
    # ACTUALLY, checking for 404s again is wasteful. 
    # But maybe some 404s were transient?
    # Let's retry ALL failures to be safe, but expecting most 404s to persist.
    
    targets = []
    for fail in failures:
        targets.append({'cik': fail['cik'], 'ticker': fail['ticker']})
        
    logger.info(f"Retrying {len(targets)} failed tickers...")
    
    # 2. Setup
    parser = FinancialParser()
    success_count = 0
    new_failures = []
    
    # 3. Execution (Connection Cycling every 50)
    CYCLE_LIMIT = 50
    
    try:
        for i, target in enumerate(tqdm(targets, desc="Retrying")):
            cik = target['cik']
            ticker = target['ticker']
            
            try:
                time.sleep(0.5) # Rate Limit
                parser.process_company(cik)
                success_count += 1
                logger.info(f"[{ticker}] Retry SUCCESS")
                
            except Exception as e:
                # logger.error(f"[{ticker}] Retry Failed: {e}")
                new_failures.append({'cik': cik, 'ticker': ticker, 'reason': str(e)})
            
            # Connection Cycling
            if (i + 1) % CYCLE_LIMIT == 0:
                parser.db_manager.close()
                parser = None
                gc.collect()
                time.sleep(1.0)
                parser = FinancialParser()
                
    finally:
        if parser:
            parser.db_manager.close()
            
    # 4. Report
    retry_report = {
        "timestamp": report['timestamp'],
        "retry_timestamp": os.popen('date -u +"%Y-%m-%dT%H:%M:%SZ"').read().strip(),
        "total_retried": len(targets),
        "success_count": success_count,
        "failure_count": len(new_failures),
        "failures": new_failures
    }
    
    with open(RETRY_REPORT_PATH, 'w') as f:
        json.dump(retry_report, f, indent=2)
        
    logger.info(f"Retry Complete. Recovered: {success_count}/{len(targets)}. Report: {RETRY_REPORT_PATH}")

if __name__ == "__main__":
    run_retry()
