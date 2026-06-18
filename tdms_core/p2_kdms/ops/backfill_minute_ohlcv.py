import os
import sys
import logging
import time
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
logger = logging.getLogger("backfill_minute_ohlcv")

from collectors.kiwoom_client import KiwoomClient
from repositories.base import create_kdms_pool
from tasks.backfill_task import (
    DatabaseManager,
    _sync_trading_calendar_history,
    _detect_missing_and_partial_days,
    _find_earliest_missing_date,
    _execute_backfill_jobs
)

def main():
    logger.info("=== Starting Historical Minute Data Backfill Process ===")
    
    # 1. DB 및 API 클라이언트 초기화
    try:
        pool = create_kdms_pool()
        db = DatabaseManager()
        api = KiwoomClient(mock=False)
    except Exception as e:
        logger.critical(f"Failed to initialize backfill tools: {e}")
        return

    # 분기별 설정 구성
    # 2025-11-20일 이후로 유효 범위 제한
    quarters_config = [
        {
            "quarter": "2025Q4",
            "start_date": date(2025, 11, 20),
            "end_date": date(2025, 12, 31)
        },
        {
            "quarter": "2026Q1",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 3, 31)
        },
        {
            "quarter": "2026Q2",
            "start_date": date(2026, 4, 1),
            "end_date": date(2026, 6, 16) # 어제까지
        }
    ]

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
    job_id = "backfill_minute_data"

    # 2. 분기별 순차 백필 루프
    for idx, config in enumerate(quarters_config, 1):
        q = config["quarter"]
        sd = config["start_date"]
        ed = config["end_date"]
        
        logger.info(f"[{idx}/{len(quarters_config)}] ====== Processing Quarter {q} ({sd} ~ {ed}) ======")
        
        # 1) 해당 분기의 올바른 종목 리스트 획득
        query = "SELECT DISTINCT symbol FROM minute_target_history WHERE quarter = %s"
        with pool.get_cursor() as cursor:
            cursor.execute(query, (q,))
            target_stocks = [row[0] for row in cursor.fetchall()]
            
        logger.info(f"Loaded {len(target_stocks)} correct target stocks for quarter {q}.")
        if not target_stocks:
            logger.warning(f"No target stocks found in history for quarter {q}. Skipping.")
            continue
            
        # 2) 개장일 캘린더 동기화
        try:
            _sync_trading_calendar_history(db, sd)
        except Exception as e:
            logger.error(f"Failed trading calendar sync for quarter {q}: {e}")
            continue
            
        # 3) 누락일 탐지
        try:
            missing_map = _detect_missing_and_partial_days(db, target_stocks, sd, ed)
            if not missing_map:
                logger.info(f"All target stocks' minute data are up-to-date for quarter {q}.")
                continue
        except Exception as e:
            logger.error(f"Failed to detect missing days for quarter {q}: {e}")
            continue
            
        # 4) 가장 이른 공백일 기준 작업 리스트 생성
        try:
            job_list = _find_earliest_missing_date(missing_map)
            if not job_list:
                logger.warning(f"No job list generated for quarter {q}.")
                continue
        except Exception as e:
            logger.error(f"Failed job list generation for quarter {q}: {e}")
            continue
            
        # 5) 분봉 백필 실행
        try:
            logger.info(f"Executing backfill jobs for {len(job_list)} stocks in quarter {q}...")
            _execute_backfill_jobs(api, db, job_list, missing_map, False, job_statuses, job_id)
        except Exception as e:
            logger.error(f"Error executing backfill jobs for quarter {q}: {e}")
            
        logger.info(f"[{idx}/{len(quarters_config)}] ====== Completed Quarter {q} ======")
        
    logger.info("=== Historical Minute Data Backfill Process Completed Successfully ===")

if __name__ == "__main__":
    main()
