import sys
import os
import logging
from dotenv import load_dotenv

# Load Env
load_dotenv(override=True)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.collectors.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("DBKiller")

def kill_locking_sessions():
    db = DatabaseManager()
    
    with db.get_cursor() as cur:
        # 1. Check for Blocking Sessions
        logger.info(">>> Checking for Blocking Sessions...")
        cur.execute("""
            SELECT 
                pid, 
                usename, 
                state, 
                query_start, 
                query 
            FROM pg_stat_activity 
            WHERE state = 'idle in transaction' 
               OR state = 'active'
               AND pid != pg_backend_pid()
        """)
        rows = cur.fetchall()
        
        if not rows:
            logger.info("✅ No blocking sessions found.")
            return

        logger.info(f"!!! Found {len(rows)} potential blocking sessions:")
        for r in rows:
            logger.info(f"   [PID {r['pid']}] User: {r['usename']} | State: {r['state']} | Start: {r['query_start']}")
            logger.info(f"   Query: {r['query'][:100]}...")

        # 2. Ask to Kill
        logger.info("\n>>> Terminating these sessions to free locks...")
        
        for r in rows:
            pid = r['pid']
            try:
                # Use a specific logic to avoid killing SELF or System, though query excluded self.
                # Use pg_terminate_backend(pid)
                cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
                logger.info(f"   💀 Terminated PID {pid}")
            except Exception as e:
                logger.error(f"   ❌ Failed to kill PID {pid}: {e}")

    logger.info(">>> Lock Cleanup Complete. Please try running your test script again.")

if __name__ == "__main__":
    kill_locking_sessions()
