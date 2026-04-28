import sys
import os
import asyncio
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager

def main():
    print(">>> Auditing Exchanges by Status...")
    db = DatabaseManager()
    
    ALLOWED = {'NASDAQ', 'NYSE', 'AMEX', 'OTC', 'OTHER'}
    
    with db.get_cursor() as cur:
        # Check Active
        cur.execute("SELECT DISTINCT exchange FROM us_ticker_master WHERE is_active = TRUE")
        active_found = set([r['exchange'] for r in cur.fetchall() if r['exchange']])
        active_invalid = active_found - ALLOWED
        
        # Check Inactive
        cur.execute("SELECT DISTINCT exchange FROM us_ticker_master WHERE is_active = FALSE")
        inactive_found = set([r['exchange'] for r in cur.fetchall() if r['exchange']])
        inactive_invalid = inactive_found - ALLOWED
        
        print("\n[Active Records]")
        if not active_invalid:
            print("  - PASS (All exchanges valid)")
        else:
            print(f"  - FAIL: Found {active_invalid}")
            
        print("\n[Inactive Records]")
        if not inactive_invalid:
            print("  - PASS (All exchanges valid)")
        else:
            print(f"  - FAIL: Found {inactive_invalid}")

if __name__ == "__main__":
    main()
