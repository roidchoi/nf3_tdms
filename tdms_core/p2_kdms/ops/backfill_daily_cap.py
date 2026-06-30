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

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("backfill_daily_cap")

from collectors.pub_data_client import PubDataClient
from repositories.base import create_kdms_pool
from repositories.market_cap_repo import MarketCapRepo

def main():
    logger.info("=== Starting Historical Daily Market Cap Backfill Process ===")
    
    # 1. DB 커넥션 풀 생성
    try:
        pool = create_kdms_pool()
    except Exception as e:
        logger.critical(f"Failed to create DB pool: {e}")
        return

    # 2. 공공데이터 API 및 Repo 초기화
    api_key = os.getenv("PUB_DATA_API_KEY")
    if not api_key:
        logger.critical("PUB_DATA_API_KEY is not defined in env. Aborting.")
        return
        
    pub_client = PubDataClient(api_key=api_key)
    mc_repo = MarketCapRepo(pool)

    # 3. 누락 날짜 조회 (2020-01-01 ~ 2025-11-10)
    start_date = date(2020, 1, 1)
    end_date = date(2025, 11, 10)
    
    try:
        missing_dates = mc_repo.get_market_cap_missing_dates(start_date, end_date)
    except Exception as e:
        logger.critical(f"Failed to query missing dates: {e}")
        return
        
    logger.info(f"Detected {len(missing_dates)} missing trading days in range {start_date} ~ {end_date}.")
    if not missing_dates:
        logger.info("No missing market cap records found. Backfill completed.")
        return

    # 4. 누락 날짜 순회하며 백필 수행
    success_count = 0
    fail_count = 0
    
    for idx, dt in enumerate(missing_dates, 1):
        logger.info(f"[{idx}/{len(missing_dates)}] Backfilling market cap for date: {dt}")
        try:
            records = pub_client.get_market_cap_by_date(dt)
            if not records:
                logger.warning(f"No market cap data returned from API for {dt}. Skipping.")
                fail_count += 1
                time.sleep(0.5)
                continue
                
            # daily_market_cap 레코드 포맷팅
            mc_records = [
                {
                    "dt": dt,
                    "stk_cd": r["stk_cd"],
                    "cls_prc": r["cls_prc"],
                    "mkt_cap": r["mkt_cap"],
                    "vol": r["vol"],
                    "amt": r["amt"],
                    "listed_shares": r["listed_shares"]
                }
                for r in records
            ]
            
            if mc_records:
                mc_repo.upsert_daily_market_cap(mc_records)
                logger.info(f"Successfully backfilled {len(mc_records)} stocks for {dt}.")
                success_count += 1
            else:
                logger.warning(f"No valid records found to insert for {dt}.")
                fail_count += 1
                
        except Exception as e:
            logger.error(f"Error backfilling market cap for {dt}: {e}", exc_info=True)
            fail_count += 1
            
        # Rate limit 방지 지연
        time.sleep(0.5)
        
    logger.info(f"=== Backfill Daily Market Cap Summary: Total: {len(missing_dates)} | Success: {success_count} | Fail: {fail_count} ===")

if __name__ == "__main__":
    main()
