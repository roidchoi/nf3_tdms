import os
import logging
from datetime import date
from backend.collectors.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_upsert():
    db = DatabaseManager()
    
    test_data = [
        {
            'dt': date(2026, 2, 4),
            'cik': '0000000000',
            'ticker': 'TEST',
            'open_prc': 100.0,
            'high_prc': 110.0,
            'low_prc': 90.0,
            'cls_prc': 105.0,
            'vol': 1000,
            'amt': 105000.0
        }
    ]
    
    logger.info("Testing insert_daily_price...")
    try:
        db.insert_daily_price(test_data)
        logger.info("Successfully executed insert_daily_price (First time)")
        
        # Second time (Conflict)
        db.insert_daily_price(test_data)
        logger.info("Successfully executed insert_daily_price (Second time - Upsert)")
        
    except Exception as e:
        logger.error(f"Failed: {e}")

if __name__ == "__main__":
    test_upsert()
