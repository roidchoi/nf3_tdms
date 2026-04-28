"""
standalone_scripts/build_adjusted_ohlcv.py

[Phase 3-B] daily_ohlcv_adjusted 테이블 초기 구축용 일회성 스크립트.
rebuild_factors_from_kis.py 실행(KIS 팩터 적재) 완료 후 실행해야 합니다.

처리 흐름:
  - refresh_adjusted_ohlcv_batch() SQL CTE를 연도별 청크로 반복 실행하여
    daily_ohlcv의 전 기간 데이터를 수정주가로 변환 후 daily_ohlcv_adjusted에 저장합니다.
  - pandas를 사용하지 않고 DB 레벨에서 완전 처리합니다.

실행 방법 (00_kdms/ 폴더, 가상환경 활성화 상태):
    python standalone_scripts/build_adjusted_ohlcv.py [--start_year 2015] [--chunk_months 3]

주의:
  - 반드시 rebuild_factors_from_kis.py 실행 후 실행할 것 (팩터 데이터 필요)
  - 기존 daily_ohlcv_adjusted 데이터는 ON CONFLICT DO UPDATE로 덮어씌워짐
"""

import sys
import os
import time
import argparse
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.db_manager import DatabaseManager

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
SEPARATOR  = '=' * 65

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger('build_adjusted_ohlcv')


def main():
    parser = argparse.ArgumentParser(description='daily_ohlcv_adjusted 초기 구축 스크립트')
    parser.add_argument('--start_year', type=int, default=2015,
                        help='구축 시작 연도 (기본값: 2015). DB의 daily_ohlcv 데이터 시작일과 맞출 것.')
    parser.add_argument('--chunk_months', type=int, default=3,
                        help='1회 배치 처리 기간 (개월, 기본값: 3). 큰 값일수록 메모리 사용량 증가.')
    args = parser.parse_args()

    logger.info(SEPARATOR)
    logger.info(f" daily_ohlcv_adjusted 초기 구축 시작")
    logger.info(f"  시작 연도   : {args.start_year}")
    logger.info(f"  청크 (개월) : {args.chunk_months}")
    logger.info(SEPARATOR)

    try:
        db = DatabaseManager()
    except Exception as e:
        logger.critical(f"DB 초기화 실패: {e}")
        sys.exit(1)

    chunk_start  = date(args.start_year, 1, 1)
    today        = date.today()
    total_upsert = 0
    chunk_idx    = 0
    start_ts     = time.time()

    while chunk_start <= today:
        chunk_end = min(
            chunk_start + relativedelta(months=args.chunk_months) - timedelta(days=1),
            today
        )
        chunk_idx += 1

        logger.info(f"[청크 {chunk_idx:03d}] {chunk_start} ~ {chunk_end} 처리 중...")

        try:
            n = db.refresh_adjusted_ohlcv_batch(chunk_start, chunk_end)
            total_upsert += n
            logger.info(f"  → {n}건 완료 (누적: {total_upsert:,}건)")
        except Exception as e:
            logger.error(f"  → 청크 처리 실패: {e}")
            # 오류가 발생해도 다음 청크로 계속 진행
            logger.warning("  → 해당 청크 건너뛰고 계속 진행합니다.")

        chunk_start = chunk_end + timedelta(days=1)

    # --- 마일스톤 ---
    try:
        db.set_milestone(
            'DATA:ADJUSTED_OHLCV:INITIAL_BUILD',
            date.today(),
            f"daily_ohlcv_adjusted 초기 구축 완료. "
            f"총 {total_upsert:,}건, {chunk_idx}개 청크."
        )
        logger.info("✅ 마일스톤 기록 완료: DATA:ADJUSTED_OHLCV:INITIAL_BUILD")
    except Exception as e:
        logger.warning(f"마일스톤 기록 실패: {e}")

    elapsed = time.time() - start_ts
    logger.info(SEPARATOR)
    logger.info(f" 작업 완료")
    logger.info(f"  총 UPSERT : {total_upsert:,}건")
    logger.info(f"  청크 수   : {chunk_idx}개")
    logger.info(f"  소요 시간 : {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")
    logger.info(SEPARATOR)


if __name__ == '__main__':
    main()
