import os
import sys
from dotenv import load_dotenv

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.collectors.db_manager import DatabaseManager

def cleanup():
    # Load env
    load_dotenv(override=True)
    db = DatabaseManager()
    
    print(">>> Starting Test Data Cleanup...")
    
    queries = [
        # 1. Remove integration test blacklist entry
        """
        DELETE FROM us_collection_blacklist 
        WHERE cik = '9999999999';
        """,
        # 2. Remove dummy master entries (if any)
        """
        DELETE FROM us_ticker_master 
        WHERE cik = '9999999999' OR latest_ticker IN ('TEST', 'DUMMY');
        """
    ]
    
    total_deleted = 0
    with db.get_cursor() as cur:
        for q in queries:
            cur.execute(q)
            cnt = cur.rowcount
            print(f"Executed: {q.strip()} \nDeleted Rows: {cnt}")
            total_deleted += cnt
            
    print(f">>> Cleanup Complete. Total rows deleted: {total_deleted}")

if __name__ == "__main__":
    cleanup()
