import requests
import time
import sys
import logging
from datetime import datetime, timedelta

# Usage: python tests/sec_content_verifier.py

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
HEADERS = {
    "User-Agent": "MyDailyRoutine/1.0 (admin@example.com)",
    "Host": "www.sec.gov"
}
ARCHIVE_URL = "https://www.sec.gov/Archives"
KNOWN_AVAILABLE_DATE = datetime(2025, 12, 15).date() # Based on probe result

def verify_content_parsing():
    print(f"\n>>> Experiment A: Content Parsing Verification ({KNOWN_AVAILABLE_DATE}) <<<")
    
    year = KNOWN_AVAILABLE_DATE.year
    qtr = (KNOWN_AVAILABLE_DATE.month - 1) // 3 + 1
    date_str = KNOWN_AVAILABLE_DATE.strftime('%Y%m%d')
    
    url = f"{ARCHIVE_URL}/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        lines = resp.text.splitlines()
        records = []
        start_parsing = False
        
        print(f"File Size: {len(resp.text)} bytes")
        
        # Parse Logic (Same as updated sec_client.py)
        for line in lines:
            if line.startswith("---"):
                start_parsing = True
                continue
            if not start_parsing: 
                continue
                
            parts = line.strip().split()
            if len(parts) < 5: 
                continue
            
            # Form Type is 4th from end, CIK is 3rd from end
            form_type = parts[-4]
            cik_str = parts[-3]
            filename = parts[-1]
            
            if cik_str.isdigit():
                records.append({
                    'cik': int(cik_str),
                    'form_type': form_type,
                    'filename': filename
                })
                
        print(f"Total Records Parsed: {len(records)}")
        
        # Analyze Content
        filings_10k = [r for r in records if r['form_type'] in ['10-K', '10-K/A']]
        filings_10q = [r for r in records if r['form_type'] in ['10-Q', '10-Q/A']]
        filings_8k = [r for r in records if r['form_type'] in ['8-K']]
        
        print(f" - 10-K Count: {len(filings_10k)}")
        print(f" - 10-Q Count: {len(filings_10q)}")
        print(f" - 8-K  Count: {len(filings_8k)}")
        
        if len(records) > 0:
            print(f"Sample Record: {records[0]}")
            return True
        else:
            print("FAILED: No records parsed.")
            return False

    except Exception as e:
        print(f"Parsng Verification Failed: {e}")
        return False

def verify_gap_recovery():
    print(f"\n>>> Experiment B: Gap Recovery Verification (Simulation) <<<")
    # Simulate gap from Dec 02 to Dec 15 (2 weeks)
    start_date = datetime(2025, 12, 2).date()
    end_date = datetime(2025, 12, 15).date()
    
    print(f"Simulating gap fetch from {start_date} to {end_date}")
    
    current = start_date
    success_count = 0
    fail_count = 0
    
    while current <= end_date:
        # Check if weekend
        if current.weekday() >= 5:
            # print(f"Skipping Weekend: {current}")
            current += timedelta(days=1)
            continue
            
        # Business Day Check
        year = current.year
        qtr = (current.month - 1) // 3 + 1
        date_str = current.strftime('%Y%m%d')
        url = f"{ARCHIVE_URL}/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"
        
        # Rate Limit
        time.sleep(2) 
        
        try:
            resp = requests.head(url, headers=HEADERS, timeout=10) # HEAD request is lighter
            # Note: SEC might not support HEAD on archives perfectly, if fails retry GET.
            if resp.status_code == 405 or resp.status_code == 403: # Method Not Allowed
                 resp = requests.get(url, headers=HEADERS, timeout=10, stream=True)
                 resp.close() # Just check headers
            
            if resp.status_code == 200:
                print(f"[OK] {current}: Available")
                success_count += 1
            elif resp.status_code == 404 or resp.status_code == 403:
                # 403 might happen for some older dates? Or missing files?
                print(f"[FAIL] {current}: {resp.status_code}")
                fail_count += 1
            else:
                 print(f"[?] {current}: {resp.status_code}")
        
        except Exception as e:
            print(f"[ERR] {current}: {e}")
        
        current += timedelta(days=1)
        
    print(f"\nSummary: {success_count} Available, {fail_count} Missing (Business Days)")
    if fail_count == 0:
        print("RESULT: FULL CONTINUITY CONFIRMED.")
        return True
    else:
        print("RESULT: GAPS DETECTED.")
        return False

if __name__ == "__main__":
    if verify_content_parsing():
        time.sleep(3)
        verify_gap_recovery()
