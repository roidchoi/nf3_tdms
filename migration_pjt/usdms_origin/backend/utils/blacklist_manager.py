import logging
import json
import os
from datetime import datetime
from ..collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class BlacklistManager:
    """
    Manages collection blacklist (e.g. 403 Forbidden, Parsing Errors).
    V2.0: Migrated from JSON to Database (us_collection_blacklist table).
    """
    
    def __init__(self):
        self.db = DatabaseManager()

    def add_blacklist(self, cik: str, reason: str, ticker: str = None):
        """
        Add or Update a CIK in the blacklist.
        If already exists, increments fail_count and updates timestamp.
        Sets is_blocked = TRUE.
        """
        cik_str = str(cik).zfill(10)
        
        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    INSERT INTO us_collection_blacklist 
                    (cik, ticker, reason_code, is_blocked, fail_count, last_failed_at, created_at, updated_at)
                    VALUES (%s, %s, %s, TRUE, 1, NOW(), NOW(), NOW())
                    ON CONFLICT (cik) DO UPDATE 
                    SET is_blocked = TRUE,
                        reason_code = EXCLUDED.reason_code,
                        fail_count = us_collection_blacklist.fail_count + 1,
                        last_failed_at = NOW(),
                        updated_at = NOW()
                """, (cik_str, ticker, reason))
            logger.info(f"Blacklisted CIK {cik_str} (Reason: {reason})")
        except Exception as e:
            logger.error(f"Failed to add blacklist for {cik_str}: {e}")

    def is_blacklisted(self, cik: str) -> bool:
        """
        Check if a CIK is currently blocked.
        """
        cik_str = str(cik).zfill(10)
        try:
            with self.db.get_cursor() as cur:
                cur.execute("SELECT is_blocked FROM us_collection_blacklist WHERE cik = %s", (cik_str,))
                row = cur.fetchone()
                if row and row['is_blocked']:
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to check blacklist for {cik_str}: {e}")
            return False

    def remove_blacklist(self, cik: str, admin_note: str = "System Released"):
        """
        Unblock a CIK (set is_blocked = FALSE).
        """
        cik_str = str(cik).zfill(10)
        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    UPDATE us_collection_blacklist 
                    SET is_blocked = FALSE, 
                        updated_at = NOW(),
                        admin_note = %s
                    WHERE cik = %s
                """, (admin_note, cik_str))
            logger.info(f"Released CIK {cik_str} from blacklist.")
        except Exception as e:
            logger.error(f"Failed to remove blacklist for {cik_str}: {e}")
            
    def close(self):
        self.db.close()
