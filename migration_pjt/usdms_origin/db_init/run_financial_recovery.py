import sys
import os
import time
import gc
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from tqdm import tqdm

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.financial_parser import FinancialParser
from backend.collectors.db_manager import DatabaseManager

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FinRecov")

REPORT_PATH = "db_init/financial_recovery_report.json"

class FinancialRecoveryManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.parser = None
        
    def get_targets(self):
        """Get all active collection targets."""
        logger.info(">>> Identifying Financial Recovery Targets...")
        with self.db.get_cursor() as cur:
            cur.execute("""
                SELECT cik, latest_ticker 
                FROM us_ticker_master 
                WHERE is_collect_target = TRUE 
                  AND is_active = TRUE
                ORDER BY cik
            """)
            targets = cur.fetchall()
            
        logger.info(f"    - Found {len(targets)} targets.")
        return targets

    def run(self):
        targets = self.get_targets()
        if not targets:
            return

        # Close initial DB connection to start fresh in cycle
        self.db.close()
        
        success_count = 0
        failures = []
        
        # Configuration
        CYCLE_LIMIT = 50
        SLEEP_SEC = 0.5
        
        self.init_parser()
        
        try:
            for i, target in enumerate(tqdm(targets, desc="Processing")):
                cik = target['cik']
                ticker = target['latest_ticker']
                
                try:
                    # Rate Limit
                    time.sleep(SLEEP_SEC)
                    
                    # Process
                    # FinancialParser.process_company handles fetching and upserting logic checks
                    self.parser.process_company(cik)
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"[{ticker}] Recovery Error: {e}")
                    failures.append({'cik': cik, 'ticker': ticker, 'reason': str(e)})
                    
                # Garbage Collection & Connection Cycling
                if (i + 1) % CYCLE_LIMIT == 0:
                    logger.info(f"--- Cycling DB Connection (Processed {i+1}/{len(targets)}) ---")
                    self.cycle_parser()
                    
        finally:
            if self.parser:
                self.parser.db_manager.close()
                
        # Report
        report = {
            "timestamp": datetime.now().isoformat(),
            "target_count": len(targets),
            "success_count": success_count,
            "failure_count": len(failures),
            "failures": failures
        }
        
        with open(REPORT_PATH, 'w') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Recovery Complete. Success: {success_count}/{len(targets)}. Report: {REPORT_PATH}")

    def init_parser(self):
        """Create new parser instance (and new DB pool)"""
        if self.parser:
            try:
                self.parser.db_manager.close()
            except:
                pass
        
        # FinancialParser init creates new DatabaseManager(), which creates new Pool if None
        self.parser = FinancialParser()
        
    def cycle_parser(self):
        """Destroy and recreate parser to free resources"""
        if self.parser:
            self.parser.db_manager.close() # Closes static pool
            self.parser = None
            
        gc.collect()
        time.sleep(1.0) # Cool down
        
        self.init_parser()

if __name__ == "__main__":
    manager = FinancialRecoveryManager()
    manager.run()
