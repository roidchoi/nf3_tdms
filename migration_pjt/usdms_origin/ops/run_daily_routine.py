import logging
import json
import os
import sys
import uuid
import asyncio
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.collectors.master_sync import MasterSync
from backend.collectors.market_data_loader import MarketDataLoader
from backend.collectors.financial_parser import FinancialParser
from backend.collectors.sec_client import SECClient
from backend.engines.valuation_calculator import ValuationCalculator
from backend.collectors.db_manager import DatabaseManager
from backend.auditors.price_auditor import PriceReproducer
from backend.utils.blacklist_manager import BlacklistManager

# Load env
load_dotenv(override=True)

# Logging
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../logs/db_health/daily_routine'))
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Thread-Local Storage
thread_local_storage = threading.local()

class DailyRoutine:
    def __init__(self):
        self.db = DatabaseManager()
        self.master = MasterSync()
        self.market_loader = MarketDataLoader()
        self.fin_parser = FinancialParser()
        # self.val_engine = ValuationCalculator() # Removed for thread safety
        self.sec_client = SECClient()
        self.verifier = PriceReproducer()
        self.blacklist = BlacklistManager()
        
        self.report = {
            "meta": {
                "report_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "type": "DAILY_ROUTINE"
            },
            "steps": [],
            "stats": {},
            "anomalies": []
        }

    async def run(self):
        logger.info(">>> Starting Daily Routine (v4.0) <<<")
        
        # Test Mode
        test_limit = int(os.getenv('TEST_LIMIT', 0))
        if test_limit > 0:
            logger.info(f"TEST MODE: Limit {test_limit}")
            

        # ---------------------------------------------------------
        # Step 1: Master Sync (Async)
        # ---------------------------------------------------------
        self._record_step("Master Sync", "STARTED")
        try:
            # Sync is now async to avoid nested loops
            # Pass test_limit to restrict enrichment scope
            stats = await self.master.sync_daily(limit=test_limit if test_limit > 0 else None)
            self.report['stats']['master'] = stats
            self._record_step("Master Sync", "SUCCESS")
        except Exception as e:
            logger.error(f"Master Sync Failed: {e}", exc_info=True)
            self._record_step("Master Sync", "FAILED", str(e))
            
        # [CRITICAL] Reset DB Connection to clear session memory/locks
        logger.info(">>> Resetting DB Connection after Master Sync...")
        self.db.close()
        self.db = DatabaseManager()

        # ---------------------------------------------------------
        # Step 2: Market Data Update
        # ---------------------------------------------------------
        self._record_step("Market Update", "STARTED")
        try:
            # 2. Daily Price Update (Last 10 Days)
            # Use same test limit if needed, or implement limit in loader
            targets = None # Default is all
            if test_limit > 0:
                # For test efficiency, we might want to restrict this too, 
                # but MarketDataLoader doesn't take simple int limit for update yet.
                # However, it does check 'active' status. 
                # If Master Sync worked correctly, only test set might be active? 
                # No, is_collect_target is from DB.
                # Let's manually fetch limited CIKs if in test mode O(N)
                with self.db.get_cursor() as cur:
                     cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target=TRUE LIMIT %s", (test_limit,))
                     rows = cur.fetchall()
                     targets = [r['cik'] for r in rows]

            self.market_loader.collect_daily_updates(lookback_days=10, ciks=targets)
            self._record_step("Market Update", "SUCCESS")
            
            # Removed crashing COUNT(*) query
            self.report['stats']['market'] = {'status': 'Completed'}
            
        except Exception as e:
            logger.error(f"Market Update Failed: {e}", exc_info=True)
            self._record_step("Market Update", "FAILED", str(e))

        # [CRITICAL] Reset DB Connection
        logger.info(">>> Resetting DB Connection after Market Update...")
        self.db.close()
        self.db = DatabaseManager()
        
        # ---------------------------------------------------------
        # Step 3: Financial Data Update
        # ---------------------------------------------------------
        # ---------------------------------------------------------
        # Step 3: Financial Data Update (Smart Gap Recovery)
        # ---------------------------------------------------------
        self._record_step("Financial Update", "STARTED")
        try:
            # 1. Determine Scan Range
            # Start: Global Max Date - 3 days (Safety Overlap)
            with self.db.get_cursor() as cur:
                cur.execute("SELECT MAX(filed_dt) as d FROM us_financial_facts")
                res = cur.fetchone()
                
            global_max = res['d'] if res and res['d'] else date(2024, 1, 1)
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            start_scan = global_max - timedelta(days=1)
            # Cap start date if too old (e.g. only backfill 1 month for routine stability)
            if (yesterday - start_scan).days > 60:
                logger.warning(f"Gap too large ({start_scan} ~ {yesterday}). Limiting to last 60 days.")
                start_scan = yesterday - timedelta(days=60)
                
            if start_scan > yesterday:
                start_scan = yesterday
            
            logger.info(f"Gap Scan Range: {start_scan} ~ {yesterday}")
            
            # 2. Get Targets & Blacklist
            with self.db.get_cursor() as cur:
                cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target=TRUE")
                target_rows = cur.fetchall()
            target_ciks = {int(r['cik']) for r in target_rows if str(r['cik']).isdigit()}
            logger.info(f"Loaded {len(target_ciks)} target CIKs.")
            
            # 3. Scan & Filter
            unique_candidates = {} # {cik: filing_obj} (Keep Latest)
            current = start_scan
            
            total_filings_found = 0
            
            while current <= yesterday:
                if current.weekday() >= 5: 
                    current += timedelta(days=1)
                    continue
                
                curr_str = current.strftime('%Y%m%d')
                logger.info(f"Scanning Index for {curr_str}...")
                
                filings = self.sec_client.get_filings_by_date(curr_str)
                if not filings:
                    current += timedelta(days=1)
                    continue
                    
                for f in filings:
                    # Basic Filter: Form Type
                    if f.get('form_type') not in ['10-K', '10-Q', '8-K', '10-K/A', '10-Q/A']:
                        continue
                        
                    try:
                        cik = int(f.get('cik'))
                    except:
                        continue
                        
                    # Filter 1: Is Target?
                    if cik not in target_ciks:
                        continue
                        
                    # Filter 2: Is Blacklisted?
                    # Note: BlacklistManager uses zero-padded string internally
                    if self.blacklist.is_blacklisted(cik):
                        logger.debug(f"Skipping Blacklisted CIK {cik}")
                        continue
                        
                    # Keep Candidate (Latest date wins if duplicate in range)
                    # We store the filing object to pass to parser if needed, 
                    # but actually parser.process_filings usually just takes CIK to call get_company_facts.
                    # Wait, process_filings takes list of filing dicts.
                    # We keep the object.
                    f['filed_dt'] = current # [CRITICAL] Inject Date for later comparison
                    unique_candidates[cik] = f
                    total_filings_found += 1
                
                current += timedelta(days=1)
                
            logger.info(f"Found {total_filings_found} filings. Unique Candidate CIKs: {len(unique_candidates)}")
            
            if not unique_candidates:
                self._record_step("Financial Update", "SUCCESS", "No candidates found.")
                
            else:
                # Filter 3: DB Overlap Check (Zero-Padding Fix)
                ciks = list(unique_candidates.keys())
                final_targets = []
                
                # Batch check
                batch_size = 500
                for i in range(0, len(ciks), batch_size):
                    batch = ciks[i:i+batch_size]
                    batch_padded = [str(c).zfill(10) for c in batch]
                    placeholders = ','.join(['%s'] * len(batch))
                    
                    query = f"""
                        SELECT cik, MAX(filed_dt) as last_collected 
                        FROM us_financial_facts 
                        WHERE cik IN ({placeholders}) 
                        GROUP BY cik
                    """
                    
                    with self.db.get_cursor() as cur:
                        cur.execute(query, batch_padded)
                        rows = cur.fetchall()
                        
                    db_map = {int(r['cik']): r['last_collected'] for r in rows}
                    
                    for cik in batch:
                        candidate = unique_candidates[cik]
                        candidate_date = candidate['filed_dt']
                        last_collected = db_map.get(cik)
                        
                        # Process if:
                        # 1. New to DB (not in db_map)
                        # 2. Newer than last collected date
                        if not last_collected or candidate_date > last_collected:
                            final_targets.append(candidate)

                logger.info(f"Identified {len(final_targets)} NEW filings to process (after DB overlap check).")
                
                if final_targets:
                    # Execute Parsing & Saving
                    # process_filings expects list of dicts.
                    self.fin_parser.process_filings(final_targets)
                else:
                    self._record_step("Financial Update", "SUCCESS", "No new filings.")

        except Exception as e:
            logger.error(f"Financial Update Failed: {e}", exc_info=True)
            self._record_step("Financial Update", "FAILED", str(e))

        # ---------------------------------------------------------
        # Step 3.5: Metric Update (Calculated Financials)
        # ---------------------------------------------------------
        self._record_step("Metric Update", "STARTED")
        try:
            # Requires MetricCalculator import
            from backend.engines.metric_calculator import MetricCalculator
            
            metric_targets = []
            # Optimized: Only update metrics for CIKs that had NEW filings today
            # But 'final_targets' from Step 3 is local scope.
            # Alternative: Update all targets? Fast enough.
            # Or rely on 'final_targets' if we lift it to self scope?
            # Let's rebuild for ALL targets for safety in V4.0 (Fast enough)
            
            with self.db.get_cursor() as cur:
                cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target=TRUE")
                rows = cur.fetchall()
                metric_targets = [r['cik'] for r in rows]
                
            if test_limit > 0:
                metric_targets = metric_targets[:test_limit]
            
            logger.info(f"Updating Metrics for {len(metric_targets)} tickers...")
            
            mc = MetricCalculator()
            m_count = 0
            for cik in metric_targets:
                try:
                    mc.calculate_and_save(cik)
                    m_count += 1
                except Exception as e:
                    logger.warning(f"Metric Calc failed for {cik}: {e}")
            
            self.report['stats']['metrics'] = {'calculated_count': m_count}
            self._record_step("Metric Update", "SUCCESS")
            
        except Exception as e:
            logger.error(f"Metric Update Failed: {e}", exc_info=True)
            self._record_step("Metric Update", "FAILED", str(e))


        # ---------------------------------------------------------
        # Step 4: Valuation Update (Single-Threaded Sequential)
        # ---------------------------------------------------------
        self._record_step("Valuation Update", "STARTED")
        try:
            # [Step 4] Valuation Update
            # Optimized: Only run for 'is_collect_target=TRUE' (Data Consistency)
            # Was: 'is_active=TRUE' -> Caused stale data issue
            self._record_step("Valuation Update", "IN_PROGRESS", "Calculating ratios for targets...")

            with self.db.get_cursor() as cur:
                cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target = TRUE")
                val_targets = [row['cik'] for row in cur.fetchall()]
            
            if test_limit > 0:
                val_targets = val_targets[:test_limit]
                
            target_date = datetime.now().date()
            # Optimization: Only recalculate last 60 days to bridge the transition gap
            window_start_date = target_date - timedelta(days=60)
            
            logger.info(f"Calculating Valuation for {len(val_targets)} tickers (Window: {window_start_date} ~ {target_date})...")
            
            # Single-Threaded Execution to prevent OutOfMemory / DB Lock Contention
            val_engine = ValuationCalculator()
            count = 0
            
            # Use small batches and reset connection occasionally? 
            # Or just rely on single thread + incremental window.
            # V3 Plan: Reduce Batch Size if internal batching exists. 
            # Actually run_daily_routine loop calls calculate_and_save ONE BY ONE.
            # To fix OOM in loop, we should re-instantiate val_engine (and its db) every N items.
            
            for i, cik in enumerate(val_targets):
                try:
                    val_engine.calculate_and_save(cik, start_date=window_start_date)
                    count += 1
                    
                    if i > 0 and i % 50 == 0:
                        logger.info(f"Valuation Progress: {i}/{len(val_targets)} ({int(i/len(val_targets)*100)}%)")
                        val_engine.db.close()
                        val_engine.db = DatabaseManager()
                        
                except Exception as e:
                    logger.warning(f"Valuation failed for {cik}: {e}")
                    # Critical OOM Handling
                    if "out of shared memory" in str(e).lower():
                         logger.error("OOM Detected in Valuation! Sleeping and Resetting Connection...")
                         import time
                         time.sleep(5)
                         val_engine.db.close()
                         val_engine.db = DatabaseManager()
                    # Continue to next
            
            self.report['stats']['valuation'] = {'calculated_count': count}
            self._record_step("Valuation Update", "SUCCESS")
            
        except Exception as e:
            logger.error(f"Valuation Update Failed: {e}", exc_info=True)
            self._record_step("Valuation Update", "FAILED", str(e))

        # [CRITICAL] Reset DB Connection
        logger.info(">>> Resetting DB Connection after Valuation Update...")
        self.db.close()
        self.db = DatabaseManager()

        # ---------------------------------------------------------
        # Step 5: Health Check (Anomaly Detection)
        # ---------------------------------------------------------
        self._record_step("Health Check", "STARTED")
        try:
            anomalies = self._detect_anomalies()
            self.report['anomalies'] = anomalies
            
            if anomalies:
                self._record_step("Health Check", "WARNING", f"Found {len(anomalies)} anomalies")
            else:
                self._record_step("Health Check", "SUCCESS")
                
        except Exception as e:
             logger.error(f"Health Check Failed: {e}", exc_info=True)
             self._record_step("Health Check", "FAILED", str(e))

        self._save_report()
        logger.info(">>> Daily Routine Complete <<<")

    def _detect_anomalies(self):
        """
        5-1. Price Spikes (> 50%)
        5-2. Valuation Jumps (PER/PBR 2x or 0.5x)
        PYTHON-SIDE LOGIC (NO DB JOIN)
        """
        anomalies = []
        try:
            # 1. Fetch Today's Data vs Yesterday's Data separately (Simple SELECTs = Safe Locks)
            # FORCE PARTITION PRUNING: Use string literals for dates, NOT SQL functions (CURRENT_DATE)
            today_str = datetime.now().strftime('%Y-%m-%d')
            prev_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            query_current_price = f"SELECT cik, cls_prc FROM us_daily_price WHERE dt = '{today_str}'"
            query_prev_price = f"SELECT cik, cls_prc FROM us_daily_price WHERE dt = '{prev_str}'"
            
            with self.db.get_cursor() as cur:
                cur.execute(query_current_price)
                df_curr = pd.DataFrame(cur.fetchall())
                
                cur.execute(query_prev_price)
                df_prev = pd.DataFrame(cur.fetchall())

            # 2. Process Price Spikes in Python
            if not df_curr.empty and not df_prev.empty and 'cik' in df_curr.columns and 'cik' in df_prev.columns:
                merged = pd.merge(df_curr, df_prev, on='cik', suffixes=('_curr', '_prev'))
                # Filter
                merged['prev_curr'] = pd.to_numeric(merged['cls_prc_prev'], errors='coerce')
                merged['curr_curr'] = pd.to_numeric(merged['cls_prc_curr'], errors='coerce')
                merged = merged[merged['prev_curr'] > 0]
                merged['change'] = (merged['curr_curr'] - merged['prev_curr']) / merged['prev_curr']
                
                spikes = merged[merged['change'].abs() > 0.5]
                
                # We need tickers, fetch master map
                if not spikes.empty:
                    with self.db.get_cursor() as cur:
                        cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (spikes['cik'].tolist(),))
                        ticker_map = {r['cik']: r['latest_ticker'] for r in cur.fetchall()}
                    
                    for _, row in spikes.iterrows():
                        anomalies.append({
                            'type': 'PRICE_SPIKE',
                            'ticker': ticker_map.get(row['cik'], str(row['cik'])),
                            'curr': row['curr_curr'],
                            'prev': row['prev_curr'],
                            'change_pct': round(row['change'] * 100, 2)
                        })

            # 3. Process Valuation Jumps in Python
            query_curr_val = f"SELECT cik, pe FROM us_daily_valuation WHERE dt = '{today_str}'"
            query_prev_val = f"SELECT cik, pe FROM us_daily_valuation WHERE dt = '{prev_str}'"
            
            with self.db.get_cursor() as cur:
                cur.execute(query_curr_val)
                # handle empty
                rows_c = cur.fetchall()
                df_v_curr = pd.DataFrame(rows_c) if rows_c else pd.DataFrame()
                
                cur.execute(query_prev_val)
                rows_p = cur.fetchall()
                df_v_prev = pd.DataFrame(rows_p) if rows_p else pd.DataFrame()

            if not df_v_curr.empty and not df_v_prev.empty and 'cik' in df_v_curr.columns:
                merged_val = pd.merge(df_v_curr, df_v_prev, on='cik', suffixes=('_curr', '_prev'))
                merged_val['pe_curr'] = pd.to_numeric(merged_val['pe_curr'], errors='coerce')
                merged_val['pe_prev'] = pd.to_numeric(merged_val['pe_prev'], errors='coerce')
                merged_val = merged_val[merged_val['pe_prev'] > 0]
                merged_val['ratio'] = merged_val['pe_curr'] / merged_val['pe_prev']
                
                jumps = merged_val[(merged_val['ratio'] >= 2.0) | (merged_val['ratio'] <= 0.5)]
                
                if not jumps.empty:
                    # Reuse ticker map if possible or fetch
                    ciks_needed = jumps['cik'].tolist()
                    with self.db.get_cursor() as cur:
                        cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (ciks_needed,))
                        t_map = {r['cik']: r['latest_ticker'] for r in cur.fetchall()}
                        
                    for _, row in jumps.iterrows():
                        anomalies.append({
                            'type': 'VALUATION_JUMP',
                            'ticker': t_map.get(row['cik'], str(row['cik'])),
                            'metric': 'PE',
                            'curr': row['pe_curr'],
                            'prev': row['pe_prev'],
                            'ratio': round(row['ratio'], 2)
                        })

        except Exception as e:
            logger.error(f"Anomaly Detection Failed (Soft Fail): {e}")

        return anomalies

    def _record_step(self, step, status, msg=""):
        self.report["steps"].append({
            "step": step,
            "status": status,
            "message": msg,
            "timestamp": datetime.now().isoformat()
        })

    def _save_report(self):
        filename = f"daily_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(LOG_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, indent=2, default=str)
        logger.info(f"Report saved to {path}")

if __name__ == "__main__":
    routine = DailyRoutine()
    asyncio.run(routine.run())

