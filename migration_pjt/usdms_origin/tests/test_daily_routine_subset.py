import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

# Load Env
load_dotenv(override=True)

# Set Test Limit explicitly
os.environ["TEST_LIMIT"] = "20"
os.environ["LOG_LEVEL"] = "INFO"

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ops.run_daily_routine import DailyRoutine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("TestSubset")

async def run_test():
    logger.info(">>> STARTING SUBSET TEST (Limit=20) <<<")
    
    routine = DailyRoutine()
    
    try:
        # Pre-Verification: Ensure Blacklist DB Connection works
        from backend.utils.blacklist_manager import BlacklistManager
        bl_manager = BlacklistManager()
        test_cik = '9999999999'
        bl_manager.add_blacklist(test_cik, 'INTEGRATION_TEST_BLOCK')
        logger.info(f"Pre-Check: Added {test_cik} to Blacklist.")
        
        await routine.run()
        logger.info(">>> TEST COMPLETED SUCCESSFULLY <<<")
        
        # Post-Verification
        if bl_manager.is_blacklisted(test_cik):
             logger.info("Post-Check: Blacklist persistence verified.")
             # Clean up
             bl_manager.remove_blacklist(test_cik, 'Integration Test Cleanup')
        else:
             logger.error("Post-Check Failed: Test CIK not found in Blacklist!")
        
        bl_manager.close()
        
        # Verify Report
        if routine.report['anomalies']:
            logger.info(f"Anomalies Found: {len(routine.report['anomalies'])}")
        else:
            logger.info("No Anomalies Found.")
            
    except Exception as e:
        logger.error(f"!!! TEST FAILED: {e}", exc_info=True)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(run_test())
