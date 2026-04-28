import sys
import os
import json
import asyncio
import logging
import random
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager
from backend.utils.blacklist_manager import BlacklistManager

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MajorEnricher")

class MajorUniverseEnricher:
    def __init__(self):
        self.db = DatabaseManager()
        self.blacklist = BlacklistManager()
        self.sem = asyncio.Semaphore(5) # Concurrency Limit
        self.report_path = "db_init/enrichment_summary.json"
        
    def normalize_exchange(self, raw):
        if not raw: return 'OTHER'
        up = raw.upper().strip()
        if up in ['NASDAQ', 'NMS', 'NGM', 'NCM', 'NAS', 'NMFQS']: return 'NASDAQ'
        if up in ['NYSE', 'NEW YORK STOCK EXCHANGE', 'NYQ', 'NYS', 'NYC']: return 'NYSE'
        if up in ['AMEX', 'AMERICAN STOCK EXCHANGE', 'ASE', 'ASEQ']: return 'AMEX'
        if up in ['PNK', 'PINK', 'PINK SHEETS', 'OTC', 'OTCQX', 'OTCQB', 'OTC MARKETS', 'OTC Markets']: return 'OTC'
        return 'OTHER'

    async def _fetch_metadata(self, cik, ticker):
        if self.blacklist.is_blacklisted(cik):
            return None
            
        async with self.sem:
            # Random delay 0.5 ~ 1.0s
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            try:
                loop = asyncio.get_event_loop()
                def fetch():
                    t = yf.Ticker(ticker)
                    return t.info
                
                info = await loop.run_in_executor(None, fetch)
                if not info:
                    self.blacklist.add_blacklist(cik, "Empty Info", ticker)
                    return None
                    
                exch_raw = info.get('exchange')
                if not exch_raw:
                    return None
                    
                return {
                    'cik': cik,
                    'ticker': ticker,
                    'exchange': self.normalize_exchange(exch_raw),
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'market_cap': info.get('marketCap'),
                    'current_price': info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose'),
                    'quote_type': info.get('quoteType'),
                    'country': info.get('country')
                }
            except Exception as e:
                # Handle 404/Block
                if "404" in str(e) or "Not Found" in str(e):
                    self.blacklist.add_blacklist(cik, f"404 Not Found: {e}", ticker)
                return None

    async def run(self):
        logger.info(">>> Identifying Enrichment Targets...")
        
        # 1. Select Targets
        with self.db.get_cursor() as cur:
            cur.execute("""
                SELECT cik, latest_ticker 
                FROM us_ticker_master 
                WHERE is_active = TRUE 
                  AND exchange IN ('NYSE', 'NASDAQ', 'AMEX')
                  AND is_collect_target = FALSE
            """)
            targets = cur.fetchall()
            
        total_targets = len(targets)
        logger.info(f"    - Found {total_targets} targets.")
        
        # 2. Batch Enrichment
        results = []
        batch_size = 50
        
        for i in range(0, total_targets, batch_size):
            batch = targets[i:i+batch_size]
            logger.info(f"Processing Batch {i//batch_size + 1}/{(total_targets // batch_size) + 1}...")
            
            tasks = [self._fetch_metadata(r['cik'], r['latest_ticker']) for r in batch]
            batch_res = await asyncio.gather(*tasks)
            valid_batch = [r for r in batch_res if r is not None]
            results.extend(valid_batch)
            
            # Bulk Update DB
            if valid_batch:
                self._update_db(valid_batch)
                
        enrich_success_count = len(results)
        logger.info(f"Enrichment Complete. Success: {enrich_success_count}/{total_targets}")
        
        # 3. Target Promotion
        logger.info(">>> Executing Target Promotion...")
        promoted_count = 0
        rejected_count = 0
        
        with self.db.get_cursor() as cur:
            # Promote Logic: US Equity + Sector/Industry Exists
            cur.execute("""
                UPDATE us_ticker_master
                SET is_collect_target = TRUE, updated_at = NOW()
                WHERE is_active = TRUE
                  AND is_collect_target = FALSE
                  AND exchange IN ('NYSE', 'NASDAQ', 'AMEX')
                  AND country = 'United States'
                  AND quote_type = 'EQUITY'
                  AND sector IS NOT NULL
                  AND industry IS NOT NULL
            """)
            promoted_count = cur.rowcount
            
            # Calculate Rejected (Attempted - Promoted) 
            # Note: This is an approximation. Some might have been skipped in enrichment.
            # Accurately:
            # Candidates = total_targets
            # Promoted = promoted_count
            # Rejected/Leftover = total_targets - promoted_count
            rejected_count = total_targets - promoted_count

        logger.info(f"    - Promoted: {promoted_count}")
        logger.info(f"    - Rejected/Skipped: {rejected_count}")
        
        # 4. Report
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_attempts": total_targets,
            "enrich_success": enrich_success_count,
            "promoted": promoted_count,
            "rejected_or_skipped": rejected_count
        }
        
        with open(self.report_path, 'w') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Summary saved to {self.report_path}")

    def _update_db(self, data):
        with self.db.get_cursor() as cur:
            q = """
                UPDATE us_ticker_master
                SET 
                    exchange = %s,
                    sector = %s,
                    industry = %s,
                    market_cap = %s,
                    current_price = %s,
                    quote_type = %s,
                    country = %s,
                    updated_at = NOW()
                WHERE cik = %s
            """
            values = [(
                d['exchange'], d['sector'], d['industry'],
                d['market_cap'], d['current_price'],
                d['quote_type'], d['country'],
                d['cik']
            ) for d in data]
            
            from psycopg2.extras import execute_batch
            execute_batch(cur, q, values)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    enricher = MajorUniverseEnricher()
    asyncio.run(enricher.run())
