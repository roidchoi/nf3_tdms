import os
import sys
import time
import argparse
import subprocess
import logging
from datetime import date, datetime, timedelta

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] run_monthly_backfill - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/roid2/pjt/nf3/01_nf3_tdms/logs/run_monthly_backfill.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("run_monthly_backfill")

def get_last_day_of_month(any_date: date) -> date:
    """해당 월의 마지막 날짜를 구합니다."""
    next_month = any_date.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)

def split_range_into_months(start_date: date, end_date: date) -> list:
    """시작일과 종료일을 월단위 파티션 범위 리스트로 슬라이싱합니다."""
    partitions = []
    current_start = start_date
    
    while current_start <= end_date:
        last_day = get_last_day_of_month(current_start)
        current_end = min(last_day, end_date)
        partitions.append((current_start, current_end))
        # 다음 달 1일로 갱신
        current_start = last_day + timedelta(days=1)
        
    return partitions

def run_monthly_backfill(start_date: date, end_date: date, dry_run: bool = False):
    logger.info("=== KDMS Monthly Partitioned Minute Backfill Wrapper Starting ===")
    logger.info(f"Total target period: {start_date} ~ {end_date} (Dry Run: {dry_run})")
    
    # 1. 월단위 슬라이싱 생성
    partitions = split_range_into_months(start_date, end_date)
    logger.info(f"Sliced period into {len(partitions)} partition(s):")
    for idx, (sd, ed) in enumerate(partitions, 1):
         logger.info(f"  Partition #{idx}: {sd} ~ {ed}")
         
    if dry_run:
        logger.info("Dry-run check finished. No process will be spawned. Exiting.")
        return

    # 2. 순차 파이프라인 가동
    cwd_path = "/home/roid2/pjt/nf3/01_nf3_tdms"
    python_cmd = ["conda", "run", "-n", "tdms_p2_env", "python", "tdms_core/p2_kdms/ops/backfill_pipeline.py"]
    
    for idx, (sd, ed) in enumerate(partitions, 1):
        logger.info(f"\n>>> [Partition {idx}/{len(partitions)}] Executing backfill for range: {sd} ~ {ed} <<<")
        cmd = python_cmd + ["--start-date", sd.strftime("%Y-%m-%d"), "--end-date", ed.strftime("%Y-%m-%d")]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        sys.stdout.flush()
        
        start_time = time.time()
        
        # subprocess 실행 및 로그 실시간 스트리밍
        try:
            # stdout/stderr를 실시간 출력하기 위해 Popen 활용
            process = subprocess.Popen(
                cmd,
                cwd=cwd_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 실시간 로그 수집 및 출력
            for line in process.stdout:
                print(line, end="")
                sys.stdout.flush()
                
            process.wait()
            rc = process.returncode
            
            elapsed = time.time() - start_time
            
            if rc == 0:
                logger.info(f"Partition {idx} Completed Successfully. Elapsed time: {elapsed:.1f}s.")
            else:
                logger.error(f"Partition {idx} FAILED with return code: {rc}. Aborting entire sequence.")
                sys.exit(rc)
                
        except Exception as err:
            logger.critical(f"Exception raised while running partition {idx}: {err}", exc_info=True)
            sys.exit(1)
            
        # 마지막 파티션이 아닐 경우 Cooldown 대기
        if idx < len(partitions):
            cooldown_sec = 10
            logger.info(f"Waiting {cooldown_sec} seconds for API session cooldown before next partition...")
            time.sleep(cooldown_sec)
            
    logger.info("=== All Monthly Backfill Partitions Finished Successfully! ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KDMS Monthly Minute Backfill Wrapper")
    parser.add_argument("--start-date", type=str, help="Overall start date (YYYY-MM-DD)", default="2025-11-21")
    parser.add_argument("--end-date", type=str, help="Overall end date (YYYY-MM-DD)", default="2026-05-13")
    parser.add_argument("--dry-run", action="store_true", help="Only show partitioning schedules without execution")
    args = parser.parse_args()
    
    try:
        sd = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD.")
        sys.exit(1)
        
    if sd > ed:
        logger.error("start-date must be prior or equal to end-date.")
        sys.exit(1)
        
    run_monthly_backfill(sd, ed, args.dry_run)
