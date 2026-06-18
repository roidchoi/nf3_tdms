import os
import sys
import logging
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
logger = logging.getLogger("rebuild_minute_targets")

from repositories.base import create_kdms_pool
from repositories.ohlcv_repo import OhlcvRepo
from collectors.target_selector import TargetSelector

def main():
    logger.info("=== Starting Minute Target Rebuilding Pipeline ===")
    
    # 1. DB 커넥션 풀 생성
    try:
        pool = create_kdms_pool()
    except Exception as e:
        logger.critical(f"Failed to create DB pool: {e}")
        return

    ohlcv_repo = OhlcvRepo(pool)
    selector = TargetSelector(pool)

    target_quarters = ["2025Q4", "2026Q1", "2026Q2"]

    # 2. 기존 대상 목록 삭제
    logger.info(f"Deleting existing targets for quarters: {target_quarters}")
    delete_query = """
        DELETE FROM minute_target_history 
        WHERE quarter = ANY(%s);
    """
    with pool.get_cursor() as cursor:
        cursor.execute(delete_query, (target_quarters,))
        logger.info(f"Deleted {cursor.rowcount} stale target records.")

    # 3. 쿼터별 대상 재선정 및 적재
    for quarter in target_quarters:
        logger.info(f"--- Rebuilding targets for quarter: {quarter} ---")
        
        # KOSPI 200개 선출
        logger.info(f"Selecting KOSPI top 200 stocks for {quarter}...")
        kospi_targets = selector.select_top_n_stocks(quarter=quarter, top_n=200, market="KOSPI")
        if kospi_targets:
            ohlcv_repo.upsert_minute_target_history(kospi_targets)
            logger.info(f"Upserted {len(kospi_targets)} KOSPI targets for {quarter}.")
        else:
            logger.warning(f"No KOSPI targets selected for {quarter}.")

        # KOSDAQ 400개 선출
        logger.info(f"Selecting KOSDAQ top 400 stocks for {quarter}...")
        kosdaq_targets = selector.select_top_n_stocks(quarter=quarter, top_n=400, market="KOSDAQ")
        if kosdaq_targets:
            ohlcv_repo.upsert_minute_target_history(kosdaq_targets)
            logger.info(f"Upserted {len(kosdaq_targets)} KOSDAQ targets for {quarter}.")
        else:
            logger.warning(f"No KOSDAQ targets selected for {quarter}.")

    # 4. 검증 결과 출력
    logger.info("--- Verification of updated minute_target_history ---")
    verify_query = """
        SELECT quarter, market, COUNT(*), MIN(rank), MAX(rank)
        FROM minute_target_history
        WHERE quarter = ANY(%s)
        GROUP BY quarter, market
        ORDER BY quarter, market;
    """
    with pool.get_cursor() as cursor:
        cursor.execute(verify_query, (target_quarters,))
        for row in cursor.fetchall():
            logger.info(f"Quarter: {row[0]} | Market: {row[1]:<7} | Count: {row[2]} | Rank: {row[3]} ~ {row[4]}")

    logger.info("=== Rebuilding Minute Targets Pipeline Completed Successfully ===")

if __name__ == "__main__":
    main()
