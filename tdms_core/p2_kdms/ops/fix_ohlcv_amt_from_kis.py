import os
import sys
import time
import logging
from datetime import date
from dotenv import load_dotenv

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

# .env 로드
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("fix_ohlcv_amt_from_kis")

from tasks.financial_task import KisREST
from repositories.base import create_kdms_pool

def main():
    logger.info("=== Starting June 16 missing amt/turn_rt recovery using KIS API ===")
    
    try:
        pool = create_kdms_pool()
        kis_api = KisREST(mock=False, log_level=1)
    except Exception as e:
        logger.critical(f"Initialization failed: {e}")
        return

    if kis_api.client is None:
        logger.critical("KIS API client is not configured correctly.")
        return

    # 1. 2026-06-16에 amt가 NULL인 상장주식 종목 목록 조회
    query = """
        SELECT o.stk_cd 
        FROM daily_ohlcv o 
        JOIN stock_info s ON o.stk_cd = s.stk_cd 
        WHERE o.dt = '2026-06-16' AND o.amt IS NULL AND s.cap > 0;
    """
    
    target_stocks = []
    with pool.get_cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        target_stocks = [row[0] for row in rows]
        
    logger.info(f"Found {len(target_stocks)} stocks with missing amt/turn_rt for 2026-06-16.")
    if not target_stocks:
        logger.info("No missing stocks. Recovery not required.")
        return

    # 2. 개별 종목 수집 및 업데이트
    update_query = """
        UPDATE daily_ohlcv 
        SET amt = %s, turn_rt = %s 
        WHERE stk_cd = %s AND dt = '2026-06-16';
    """
    
    success = 0
    fail = 0
    total = len(target_stocks)
    
    for idx, stk_cd in enumerate(target_stocks, 1):
        if idx % 100 == 0 or idx == total:
            logger.info(f"Processing progress: {idx}/{total}")

        # KIS API Rate Limit 준수 (초당 20건 = 0.05초 sleep)
        time.sleep(0.06)

        try:
            ohlcv = kis_api.client.fetch_daily_ohlcv(stk_cd, date(2026, 6, 16))
            if ohlcv:
                amt_val = ohlcv.get("amt")
                turn_rt_val = ohlcv.get("turn_rt")
                
                # 거래량이 0인 경우 명시적 0 처리
                if ohlcv.get("volume") == 0:
                    amt_val = 0
                    turn_rt_val = 0.0
                    
                with pool.get_cursor() as cursor:
                    cursor.execute(update_query, (amt_val, turn_rt_val, stk_cd))
                success += 1
            else:
                # KIS API에서도 시세 정보가 안 오면 거래량 0인 종목일 수 있으므로 0으로 자동 복구
                with pool.get_cursor() as cursor:
                    cursor.execute(update_query, (0, 0.0, stk_cd))
                success += 1
        except Exception as e:
            logger.warning(f"Failed to recover {stk_cd}: {e}")
            fail += 1

    logger.info(f"=== Recovery Summary: Total: {total} | Success: {success} | Fail: {fail} ===")

if __name__ == "__main__":
    main()
