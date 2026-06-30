import os
import sys
import time
import json
import logging
import argparse
from datetime import date, datetime, timedelta
import pandas as pd
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
logger = logging.getLogger("rebuild_factors")

from tasks.financial_task import KisREST
from repositories.base import create_kdms_pool
from repositories.master_repo import MasterRepo
from repositories.factor_repo import FactorRepo
from collectors.factor_calculator import calculate_factors

PROGRESS_FILE = "/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/ops/rebuild_factors_progress.json"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_progress(progress_dict):
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress_dict, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")

def main():
    parser = argparse.ArgumentParser(description="Rebuild KIS Price Adjustment Factors")
    parser.add_argument("--target-only", action="store_true", help="Only rebuild for core 600 target stocks")
    parser.add_argument("--reset", action="store_true", help="Reset progress and start from scratch")
    args = parser.parse_args()

    logger.info("=== Starting Historical Price Adjustment Factors Rebuilding Pipeline (KIS) ===")

    # 1. 초기화
    try:
        pool = create_kdms_pool()
        master_repo = MasterRepo(pool)
        factor_repo = FactorRepo(pool)
        kis_api = KisREST(mock=False, log_level=1)
    except Exception as e:
        logger.critical(f"Initialization failed: {e}")
        return

    if kis_api.client is None:
        logger.critical("KIS API client is not configured correctly. Check env credentials.")
        return

    # 2. 대상 종목 결정
    if args.target_only:
        logger.info("Target Mode: Rebuilding only for core 600 stocks from minute_target_history...")
        query = "SELECT DISTINCT symbol FROM minute_target_history;"
        with pool.get_cursor() as cursor:
            cursor.execute(query)
            stocks_to_process = [row[0] for row in cursor.fetchall()]
    else:
        logger.info("Full Mode: Rebuilding for all active stocks in stock_info...")
        stocks = master_repo.get_all_active_stocks()
        stocks_to_process = [s["stk_cd"] for s in stocks if s.get("stk_cd")]

    logger.info(f"Total stocks to process: {len(stocks_to_process)}")

    # 3. 진행 상황(Progress) 로드
    progress = {} if args.reset else load_progress()
    
    # 4. 종목별 루프
    total_cnt = len(stocks_to_process)
    for idx, stk_cd in enumerate(stocks_to_process, 1):
        if stk_cd in progress and progress[stk_cd].get("status") == "done":
            logger.info(f"[{idx}/{total_cnt}] Stock {stk_cd} already processed. Skipping.")
            continue

        logger.info(f"[{idx}/{total_cnt}] Processing stock: {stk_cd}")
        progress[stk_cd] = {"status": "running", "started_at": datetime.now().isoformat()}
        save_progress(progress)

        try:
            # 1) DB에서 이 종목의 원본 종가(daily_ohlcv) 데이터가 존재하는 범위 획득
            raw_query = """
                SELECT dt, cls_prc as raw_close
                FROM daily_ohlcv
                WHERE stk_cd = %s
                ORDER BY dt ASC;
            """
            with pool.get_cursor() as cursor:
                cursor.execute(raw_query, (stk_cd,))
                raw_rows = cursor.fetchall()
            
            if not raw_rows:
                logger.warning(f"[{stk_cd}] No raw daily ohlcv records found in DB. Skipping.")
                progress[stk_cd] = {"status": "done", "factors_count": 0, "msg": "No raw data"}
                save_progress(progress)
                continue

            df_raw = pd.DataFrame(raw_rows, columns=["dt", "raw_close"])
            df_raw["dt"] = pd.to_datetime(df_raw["dt"]).dt.date
            start_date = df_raw["dt"].min()
            end_date = df_raw["dt"].max()

            logger.info(f"[{stk_cd}] Raw data range: {start_date} ~ {end_date} (Total {len(df_raw)} days)")

            # 2) KIS API를 이용해 수정주가(adj_price='0') 반영 일봉을 100일 단위 루프로 과거 수집
            # KIS API fetch_ohlcv_range 이용
            adj_close_list = []
            curr_end = end_date
            
            while curr_end >= start_date:
                curr_start = max(start_date, curr_end - timedelta(days=99))
                logger.info(f"[{stk_cd}] Querying KIS adjusted ohlcv: {curr_start} ~ {curr_end}")
                
                try:
                    records = kis_api.client.fetch_ohlcv_range(stk_cd, curr_start, curr_end, adj_price="0")
                    if records:
                        adj_close_list.extend(records)
                except Exception as api_err:
                    logger.error(f"[{stk_cd}] KIS API Error for range {curr_start} ~ {curr_end}: {api_err}")
                
                # Rate limit 방지
                time.sleep(0.25)
                curr_end = curr_start - timedelta(days=1)

            if not adj_close_list:
                logger.warning(f"[{stk_cd}] Failed to fetch adjusted price history from KIS API.")
                progress[stk_cd] = {"status": "failed", "msg": "API failure"}
                save_progress(progress)
                continue

            df_adj = pd.DataFrame(adj_close_list)
            df_adj["dt"] = pd.to_datetime(df_adj["dt"]).dt.date
            df_adj = df_adj.drop_duplicates(subset=["dt"])

            # 3) 원본 주가와 수정 주가 병합
            df_merged = pd.merge(df_adj, df_raw, on="dt", how="inner")
            df_merged = df_merged.rename(columns={"close": "adj_close"})
            df_merged = df_merged.sort_values(by="dt").reset_index(drop=True)

            if df_merged.empty or len(df_merged) < 2:
                logger.warning(f"[{stk_cd}] Insufficient overlap data to calculate factors.")
                progress[stk_cd] = {"status": "done", "factors_count": 0, "msg": "Insufficient data"}
                save_progress(progress)
                continue

            # 4) 수정 팩터 역산 수행
            factors = calculate_factors(df_merged, stk_cd, "KIS")
            
            # 5) DB에 적재
            if factors:
                factor_repo.upsert_adjustment_factors(factors)
                logger.info(f"✅ [{stk_cd}] Upserted {len(factors)} price adjustment factors (KIS).")
                progress[stk_cd] = {"status": "done", "factors_count": len(factors)}
            else:
                logger.info(f"[{stk_cd}] No adjustment events detected in history.")
                progress[stk_cd] = {"status": "done", "factors_count": 0}

            save_progress(progress)

        except Exception as e:
            logger.error(f"[{stk_cd}] Fatal error rebuilding factors: {e}", exc_info=True)
            progress[stk_cd] = {"status": "error", "error": str(e)}
            save_progress(progress)

    logger.info("=== Historical Price Adjustment Factors Rebuilding Pipeline Completed Successfully ===")

if __name__ == "__main__":
    main()
