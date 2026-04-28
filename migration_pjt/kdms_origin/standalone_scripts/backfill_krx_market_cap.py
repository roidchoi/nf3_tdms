#!/usr/bin/env python3
"""
KRX 시가총액 데이터 스마트 백필 스크립트

사용법:
  python standalone_scripts/backfill_krx_market_cap.py --start-date 20180102
  python standalone_scripts/backfill_krx_market_cap.py --start-date 20180102 --end-date 20201231

기능:
  - DB의 MAX(dt) 이후부터 자동 수집 (스마트 구간 감지)
  - --end-date 미지정 시 어제까지 수집
  - 휴장일 자동 스킵
  - Rate limiting (1초 대기)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import logging
import time
import pandas as pd
from datetime import datetime, timedelta, date
from collectors.krx_loader import KRXLoader
from collectors.db_manager import DatabaseManager
from rich.logging import RichHandler

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger(__name__)


def calculate_date_range(db: DatabaseManager, start_date_arg: str, end_date_arg: str) -> tuple:
    """
    스마트 날짜 범위 계산

    - start_date: CLI 인자 또는 DB MAX(dt) + 1일
    - end_date: CLI 인자 또는 어제
    """
    date_range = db.get_market_cap_date_range()
    max_db_date = date_range.get('max_date')

    # Start Date 결정
    if max_db_date:
        # DB에 데이터가 있으면 MAX(dt) + 1일부터
        smart_start = max_db_date + timedelta(days=1)
        logger.info(f"📊 DB 최대 날짜: {max_db_date} → 자동 시작일: {smart_start}")

        if start_date_arg:
            user_start = datetime.strptime(start_date_arg, '%Y%m%d').date()
            if user_start < smart_start:
                logger.warning(
                    f"⚠️ 사용자 지정 시작일({user_start})이 DB 이후 날짜({smart_start})보다 이릅니다. "
                    f"DB 이후 날짜를 사용합니다."
                )
                start_date = smart_start
            else:
                start_date = user_start
        else:
            start_date = smart_start
    else:
        # DB가 비어있으면 CLI 인자 또는 기본값
        if start_date_arg:
            start_date = datetime.strptime(start_date_arg, '%Y%m%d').date()
        else:
            start_date = date(2018, 1, 2)  # 기본값
            logger.info(f"📊 DB 빈 테이블 → 기본 시작일: {start_date}")

    # End Date 결정
    if end_date_arg:
        end_date = datetime.strptime(end_date_arg, '%Y%m%d').date()
    else:
        end_date = date.today() - timedelta(days=1)  # 어제
        logger.info(f"📊 종료일 미지정 → 어제: {end_date}")

    return start_date, end_date


def main():
    parser = argparse.ArgumentParser(description='KRX 시가총액 데이터 스마트 백필')
    parser.add_argument('--start-date', default=None,
                        help='시작 날짜 (YYYYMMDD, 미지정 시 DB MAX(dt)+1일)')
    parser.add_argument('--end-date', default=None,
                        help='종료 날짜 (YYYYMMDD, 미지정 시 어제)')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 KRX 시가총액 데이터 스마트 백필 시작")
    logger.info("=" * 60)

    # 초기화
    db = DatabaseManager()
    krx = KRXLoader(logger)

    # 스마트 날짜 범위 계산
    start_date, end_date = calculate_date_range(db, args.start_date, args.end_date)

    # 평일만 생성 (주말 제외)
    business_days = pd.bdate_range(start=start_date, end=end_date)
    total = len(business_days)

    if total == 0:
        logger.warning("⚠️ 수집할 날짜가 없습니다. (이미 최신 상태이거나 잘못된 날짜 범위)")
        return

    logger.info(f"📅 수집 기간: {start_date} ~ {end_date} (평일 {total}일)")
    logger.info("-" * 60)

    # 수집 루프
    success = 0
    skipped = 0
    failed = 0

    for idx, day in enumerate(business_days, start=1):
        date_str = day.strftime('%Y%m%d')

        try:
            data = krx.get_market_cap_data(date_str)

            if not data:
                skipped += 1
                logger.warning(f"[{idx}/{total}] {date_str}: 데이터 없음 (휴장일)")
            else:
                count = db.upsert_daily_market_cap(data)
                success += 1
                logger.info(f"[{idx}/{total}] {date_str}: {count}건 저장 완료 ✅")

            # Rate limiting (IP 차단 방지)
            time.sleep(1.0)

        except Exception as e:
            failed += 1
            logger.error(f"[{idx}/{total}] {date_str}: 에러 발생 - {e}")
            continue

    logger.info("=" * 60)
    logger.info(f"✅ 백필 완료: 성공 {success}일, 스킵 {skipped}일, 실패 {failed}일")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
