import logging
import os
import gc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional

from p3_usdms.repositories.price_repo import PriceRepo
from p3_usdms.collectors.price_engine import PriceEngine
from p3_usdms.collectors.kis_us_client import KisUSClient
from p1_shared.db.connection import DbConnectionPool
from p3_usdms.utils.silent_logger import SilentLoopContext

logger = logging.getLogger(__name__)

class MarketDataLoader:
    def __init__(self):
        # DB connection pool 및 Repository 초기화
        self.price_repo = PriceRepo()
        self.pool = self.price_repo._pool
        
        self.price_engine = PriceEngine(self.price_repo)
        
        # KIS API 자격증명 획득 (환경 변수 또는 프로필 설정 우선순위 대응)
        app_key = os.environ.get("KIS_APP_KEY") or os.environ.get("KIS_APPKEY", "")
        app_secret = os.environ.get("KIS_APP_SECRET") or os.environ.get("KIS_APPSECRET", "")
        account_no = os.environ.get("KIS_ACCOUNT_NO") or os.environ.get("KIS_CANO", "")
        
        # 모의투자 모드 판단 (KIS_MOCK 또는 TDMS_ENV가 test/dev일 때 대응 가능)
        is_mock = os.environ.get("KIS_MOCK", "false").lower() in ("true", "1", "yes")
        
        self.kis = KisUSClient(
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            is_mock=is_mock
        )

    def collect_batch(self, limit: int = 50):
        """
        수집 대상 종목 중 아직 데이터가 없는 종목들을 배치 수집합니다.
        """
        logger.info(f"Identifying pending targets (Limit: {limit})...")
        
        # 1. 수집 대상인 전체 활성 종목 조회
        query_all = "SELECT cik, latest_ticker FROM us_ticker_master WHERE is_collect_target = true"
        with self.price_repo.get_cursor() as cur:
            cur.execute(query_all)
            all_tickers = cur.fetchall()
            
        if not all_tickers:
            logger.info("No active tickers found in master.")
            return

        # 2. 이미 수집이 완료된 종목 확인
        query_done = "SELECT DISTINCT ticker FROM us_daily_price"
        with self.price_repo.get_cursor() as cur:
            cur.execute(query_done)
            done_rows = cur.fetchall()
            done_tickers = {r['ticker'] for r in done_rows}
            
        # 3. 미수집 종목 필터링
        pending = [t for t in all_tickers if t['latest_ticker'] not in done_tickers]
        
        if not pending:
            logger.info("All targets collected.")
            return

        targets = pending[:limit]
        logger.info(f"Starting batch collection for {len(targets)} tickers...")
        
        success_count = 0
        for t in targets:
            try:
                if self.process_ticker(t['cik'], t['latest_ticker']):
                    success_count += 1
            except Exception as e:
                logger.error(f"[{t['latest_ticker']}] Batch Process Error: {e}")
                
        logger.info(f"Batch Complete. Success: {success_count}/{len(targets)}")

    def collect_daily_updates(self, lookback_days: int = 10, ciks: List[str] = None):
        """
        활성 종목들에 대해 증분 데이터를 갱신합니다.
        """
        logger.info(f"Starting Daily Update (Lookback: {lookback_days}d)...")
        
        if ciks:
            query = "SELECT cik, latest_ticker FROM us_ticker_master WHERE cik = ANY(%s)"
            params = (ciks,)
        else:
            query = "SELECT cik, latest_ticker FROM us_ticker_master WHERE is_collect_target = true"
            params = ()
            
        with self.price_repo.get_cursor() as cur:
            cur.execute(query, params)
            targets = cur.fetchall()
            
        if not targets:
            logger.info("No active targets found.")
            return

        logger.info(f"Updating {len(targets)} tickers...")
        
        # 한국 시차(KST) 및 미국 시장 마감/집계 완료 시간(06:30 KST)을 반영한 동적 수집 최종일 결정
        from zoneinfo import ZoneInfo
        now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
        
        if now_kst.time() < datetime.strptime("06:30", "%H:%M").time():
            # 미국 당일 장중이거나 KIS 일봉 최종 배치 확정 전이므로 안전하게 KST 기준 그저께(미국 현지 2일 전)
            target_date = now_kst.date() - timedelta(days=2)
        else:
            # 미국 장 마감 및 최종 집계 완료 시점이므로 KST 기준 어제(미국 현지 1일 전)
            target_date = now_kst.date() - timedelta(days=1)
            
        start_date = target_date - timedelta(days=lookback_days)
        start_str = start_date.strftime('%Y%m%d')
        end_str = target_date.strftime('%Y%m%d')
        
        logger.info(f"Dynamic US Market Date bounds resolved: {start_str} ~ {end_str} (Based on KST Run Time: {now_kst.strftime('%Y-%m-%d %H:%M:%S')})")
        
        success_count = 0
        failure_count = 0
        import time
        loop_start_time = time.time()
        
        silent_modules = [
            "p3_usdms.collectors.kis_us_client",
            "p3_usdms.collectors.price_engine",
            "urllib3",
            "requests"
        ]
        with SilentLoopContext(silent_modules):
            for i, t in enumerate(targets):
                try:
                    if self.process_ticker(t['cik'], t['latest_ticker'], start_date=start_str, end_date=end_str):
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    logger.debug(f"[{t['latest_ticker']}] Update Error: {e}")
                    failure_count += 1

                if (i + 1) % 50 == 0 or i == len(targets) - 1:
                    elapsed = time.time() - loop_start_time
                    if elapsed == 0:
                        elapsed = 1e-6
                    items_per_sec = (i + 1) / elapsed
                    remaining = len(targets) - (i + 1)
                    eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                    progress_pct = (i + 1) / len(targets) * 100.0
                    
                    logger.info(
                        f"[USDMS 시세 수집] Progress: {progress_pct:.1f}% ({i+1}/{len(targets)}) | "
                        f"Speed: {items_per_sec:.1f} symbols/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str} | "
                        f"Success: {success_count} | Failure: {failure_count} | Current Ticker: {t['latest_ticker']}"
                    )

    def process_ticker(self, cik: str, ticker: str, start_date: str = None, end_date: str = None) -> bool:
        """
        특정 종목의 시세를 KIS로부터 긁어와 DB에 저장하고 수정계수 프로세스를 유도합니다.
        """
        try:
            # 1. KIS로부터 데이터 조회 (수정계수 계산을 위해 add_adjusted=True 필수)
            df = self.kis.get_ohlcv(ticker, start_date=start_date, end_date=end_date, add_adjusted=True)
            
            if df.empty:
                logger.debug(f"[{ticker}] No data returned from KIS API (empty DataFrame).")
                return False
                
            # 2. 가격 데이터 및 수정계수 연쇄 반영
            self._save_data(cik, ticker, df)
            return True
            
        except Exception as e:
            logger.debug(f"[{ticker}] Process Error: {e}")
            return False

    def _save_data(self, cik: str, ticker: str, df: pd.DataFrame):
        """
        수집된 DataFrame을 us_daily_price 테이블에 업서트하고 수정주가 엔진에 전달합니다.
        """
        try:
            # 수정주가 엔진용 백업
            df_for_engine = df.copy()
            
            if df.index.name != 'Date':
                df.index.name = 'Date'
                
            df = df.reset_index()
            
            rename_map = {
                'Date': 'dt',
                'Open': 'open_prc',
                'High': 'high_prc', 
                'Low': 'low_prc', 
                'Close': 'cls_prc', 
                'Volume': 'vol'
            }
            
            if not all(c in df.columns for c in rename_map.keys()):
                logger.debug(f"[{ticker}] Missing columns: {df.columns}")
                return

            df = df.rename(columns=rename_map)
            
            df['cik'] = cik
            df['ticker'] = ticker
            df['amt'] = 0.0  # KIS 해외주식 일봉 차트에서 거래대금을 쉽게 얻기 어려우므로 디폴트값 주입
            
            # 타입 변환 및 정규화
            df['dt'] = pd.to_datetime(df['dt']).dt.date
            df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0).astype(int)
            
            # DB 삽입 대상 열 필터링
            db_cols = ['dt', 'cik', 'ticker', 'open_prc', 'high_prc', 'low_prc', 'cls_prc', 'vol', 'amt']
            price_records = df[db_cols].to_dict('records')
            
            # numpy 타입 객체들을 pure python 타입으로 클렌징
            clean_prices = []
            for r in price_records:
                clean_r = {k: (v.item() if isinstance(v, (np.generic)) else v) for k, v in r.items()}
                clean_prices.append(clean_r)
                
            # DB 삽입
            self.price_repo.insert_daily_price(clean_prices)
            
            # 수정계수 감지/계산 수행
            try:
                self.price_engine.calculate_factors_from_ratio(cik, df_for_engine)
            except Exception as e:
                logger.error(f"[{ticker}] Factor Calculation Error: {e}")

        except Exception as e:
            logger.error(f"[{ticker}] Save Error: {e}")
            raise e
        finally:
            del df
            gc.collect()
