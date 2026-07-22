import asyncio
import aiohttp
import logging
import random
import os
import concurrent.futures
import threading
import time
import queue
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
from psycopg2.extras import execute_batch, execute_values
from p3_usdms.repositories.base import BaseRepository
from p3_usdms.collectors.sec_client import SECClient
from p3_usdms.config import get_settings

logger = logging.getLogger(__name__)

class BufferedLogHandler(logging.Handler):
    """
    Captures logs using a lock-free SimpleQueue for emit, 
    and drains to a buffer for querying. 
    Prevents Deadlocks during logging storms.
    """
    def __init__(self):
        super().__init__()
        self.queue = queue.SimpleQueue()
        self.buffer = defaultdict(list)
        self.buffer_lock = threading.Lock()
        
    def emit(self, record):
        try:
            msg = self.format(record)
            entry = (record.thread, msg, record.created)
            self.queue.put_nowait(entry)
        except Exception:
            self.handleError(record)
            
    def drain(self):
        """Move logs from Queue to Buffer safely."""
        while not self.queue.empty():
            try:
                entry = self.queue.get_nowait()
                with self.buffer_lock:
                    self.buffer[entry[0]].append({
                        'msg': entry[1],
                        'time': entry[2]
                    })
            except queue.Empty:
                break
            
    def get_logs_by_thread(self, thread_id, min_time=0):
        self.drain()
        with self.buffer_lock:
            if thread_id in self.buffer:
                 return [entry['msg'] for entry in self.buffer[thread_id] if entry['time'] >= min_time]
            return []

class MasterSync:
    def __init__(self):
        self.db = BaseRepository()
        self.sec_client = SECClient()
        self.sem = asyncio.Semaphore(int(os.getenv('MAX_CONCURRENCY', 5)))
        
        self.log_handler = BufferedLogHandler()
        yf_logger = logging.getLogger('yfinance')
        yf_logger.addHandler(self.log_handler)
        
        if yf_logger.getEffectiveLevel() > logging.INFO:
            yf_logger.setLevel(logging.INFO)
            
        self.yf_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=int(os.getenv('MAX_CONCURRENCY', 5)) * 2,
            thread_name_prefix='YF_Worker'
        ) 

    @staticmethod
    def normalize_exchange(raw: str) -> str:
        """
        Normalize exchange names to 5 standard values:
        ['NASDAQ', 'NYSE', 'AMEX', 'OTC', 'OTHER']
        """
        if not raw:
            return 'OTHER'
            
        up = raw.upper().strip()
        
        if 'NASDAQ' in up or any(x == up for x in ['NMS', 'NGM', 'NCM', 'NAS', 'NMFQS']):
            return 'NASDAQ'
        if 'NEW YORK STOCK EXCHANGE' in up or 'NYSE' in up or any(x == up for x in ['NYQ', 'NYS', 'NYC']):
            return 'NYSE'
        if 'AMERICAN STOCK EXCHANGE' in up or 'AMEX' in up or any(x == up for x in ['ASE', 'ASEQ']):
            return 'AMEX'
        if 'PINK' in up or 'OTC' in up or any(x == up for x in ['PNK', 'PINK SHEETS', 'OTCQX', 'OTCQB', 'OTC MARKETS']):
            return 'OTC'
            
        return 'OTHER'


    def _resolve_primary_ticker(self, candidates: List[Dict], current_db_ticker: Optional[str] = None) -> Dict:
        """
        Logic V2:
        Rule 0: Exception Map (Hard Override)
        Rule 1: Exchange Rank (NYSE > NASDAQ > AMEX > OTC > OTHER)
        Rule 2: Purity (No Special Chars)
        Rule 3: Stickiness (If Rank/Purity essentially tied)
        Rule 4: Tie-Breaker (Length ASC -> Alpha ASC)
        """
        if not candidates:
            return None
            
        cik_str = str(candidates[0].get('cik_str', candidates[0].get('cik', 0))).zfill(10)
        
        EXCEPTION_MAP = {
            '0001652044': 'GOOGL',  # Alphabet
            '0001067983': 'BRK-B',  # Berkshire
            '0001336917': 'UAA',    # Under Armour
            '0001754301': 'FOXA'    # Fox Corp
        }
        
        if cik_str in EXCEPTION_MAP:
            target = EXCEPTION_MAP[cik_str]
            for c in candidates:
                if c.get('ticker') == target:
                    return c
        
        EXCHANGE_RANK = {'NYSE': 1, 'NASDAQ': 2, 'AMEX': 3, 'OTC': 4, 'OTHER': 5}
        
        def get_rank(item):
            # 후보가 exchange 정보를 가지고 있다면 사용하고, 없으면 SECClient 전체 조회 데이터(sec_exchanges)로 판단할 수도 있음
            exc_raw = item.get('exchange_norm') or item.get('exchange') or 'OTHER'
            return EXCHANGE_RANK.get(self.normalize_exchange(exc_raw), 5)

        def is_special(t):
            return not t.replace('.', '').replace('-', '').replace('$', '').isalpha()

        enriched_candidates = []
        for c in candidates:
            ticker_text = c.get('ticker', '')
            rank = get_rank(c)
            special = is_special(ticker_text)
            length = len(ticker_text)
            
            enriched_candidates.append({
                'item': c,
                'rank': rank,
                'special': special,
                'len': length,
                'ticker': ticker_text,
                'sort_key': (rank, special, length, ticker_text)
            })

        enriched_candidates.sort(key=lambda x: x['sort_key'])
        best_candidate = enriched_candidates[0]

        if current_db_ticker:
            current_obj = next((x for x in enriched_candidates if x['ticker'] == current_db_ticker), None)
            if current_obj:
                if current_obj['rank'] == best_candidate['rank'] and current_obj['special'] == best_candidate['special']:
                    return current_obj['item']

        return best_candidate['item']

    async def collect_daily_master_updates(self, ciks: List[str] = None):
        if ciks:
             await self._enrich_specific_ciks(ciks)
        else:
             await self.sync_daily()

    async def sync_daily(self, limit: int = None) -> Dict[str, int]:
        logger.info(">>> Starting Master Sync (Daily)...")
        
        stats = {
            'new_listings': 0, 
            'delistings': 0, 
            'ticker_changes': 0, 
            'exchange_updates': 0
        }
        
        monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info(">>> [Step 1] Loading SEC Data...")
        try:
            sec_exchanges = self.sec_client.get_tickers_exchange()
        except Exception as e:
            logger.warning(f"Could not fetch SEC exchanges: {e}. using empty.")
            sec_exchanges = {}
            
        sec_tickers_raw = self.sec_client.get_company_tickers()
        
        sec_cik_candidates = defaultdict(list)
        for item in sec_tickers_raw.values():
            cik_int = int(item['cik_str'])
            # Exchange Rank 결정 등을 돕기 위해 후보군에 거래소 정보 주입
            ticker = item.get('ticker')
            if ticker in sec_exchanges:
                item['exchange'] = sec_exchanges[ticker]
            sec_cik_candidates[cik_int].append(item)
            
        sec_cik_set = set(sec_cik_candidates.keys())
        
        logger.info(">>> [Step 2] Loading DB State...")
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker, exchange, is_active FROM us_ticker_master")
            db_records = cur.fetchall()
            
        db_cik_map = {int(r['cik']): r for r in db_records}
        db_cik_set = set(db_cik_map.keys())
        
        logger.info(f"SEC: {len(sec_cik_set)}, DB: {len(db_cik_set)}")
        
        logger.info(">>> [Step 3] Diff Processing...")
        
        # Case A: New Listings
        new_ciks = sec_cik_set - db_cik_set
        new_data = [] 
        new_history = [] 
        
        for cik in new_ciks:
            candidates = sec_cik_candidates[cik]
            resolved = self._resolve_primary_ticker(candidates, current_db_ticker=None)
            
            ticker = resolved['ticker']
            name = resolved['title']
            exchange_raw = sec_exchanges.get(ticker)
            exchange = self.normalize_exchange(exchange_raw) if exchange_raw else 'OTHER'
            
            cik_str = str(cik).zfill(10)
            new_data.append((cik_str, ticker, name, exchange))
            new_history.append((cik_str, ticker, datetime.now().date()))
            stats['new_listings'] += 1
            
        if new_data:
            with self.db.get_cursor() as cur:
                q_master = """
                INSERT INTO us_ticker_master (cik, latest_ticker, latest_name, exchange, is_active, is_collect_target, created_at, updated_at)
                VALUES %s
                ON CONFLICT (cik) DO NOTHING
                """
                rows_master = [(x[0], x[1], x[2], x[3], True, False, datetime.now(), datetime.now()) for x in new_data]
                execute_values(cur, q_master, rows_master)
                
                q_history = """
                INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt)
                VALUES %s
                ON CONFLICT DO NOTHING
                """
                rows_history = [(x[0], x[1], x[2], '9999-12-31') for x in new_history]
                execute_values(cur, q_history, rows_history)
                
            logger.info(f"Inserted {len(new_data)} new tickers.")
            
            new_ciks_str = [x[0] for x in new_data]
            await self._enrich_specific_ciks(new_ciks_str)

        ticker_updates_cik = [] 
        new_history_rows = [] 
        master_updates = [] 
        exchange_updates_only = [] 
        
        today_date = datetime.now().date()
        yesterday_date = today_date - timedelta(days=1)
        
        # Case B: Delisted (Potential)
        delisted_candidates = db_cik_set - sec_cik_set
        verified_delisted = []
        recovered_active = [] 
        
        if delisted_candidates:
            logger.info(f"Detected {len(delisted_candidates)} missing CIKs. Starting Authority Verification...")
            auth_results = await self._verify_batch_authority(list(delisted_candidates))
            
            for res in auth_results:
                cik = int(res['cik'])
                if res.get('is_active') is True:
                    recovered_active.append(res)
                    logger.info(f"Authority Check SAVED {cik}: {res['ticker']} ({res['exchange']})")
                elif res.get('is_active') is False:
                    verified_delisted.append(cik)
                else:
                    logger.debug(f"Authority Check UNCERTAIN {cik}. Retaining active status.")
            
            # 대량 상장폐지 방지 임계치 (Safety Lock): 35개 초과 시 자동 비활성화 스킵 및 경고
            safety_threshold = max(35, int(len(db_cik_set) * 0.01))
            if len(verified_delisted) > safety_threshold:
                logger.error(
                    f"🚨 SAFETY LOCK ACTIVATED: Unusually large number of delistings detected ({len(verified_delisted)} > threshold {safety_threshold}). "
                    f"Aborting automatic deactivation to prevent false positive delistings."
                )
                verified_delisted = []
            
            if verified_delisted:
                ciks_list = [str(c).zfill(10) for c in verified_delisted]
                with self.db.get_cursor() as cur:
                    cur.execute("""
                        UPDATE us_ticker_master 
                        SET is_active = FALSE, is_collect_target = FALSE, updated_at = NOW()
                        WHERE cik = ANY(%s) AND is_active = TRUE
                    """, (ciks_list,))
                    
                    cur.execute("""
                        UPDATE us_ticker_history
                        SET end_dt = CURRENT_DATE
                        WHERE cik = ANY(%s) AND end_dt = '9999-12-31'
                    """, (ciks_list,))
                    
                    stats['delistings'] = cur.rowcount
                logger.info(f"Confirmed & Deactivated {stats['delistings']} tickers.")
                
            for item in recovered_active:
                cik = int(item['cik']) 
                sec_ticker = item['ticker']
                sec_exch = item['exchange']
                
                db_item = db_cik_map.get(cik)
                if not db_item:
                    continue
                    
                db_ticker = db_item['latest_ticker']
                db_exch = db_item['exchange']
                cik_str = str(cik).zfill(10)
                
                if sec_ticker != db_ticker:
                    logger.info(f"[{cik_str}] Authority Update (Ticker): {db_ticker} -> {sec_ticker}")
                    ticker_updates_cik.append(cik_str)
                    new_history_rows.append((cik_str, sec_ticker, today_date, '9999-12-31'))
                    master_updates.append((sec_ticker, sec_exch, cik_str))
                    stats['ticker_changes'] += 1
                elif sec_exch != 'OTHER' and sec_exch != db_exch:
                    logger.info(f"[{cik_str}] Authority Update (Exchange): {db_exch} -> {sec_exch}")
                    exchange_updates_only.append((sec_exch, cik_str))
                    stats['exchange_updates'] += 1

        # Case C: Existing (Ticker Changes - SCD Type 2)
        common_ciks = sec_cik_set.intersection(db_cik_set)
        
        for cik in common_ciks:
            candidates = sec_cik_candidates[cik]
            db_item = db_cik_map[cik]
            db_ticker = db_item['latest_ticker']
            
            resolved = self._resolve_primary_ticker(candidates, current_db_ticker=db_ticker)
            sec_ticker = resolved['ticker']
            
            sec_exch_raw = sec_exchanges.get(sec_ticker)
            sec_exch = self.normalize_exchange(sec_exch_raw) if sec_exch_raw else 'OTHER'
            db_exch = db_item['exchange']
            cik_str = str(cik).zfill(10)
            
            if sec_ticker != db_ticker:
                logger.info(f"[{cik_str}] Ticker Change: {db_ticker} -> {sec_ticker}")
                ticker_updates_cik.append(cik_str)
                new_history_rows.append((cik_str, sec_ticker, today_date, '9999-12-31'))
                
                final_exch = sec_exch if sec_exch != 'OTHER' else db_exch
                master_updates.append((sec_ticker, final_exch, cik_str))
                stats['ticker_changes'] += 1
            elif sec_exch != 'OTHER' and sec_exch != db_exch:
                logger.info(f"[{db_ticker}] Exchange Update: {db_exch} -> {sec_exch}")
                exchange_updates_only.append((sec_exch, cik_str))
                stats['exchange_updates'] += 1
                
        if ticker_updates_cik:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    DELETE FROM us_ticker_history
                    WHERE cik = ANY(%s) AND end_dt = '9999-12-31' AND start_dt > %s
                """, (ticker_updates_cik, yesterday_date))

                cur.execute("""
                    UPDATE us_ticker_history
                    SET end_dt = %s
                    WHERE cik = ANY(%s) AND end_dt = '9999-12-31'
                """, (yesterday_date, ticker_updates_cik))
                
                q_hist = "INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt) VALUES %s"
                execute_values(cur, q_hist, new_history_rows)
                
                q_mast = """
                    UPDATE us_ticker_master
                    SET latest_ticker = %s, exchange = %s, updated_at = NOW()
                    WHERE cik = %s
                """
                execute_batch(cur, q_mast, master_updates)

        if exchange_updates_only:
             with self.db.get_cursor() as cur:
                q_exch = "UPDATE us_ticker_master SET exchange = %s, updated_at = NOW() WHERE cik = %s"
                execute_batch(cur, q_exch, exchange_updates_only)

        logger.info(f"Diff Processed. Stats: {stats}")
        
        # Step 4: Metadata Enrichment & Price Updates
        logger.info(">>> [Step 4] Metadata & Price Updates...")
        
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik FROM us_ticker_master WHERE is_collect_target = TRUE")
            target_ciks = [r['cik'] for r in cur.fetchall()]
            
        total_updated = 0
        total_ciks = len(target_ciks)
        pruning_date = datetime.now().date() - timedelta(days=14)
        
        logger.info(f"Updating {total_ciks} targets (Iterative Robust Mode)...")
        
        MINI_BATCH_SIZE = 5 
        for i in range(0, total_ciks, MINI_BATCH_SIZE):
            batch = target_ciks[i:i+MINI_BATCH_SIZE]
            update_data = []
            
            for cik in batch:
                try:
                    cap = None
                    prc = None
                    
                    with self.db.get_cursor() as cur:
                        cur.execute("""
                            SELECT mkt_cap FROM us_daily_valuation 
                            WHERE cik = %s AND dt >= %s 
                            ORDER BY dt DESC LIMIT 1
                        """, (cik, pruning_date))
                        r_cap = cur.fetchone()
                        if r_cap: 
                            cap = r_cap['mkt_cap']
                        
                        cur.execute("""
                            SELECT cls_prc FROM us_daily_price 
                            WHERE cik = %s AND dt >= %s 
                            ORDER BY dt DESC LIMIT 1
                        """, (cik, pruning_date))
                        r_prc = cur.fetchone()
                        if r_prc: 
                            prc = r_prc['cls_prc']
                    
                    if cap is not None or prc is not None:
                        update_data.append((cap, prc, cik))
                except Exception as e:
                    logger.warning(f"Error fetching for {cik}: {e}")
                    continue

            if update_data:
                with self.db.get_cursor() as cur:
                    q_update = """
                        UPDATE us_ticker_master
                        SET market_cap = COALESCE(%s, market_cap),
                            current_price = COALESCE(%s, current_price),
                            updated_at = NOW()
                        WHERE cik = %s
                    """
                    execute_batch(cur, q_update, update_data)
                    total_updated += len(update_data)
            
        logger.info(f"Updated {total_updated}/{total_ciks} targets (Robust Strategy).")
        
        query_enrich = """
            SELECT cik, latest_ticker FROM us_ticker_master 
            WHERE is_active = TRUE 
              AND (is_collect_target = FALSE OR market_cap IS NULL OR current_price IS NULL OR sector IS NULL)
              AND (country = 'United States' OR country IS NULL)
              AND (quote_type = 'EQUITY' OR quote_type IS NULL)
        """
        if limit and limit > 0:
             query_enrich += f" LIMIT {limit}"
             
        with self.db.get_cursor() as cur:
            cur.execute(query_enrich)
            candidates = cur.fetchall()
            
        if candidates:
            ciks_to_enrich = [r['cik'] for r in candidates]
            logger.info(f"Enriching {len(ciks_to_enrich)} candidates via yfinance...")
            
            BATCH_SIZE = 50
            total_enrich = len(ciks_to_enrich)
            
            for i in range(0, total_enrich, BATCH_SIZE):
                chunk = ciks_to_enrich[i:i+BATCH_SIZE]
                
                chunk_tickers = []
                with self.db.get_cursor() as cur:
                     cur.execute("SELECT latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (chunk,))
                     chunk_tickers = [r['latest_ticker'] for r in cur.fetchall()]
                logger.info(f"Processing Batch {i//BATCH_SIZE}: {chunk_tickers}")

                try:
                    await self._enrich_specific_ciks(chunk)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Enrichment Batch {i} Failed: {e}") 

        logger.info(">>> [Step 5] Targeting Analysis...")
        self._update_target_status()
        
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
            
        return stats

    async def _monitor_loop(self):
        while True:
            await asyncio.sleep(5)
            logger.info(f"[Heartbeat] Main Loop Active - {time.time()}")
                    
    async def _enrich_specific_ciks(self, ciks: List[str]):
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)", (ciks,))
            rows = cur.fetchall()
            ciks_map = {r['cik']: r['latest_ticker'] for r in rows}
            
        tasks = [self._fetch_yfinance_metadata(cik, ticker) for cik, ticker in ciks_map.items()]
        results = await asyncio.gather(*tasks)
        
        valid_results = [r for r in results if r is not None]
        self._bulk_update_metadata(valid_results)

    async def _verify_batch_authority(self, ciks: List[int]) -> List[Dict]:
        results = []
        ua = self.sec_client.user_agent
        headers = {"User-Agent": ua, "Host": "data.sec.gov"}
        
        async def fetch(session, cik):
            url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
            async with self.sem:
                await asyncio.sleep(0.12)
                try:
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            tickers = data.get('tickers', [])
                            exchanges = data.get('exchanges', [])
                            if tickers and exchanges:
                                return {
                                    'cik': str(cik).zfill(10),
                                    'is_active': True,
                                    'ticker': tickers[0],
                                    'exchange': self.normalize_exchange(exchanges[0])
                                }
                            return {'cik': str(cik).zfill(10), 'is_active': False}
                        elif resp.status == 404:
                            # 명확히 SEC 미존재(404) 시에만 상장폐지로 판정
                            return {'cik': str(cik).zfill(10), 'is_active': False}
                        else:
                            # HTTP 429, 500/503 등은 검증 보류(None) 리턴
                            logger.warning(f"Authority Check SEC HTTP {resp.status} for CIK {cik}. Retaining state.")
                            return {'cik': str(cik).zfill(10), 'is_active': None}
                except Exception as e:
                    logger.warning(f"Authority Check Exception for CIK {cik}: {e}. Retaining state.")
                    return {'cik': str(cik).zfill(10), 'is_active': None}

        async with aiohttp.ClientSession() as session:
            tasks = [fetch(session, cik) for cik in ciks]
            results = await asyncio.gather(*tasks)
            
        return results

    async def _fetch_yfinance_metadata(self, cik: str, ticker: str) -> Optional[Dict[str, Any]]:
        async with self.sem:
            delay = random.uniform(0.1, 0.5)
            await asyncio.sleep(delay)
            try:
                loop = asyncio.get_event_loop()
                def fetch():
                    tid = threading.get_ident()
                    t = yf.Ticker(ticker)
                    try:
                        return t.info, tid
                    except Exception:
                        return None, tid
                
                start_ts = time.time()
                info = None
                worker_tid = None
                
                try:
                    info, worker_tid = await asyncio.wait_for(
                        loop.run_in_executor(self.yf_executor, fetch), 
                        timeout=15.0  
                    )
                except asyncio.TimeoutError:
                    return None
                except Exception as e:
                    logger.warning(f"Executor Error for {ticker}: {e}")
                    return None
                
                captured_logs = []
                if worker_tid:
                     captured_logs = self.log_handler.get_logs_by_thread(worker_tid, min_time=start_ts)
                
                exchange_raw = None
                if info:
                    exchange_raw = info.get('exchange')
                
                if not exchange_raw:
                      if captured_logs:
                          for log_msg in captured_logs:
                              if "Rate limited" in log_msg or "Too Many Requests" in log_msg or "429" in log_msg:
                                  logger.warning(f"[{ticker}] Rate Limit Hit. Skipping blacklist and backing off...")
                                  await asyncio.sleep(5)
                                  return None
                              if "401" in log_msg or "Unauthorized" in log_msg:
                                  logger.warning(f"[{ticker}] Deducted 401/Unauthorized (Crumb Failure). Skipping blacklist to allow future retry.")
                                  return None
                      return None
                      
                norm_exchange = self.normalize_exchange(exchange_raw)
                
                return {
                    'cik': cik,
                    'exchange': norm_exchange,
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'market_cap': info.get('marketCap'),
                    'current_price': info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose'),
                    'quote_type': info.get('quoteType'),
                    'country': info.get('country')
                }
            except Exception as e:
                return None

    def _bulk_update_metadata(self, data: List[Dict[str, Any]]):
        if not data: 
            return
        with self.db.get_cursor() as cur:
            query = """
                UPDATE us_ticker_master
                SET 
                    exchange = CASE 
                        WHEN exchange IS NULL OR exchange = 'OTHER' THEN %s 
                        ELSE exchange 
                    END,
                    sector = %s,
                    industry = %s,
                    market_cap = %s,
                    current_price = %s,
                    quote_type = %s,
                    country = %s,
                    updated_at = NOW()
                WHERE cik = %s
            """
            
            values = [
                (
                    d['exchange'],
                    d['sector'], d['industry'],
                    d['market_cap'], d['current_price'],
                    d['quote_type'], d['country'],
                    d['cik']
                ) for d in data
            ]
            execute_batch(cur, query, values)
            logger.info(f"Bulk enriched {len(values)} tickers.")

    def _update_target_status(self):
        settings = get_settings()
        
        with self.db.get_cursor() as cur:
            major_exchanges = "('NASDAQ', 'NYSE', 'AMEX')"
            retention_q = f"""
                UPDATE us_ticker_master
                SET is_collect_target = FALSE, updated_at = NOW()
                WHERE is_collect_target = TRUE
                  AND (
                      market_cap < %s 
                      OR current_price < %s
                      OR exchange NOT IN {major_exchanges}
                      OR country != 'United States'
                      OR quote_type != 'EQUITY'
                      OR market_cap IS NULL
                      OR current_price IS NULL
                  )
            """
            cur.execute(retention_q, (settings.TARGET_RETAIN_MARKET_CAP, settings.TARGET_RETAIN_PRICE))
            logger.info(f"Retention logic applied. Dropped count: {cur.rowcount}")
            
            entry_q = f"""
                UPDATE us_ticker_master
                SET is_collect_target = TRUE, updated_at = NOW()
                WHERE is_collect_target = FALSE
                  AND is_active = TRUE
                  AND market_cap >= %s
                  AND current_price >= %s
                  AND exchange IN {major_exchanges}
                  AND country = 'United States'
                  AND quote_type = 'EQUITY'
                  AND cik NOT IN (SELECT cik FROM us_collection_blacklist WHERE is_blocked = TRUE)
            """
            cur.execute(entry_q, (settings.TARGET_MIN_MARKET_CAP, settings.TARGET_MIN_PRICE))
            logger.info(f"Entry logic applied. Added count: {cur.rowcount}")
