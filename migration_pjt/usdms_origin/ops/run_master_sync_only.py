import asyncio
import logging
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.master_sync import MasterSync
from backend.collectors.db_manager import DatabaseManager

# Logging Setup
os.makedirs("logs/ops", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"logs/ops/master_sync_only_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info(">>> Starting Standalone Master Sync...")
    
    try:
        # Initialize DB to ensure connection is okay
        db = DatabaseManager()
        
        # Initialize and Run Master Sync
        sync = MasterSync()
        stats = await sync.sync_daily(limit=None)
        
        logger.info(">>> Master Sync Completed Successfully.")
        logger.info(f"Stats: {stats}")
        
    except Exception as e:
        logger.error(f"Critical Error during Master Sync: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
