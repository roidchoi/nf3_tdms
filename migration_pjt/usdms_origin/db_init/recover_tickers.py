import sys
import os
import json
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager

# Configuration
USER_AGENT = os.getenv("SEC_USER_AGENT", "US-DMS-Project/1.0 (admin@example.com)")
REPORT_PATH = "db_init/recovery_final_report.json"
AUDIT_CSV_PATH = "db_init/sec_source_audit_report.csv"

# Exchange Normalization Logic
def normalize_exchange(raw_exchange):
    if not raw_exchange:
        return 'OTHER'
    
    raw = raw_exchange.upper().strip()
    
    # NYSE
    if raw in ['NYSE', 'NYQ', 'NYS', 'NYC', 'NEW YORK STOCK EXCHANGE']:
        return 'NYSE'
    
    # NASDAQ
    if raw in ['NASDAQ', 'NMS', 'NCM', 'NGM', 'NAS', 'NMFQS']:
        return 'NASDAQ'
        
    # AMEX
    if raw in ['AMEX', 'ASE', 'ASEQ', 'AMERICAN STOCK EXCHANGE']:
        return 'AMEX'
        
    # OTC
    if raw in ['OTC', 'PNK', 'PINK', 'PINK SHEETS', 'OTCQX', 'OTCQB']:
        return 'OTC'
        
    return 'OTHER'

class RecoveryManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.sem = asyncio.Semaphore(5) # Conservative Concurrency
        self.results = []
        
    async def fetch_submission(self, session, cik):
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {"User-Agent": USER_AGENT, "Host": "data.sec.gov"}
        
        async with self.sem:
            # Strict Rate Limit adherence: > 0.1s
            await asyncio.sleep(0.15) 
            
            try:
                async with session.get(url, headers=headers, timeout=20) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {'cik': cik, 'status': 200, 'data': data}
                    elif resp.status == 404:
                        return {'cik': cik, 'status': 404, 'error': 'Not Found'}
                    else:
                        return {'cik': cik, 'status': resp.status, 'error': resp.reason}
            except Exception as e:
                return {'cik': cik, 'status': 'Error', 'error': str(e)}

    async def run_recovery(self):
        print(">>> [Phase 1] Loading Audit Targets...")
        
        if not os.path.exists(AUDIT_CSV_PATH):
            print(f"!!! Audit file not found: {AUDIT_CSV_PATH}")
            return
            
        df = pd.read_csv(AUDIT_CSV_PATH)
        # Assuming CSV has 'cik' column.
        # Targets: All items in report (Assuming report contains only misclassified inactive ones as per audit design)
        # But let's filter just in case.
        target_ciks = [str(c).zfill(10) for c in df['cik'].tolist()]
        print(f"    - Target CIKs: {len(target_ciks)}")
        
        print(f">>> [Phase 2] Fetching Submissions API (User-Agent: {USER_AGENT})...")
        
        tasks = []
        async with aiohttp.ClientSession() as session:
            for cik in target_ciks:
                tasks.append(self.fetch_submission(session, cik))
            
            responses = await asyncio.gather(*tasks)
            
        print("    - API Fetch Complete.")
        
        # Process Responses
        recovered_data = []
        failure_data = []
        
        for res in responses:
            cik = res['cik']
            if res.get('status') == 200:
                data = res['data']
                # Extract Ticker & Exchange
                # Submissions JSON structure: 
                # "tickers": ["IPG"], "exchanges": ["NYSE"]
                tickers = data.get('tickers', [])
                exchanges = data.get('exchanges', [])
                
                if tickers and exchanges:
                    primary_ticker = tickers[0]
                    raw_exch = exchanges[0]
                    norm_exch = normalize_exchange(raw_exch)
                    
                    recovered_data.append({
                        'cik': cik,
                        'ticker': primary_ticker,
                        'exchange_raw': raw_exch,
                        'exchange': norm_exch
                    })
                else:
                    failure_data.append({'cik': cik, 'reason': 'Empty Ticker/Exchange in API'})
            else:
                failure_data.append({'cik': cik, 'reason': f"API Status {res.get('status')}: {res.get('error')}"})
                
        print(f"    - Recoverable: {len(recovered_data)}")
        print(f"    - Failures: {len(failure_data)}")
        
        if not recovered_data:
            print("!!! No data to recover. Exiting.")
            return

        print(">>> [Phase 3 & 4] Executing Atomic DB Recovery & Purge...")
        
        recovered_stats = {'master_updated': 0, 'history_reset': 0}
        purge_stats = {'price_purged': 0, 'financials_truncated': False}
        
        try:
            with self.db.get_cursor() as cur:
                # --- Phase 3: DB Recovery ---
                
                # 1. Update Master
                q_master = """
                    UPDATE us_ticker_master
                    SET is_active = TRUE,
                        latest_ticker = %s,
                        exchange = %s,
                        market_cap = NULL,
                        sector = NULL,
                        industry = NULL,
                        quote_type = NULL,
                        country = NULL,
                        updated_at = NOW()
                    WHERE cik = %s
                """
                
                master_params = [(r['ticker'], r['exchange'], r['cik']) for r in recovered_data]
                
                # Use execute_batch for performance
                from psycopg2.extras import execute_batch, execute_values
                execute_batch(cur, q_master, master_params)
                print(f"    - Updated {len(master_params)} Master records.")
                recovered_stats['master_updated'] = len(master_params)
                
                # 2. Reset History
                ciks_to_reset = [r['cik'] for r in recovered_data]
                
                cur.execute("DELETE FROM us_ticker_history WHERE cik = ANY(%s)", (ciks_to_reset,))
                print(f"    - Deleted old history for {len(ciks_to_reset)} CIKs.")
                
                # Insert Baseline History (1980-01-01 ~ 9999-12-31)
                q_hist = """
                    INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt)
                    VALUES %s
                """
                hist_params = [(r['cik'], r['ticker'], '1980-01-01', '9999-12-31') for r in recovered_data]
                
                execute_values(cur, q_hist, hist_params)
                print(f"    - Inserted {len(hist_params)} Baseline History records.")
                recovered_stats['history_reset'] = len(hist_params)
                
                # --- Phase 4: The Final Purge ---
                print("    - Purging mismatched Price data...")
                cur.execute("""
                    DELETE FROM us_daily_price p
                    USING us_ticker_master m
                    WHERE p.cik = m.cik
                      AND p.ticker != m.latest_ticker
                """)
                purge_stats['price_purged'] = cur.rowcount
                print(f"      * Deleted {cur.rowcount} mismatched price records.")
                
                # Financial Truncate
                print("    - Truncating Financial Tables...")
                tables = ['us_standard_financials', 'us_share_history', 'us_daily_valuation', 'us_financial_metrics']
                for t in tables:
                    cur.execute(f"TRUNCATE TABLE {t}")
                    print(f"      * Truncated {t}.")
                purge_stats['financials_truncated'] = True
                
        except Exception as e:
            print(f"!!! Critical Transaction Error (Rolled Back): {e}")
            return
             
        # Reporting
        final_report = {
            'timestamp': datetime.now().isoformat(),
            'recovery_process': {
                'targets': len(target_ciks),
                'success': len(recovered_data),
                'failures': failure_data
            },
            'db_stats': recovered_stats,
            'purge_stats': purge_stats,
            'details': recovered_data
        }
        
        with open(REPORT_PATH, 'w') as f:
            json.dump(final_report, f, indent=2)
            
        print(f"\n>>> Recovery & Purge Complete. Report saved to {REPORT_PATH}")
        
        # Validation for Key Tickers (IPG, HBI, VRNT)
        print("\n[Validation Check]")
        key_tickers = ['IPG', 'HBI', 'VRNT']
        # Find them in recovered_data
        for key in key_tickers:
            match = next((x for x in recovered_data if x['ticker'] == key), None)
            status = "Recovered" if match else "Not Found / Not Recovered"
            exch = match['exchange'] if match else "N/A"
            print(f"  - {key}: {status} (Exchange: {exch})")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    manager = RecoveryManager()
    asyncio.run(manager.run_recovery())
