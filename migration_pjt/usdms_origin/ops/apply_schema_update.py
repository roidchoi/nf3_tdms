import logging
import sys
import os
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.collectors.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_blacklist_schema():
    logger.info("Applying Blacklist Schema Update...")
    
    ddl = """
    -- [9] 수집 차단 목록 (Blacklist Management)
    CREATE TABLE IF NOT EXISTS us_collection_blacklist (
        cik VARCHAR(10) PRIMARY KEY,       -- Zero-padded CIK
        ticker VARCHAR(10),
        reason_code VARCHAR(50),           -- SEC_403, PARSE_ERROR, NO_DATA
        reason_detail TEXT,
        is_blocked BOOLEAN DEFAULT TRUE,   -- TRUE: 수집 제외, FALSE: 해제(재시도)
        fail_count INTEGER DEFAULT 0,
        last_failed_at TIMESTAMP,
        last_verified_at TIMESTAMP,        -- 관리자 검증 시각
        admin_note TEXT,                   -- 대시보드 관리자 메모
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_blacklist_status ON us_collection_blacklist(is_blocked);
    """
    
    db = DatabaseManager()
    try:
        with db.get_cursor() as cur:
            cur.execute(ddl)
            logger.info("Successfully created table 'us_collection_blacklist'.")
        
        # Verify
        with db.get_cursor() as cur:
            cur.execute("SELECT to_regclass('public.us_collection_blacklist')")
            res = cur.fetchone()
            if res and res[0] == 'us_collection_blacklist':
                 logger.info("Verification Passed: Table exists.")
            else:
                 logger.error("Verification Failed: Table not found.")
                 
    except Exception as e:
        logger.error(f"Schema Update Failed: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    apply_blacklist_schema()
