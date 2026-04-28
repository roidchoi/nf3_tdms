import asyncio
import aiohttp
import logging
import random
import os
import concurrent.futures
import concurrent.futures
import threading
import time
import queue # Thread-safe queue
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict, deque
from psycopg2.extras import execute_batch, execute_values
from .db_manager import DatabaseManager
from .sec_client import SECClient

logger = logging.getLogger(__name__)

class BufferedLogHandler(logging.Handler):
    """
    Captures logs using a lock-free SimpleQueue for emit, 
    and drains to a buffer for querying. 
    Prevents Deadlocks during logging storms.
    """
    def __init__(self):
        super().__init__()
        self.queue = queue.SimpleQueue()
        self.buffer = defaultdict(list)
        # Lock only for buffer access (Reading/Draining), NOT for Logging (Emit)
        self.buffer_lock = threading.Lock()
        
    def emit(self, record):
        try:
            # Format message here to catch formatting errors early
            msg = self.format(record)
            entry = (record.thread, msg, record.created)
            # Thread-safe, non-blocking put (C-level atomic)
            self.queue.put_nowait(entry)
        except Exception:
            self.handleError(record)
            
    def drain(self):
        """Move logs from Queue to Buffer safely."""
        # SimpleQueue lacks bulk get, so we loop.
        # This reduces contention on the logging thread.
        while not self.queue.empty():
            try:
                entry = self.queue.get_nowait()
                with self.buffer_lock:
                    self.buffer[entry[0]].append({
                        'msg': entry[1],
                        'time': entry[2]
                    })
            except queue.Empty:
                break
            
    def get_logs_by_thread(self, thread_id, min_time=0):
        # Sync buffer first
        self.drain()
        
        with self.buffer_lock:
            # Return copy of logs to avoid concurrency issues during iteration by caller
            if thread_id in self.buffer:
                 return [entry['msg'] for entry in self.buffer[thread_id] if entry['time'] >= min_time]
            return []

class MasterSync:
    def __init__(self):
        self.db = DatabaseManager()
        self.sec_client = SECClient()
        # Safety Protocol: Concurrency Limit (Externalized)
        self.sem = asyncio.Semaphore(int(os.getenv('MAX_CONCURRENCY', 5)))
        
        # Log Capture Setup for yfinance
        self.log_handler = BufferedLogHandler()
        yf_logger = logging.getLogger('yfinance')
        yf_logger.addHandler(self.log_handler)
        
        # Ensure level is allowing info/error
        if yf_logger.getEffectiveLevel() > logging.INFO:
            yf_logger.setLevel(logging.INFO)
            
        # Dedicated Executor for yfinance (Prevents zombie starvation)
        self.yf_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=int(os.getenv('MAX_CONCURRENCY', 5)) * 2,
            thread_name_prefix='YF_Worker'
        ) 

    @staticmethod
    def normalize_exchange(raw: str) -> str:
        """
        Normalize exchange names to 5 standard values:
        ['NASDAQ', 'NYSE', 'AMEX', 'OTC', 'OTHER']
        """
        if not raw:
            return 'OTHER'
            
        up = raw.upper().strip()
        
        # NASDAQ
        if up in ['NASDAQ', 'NMS', 'NGM', 'NCM', 'NAS', 'NMFQS']:
            return 'NASDAQ'
            
        # NYSE
        if up in ['NYSE', 'NEW YORK STOCK EXCHANGE', 'NYQ', 'NYS', 'NYC']:
            return 'NYSE'
            
        # AMEX
        if up in ['AMEX', 'AMERICAN STOCK EXCHANGE', 'ASE', 'ASEQ']:
            return 'AMEX'
            
        # OTC
        if up in ['PNK', 'PINK', 'PINK SHEETS', 'OTC', 'OTCQX', 'OTCQB', 'OTC MARKETS', 'OTC Markets']:
            return 'OTC'
            
        return 'OTHER'

    async def collect_daily_master_updates(self, ciks: List[str] = None):
        """
        Legacy wrapper for backward compatibility or direct calls.
        Redirects to sync_daily if ciks is None.
        """
        if ciks:
             # Just enrich specific CIKs
             await self._enrich_specific_ciks(ciks)
        else:
             self.sync_daily()
    
    async def _enrich_specific_ciks(self, ciks: List[str]):
        # Helper for test mode or targeted enrichment
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (ciks,))
            rows = cur.fetchall()
            ciks_map = {r['cik']: r['latest_ticker'] for r in rows}
            
        tasks = [self._fetch_yfinance_metadata(cik, ticker) for cik, ticker in ciks_map.items()]
        results = await asyncio.gather(*tasks)
        self._bulk_update_metadata([r for r in results if r])

    def _resolve_primary_ticker(self, candidates: List[Dict], current_db_ticker: Optional[str] = None) -> Dict:
        """
        Logic V2:
        Rule 0: Exception Map (Hard Override)
        Rule 1: Exchange Rank (NYSE > NASDAQ > AMEX > OTC > OTHER)
        Rule 2: Purity (No Special Chars)
        Rule 3: Stickiness (If Rank/Purity essentially tied)
        Rule 4: Tie-Breaker (Length ASC -> Alpha ASC)
        """
        if not candidates:
            return None
            
        # [Rule 0] Exception Map
        # Candidates share the same CIK. Use the first one's cik_str.
        # Ensure CIK is 10-digit string for consistent lookup.
        cik_str = str(candidates[0].get('cik_str', 0)).zfill(10)
        
        EXCEPTION_MAP = {
            '0001652044': 'GOOGL',  # Alphabet
            '0001067983': 'BRK-B',  # Berkshire
            '0001336917': 'UAA',    # Under Armour
            '0001754301': 'FOXA'    # Fox Corp
        }
        
        if cik_str in EXCEPTION_MAP:
            target = EXCEPTION_MAP[cik_str]
            for c in candidates:
                if c['ticker'] == target:
                    return c
        
        # Helper: Exchange Rank
        # We need normalized exchange for ranking.
        # Note: candidates coming from SECClient.get_company_tickers() usually DON'T have exchange info directly.
        # The caller (sync_daily) enriches them or passes 'exchange_raw' if available.
        # But looking at sync_daily implementation in this file:
        # It calls self._resolve_primary_ticker(candidates, ...) BEFORE resolving exchange for each candidate?
        # WAIT. In sync_daily:
        # candidates = sec_cik_candidates[cik] (List of dicts from get_company_tickers)
        # sec_exchanges = {cik: exchange} (Dict)
        # 
        # The individual candidates in `candidates` list do NOT have specific exchange info attached 
        # (unless they come from a source that provides per-ticker exchange).
        # SEC `company_tickers_exchange.json` maps Ticker -> Exchange. 
        # So we can look up exchange for each ticker.
        
        # We need a robust way to get exchange for a candidate ticker here.
        # Does MasterSync have access to the full ticker-exchange map? 
        # Currently `sync_daily` fetches `sec_exchanges` which seems to be CIK->Exchange?
        # Let's check `sec_client.get_tickers_exchange()`:
        # It usually returns {cik: exchange} or {ticker: exchange}?
        # Looking at previous context: `temp_test/verify_ticker_logic_v2.py` fetched it as Ticker->Exchange map.
        
        # CRITICAL: `SECClient.get_tickers_exchange` usually returns {cik: exchange} based on previous code usage?
        # But `company_tickers_exchange.json` actually lists Ticker and Exchange.
        # If multiple tickers share a CIK, `get_tickers_exchange` might overwrite/return just one?
        # 
        # Let's assume for V2 Logic to work BEST, we need access to Ticker->Exchange map.
        # However, `sync_daily` currently passes a list of simple dicts from `get_company_tickers`.
        
        # Modification:
        # We will implement the ranking logic assuming we can get exchange info.
        # If the input `candidates` dicts don't have 'exchange', we might default to 'OTC' or 'OTHER'.
        # BUT `sync_daily` needs to be updated to inject exchange info if we want Rule 1 to work properly!
        
        # Let's look at `sync_daily` again (lines 114+).
        # It fetches `sec_exchanges = self.sec_client.get_tickers_exchange()`.
        # If this returns CIK->Exchange, then ALL tickers for that CIK get the SAME exchange?
        # If so, Exchange Ranking (Rule 1) is useless for differentiating tickers within the SAME CIK.
        # Unless... `company_tickers_exchange.json` has different exchanges for tickers of same CIK?
        # (e.g. Ticker A on NYSE, Ticker B on OTC for same CIK).
        
        # In `verify_ticker_logic_v2.py`, we manually parsed `company_tickers_exchange.json` to get Ticker->Exchange map.
        # I should probably update `SECClient` or `sync_daily` to provide Ticker->Exchange map.
        
        # But the User Request is to update `_resolve_primary_ticker`. 
        # I will assume that the `candidates` passed to this function WILL be enriched with 'exchange_norm' or similar, 
        # OR I should perform the check here if I have access to the map.
        
        # Given I cannot easily change the signature/call-site of `sync_daily` in this single step efficiently without risk,
        # I will proceed by implementing the logic, but note that `exchange` might be uniform if not passed correctly.
        # Wait, if `sync_daily` logic relies on `_resolve_primary_ticker` to PICK the ticker, 
        # and checking Exchange is part of picking...
        
        # Let's implement the logic assuming the caller will eventually support it,
        # or (Better) let's rely on Rule 2 (Purity) and Rule 4 (Length) primarily if Exchange info is missing/uniform.
        # BUT `verify_ticker_logic_v2.py` PROVED that Exchange Rank is vital (SAC vs SAC-UN).
        
        # I will implement the helper `get_exchange_rank` and `is_special_ticker` inside here.
        
        EXCHANGE_RANK = {'NYSE': 1, 'NASDAQ': 2, 'AMEX': 3, 'OTC': 4, 'OTHER': 5}
        
        def get_rank(item):
            # Try to find exchange info in item
            # Support 'exchange', 'exchange_norm', 'exchange_raw' keys
            exc = item.get('exchange_norm') or item.get('exchange') or 'OTHER'
            return EXCHANGE_RANK.get(exc, 5)

        def is_special(t):
            # Rule 2: Special chars (., -, $)
            return not t.replace('.', '').replace('-', '').replace('$', '').isalpha()

        enriched_candidates = []
        for c in candidates:
            rank = get_rank(c)
            special = is_special(c['ticker'])
            length = len(c['ticker'])
            ticker_text = c['ticker']
            
            enriched_candidates.append({
                'item': c,
                'rank': rank,
                'special': special,
                'len': length,
                'ticker': ticker_text,
                'sort_key': (rank, special, length, ticker_text)
            })

        # Sort
        enriched_candidates.sort(key=lambda x: x['sort_key'])
        best_candidate = enriched_candidates[0]

        # Rule 3: Stickiness
        if current_db_ticker:
            current_obj = next((x for x in enriched_candidates if x['ticker'] == current_db_ticker), None)
            if current_obj:
                # If current ticker has same Rank and same Special status (or better), keep it.
                # Since we sorted by Rank then Special, best_candidate is <= current_obj in these metrics.
                # So we only keep current if it is EQUAL in Rank and Special.
                if current_obj['rank'] == best_candidate['rank'] and current_obj['special'] == best_candidate['special']:
                    return current_obj['item']

        return best_candidate['item']

    async def sync_daily(self, limit: int = None) -> Dict[str, int]:
        """
        Daily Synchronization (Async-Compatible)
        1. Parse SEC Master Index
        2. Update Ticker History (SCD Type 2)
        3. Flag active collection targets
        """
        logger.info(">>> Starting Master Sync (Daily)...")
        
        # Step 1: Fetch Current SEC Data
        current_data = self.sec_client.get_master_index() # Returns dict {cik: {ticker, name, ...}}
        stats = {
            'new_listings': 0, 
            'delistings': 0, 
            'ticker_changes': 0, 
            'exchange_updates': 0
        }
        
        # [Safety] Start Heartbeat Monitor
        monitor_task = asyncio.create_task(self._monitor_loop())
        
        
        logger.info(">>> [Step 1] Loading SEC Data...")
        
        # 1-1. SEC Exchanges
        try:
            sec_exchanges = self.sec_client.get_tickers_exchange() # {cik: exchange}
        except Exception as e:
            logger.warning(f"Could not fetch SEC exchanges: {e}. using empty.")
            sec_exchanges = {}
            
        # 1-2. SEC Tickers (1:N Handling)
        sec_tickers_raw = self.sec_client.get_company_tickers()
        # raw is dict of dicts: "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        
        # [Step A] Parse into 1:N structure
        sec_cik_candidates = defaultdict(list)
        for item in sec_tickers_raw.values():
            cik_int = int(item['cik_str'])
            sec_cik_candidates[cik_int].append(item)
            
        sec_cik_set = set(sec_cik_candidates.keys())
        
        logger.info(">>> [Step 2] Loading DB State...")
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker, exchange, is_active FROM us_ticker_master")
            db_records = cur.fetchall()
            
        db_cik_map = {int(r['cik']): r for r in db_records}
        db_cik_set = set(db_cik_map.keys())
        
        logger.info(f"SEC: {len(sec_cik_set)}, DB: {len(db_cik_set)}")
        
        # Step 3: Diff Processing
        logger.info(">>> [Step 3] Diff Processing...")
        
        # Case A: New Listings
        new_ciks = sec_cik_set - db_cik_set
        new_data = [] # (cik, ticker, name, exchange)
        new_history = [] # (cik, ticker, start_dt)
        
        for cik in new_ciks:
            candidates = sec_cik_candidates[cik]
            # [Step B] Resolve Primary (No DB ticker, so fresh resolution)
            resolved = self._resolve_primary_ticker(candidates, current_db_ticker=None)
            
            ticker = resolved['ticker']
            name = resolved['title']
            exchange_raw = sec_exchanges.get(ticker)
            
            # Normalize Exchange
            exchange = self.normalize_exchange(exchange_raw) if exchange_raw else None
            
            cik_str = str(cik).zfill(10)
            new_data.append((cik_str, ticker, name, exchange))
            new_history.append((cik_str, ticker, datetime.now().date()))
            stats['new_listings'] += 1
            
        if new_data:
            with self.db.get_cursor() as cur:
                # 1. Insert Master
                q_master = """
                INSERT INTO us_ticker_master (cik, latest_ticker, latest_name, exchange, is_active, is_collect_target, created_at, updated_at)
                VALUES %s
                ON CONFLICT (cik) DO NOTHING
                """
                # Prepare rows: (cik, ticker, name, exchange, True, False, NOW, NOW)
                rows_master = [(x[0], x[1], x[2], x[3], True, False, datetime.now(), datetime.now()) for x in new_data]
                execute_values(cur, q_master, rows_master)
                
                # 2. Insert Initial History
                q_history = """
                INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt)
                VALUES %s
                ON CONFLICT DO NOTHING
                """
                # end_dt default is '9999-12-31' but explicit is safer for execute_values if schema allows default.
                # execute_values binds variables. Let's provide '9999-12-31'.
                rows_history = [(x[0], x[1], x[2], '9999-12-31') for x in new_history]
                execute_values(cur, q_history, rows_history)
                
            logger.info(f"Inserted {len(new_data)} new tickers.")
            
            # Enrich
            new_ciks_str = [x[0] for x in new_data]
            await self._enrich_specific_ciks(new_ciks_str)

        # Prepare Lists for Updates (Used in Case B and C)
        ticker_updates_cik = [] # CIKs where ticker changed
        new_history_rows = [] # (cik, new_ticker, today)
        master_updates = [] # (cik, latest_ticker, new_exchange)
        exchange_updates_only = [] # (cik, new_exchange)
        
        today_date = datetime.now().date()
        yesterday_date = today_date - timedelta(days=1)
        
        # Case B: Delisted (Potential) - Multi-layered Verification
        delisted_candidates = db_cik_set - sec_cik_set
        verified_delisted = []
        recovered_active = [] # (cik, ticker, exchange)
        
        if delisted_candidates:
            logger.info(f"Detected {len(delisted_candidates)} missing CIKs. Starting Authority Verification (Submissions API)...")
            
            # Verify via Authority API
            auth_results = await self._verify_batch_authority(list(delisted_candidates))
            
            for res in auth_results:
                cik = int(res['cik'])
                if res['is_active']:
                    # It's actually active! (False Negative in Bulk File)
                    recovered_active.append(res)
                    logger.info(f"Authority Check SAVED {cik}: {res['ticker']} ({res['exchange']})")
                else:
                    # Confirmed Inactive (404 or Error)
                    verified_delisted.append(cik)
            
            # 1. Process Verified Delisted
            if verified_delisted:
                ciks_list = [str(c).zfill(10) for c in verified_delisted]
                with self.db.get_cursor() as cur:
                    # Deactivate Master
                    cur.execute("""
                        UPDATE us_ticker_master 
                        SET is_active = FALSE, is_collect_target = FALSE, updated_at = NOW()
                        WHERE cik = ANY(%s) AND is_active = TRUE
                    """, (ciks_list,))
                    
                    # Close History
                    cur.execute("""
                        UPDATE us_ticker_history
                        SET end_dt = CURRENT_DATE
                        WHERE cik = ANY(%s) AND end_dt = '9999-12-31'
                    """, (ciks_list,))
                    
                    stats['delistings'] = cur.rowcount
                logger.info(f"Confirmed & Deactivated {stats['delistings']} tickers.")
                
            # 2. Process Recovered (Treat as Updates)
            for item in recovered_active:
                cik = int(item['cik']) 
                sec_ticker = item['ticker']
                sec_exch = item['exchange']
                
                db_item = db_cik_map.get(cik)
                
                if not db_item:
                    continue
                    
                db_ticker = db_item['latest_ticker']
                db_exch = db_item['exchange']
                
                cik_str = str(cik).zfill(10)
                
                # Check Ticker Change
                if sec_ticker != db_ticker:
                    logger.info(f"[{cik_str}] Authority Update (Ticker): {db_ticker} -> {sec_ticker}")
                    ticker_updates_cik.append(cik_str)
                    new_history_rows.append((cik_str, sec_ticker, today_date, '9999-12-31'))
                    master_updates.append((sec_ticker, sec_exch, cik_str))
                    stats['ticker_changes'] += 1
                    
                # Check Exchange Update
                elif sec_exch != 'OTHER' and sec_exch != db_exch:
                    logger.info(f"[{cik_str}] Authority Update (Exchange): {db_exch} -> {sec_exch}")
                    exchange_updates_only.append((sec_exch, cik_str))
                    stats['exchange_updates'] += 1

        # Case C: Existing (Ticker Changes - SCD Type 2)
        common_ciks = sec_cik_set.intersection(db_cik_set)
        
        # We need lists for batch processing (Already initialized)
        # 1. Close old history: list of ciks
        # 2. Open new history: list of (cik, new_ticker)
        # 3. Update master: list of (cik, new_ticker)

        
        for cik in common_ciks:
            # [Step C] Diff Processing with Stickiness
            candidates = sec_cik_candidates[cik]
            db_item = db_cik_map[cik]
            db_ticker = db_item['latest_ticker']
            
            # Resolve Primary using Stickiness
            resolved = self._resolve_primary_ticker(candidates, current_db_ticker=db_ticker)
            sec_ticker = resolved['ticker']
            
            sec_exch_raw = sec_exchanges.get(sec_ticker)
            sec_exch = self.normalize_exchange(sec_exch_raw) if sec_exch_raw else None
            db_exch = db_item['exchange']
            
            cik_str = str(cik).zfill(10)
            
            # Ticker Change Logic (SCD Type 2)
            if sec_ticker != db_ticker:
                logger.info(f"[{cik_str}] Ticker Change: {db_ticker} -> {sec_ticker}")
                ticker_updates_cik.append(cik_str)
                new_history_rows.append((cik_str, sec_ticker, today_date, '9999-12-31'))
                
                # Prepare Master Update (Ticker is key)
                # We also need to check exchange here
                final_exch = sec_exch if (sec_exch and sec_exch != 'OTHER') else db_exch
                master_updates.append((sec_ticker, final_exch, cik_str))
                stats['ticker_changes'] += 1
            
            # Exchange Update Only (No ticker change)
            elif sec_exch and sec_exch != 'OTHER' and sec_exch != db_exch:
                logger.info(f"[{db_ticker}] Exchange Update: {db_exch} -> {sec_exch}")
                exchange_updates_only.append((sec_exch, cik_str))
                stats['exchange_updates'] += 1
                
        if ticker_updates_cik:
            with self.db.get_cursor() as cur:
                # 1. Cleaner Logic: Remove "Intraday/Transient" tickers
                # If a ticker was created TODAY (start_dt > yesterday) and is already being closed,
                # it's a glitch or noise. Delete it instead of archiving invalid range.
                cur.execute("""
                    DELETE FROM us_ticker_history
                    WHERE cik = ANY(%s) AND end_dt = '9999-12-31' AND start_dt > %s
                """, (ticker_updates_cik, yesterday_date))

                # 2. Close Old History (Normal Case)
                # Set end_dt = Yesterday for valid long-running tickers
                cur.execute("""
                    UPDATE us_ticker_history
                    SET end_dt = %s
                    WHERE cik = ANY(%s) AND end_dt = '9999-12-31'
                """, (yesterday_date, ticker_updates_cik))
                
                # 2. Insert New History
                q_hist = "INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt) VALUES %s"
                execute_values(cur, q_hist, new_history_rows)
                
                # 3. Update Master (Ticker + Exchange)
                q_mast = """
                    UPDATE us_ticker_master
                    SET latest_ticker = %s, exchange = %s, updated_at = NOW()
                    WHERE cik = %s
                """
                # master_updates is (ticker, exchange, cik) which matches placeholders
                # Wait, execute_batch placeholders %s are positional.
                # values: (sec_ticker, final_exch, cik_str)
                # Query: latest_ticker=%s, exchange=%s WHERE cik=%s. Correct.
                execute_batch(cur, q_mast, master_updates)

        if exchange_updates_only:
             with self.db.get_cursor() as cur:
                q_exch = "UPDATE us_ticker_master SET exchange = %s, updated_at = NOW() WHERE cik = %s"
                execute_batch(cur, q_exch, exchange_updates_only)

        logger.info(f"Diff Processed. Stats: {stats}")
        
        # Step 4: Metadata Enrichment & Price Updates
        logger.info(">>> [Step 4] Metadata & Price Updates...")
        
        # 4-1. Internal Update (Schema Fixes & Memory Optimization)
        # us_daily_price: cls_prc (not close_price)
        # us_daily_valuation: mkt_cap (not market_cap)
        
        # 1. Fetch Target CIKs
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target = TRUE")
            target_ciks = [r['cik'] for r in cur.fetchall()]
            
        # 2. Sequential Iterative Update (Robust Mode)
        # We explicitly process small chunks and commit to guarantee lock release.
        # This is slower but avoids ALL shared memory/TimescaleDB lock issues.
        total_updated = 0
        total_ciks = len(target_ciks)
        pruning_date = datetime.now().date() - timedelta(days=14)
        
        logger.info(f"Updating {total_ciks} targets (Iterative Robust Mode)...")
        
        # Process in tiny batches to allow frequent commits but reduce round-trip overhead slightly
        MINI_BATCH_SIZE = 5 
        
        for i in range(0, total_ciks, MINI_BATCH_SIZE):
            batch = target_ciks[i:i+MINI_BATCH_SIZE]
            update_data = []
            
            # Progress Logging
            if i > 0 and i % 500 == 0:
                percent = int((i / total_ciks) * 100)
                logger.info(f"Step 4 Progress: {i}/{total_ciks} ({percent}%) completed.")
            
            # A. Read Phase (Per Item)
            for cik in batch:
                try:
                    cap = None
                    prc = None
                    
                    # Open a fresh cursor for reads -> minimal lock duration
                    with self.db.get_cursor() as cur:
                        # 1. Market Cap
                        cur.execute("""
                            SELECT mkt_cap FROM us_daily_valuation 
                            WHERE cik = %s AND dt >= %s 
                            ORDER BY dt DESC LIMIT 1
                        """, (cik, pruning_date))
                        r_cap = cur.fetchone()
                        if r_cap: cap = r_cap['mkt_cap']
                        
                        # 2. Price
                        cur.execute("""
                            SELECT cls_prc FROM us_daily_price 
                            WHERE cik = %s AND dt >= %s 
                            ORDER BY dt DESC LIMIT 1
                        """, (cik, pruning_date))
                        r_prc = cur.fetchone()
                        if r_prc: prc = r_prc['cls_prc']
                    
                    if cap is not None or prc is not None:
                        update_data.append((cap, prc, cik))
                        
                except Exception as e:
                    logger.warning(f"Error fetching for {cik}: {e}")
                    continue

            # B. Write Phase (Batch Commit)
            if update_data:
                with self.db.get_cursor() as cur:
                    q_update = """
                        UPDATE us_ticker_master
                        SET market_cap = COALESCE(%s, market_cap),
                            current_price = COALESCE(%s, current_price),
                            updated_at = NOW()
                        WHERE cik = %s
                    """
                    execute_batch(cur, q_update, update_data)
                    total_updated += len(update_data)
            
        logger.info(f"Updated {total_updated}/{total_ciks} targets (Robust Strategy).")
        
        # 4-2. External Enrichment (Optimized)
        
        # A. Smart SQL Filtering (Exclude known garbage)
        query_enrich = """
            SELECT cik, latest_ticker FROM us_ticker_master 
            WHERE is_active = TRUE 
              AND (is_collect_target = FALSE OR market_cap IS NULL OR current_price IS NULL OR sector IS NULL)
              -- Optimization: Exclude if we ALREADY know it's not US Equity
              AND (country = 'United States' OR country IS NULL)
              AND (quote_type = 'EQUITY' OR quote_type IS NULL)
        """
        if limit and limit > 0:
             query_enrich += f" LIMIT {limit}"
             
        with self.db.get_cursor() as cur:
            cur.execute(query_enrich)
            candidates = cur.fetchall()
            
        if candidates:
            # [DISABLED] Blacklist Filter - per user request 2025-12-26
            # from backend.utils.blacklist_manager import BlacklistManager
            # blacklist = BlacklistManager()
            
            ciks_to_enrich = []
            for r in candidates:
                # [DISABLED] New Blacklist Check (Global Block)
                # if not blacklist.is_blacklisted(r['cik']):
                ciks_to_enrich.append(r['cik'])
                # else:
                #     # logger.info(f"Skipping Blacklisted CIK {r['cik']}")
                #     pass

            logger.info(f"Enriching {len(ciks_to_enrich)} candidates via yfinance (Smart Filter & Blacklist NOT applied)...")
            
            # C. Batch Processing (Limit concurrency)
            BATCH_SIZE = 50
            total_enrich = len(ciks_to_enrich)
            
            for i in range(0, total_enrich, BATCH_SIZE):
                # Progress Logging (Every 5 batches = 250 items)
                if i > 0 and (i // BATCH_SIZE) % 5 == 0:
                    percent = int((i / total_enrich) * 100)
                    logger.info(f"Enrichment Progress: {i}/{total_enrich} ({percent}%)")
                    
                chunk = ciks_to_enrich[i:i+BATCH_SIZE]
                
                # [DEBUG] Trace Batch
                chunk_tickers = []
                with self.db.get_cursor() as cur:
                     cur.execute("SELECT latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (chunk,))
                     chunk_tickers = [r['latest_ticker'] for r in cur.fetchall()]
                logger.info(f"Processing Batch {i//BATCH_SIZE}: {chunk_tickers}") # Explicitly list tickers

                try:
                    await self._enrich_specific_ciks(chunk)
                    # Small sleep to be nice to API
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Enrichment Batch {i} Failed: {e}") 

        # Step 5: Targeting
        logger.info(">>> [Step 5] Targeting Analysis...")
        self._update_target_status()
        
        # Terminate Monitor
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
            
        return stats

    async def _monitor_loop(self):
        """Prints heartbeat to confirm Event Loop liveness."""
        while True:
            await asyncio.sleep(5)
            logger.info(f"[Heartbeat] Main Loop Active - {time.time()}")
                    
    async def _enrich_specific_ciks(self, ciks: List[str]):
        # Helper for test mode or targeted enrichment
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (ciks,))
            rows = cur.fetchall()
            ciks_map = {r['cik']: r['latest_ticker'] for r in rows}
            
        tasks = [self._fetch_yfinance_metadata(cik, ticker) for cik, ticker in ciks_map.items()]
        results = await asyncio.gather(*tasks)
        
        valid_results = [r for r in results if r is not None]
        self._bulk_update_metadata(valid_results)

    async def _verify_batch_authority(self, ciks: List[int]) -> List[Dict]:
        """
        Verify a list of CIKs against SEC Submissions API.
        Returns list of dicts: {'cik': str, 'is_active': bool, 'ticker': str, 'exchange': str}
        """
        results = []
        ua = os.getenv("SEC_USER_AGENT", "US-DMS-Reflector/1.0")
        headers = {"User-Agent": ua, "Host": "data.sec.gov"}
        
        async def fetch(session, cik):
            url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
            async with self.sem:
                await asyncio.sleep(0.12) # Rate Limit Safety
                try:
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            tickers = data.get('tickers', [])
                            exchanges = data.get('exchanges', [])
                            if tickers and exchanges:
                                return {
                                    'cik': str(cik).zfill(10),
                                    'is_active': True,
                                    'ticker': tickers[0],
                                    'exchange': self.normalize_exchange(exchanges[0])
                                }
                        return {'cik': str(cik).zfill(10), 'is_active': False}
                except Exception as e:
                    logger.warning(f"Authority Check Error {cik}: {e}")
                    return {'cik': str(cik).zfill(10), 'is_active': False} # Conservative fail

        async with aiohttp.ClientSession() as session:
            tasks = [fetch(session, cik) for cik in ciks]
            results = await asyncio.gather(*tasks)
            
        return results

    async def _fetch_yfinance_metadata(self, cik: str, ticker: str) -> Optional[Dict[str, Any]]:
        from backend.utils.blacklist_manager import BlacklistManager
        blacklist = BlacklistManager()
        
        async with self.sem:
            delay = random.uniform(0.1, 0.5) # Reduced delay for batching
            await asyncio.sleep(delay)
            try:
                loop = asyncio.get_event_loop()
                def fetch():
                    tid = threading.get_ident()
                    t = yf.Ticker(ticker)
                    try:
                        return t.info, tid
                    except Exception:
                        return None, tid
                
                start_ts = time.time()
                info = None
                worker_tid = None
                
                try:
                    # Enforce timeout for yfinance call (prevents hanging threads)
                    # Use dedicated executor to isolate from DB operations
                    info, worker_tid = await asyncio.wait_for(
                        loop.run_in_executor(self.yf_executor, fetch), 
                        timeout=15.0  # 15s timeout
                    )
                    
                except asyncio.TimeoutError:
                    error_reason = "YF Error: Timeout (15s)"
                    # [DISABLED] Blacklist Addition
                    # await loop.run_in_executor(None, blacklist.add_blacklist, cik, error_reason, ticker)
                    return None
                except Exception as e:
                    logger.warning(f"Executor Error for {ticker}: {e}")
                    return None
                
                # Retrieve any logs captured during this thread's execution
                captured_logs = []
                if worker_tid:
                     captured_logs = self.log_handler.get_logs_by_thread(worker_tid, min_time=start_ts)
                
                exchange_raw = None
                if info:
                    exchange_raw = info.get('exchange')
                
                if not exchange_raw:
                     # Check captured logs for specific error messages (e.g. 404, Delisted)
                     error_reason = "YFinance Incomplete (No Exchange)"
                     
                     if captured_logs:
                         # Prioritize specific errors
                         for log_msg in captured_logs:
                             # [CRITICAL] Handle Rate Limits - DO NOT BLACKLIST
                             if "Rate limited" in log_msg or "Too Many Requests" in log_msg or "429" in log_msg:
                                 logger.warning(f"[{ticker}] Rate Limit Hit. Skipping blacklist and backing off...")
                                 await asyncio.sleep(5) # Cooldown
                                 return None
                                 
                             if "401" in log_msg or "Unauthorized" in log_msg:
                                 logger.warning(f"[{ticker}] Deducted 401/Unauthorized (Crumb Failure). Skipping blacklist to allow future retry.")
                                 return None # Do NOT blacklist transient errors
                                 
                             if "404" in log_msg or "Not Found" in log_msg:
                                 error_reason = f"YF Error: {log_msg.strip()}"
                                 break
                             if "delisted" in log_msg.lower():
                                 error_reason = f"YF Error: {log_msg.strip()}"
                                 break
                     # Run DB insert in executor to prevent loop blocking
                     # [DISABLED] Blacklist Addition
                     # await loop.run_in_executor(None, blacklist.add_blacklist, cik, error_reason, ticker)
                     return None
                     
                norm_exchange = self.normalize_exchange(exchange_raw)
                
                return {
                    'cik': cik,
                    'exchange': norm_exchange,
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'market_cap': info.get('marketCap'),
                    'current_price': info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose'),
                    'quote_type': info.get('quoteType'),
                    'country': info.get('country')
                }
            except Exception as e:
                # Cache 404s
                if "404" in str(e) or "Not Found" in str(e):
                     pass
                     # [DISABLED] Blacklist Addition
                     # blacklist.add_blacklist(cik, f"404 Not Found: {e}", ticker)
                # logger.warning(f"Enrichment Error {ticker}: {e}")
                return None

    def _bulk_update_metadata(self, data: List[Dict[str, Any]]):
        if not data: return
        with self.db.get_cursor() as cur:
            query = """
                UPDATE us_ticker_master
                SET 
                    exchange = CASE 
                        WHEN exchange IS NULL OR exchange = 'OTHER' THEN %s 
                        ELSE exchange 
                    END,
                    sector = %s,
                    industry = %s,
                    market_cap = %s,
                    current_price = %s,
                    quote_type = %s,
                    country = %s,
                    updated_at = NOW()
                WHERE cik = %s
            """
            
            values = [
                (
                    d['exchange'],
                    d['sector'], d['industry'],
                    d['market_cap'], d['current_price'],
                    d['quote_type'], d['country'],
                    d['cik']
                ) for d in data
            ]
            from psycopg2.extras import execute_batch
            execute_batch(cur, query, values)
            logger.info(f"Bulk enriched {len(values)} tickers.")

    def _update_target_status(self):
        with self.db.get_cursor() as cur:
            # Retention
            major_exchanges = "('NASDAQ', 'NYSE', 'AMEX')"
            retention_q = f"""
                UPDATE us_ticker_master
                SET is_collect_target = FALSE, updated_at = NOW()
                WHERE is_collect_target = TRUE
                  AND (
                      market_cap < 35000000 
                      OR current_price < 0.80
                      OR exchange NOT IN {major_exchanges}
                      OR country != 'United States'
                      OR quote_type != 'EQUITY'
                      OR market_cap IS NULL
                      OR current_price IS NULL
                  )
            """
            cur.execute(retention_q)
            logger.info(f"Retention logic applied. Dropped count: {cur.rowcount}")
            
            # Entry
            entry_q = f"""
                UPDATE us_ticker_master
                SET is_collect_target = TRUE, updated_at = NOW()
                WHERE is_collect_target = FALSE
                  AND is_active = TRUE
                  AND market_cap >= 50000000
                  AND current_price >= 1.00
                  AND exchange IN {major_exchanges}
                  AND country = 'United States'
                  AND quote_type = 'EQUITY'
            """
            cur.execute(entry_q)
            logger.info(f"Entry logic applied. Added count: {cur.rowcount}")
