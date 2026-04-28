import sys
import os
import logging
import yfinance as yf
from typing import List, Dict, Any
import time
import random
from tqdm import tqdm
from dotenv import load_dotenv

# Load .env
load_dotenv(override=True)

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class MasterEnricher:
    def __init__(self):
        self.db = DatabaseManager()

    def run_enrichment(self):
        """
        Enrich metadata for targets with missing country info.
        Filter out non-US companies (ADRs).
        """
        logger.info("Starting Master Enrichment...")
        
        # 1. Get Targets (Missing Country)
        with self.db.get_cursor() as cur:
            cur.execute("""
                SELECT cik, latest_ticker 
                FROM us_ticker_master 
                WHERE is_collect_target = TRUE AND country IS NULL
            """)
            targets = cur.fetchall()
            
        logger.info(f"Found {len(targets)} targets needing enrichment.")
        
        if not targets:
            return

        updates = []
        adr_count = 0
        
        # 2. Fetch from yfinance
        # We process one by one. yfinance wraps API calls.
        # We can use Ticker object.
        
        for i, row in tqdm(enumerate(targets), total=len(targets), desc="Enriching Metadata"):
            cik = row['cik']
            ticker_symbol = row['latest_ticker']
            
            try:
                # yfinance ticker
                t = yf.Ticker(ticker_symbol)
                info = t.info
                
                # Fields
                country = info.get('country')
                sector = info.get('sector')
                industry = info.get('industry')
                
                # Check consistency
                # Some tickers might fail or return empty info
                if not country:
                    logger.warning(f"[{ticker_symbol}] No country info found.")
                    # We assume it is US if unknown? Or keep NULL? 
                    # Let's keep NULL if really unknown, but maybe set to 'Unknown' to avoid re-querying forever?
                    # Or maybe retry later. For now, skip update if empty.
                    pass
                else:
                    # Determine Status
                    is_target = True
                    if country != 'United States':
                        is_target = False
                        adr_count += 1
                        logger.info(f"[{ticker_symbol}] Excluding ADR/Foreign: {country}")
                        
                    updates.append({
                        'cik': cik,
                        'country': country,
                        'sector': sector,
                        'industry': industry,
                        'is_collect_target': is_target
                    })
                    
            except Exception as e:
                logger.error(f"[{ticker_symbol}] Error fetching info: {e}")
                
            # Throttling
            # Sleep 1.0 ~ 2.0 seconds between requests to be safe from IP Ban
            time.sleep(random.uniform(1.0, 2.0))

        # 3. Batch Update
        if updates:
            self._batch_update(updates)
            
        logger.info(f"Enrichment Complete. Processed {len(updates)}. Excluded {adr_count} ADRs.")

    def _batch_update(self, updates: List[Dict]):
        query = """
            UPDATE us_ticker_master
            SET country = %(country)s,
                sector = COALESCE(%(sector)s, sector), 
                industry = %(industry)s,
                is_collect_target = %(is_collect_target)s,
                updated_at = NOW()
            WHERE cik = %(cik)s
        """
        # Note: We update sector only if new value exists? 
        # Actually user said "yfinance sector info is reliable". We can overwrite or coalesce.
        # COALESCE(new, old) keeps old if new is None.
        
        with self.db.get_cursor() as cur:
            from psycopg2.extras import execute_batch
            execute_batch(cur, query, updates)
            logger.info(f"Updated {len(updates)} records in DB.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    enricher = MasterEnricher()
    enricher.run_enrichment()
