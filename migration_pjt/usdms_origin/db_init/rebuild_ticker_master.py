import sys
import os
import asyncio
import pandas as pd
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.sec_client import SECClient
from backend.collectors.db_manager import DatabaseManager
from backend.collectors.master_sync import MasterSync

async def rebuild_db():
    print(">>> Starting DB Rebuild (Strategic Reset)...")
    
    sec = SECClient()
    db = DatabaseManager()
    sync = MasterSync() # Instance to use helper methods
    
    # 1. Fetch SEC Data (Live)
    print(">>> [Step 1] Fetching Live SEC Data...")
    
    # A. Exchange Map (Ticker -> Exchange)
    # We need to manually parse this to support V2 Logic (Rank 1 vs Rank 5 distinction within same CIK)
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    headers = sec.headers.copy()
    headers["Host"] = "www.sec.gov"
    sec._enforce_rate_limit()
    
    try:
        resp = sec.session.get(url, headers=headers, timeout=30)
        exch_data = resp.json()
        
        t_idx = exch_data['fields'].index('ticker')
        e_idx = exch_data['fields'].index('exchange')
        
        ticker_exchange_map = {}
        for row in exch_data['data']:
            ticker_exchange_map[row[t_idx]] = row[e_idx]
            
        print(f"    - Parsed {len(ticker_exchange_map)} ticker-exchange pairs.")
        
    except Exception as e:
        print(f"!!! Error fetching exchange data: {e}")
        return

    # B. Company Tickers (CIK -> Tickers)
    raw_tickers = sec.get_company_tickers()
    
    # Group by CIK
    cik_candidates = defaultdict(list)
    for item in raw_tickers.values():
        cik_str = str(item['cik_str']).zfill(10)
        ticker = item['ticker']
        
        # Enrich candidate with Exchange info for Logic V2
        exc_raw = ticker_exchange_map.get(ticker, None)
        exc_norm = MasterSync.normalize_exchange(exc_raw) if exc_raw else 'OTHER'
        
        candidate = {
            'cik_str': cik_str,
            'ticker': ticker,
            'title': item['title'],
            'exchange_raw': exc_raw,
            'exchange_norm': exc_norm,
            'exchange': exc_norm # Logic V2 looks for this or exchange_norm
        }
        cik_candidates[cik_str].append(candidate)
        
    print(f"    - Grouped {len(cik_candidates)} CIKs with candidates.")

    # 2. Load DB State (for Stickiness)
    print(">>> [Step 2] Loading Current DB for Stickiness...")
    with db.get_cursor() as cur:
        cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE is_active = TRUE")
        rows = cur.fetchall()
        db_state = {str(r['cik']).zfill(10): r['latest_ticker'] for r in rows}
        
    # 3. Calculate New Master State
    print(">>> [Step 3] Calculating New Master State (Logic V2)...")
    
    master_batch = [] # List of dicts
    history_batch = [] # List of dicts
    
    for cik, candidates in cik_candidates.items():
        curr_ticker = db_state.get(cik)
        
        # Apply Logic V2
        # Note: sync._resolve_primary_ticker is now V2.
        # It relies on 'exchange_norm' or 'exchange' keys in candidate dicts (which we populated).
        selected = sync._resolve_primary_ticker(candidates, current_db_ticker=curr_ticker)
        
        final_ticker = selected['ticker']
        final_name = selected['title']
        final_exchange = selected['exchange_norm']
        
        # Add to Master Batch
        master_batch.append({
            'cik': cik,
            'latest_ticker': final_ticker,
            'latest_name': final_name,
            'exchange': final_exchange,
            'is_active': True,
            'last_seen_dt': datetime.now().date()
        })
        
        # Add to History Batch (Baseline)
        history_batch.append({
            'cik': cik,
            'ticker': final_ticker,
            'start_dt': '1980-01-01', # PIT Reset
            'end_dt': '9999-12-31'
        })
        
    print(f"    - Prepared {len(master_batch)} master records.")

    # 4. Execute DB Updates
    print(">>> [Step 4] Executing DB Updates...")
    
    # A. Upsert Master
    print("    - Upserting us_ticker_master...")
    db.upsert_ticker_master(master_batch)
    
    # B. Reset History
    print("    - Resetting us_ticker_history (TRUNCATE & INSERT)...")
    with db.get_cursor() as cur:
        cur.execute("TRUNCATE TABLE us_ticker_history RESTART IDENTITY;")
        print("      * Table Truncated.")
        
    # db.insert_ticker_history ignores conflicts, but we just truncated, so mostly fine.
    # However, db.insert_ticker_history checks ON CONFLICT DO NOTHING.
    # Since we have unique (cik, ticker, start_dt) constraint likely, and we have 1 row per CIK here.
    db.insert_ticker_history(history_batch)
    
    print("\n>>> DB Rebuild Complete successfully.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(rebuild_db())
