import sys
import os
import asyncio
import pandas as pd
import aiohttp
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager
from backend.collectors.sec_client import SECClient

# Rate Limit Configuration
MAX_REQ_PER_SEC = 9  # Safe margin under 10
SEM = asyncio.Semaphore(MAX_REQ_PER_SEC)

async def fetch_submission(session, cik, headers):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    async with SEM:
        try:
            async with session.get(url, headers=headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {'status': 200, 'data': data}
                else:
                    return {'status': resp.status, 'data': None}
        except Exception as e:
            return {'status': 'Error', 'error': str(e), 'data': None}
        finally:
            # Enforce rate limit
            await asyncio.sleep(1.1 / MAX_REQ_PER_SEC)

async def main():
    print(">>> Starting SEC Source Reliability Audit...")
    
    # Debug: Check Env
    ua = os.getenv('SEC_USER_AGENT')
    print(f"    - Env SEC_USER_AGENT: {ua}")
    
    db = DatabaseManager()
    sec = SECClient()
    print(f"    - Client User-Agent: {sec.user_agent}")
    
    # 1. Target Identification
    print(">>> [Step 1] Loading Inactive CIKs...")
    with db.get_cursor() as cur:
        cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE is_active = FALSE")
        targets = cur.fetchall()
        
    target_map = {r['cik']: r['latest_ticker'] for r in targets}
    target_ciks = list(target_map.keys())
    print(f"    - Found {len(target_ciks)} inactive CIKs.")

    # 2. Channel A Check (company_tickers.json)
    print(">>> [Step 2] Checking Channel A (company_tickers.json)...")
    channel_a_map = {}
    try:
        # Check for local file override
        local_path_a = "temp_test/company_tickers.json"
        if os.path.exists(local_path_a):
            print(f"    - Using local file: {local_path_a}")
            import json
            with open(local_path_a, 'r') as f:
                raw_tickers = json.load(f)
        else:
            print("    - Local file not found, attempting download...")
            raw_tickers = sec.get_company_tickers()
            
        # Map CIK -> Ticker info locally
        # raw_tickers values: {'cik_str': 320193, 'ticker': 'AAPL', ...}
        for item in raw_tickers.values():
            if hasattr(item, 'get'): # Ensure it's a dict
                c = str(item.get('cik_str', '')).zfill(10)
                channel_a_map[c] = item.get('ticker', '')
    except Exception as e:
        print(f"!!! Failed to fetch Channel A: {e}")
        # Proceed with empty map


    # 3. Channel B Check (company_tickers_exchange.json)
    # 3. Channel B Check (company_tickers_exchange.json)
    print(">>> [Step 3] Checking Channel B (company_tickers_exchange.json)...")
    channel_b_cik_map = {}
    try:
        import json
        local_path_b = "temp_test/company_tickers_exchange.json"
        
        if os.path.exists(local_path_b):
            print(f"    - Using local file: {local_path_b}")
            with open(local_path_b, 'r') as f:
                data = json.load(f)
                
            # Parse local file structure
            # keys: 'fields', 'data'
            # fields: ["cik", "name", "ticker", "exchange"]
            fields = data['fields']
            cik_idx = fields.index('cik')
            exch_idx = fields.index('exchange')
            
            for row in data['data']:
                cik_val = row[cik_idx]
                exch_val = row[exch_idx]
                c_str = str(cik_val).zfill(10)
                channel_b_cik_map[c_str] = exch_val
        
        else:
            print("    - Local file not found, attempting download...")
            sec_exch_map = sec.get_tickers_exchange() # {cik(int): exchange(str)}
            channel_b_cik_map = {str(k).zfill(10): v for k, v in sec_exch_map.items()}
            
    except Exception as e:
        print(f"!!! Failed to fetch Channel B: {e}")
        # Proceed with empty map

    # 4. Channel C Check (Submissions API)
    print(">>> [Step 4] Checking Channel C (Submissions API)...")
    
    results = []
    
    headers = sec.headers.copy()
    headers["Host"] = "data.sec.gov"
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for cik in target_ciks:
            tasks.append(fetch_submission(session, cik, headers))
            
        responses = await asyncio.gather(*tasks)
        
    print("    - API Calls Complete.")
    
    # 5. Analysis & Reporting
    print(">>> [Step 5] Analyzing Results...")
    
    for i, cik in enumerate(target_ciks):
        db_ticker = target_map[cik]
        api_res = responses[i]
        
        # Channel A Status
        in_a = 'Y' if cik in channel_a_map else 'N'
        
        # Channel B Status
        # We check if the CIK exists in Exchange File (since we retrieved CIK map)
        in_b = 'Y' if cik in channel_b_cik_map else 'N'
        
        # Channel C Status
        api_status = api_res['status']
        api_tickers_list = []
        api_exchanges_list = []
        
        if api_status == 200:
            sub_data = api_res['data']
            # Submissions API returns 'tickers': ['IPG'], 'exchanges': ['NYSE']
            # Ensure lists and convert elements to string, filtering None
            raw_tickers = sub_data.get('tickers', [])
            raw_exchanges = sub_data.get('exchanges', [])
            
            api_tickers_list = [str(t) for t in raw_tickers if t] if raw_tickers else []
            api_exchanges_list = [str(e) for e in raw_exchanges if e] if raw_exchanges else []
            
        api_ticker_str = ",".join(api_tickers_list)
        api_exchange_str = ",".join(api_exchanges_list)
        
        # Reason Analysis
        reasons = []
        if in_a == 'N': reasons.append("Missing in Tickers JSON")
        if in_b == 'N': reasons.append("Missing in Exchange JSON")
        if in_a == 'Y' and in_b == 'N': reasons.append("Exchange Metadata Missing")
        if api_status == 200 and db_ticker not in api_tickers_list: reasons.append("Ticker Mismatch in API")
        
        mismatch_reason = "; ".join(reasons) if reasons else "Unknown"
        
        results.append({
            'cik': cik,
            'ticker': db_ticker,
            'in_tickers_json': in_a,
            'in_exchange_json': in_b,
            'api_status': api_status,
            'api_ticker': api_ticker_str,
            'api_exchange': api_exchange_str,
            'mismatch_reason': mismatch_reason
        })
        
    # Output
    out_path = "db_init/sec_source_audit_report.csv"
    df = pd.DataFrame(results)
    df.to_csv(out_path, index=False)
    print(f"    - Report saved to {out_path}")
    
    # Specific Report for IPG
    print("\n[Audit Summary for Key Tickers]")
    key_ciks = ['0000051644'] # IPG
    for k in key_ciks:
        row = df[df['cik'] == k]
        if not row.empty:
            print(f"CIK {k} ({row.iloc[0]['ticker']}):")
            print(f"  - Channel A (Tickers): {row.iloc[0]['in_tickers_json']}")
            print(f"  - Channel B (Exchange): {row.iloc[0]['in_exchange_json']}")
            print(f"  - Channel C (API): Status {row.iloc[0]['api_status']}, Tickers [{row.iloc[0]['api_ticker']}], Exch [{row.iloc[0]['api_exchange']}]")
            print(f"  - Reason: {row.iloc[0]['mismatch_reason']}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
