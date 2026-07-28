#!/usr/bin/env python3
"""
KDMS 연도별 전종목 투자자 매매동향(일별 수급) 대량 백필 CLI 스크립트

사용법:
    # 2026년 백필 실행 (이미 데이터가 있는 종목도 UPSERT 덮어쓰기)
    conda run -n tdms_p2_env python scripts/backfill_investor_trade_by_year.py --start-year 2026 --end-year 2026

    # 이미 지정 연도 데이터가 적재된 종목은 API 호출 Skip 옵션 적용
    conda run -n tdms_p2_env python scripts/backfill_investor_trade_by_year.py --start-year 2026 --end-year 2026 --skip-existing
"""

import os
import sys
import time
import argparse
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Any

# 프로젝트 경로 설정
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TDMS_CORE_PATH = os.path.join(PROJECT_ROOT, "tdms_core")
P2_KDMS_PATH = os.path.join(TDMS_CORE_PATH, "p2_kdms")

if TDMS_CORE_PATH not in sys.path:
    sys.path.insert(0, TDMS_CORE_PATH)
if P2_KDMS_PATH not in sys.path:
    sys.path.insert(0, P2_KDMS_PATH)

from collectors.kis_kr_client import KisKrClient
from repositories.base import create_kdms_pool
from repositories.investor_trade_repo import InvestorTradeRepo
from p1_shared.api.kis_api_core import KisApiCore
from p1_shared.utils.env_detector import EnvDetector
from unittest.mock import MagicMock

# 로깅 설정 (sys.stdout 명시 및 unbuffered 출력)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("backfill_investor_trade_by_year")


def get_active_symbols(pool) -> List[str]:
    """stock_info 테이블에서 상장 활성 종목 코드 리스트 조회"""
    query = """
        SELECT stk_cd 
        FROM stock_info 
        WHERE status = 'listed' 
          AND (delist_dt IS NULL OR delist_dt > CURRENT_DATE)
        ORDER BY stk_cd;
    """
    with pool.get_cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        return [r[0] for r in rows]


def get_existing_symbols_for_period(pool, start_date: date, end_date: date) -> Set[str]:
    """해당 기간 동안 이미 daily_investor_trade에 데이터가 1건 이상 있는 종목 세트 조회"""
    query = """
        SELECT DISTINCT stk_cd 
        FROM daily_investor_trade 
        WHERE dt BETWEEN %s AND %s;
    """
    with pool.get_cursor() as cur:
        cur.execute(query, (start_date, end_date))
        rows = cur.fetchall()
        return {r[0] for r in rows}


def get_kis_client(test_mode: bool = False) -> KisKrClient:
    """KIS API 클라이언트 초기화"""
    if test_mode:
        return MagicMock()
    
    detector = EnvDetector()
    profile = detector.load_env_profile()
    env = detector.detect()
    is_dev = (env == "dev")
    appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
    appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
    
    api_core = KisApiCore(
        app_key=appkey,
        app_secret=appsecret,
        account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
        is_mock=not is_dev
    )
    return KisKrClient(api_core=api_core)


def run_backfill(
    start_year: int, 
    end_year: int, 
    target_symbol: str = None, 
    skip_existing: bool = False,
    test_mode: bool = False
):
    """연도별 전종목 수급 백필 실행 메인 함수"""
    logger.info(f"🚀 [수급 연도별 백필] 작업 시작 (대상 연도: {start_year}년 ~ {end_year}년, Skip Existing: {skip_existing}, Test Mode: {test_mode})")
    sys.stdout.flush()
    
    pool = create_kdms_pool()
    trade_repo = InvestorTradeRepo(pool)
    kis_client = get_kis_client(test_mode=test_mode)
    
    try:
        if target_symbol:
            symbols = [target_symbol]
            logger.info(f"🎯 단일 지정 종목 백필: {target_symbol}")
        else:
            symbols = get_active_symbols(pool)
            logger.info(f"📊 상장 활성 종목 총 {len(symbols)}개 조회 완료")
            
        if not symbols:
            logger.error("❌ 수집 대상 종목이 없습니다.")
            return

        today = date.today()
        now_hour = datetime.now().hour
        if now_hour < 16:
            max_target_date = today - timedelta(days=1)
        else:
            max_target_date = today

        total_symbols_cnt = len(symbols)
        overall_start_time = time.time()

        for yr in range(start_year, end_year + 1):
            yr_start_date = date(yr, 1, 1)
            yr_end_date = min(date(yr, 12, 31), max_target_date)
            
            if yr_start_date > max_target_date:
                logger.info(f"⏭️ {yr}년은 미래 날짜이므로 건너뜁니다.")
                continue

            existing_set = set()
            if skip_existing and not test_mode:
                existing_set = get_existing_symbols_for_period(pool, yr_start_date, yr_end_date)
                logger.info(f"🔍 [{yr}년] 이미 데이터가 존재하는 종목 {len(existing_set)}개 감지 (Skip 적용)")

            logger.info(f"\n==================================================")
            logger.info(f"📅 [{yr}년도 수급 백fill 시작] 수집 기간: {yr_start_date} ~ {yr_end_date} (대상 종목: {total_symbols_cnt}개)")
            logger.info(f"==================================================")
            sys.stdout.flush()

            yr_start_time = time.time()
            collected_records_cnt = 0
            success_symbols_cnt = 0
            skipped_symbols_cnt = 0
            failed_symbols_cnt = 0

            for idx, stk_cd in enumerate(symbols):
                if skip_existing and stk_cd in existing_set:
                    skipped_symbols_cnt += 1
                    continue

                if (idx + 1) % 50 == 0 or idx == total_symbols_cnt - 1:
                    elapsed = time.time() - yr_start_time
                    if elapsed == 0:
                        elapsed = 1e-6
                    processed_count = (idx + 1) - skipped_symbols_cnt
                    speed = processed_count / elapsed if elapsed > 0 else 0
                    remaining = total_symbols_cnt - (idx + 1)
                    eta_seconds = remaining / speed if speed > 0 else 0
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                    progress_pct = ((idx + 1) / total_symbols_cnt) * 100.0

                    logger.info(
                        f"[{yr}년 수급 백필] Progress: {progress_pct:.1f}% ({idx+1}/{total_symbols_cnt}) | "
                        f"Speed: {speed:.1f} it/s | Elapsed: {int(elapsed)}s | ETA: {eta_str} | "
                        f"Current: {stk_cd}"
                    )
                    sys.stdout.flush()

                try:
                    if test_mode:
                        mock_recs = [{
                            "dt": yr_start_date, "stk_cd": stk_cd, "stck_clpr": 50000,
                            "prsn_ntby_qty": 0, "frgn_ntby_qty": 0, "orgn_ntby_qty": 0
                        }]
                        trade_repo.upsert_daily_investor_trade(mock_recs)
                        collected_records_cnt += len(mock_recs)
                        success_symbols_cnt += 1
                    else:
                        recs = kis_client.fetch_investor_trade_daily(stk_cd, start_date=yr_start_date, end_date=yr_end_date)
                        if recs:
                            saved_cnt = trade_repo.upsert_daily_investor_trade(recs)
                            collected_records_cnt += saved_cnt
                            success_symbols_cnt += 1
                        else:
                            success_symbols_cnt += 1
                except Exception as e:
                    failed_symbols_cnt += 1
                    logger.error(f"❌ [{stk_cd}] {yr}년 수급 수집 중 오류 발생: {e}")

            yr_elapsed = time.time() - yr_start_time
            logger.info(
                f"✅ [{yr}년도 수급 백필 완료] 소요시간: {int(yr_elapsed)}초 | "
                f"성공: {success_symbols_cnt}종목 | 스킵: {skipped_symbols_cnt}종목 | 실패: {failed_symbols_cnt}종목 | 적재: {collected_records_cnt}건"
            )
            sys.stdout.flush()

        overall_elapsed = time.time() - overall_start_time
        logger.info(f"\n🎉 [전체 백필 종료] 총 소요시간: {int(overall_elapsed)}초 ({overall_elapsed/60:.1f}분)")
        sys.stdout.flush()

    finally:
        # DB 커넥션 풀 자원 해제
        if hasattr(pool, "closeall"):
            try:
                pool.closeall()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="KDMS 연도별 전종목 수급(투자자 매매동향) 대량 백필 스크립트")
    parser.add_argument("--start-year", type=int, required=True, help="백필 시작 연도 (예: 2020)")
    parser.add_argument("--end-year", type=int, required=True, help="백필 종료 연도 (예: 2026)")
    parser.add_argument("--stk-cd", type=str, default=None, help="특정 종목코드 필터 (옵션)")
    parser.add_argument("--skip-existing", action="store_true", help="이미 해당 연도 데이터가 존재하면 API 호출 Skip")
    parser.add_argument("--test-mode", action="store_true", help="테스트 모드 여부")

    args = parser.parse_args()

    if args.start_year > args.end_year:
        logger.error(f"시작 연도({args.start_year})가 종료 연도({args.end_year})보다 클 수 없습니다.")
        sys.exit(1)

    run_backfill(
        start_year=args.start_year,
        end_year=args.end_year,
        target_symbol=args.stk_cd,
        skip_existing=args.skip_existing,
        test_mode=args.test_mode
    )
    sys.stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    main()
