import os
import sys
import time
import logging
import pandas as pd
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

# .env 로드
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

# 로그 디렉토리 생성
os.makedirs("/home/roid2/pjt/nf3/01_nf3_tdms/logs", exist_ok=True)

# 로깅 설정 (StreamHandler에 sys.stdout를 명시하여 flush 가능하게 설정)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/roid2/pjt/nf3/01_nf3_tdms/logs/backfill_pipeline.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("backfill_pipeline")

from p1_shared.api.kis_api_core import KisApiCore
from collectors.kis_kr_client import KisKrClient
from collectors.kiwoom_client import KiwoomClient
from collectors.pub_data_client import PubDataClient
from p1_shared.utils.date_utils import get_kr_trading_days
from repositories.base import create_kdms_pool
from repositories.master_repo import MasterRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.factor_repo import FactorRepo
from repositories.market_cap_repo import MarketCapRepo
from tasks.daily_task import DailyTask, calculate_factors
from tasks.backfill_task import run_backfill_minute_data

def get_corporate_action_suspects(pool, dt: date) -> list:
    """
    당일(dt)과 직전 영업일의 데이터를 대조하여, 상장주식수가 변경되었거나 
    종가 격차가 15% 이상 발생해 수정계수 계산이 필요한 종목을 추출합니다.
    """
    query = """
        SELECT t.stk_cd 
        FROM daily_market_cap t
        JOIN daily_market_cap y ON t.stk_cd = y.stk_cd 
        WHERE t.dt = %s 
          AND y.dt = (
              SELECT MAX(dt) 
              FROM daily_market_cap 
              WHERE dt < %s AND stk_cd = t.stk_cd
          )
          AND (
              t.listed_shares <> y.listed_shares 
              OR ABS((t.cls_prc - y.cls_prc)::float / y.cls_prc) >= 0.15
          )
    """
    try:
        with pool.get_cursor() as cursor:
            cursor.execute(query, (dt, dt))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.warning(f"Failed to query corporate action suspects: {e}")
        return []

def run_backfill(start_date: date = None, end_date: date = None):
    logger.info("=== KDMS Database High-Performance Backfill Pipeline Starting ===")
    
    # 1. DB 커넥션 풀 생성
    try:
        pool = create_kdms_pool()
        logger.info("Database connection pool established successfully.")
    except Exception as err:
        logger.critical(f"Failed to create database pool: {err}")
        return

    # 2. KIS API Core & Client 초기화 (선별적 팩터 연산용)
    try:
        kis_core = KisApiCore(
            app_key=os.getenv("KIS_APP_KEY") or os.getenv("KIS_APPkey") or "",
            app_secret=os.getenv("KIS_APP_SECRET") or os.getenv("KIS_APPsecret") or "",
            account_no=os.getenv("KIS_ACCOUNT_NO", ""),
            is_mock=False
        )
        kis_client = KisKrClient(kis_core)
        logger.info("KIS API client initialized successfully.")
    except Exception as err:
        logger.critical(f"Failed to initialize KIS client: {err}")
        return

    # 3. 공공데이터포털 API 클라이언트 초기화
    pub_api_key = os.getenv("PUB_DATA_API_KEY")
    if not pub_api_key:
        logger.critical("PUB_DATA_API_KEY not found in env! Aborting.")
        return
    pub_client = PubDataClient(api_key=pub_api_key)

    # 4. Repositories 및 스키마 초기화
    ohlcv_repo = OhlcvRepo(pool)
    master_repo = MasterRepo(pool)
    factor_repo = FactorRepo(pool)
    market_cap_repo = MarketCapRepo(pool)

    # ==========================================
    # PHASE 1: 일봉 및 팩터/시총 영업일별 벌크 백필
    # ==========================================
    if start_date is None:
        start_date = date(2025, 11, 21)
    if end_date is None:
        end_date = date(2026, 5, 22)  # 오늘날짜
    
    logger.info(f"--- Phase 1: Bulk Daily OHLCV & Market Cap Backfill ({start_date} ~ {end_date}) ---")
    trading_days = get_kr_trading_days(start_date, end_date)
    logger.info(f"Found {len(trading_days)} Korean trading days in this period.")
    
    success_days = 0
    failed_days = 0
    
    for idx, dt in enumerate(trading_days, 1):
        logger.info(f"[{idx}/{len(trading_days)}] Processing trading day via Public Data API: {dt}")
        sys.stdout.flush()
        loop_start = time.time()
        try:
            # 1) 공공데이터포털에서 전 종목 시세 1회 벌크 호출로 긁어오기
            records = pub_client.get_market_cap_by_date(dt)
            if not records:
                logger.warning(f"No records found for trading day {dt} from Public Data Portal. Skipping.")
                failed_days += 1
                continue
            
            # 2) daily_ohlcv 벌크 적재 준비 및 실행
            ohlcv_records = [
                {
                    "stk_cd": r["stk_cd"],
                    "dt": dt,
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["cls_prc"],
                    "volume": r["vol"]
                }
                for r in records if r["open"] > 0
            ]
            if ohlcv_records:
                ohlcv_repo.upsert_daily_ohlcv(ohlcv_records)
            
            # 3) market_cap 벌크 적재 준비 및 실행
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
                market_cap_repo.upsert_daily_market_cap(mc_records)
            
            # 4) 선별적 수정계수 역산 및 적재
            # 2026-03-12 이후의 최근 데이터 기간에 대해서만 실행 (이전 기간은 팩터 기적재 완료)
            if dt > date(2026, 3, 11):
                suspect_stocks = get_corporate_action_suspects(pool, dt)
                if suspect_stocks:
                    logger.info(f"Detected {len(suspect_stocks)} potential corporate action suspect stocks on {dt}.")
                    # 각 의심 종목에 대해 KIS API 호출하여 권리락/배당락 정밀 팩터 계산
                    for stk_cd in suspect_stocks:
                        try:
                            check_start = dt - timedelta(days=45)
                            raw_list = kis_client.fetch_ohlcv_range(stk_cd, check_start, dt, adj_price='1')
                            adj_list = kis_client.fetch_ohlcv_range(stk_cd, check_start, dt, adj_price='0')
                            
                            df_raw = pd.DataFrame(raw_list).rename(columns={"close": "raw_close"})
                            df_adj = pd.DataFrame(adj_list).rename(columns={"close": "adj_close"})
                            
                            if not df_raw.empty and not df_adj.empty:
                                df = pd.merge(df_raw, df_adj, on="dt", how="inner")
                                factors = calculate_factors(df, stk_cd, "KIS")
                                if factors:
                                    factor_repo.upsert_adjustment_factors(factors)
                                    logger.info(f"Upserted {len(factors)} adjustment factors for suspect stock {stk_cd} on {dt}.")
                            # KIS API 트래픽 한도 제어를 위해 0.2초 대기
                            time.sleep(0.2)
                        except Exception as fe:
                            logger.warning(f"Failed factor check for suspect {stk_cd} on {dt}: {fe}")
            
            elapsed = time.time() - loop_start
            logger.info(f"Successfully backfilled {dt} (OHLCV count: {len(ohlcv_records)}, MarketCap count: {len(mc_records)}) in {elapsed:.2f}s.")
            success_days += 1
            
        except Exception as e:
            failed_days += 1
            logger.error(f"Failed to process trading day {dt} during bulk phase: {e}", exc_info=True)
        
        # 공공데이터 API Rate limit 및 트래픽 부하 방지용 지연
        time.sleep(0.5)

    logger.info(f"Phase 1 Summary: Total {len(trading_days)} trading days | Success: {success_days} | Failure: {failed_days}")

    # ==========================================
    # PHASE 2: daily_ohlcv_adjusted 전체기간 벌크 계산 및 갱신 (1년 단위 분할 실행)
    # ==========================================
    logger.info("--- Phase 2: Adjusted Prices Physical Table (daily_ohlcv_adjusted) Bulk Refresh ---")
    year_start = 1985
    year_end = date.today().year
    
    for y in range(year_start, year_end + 1):
        sd = date(y, 1, 1)
        ed = date(y, 12, 31) if y < year_end else date.today()
        
        if y == 1985:
            sd = date(1985, 1, 4)
            
        logger.info(f"Refreshing adjusted OHLCV for year {y} ({sd} ~ {ed})...")
        loop_start = time.time()
        try:
            count = ohlcv_repo.refresh_adjusted_ohlcv_batch(sd, ed)
            elapsed = time.time() - loop_start
            logger.info(f"Year {y}: {count} records refreshed/upserted in {elapsed:.2f}s.")
        except Exception as e:
            logger.error(f"Failed to refresh adjusted OHLCV for year {y}: {e}", exc_info=True)

    logger.info("Phase 2 Complete: daily_ohlcv_adjusted fully populated.")

    # ==========================================
    # PHASE 3: 분봉 데이터 (minute_ohlcv) 공백 백필
    # ==========================================
    logger.info("--- Phase 3: Minute OHLCV Gap Backfill (Target Selector dynamic integration) ---")
    
    # 3. Kiwoom Client 초기화 (분봉 수집용)
    try:
        kiwoom_client = KiwoomClient(
            app_key=os.getenv("KIWOOM_APP_KEY"),
            app_secret=os.getenv("KIWOOM_APP_SECRET")
        )
        logger.info("Kiwoom client initialized.")
    except Exception as err:
        logger.critical(f"Failed to initialize Kiwoom client: {err}")
        return

    job_statuses = {
        "backfill_minute_data": {
            "is_running": True,
            "phase": "0/5",
            "phase_name": "초기화",
            "progress": 0,
            "start_time": date.today().isoformat(),
            "last_log": "백필 작업 초기화 중..."
        }
    }
    
    try:
        # start_date와 end_date가 외부에서 지정된 경우 이를 사용하고,
        # 지정되지 않은 경우 기본값으로 지난 8일간 ~ 어제 날짜 지정
        start_dt = start_date if start_date is not None else (date.today() - timedelta(days=8))
        end_dt = end_date if end_date is not None else (date.today() - timedelta(days=1))
        
        logger.info(f"Executing run_backfill_minute_data for range {start_dt} ~ {end_dt}...")
        run_backfill_minute_data(job_statuses, test_mode=False, start_date=start_dt, end_date=end_dt)
        logger.info(f"Minute backfill status: {job_statuses['backfill_minute_data']}")
    except Exception as e:
        logger.error(f"Failed to run minute data backfill task: {e}", exc_info=True)

    logger.info("=== KDMS Database Backfill Pipeline Completed ===")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="KDMS Database Backfill Pipeline")
    parser.add_argument("--start-date", type=str, help="Backfill start date (YYYY-MM-DD)", default=None)
    parser.add_argument("--end-date", type=str, help="Backfill end date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()
    
    sd = None
    ed = None
    if args.start_date:
        try:
            sd = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid start-date format. Use YYYY-MM-DD.")
            sys.exit(1)
    if args.end_date:
        try:
            ed = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid end-date format. Use YYYY-MM-DD.")
            sys.exit(1)
            
    run_backfill(sd, ed)
