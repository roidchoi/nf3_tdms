from backend.db_manager import DatabaseManager
import logging

def check_reasons():
    db = DatabaseManager()
    target_tickers = ['HAWEL', 'SHPH', 'IHT', 'NCL', 'CXAI', 'AOXY', 'CWD']
    
    with db.get_cursor() as cur:
        # Check Master Status
        cur.execute("""
            SELECT cik, latest_ticker, is_active, is_collect_target 
            FROM us_ticker_master 
            WHERE latest_ticker = ANY(%s)
        """, (target_tickers,))
        rows = cur.fetchall()
        
        print("\n--- Ticker Status ---")
        for r in rows:
            print(f"{r['latest_ticker']}: Active={r['is_active']}, Target={r['is_collect_target']}, CIK={r['cik']}")
            
        # Check Blacklist Reasons
        cur.execute("""
            SELECT cik, ticker, reason, created_at 
            FROM us_collection_blacklist 
            WHERE ticker = ANY(%s)
            ORDER BY created_at DESC
        """, (target_tickers,))
        reasons = cur.fetchall()
        
        print("\n--- Blacklist Reasons ---")
        for r in reasons:
            print(f"[{r['created_at']}] {r['ticker']}: {r['reason']}")

if __name__ == "__main__":
    check_reasons()
