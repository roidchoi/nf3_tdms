import os
import sys
import time
import logging
from datetime import datetime, date

sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

from dotenv import load_dotenv
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("backfill_via_kis")

from p1_shared.api.kis_api_core import KisApiCore
from p1_shared.utils.env_detector import EnvDetector
from collectors.kis_kr_client import KisKrClient
from repositories.base import create_kdms_pool
from repositories.ohlcv_repo import OhlcvRepo

def main():
    logger.info("=== Starting Optimized Backfill via KIS API Range ===")
    
    # 1. API 키 로드 및 KIS 클라이언트 초기화
    detector = EnvDetector()
    profile = detector.load_env_profile()
    env = detector.detect()
    is_dev = (env == "dev")
    
    appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
    appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
    account_no = os.environ.get("KIS_ACCOUNT_NO", "")
    
    api_core = KisApiCore(
        app_key=appkey,
        app_secret=appsecret,
        account_no=account_no,
        is_mock=not is_dev
    )
    kis_client = KisKrClient(api_core=api_core)
    
    pool = create_kdms_pool()
    ohlcv_repo = OhlcvRepo(pool)
    
    # 2. 보정 대상 종목 코드 목록 조회 (중복 제거)
    query_stocks = """
        SELECT DISTINCT o.stk_cd, COALESCE(s.m_vol, 0) as shares
        FROM daily_ohlcv o
        LEFT JOIN stock_info s ON o.stk_cd = s.stk_cd
        WHERE o.dt >= '2026-06-17' AND o.dt <= '2026-06-26' AND (o.amt = 0 OR o.amt IS NULL)
        ORDER BY o.stk_cd ASC;
    """
    
    with pool.get_cursor() as cursor:
        cursor.execute(query_stocks)
        stocks_info = cursor.fetchall()
        
    logger.info(f"Found {len(stocks_info)} stocks to backfill via KIS API.")
    if not stocks_info:
        logger.info("No stocks with missing/zero data. Backfill completed.")
        return
        
    start_date = date(2026, 6, 17)
    end_date = date(2026, 6, 26)
    
    records_to_upsert = []
    success_stocks = 0
    
    for idx, (stk_cd, shares) in enumerate(stocks_info, 1):
        # Rate Limit (초당 20건 제한) 대비 안전을 위해 0.06초 sleep
        time.sleep(0.06)
        
        if idx % 100 == 0 or idx == len(stocks_info):
            logger.info(f"Progress: {idx}/{len(stocks_info)} stocks processed...")
            
        try:
            # 6/17 ~ 6/25 기간 범위 일봉 조회 (단 1회 API 호출)
            ohlcv_list = kis_client.fetch_daily_ohlcv_range(stk_cd, start_date, end_date)
            if ohlcv_list:
                for ohlcv in ohlcv_list:
                    # turn_rt 연산 보정
                    vol = ohlcv["volume"]
                    turn_rt = float((vol / shares) * 100.0) if shares > 0 else 0.0
                    
                    records_to_upsert.append({
                        "stk_cd": stk_cd,
                        "dt": ohlcv["dt"],
                        "open": ohlcv["open"],
                        "high": ohlcv["high"],
                        "low": ohlcv["low"],
                        "close": ohlcv["close"],
                        "volume": vol,
                        "amt": ohlcv["amt"],
                        "turn_rt": turn_rt
                    })
                success_stocks += 1
            else:
                logger.warning(f"No ohlcv data returned for stock {stk_cd}")
        except Exception as err:
            logger.error(f"Error fetching range for {stk_cd}: {err}")
            time.sleep(0.5)
            
        # 300건씩 분할 DB upsert
        if len(records_to_upsert) >= 300:
            ohlcv_repo.upsert_daily_ohlcv(records_to_upsert)
            records_to_upsert = []
            
    # 잔여 데이터 업서트
    if records_to_upsert:
        ohlcv_repo.upsert_daily_ohlcv(records_to_upsert)
        
    logger.info(f"Finished backfilling. Successfully updated {success_stocks}/{len(stocks_info)} stocks.")

if __name__ == "__main__":
    main()
