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
logger = logging.getLogger("backfill_daily_ohlcv_amt")

from collectors.pub_data_client import PubDataClient
from repositories.base import create_kdms_pool
from repositories.ohlcv_repo import OhlcvRepo

def main():
    logger.info("=== Starting Daily OHLCV Amt & Turn_rt Backfill ===")
    
    # 1. DB 커넥션 풀 생성
    try:
        pool = create_kdms_pool()
    except Exception as e:
        logger.critical(f"Failed to create DB pool: {e}")
        return

    # 2. 공공데이터 API 클라이언트 초기화
    api_key = os.getenv("PUB_DATA_API_KEY")
    if not api_key:
        logger.critical("PUB_DATA_API_KEY is not defined in env. Aborting.")
        return
    pub_client = PubDataClient(api_key=api_key)
    ohlcv_repo = OhlcvRepo(pool)

    # 3. 대상 날짜 조회
    # 2025-11-08 이후 amt가 NULL인 날짜 리스트 추출
    query = """
        SELECT DISTINCT dt 
        FROM daily_ohlcv 
        WHERE dt >= '2025-11-08' AND amt IS NULL 
        ORDER BY dt ASC;
    """
    
    target_dates = []
    with pool.get_cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        target_dates = [row[0] for row in rows]
        
    logger.info(f"Found {len(target_dates)} dates with missing amt/turn_rt from 2025-11-08 onwards.")
    if not target_dates:
        logger.info("No dates with missing amt/turn_rt. Backfill not required.")
        return

    # 4. 날짜별 루프 돌며 백필 수행
    success_count = 0
    fail_count = 0
    
    for idx, dt in enumerate(target_dates, 1):
        logger.info(f"[{idx}/{len(target_dates)}] Processing date: {dt}")
        try:
            records = pub_client.get_market_cap_by_date(dt)
            if not records:
                logger.warning(f"No records returned for date {dt}. Skipping.")
                fail_count += 1
                time.sleep(0.5)
                continue
                
            # daily_ohlcv 업서트 리스트 준비
            ohlcv_records = [
                {
                    "stk_cd": r["stk_cd"],
                    "dt": dt,
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["cls_prc"],
                    "volume": r["vol"],
                    "amt": r["amt"],
                    "turn_rt": float((r["vol"] / r["listed_shares"]) * 100.0) if r.get("listed_shares", 0) > 0 else 0.0
                }
                for r in records if r["open"] > 0
            ]
            
            if ohlcv_records:
                count = ohlcv_repo.upsert_daily_ohlcv(ohlcv_records)
                logger.info(f"Successfully upserted {count} records for {dt}.")
                success_count += 1
            else:
                logger.warning(f"No valid trading records to insert for {dt}.")
                fail_count += 1
                
        except Exception as e:
            logger.error(f"Error processing date {dt}: {e}", exc_info=True)
            fail_count += 1
            
        # Rate limit 방지용 sleep
        time.sleep(0.5)
        
    logger.info(f"=== Backfill Summary: Total Dates: {len(target_dates)} | Success: {success_count} | Fail: {fail_count} ===")

if __name__ == "__main__":
    main()
