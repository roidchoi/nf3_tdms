# backfill_minute_data.py
"""
분봉 데이터 백필(Backfill) 스크립트 (v6 - '일부 누락일' 탐지 및 API 최적화)

- Step 1: 과거 거래일 동기화 (daily_ohlcv(Prod) -> trading_calendar(Test/Prod))
- Step 2: 최신/휴장일 동기화 (KIS API -> trading_calendar(Prod))
- Step 3: '완전/일부 누락일' 탐지 (Threshold: 360)
- Step 4: '가장 이른 공백일' 작업 목록 생성
- Step 5: 종목당 1회 API 호출 -> 필터링 -> 1회 UPSERT

Usage:
    # (운영) 2024년 1월 1일부터 어제까지 전체 공백 수집
    python backfill_minute_data.py --start-date 2025-07-01

    # (테스트) 2025년 10월 한 달간 테스트 종목(005930, 035720) 대상
    python backfill_minute_data.py --start-date 2025-07-01 --end-date 2025-11-10 --test
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from tqdm import tqdm
from psycopg2.extras import execute_values

# KDMS 프로젝트 모듈 임포트
from collectors.kiwoom_rest import KiwoomREST
from collectors.kis_rest import KisREST
from collectors.db_manager import DatabaseManager
from collectors import utils
from test_utils import TestEnvironment

# 로거 설정
logger = utils.setup_logger('backfill_minute_data')

# [v6] 일부 누락일 탐지 기준 (360분 = 6시간)
PARTIAL_DAY_THRESHOLD = 360


def _sync_trading_calendar_history(db: DatabaseManager, start_date: date, test_mode: bool, test_env: Optional[TestEnvironment]):
    """Step 1: 과거 거래일 동기화 (daily_ohlcv(Prod) -> trading_calendar(Test/Prod))"""
    logger.info("--- [1/5] 과거 거래일 동기화 시작 ---")
    
    read_table = 'daily_ohlcv'
    if test_mode:
        write_table = test_env.get_test_table_name('trading_calendar')
    else:
        write_table = 'trading_calendar'
        
    logger.info(f"Read Source: {read_table} (운영)")
    logger.info(f"Write Target: {write_table} ({'테스트' if test_mode else '운영'})")

    conn = None
    try:
        query = f"""
            SELECT DISTINCT dt 
            FROM {read_table} 
            WHERE dt >= %s
            ORDER BY dt;
        """
        results = db._execute_query(query, (start_date,), fetch='all')
        
        if not results:
            logger.warning(f"{read_table}에 기준일 이후 데이터가 없어 과거 캘린더를 동기화할 수 없습니다.")
            return

        calendar_data = [(row['dt'], 'Y') for row in results]

        upsert_query = f"""
            INSERT INTO {write_table} (dt, opnd_yn)
            VALUES %s
            ON CONFLICT (dt) DO UPDATE SET
                opnd_yn = EXCLUDED.opnd_yn,
                updated_at = NOW();
        """
        
        conn = db._get_connection()
        with conn.cursor() as cur:
            execute_values(cur, upsert_query, calendar_data)
        conn.commit()
        logger.info(f"✅ 과거 개장일 {len(calendar_data)}건 캘린더 동기화 완료 ({write_table}).")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"과거 거래일 동기화 실패: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _sync_trading_calendar_recent(kis_api: KisREST, db: DatabaseManager, test_mode: bool):
    """Step 2: 최신/휴장일 동기화 (KIS API -> trading_calendar(Prod))"""
    logger.info("--- [2/5] 최신/휴장일 동기화 시작 (Source: KIS API) ---")
    
    if test_mode:
        logger.warning("테스트 모드에서는 KIS 캘린더 API 호출을 건너뜁니다.")
        return
        
    try:
        success = utils.update_trading_calendar(kis_api, db)
        if success:
            logger.info("✅ 최신/휴장일 캘린더 동기화 완료 (운영 테이블).")
        else:
            logger.warning("⚠️ 최신/휴장일 캘린더 동기화 실패.")
    except Exception as e:
        logger.error(f"최신/휴장일 동기화 중 오류 발생: {e}", exc_info=True)
        logger.warning("캘린더 API 동기화에 실패했으나, 기존 캘린더 데이터로 백필을 계속합니다.")


def _detect_missing_and_partial_days(db: DatabaseManager, 
                                     target_stocks: List[str], 
                                     start_date: date, 
                                     end_date: date, 
                                     test_mode: bool, 
                                     test_env: Optional[TestEnvironment]) -> Dict[str, Set[date]]:
    """Step 3: [v6] '완전/일부 누락일' 탐지"""
    logger.info("--- [3/5] '완전/일부 누락일' 탐지 시작 ---")
    logger.info(f"'일부 누락' 기준: {PARTIAL_DAY_THRESHOLD}건 미만")

    if test_mode:
        calendar_read_table = test_env.get_test_table_name('trading_calendar')
    else:
        calendar_read_table = 'trading_calendar'
        
    minute_read_table = 'minute_ohlcv'
    
    logger.info(f"Calendar Source: {calendar_read_table} ({'테스트' if test_mode else '운영'})")
    logger.info(f"Minute Data Source: {minute_read_table} (운영)")

    # 1. 기준 기간 내 모든 '거래일' 목록 조회
    query_calendar = f"""
        SELECT dt FROM {calendar_read_table}
        WHERE opnd_yn = 'Y' AND dt BETWEEN %s AND %s;
    """
    results = db._execute_query(query_calendar, (start_date, end_date), fetch='all')
    all_trading_days: Set[date] = {row['dt'] for row in results}
    
    if not all_trading_days:
        logger.warning(f"{calendar_read_table}에 탐지 기간 내 거래일 정보가 없습니다.")
        return {}

    logger.info(f"기준 기간 ({start_date} ~ {end_date}) 내 총 거래일: {len(all_trading_days)}일")

    # 2. [v6] 기수집일 '건수' 맵(Map) 생성
    query_collected = f"""
        SELECT stk_cd, DATE(dt_tm) as dt, COUNT(*) as record_count
        FROM {minute_read_table}
        WHERE stk_cd = ANY(%s) AND DATE(dt_tm) BETWEEN %s AND %s
        GROUP BY 1, 2;
    """
    results = db._execute_query(query_collected, (target_stocks, start_date, end_date), fetch='all')
    
    collected_day_counts: Dict[str, Dict[date, int]] = defaultdict(dict)
    for row in results:
        collected_day_counts[row['stk_cd']][row['dt']] = row['record_count']

    # 3. [v6] '완전/일부 누락' 공백일 맵(Map) 생성
    missing_map: Dict[str, Set[date]] = defaultdict(set)
    total_missing_days = 0
    total_partial_days = 0

    for stk_cd in target_stocks:
        stock_counts = collected_day_counts[stk_cd]
        for day in all_trading_days:
            if day not in stock_counts:
                # '완전 누락'
                missing_map[stk_cd].add(day)
                total_missing_days += 1
            elif stock_counts[day] < PARTIAL_DAY_THRESHOLD:
                # '일부 누락'
                missing_map[stk_cd].add(day)
                total_partial_days += 1
            # else: (정상 수집)
            #   pass
    
    logger.info(f"✅ 공백일 탐지 완료: 총 {len(missing_map)}개 종목")
    logger.info(f"  - 완전 누락일: {total_missing_days}건")
    logger.info(f"  - 일부 누락일: {total_partial_days}건 (기준: {PARTIAL_DAY_THRESHOLD}건 미만)")
    return missing_map


def _find_earliest_missing_date(missing_map: Dict[str, Set[date]]) -> List[Tuple[str, date]]:
    """Step 4: [v6] '가장 이른 공백일' 작업 목록 생성"""
    logger.info("--- [4/5] '가장 이른 공백일' 작업 목록 생성 ---")
    
    job_list: List[Tuple[str, date]] = [] # (stk_cd, earliest_missing_date)

    for stk_cd, missing_days_set in missing_map.items():
        if not missing_days_set:
            continue
        
        earliest_missing = min(missing_days_set)
        job_list.append((stk_cd, earliest_missing))

    logger.info(f"✅ '가장 이른 공백일' 기준 작업 {len(job_list)}개 생성 완료.")
    return job_list


def _parse_cntr_tm(cntr_tm: str) -> date:
    """분봉 'cntr_tm' 문자열에서 날짜 객체를 빠르게 파싱"""
    # utils.transform_data보다 빠른 단순 날짜 파싱
    try:
        return datetime.strptime(cntr_tm[:8], '%Y%m%d').date()
    except Exception:
        return None


def _execute_backfill_jobs(api: KiwoomREST, db: DatabaseManager, 
                           job_list: List[Tuple[str, date]],
                           missing_map: Dict[str, Set[date]], # [v6] 필터링을 위해 추가
                           test_mode: bool,
                           test_env: Optional[TestEnvironment]):
    """Step 5: [v6] 종목당 1회 API 호출 -> 필터링 -> 1회 UPSERT"""
    logger.info("--- [5/5] 분봉 데이터 백필 작업 시작 (API 1회/종목) ---")
    
    if test_mode:
        minute_write_table = test_env.get_test_table_name('minute_ohlcv')
    else:
        minute_write_table = 'minute_ohlcv'
        
    logger.info(f"Write Target: {minute_write_table} ({'테스트' if test_mode else '운영'})")
        
    total_jobs = len(job_list)
    for i, (stk_cd, earliest_missing_date) in enumerate(job_list):
        logger.info(f"--- 작업 ({i+1}/{total_jobs}): [{stk_cd}] / 기준일: {earliest_missing_date} ---")
        
        # 1. [v6] 종목당 1회 API 호출
        try:
            start_date_str = earliest_missing_date.strftime('%Y%m%d')
            logger.info(f"[{stk_cd}] Kiwoom API 호출 (start_date={start_date_str})...")
            
            # API는 Now ~ start_date_str까지의 모든 데이터를 반환
            all_collected_data = api.get_minute_chart(stk_cd, start_date=start_date_str, max_requests=300)
            
            if not all_collected_data:
                logger.warning(f"[{stk_cd}] API가 {start_date_str} 기준 데이터를 반환하지 않았습니다.")
                continue
            
            logger.info(f"[{stk_cd}] API 응답 수신: 총 {len(all_collected_data)}건")

        except Exception as e:
            logger.error(f"[{stk_cd}] API 호출 실패: {e}", exc_info=True)
            continue
            
        # 2. [v6] Python에서 공백일/일부누락일 데이터만 필터링
        stk_missing_set = missing_map.get(stk_cd)
        if not stk_missing_set:
            logger.warning(f"[{stk_cd}] 공백 맵(missing_map)에 정보가 없어 필터링을 건너뜁니다.")
            continue
            
        batch_to_process = []
        for item in all_collected_data:
            # 'cntr_tm' (e.g., "20251031...")에서 날짜 파싱
            item_date = _parse_cntr_tm(item.get('cntr_tm'))
            
            if item_date and item_date in stk_missing_set:
                item['stk_cd'] = stk_cd # stk_cd 주입
                batch_to_process.append(item)
        
        if not batch_to_process:
            logger.info(f"[{stk_cd}] API 응답 {len(all_collected_data)}건 중 실제 공백일 데이터가 없습니다.")
            continue
            
        logger.info(f"[{stk_cd}] {len(all_collected_data)}건 중 {len(batch_to_process)}건 필터링 완료 (공백/일부 누락분).")

        # 3. [v6] 필터링된 데이터 변환 및 일괄 UPSERT
        try:
            transformed_batch = utils.transform_data(batch_to_process, 'kiwoom', 'minute_ohlcv')
            
            # upsert_ohlcv_data는 ON CONFLICT DO UPDATE를 사용
            # '일부 누락일'은 UPDATE(보강)되고, '완전 누락일'은 INSERT됨.
            db.upsert_ohlcv_data(minute_write_table, transformed_batch)
            
            logger.info(f"✅ [{stk_cd}] {earliest_missing_date} 기준 {len(transformed_batch)}건 일괄 저장 완료 ({minute_write_table}).")
        
        except Exception as e:
            logger.error(f"[{stk_cd}] DB 일괄 저장 실패: {e}", exc_info=True)


def get_target_stocks(db: DatabaseManager, 
                      quarter: Optional[str], 
                      market: Optional[str], 
                      stocks: Optional[List[str]], 
                      test_mode: bool) -> List[str]:
    """수집 대상 종목을 필터링하여 반환"""
    
    if stocks:
        logger.info(f"지정된 종목 {stocks}를 대상으로 합니다.")
        if test_mode:
            logger.info("테스트 모드: --stocks로 지정된 종목만 사용합니다.")
        return stocks

    if test_mode:
        known_test_stocks = {'005930', '035720'}
        logger.info(f"테스트 모드: 대상을 알려진 테스트 종목({known_test_stocks})으로 한정합니다.")
        
        read_table = 'minute_target_history'
        query = f"SELECT DISTINCT symbol FROM {read_table} WHERE symbol = ANY(%s)"
        results = db._execute_query(query, (list(known_test_stocks),), fetch='all')
        target_list = [row['symbol'] for row in results]
        
        if not target_list:
            logger.warning(f"테스트 종목 {known_test_stocks}가 {read_table}에 없습니다.")
            return []
        logger.info(f"운영 대상 중 테스트 종목 {target_list} 확인. 이 종목들로 백필 테스트.")
        return target_list

    read_table = 'minute_target_history'
    
    if not quarter:
        today = date.today()
        quarter = f"{today.year}Q{(today.month - 1) // 3 + 1}"
        logger.info(f"분기가 지정되지 않아 현재 분기({quarter})를 대상으로 합니다.")
    
    logger.info(f"(운영) 대상 분기: {quarter}, 대상 시장: {market or '전체'}")
    
    query = f"SELECT DISTINCT symbol FROM {read_table} WHERE quarter = %s"
    params = [quarter]
    
    if market:
        query += " AND market = %s"
        params.append(market)
        
    results = db._execute_query(query, tuple(params), fetch='all')
    target_list = [row['symbol'] for row in results]
    
    if not target_list:
        logger.critical(f"{quarter} {market or ''} 대상 종목이 {read_table}에 없습니다.")
        logger.critical("initial_build.py --mode build_targets 를 먼저 실행해야 할 수 있습니다.")
        sys.exit(1)
        
    logger.info(f"총 {len(target_list)}개 종목을 대상으로 백필을 시작합니다.")
    return target_list


def main():
    parser = argparse.ArgumentParser(
        description="KDMS 분봉 데이터 백필(Backfill) 스크립트 (v6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # (운영) 2024-01-01부터 어제까지 전체 종목 공백 채우기
  python backfill_minute_data.py --start-date 2024-01-01
  
  # (테스트) 2025-10-01~10-31 기간, 테스트 종목(005930, 035720) 대상
  python backfill_minute_data.py --start-date 2025-10-01 --end-date 2025-10-31 --test
"""
    )
    
    parser.add_argument('--start-date', type=str, required=True,
                       help='백필 시작일 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                       help='백필 종료일 (YYYY-MM-DD). 기본값: 어제(yesterday)')
    parser.add_argument('--quarter', type=str,
                       help='대상 분기 (e.g., 2025Q4). --stocks 또는 --test 사용 시 무시될 수 있음.')
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ'],
                       help='대상 시장. --stocks 또는 --test 사용 시 무시될 수 있음.')
    parser.add_argument('--stocks', nargs='+',
                       help='특정 종목 코드 목록. 이 옵션 사용 시 quarter/market 무시됨.')
    parser.add_argument('--test', action='store_true',
                       help='테스트 모드 활성화 (Read-Prod, Write-Test)')

    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    except ValueError:
        logger.critical("start-date 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식을 사용하세요.")
        sys.exit(1)

    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        except ValueError:
            logger.critical("end-date 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식을 사용하세요.")
            sys.exit(1)
    else:
        end_date = date.today() - timedelta(days=1)

    if start_date > end_date:
        logger.critical("시작일이 종료일보다 늦을 수 없습니다.")
        sys.exit(1)

    # --- 객체 초기화 ---
    logger.info("🚀 Kiwoom API 초기화...")
    api = KiwoomREST(mock=False, log_level=3)
    
    logger.info("🚀 KIS API 초기화...")
    try:
        kis_api = KisREST(mock=False, log_level=1)
    except Exception as e:
        logger.warning(f"KIS API 초기화 실패: {e}")
        logger.warning("최신 캘린더 동기화(Step 2)를 건너뜁니다.")
        kis_api = None
    
    logger.info("🚀 DatabaseManager 초기화...")
    db = DatabaseManager()
    
    test_env = TestEnvironment(db, logger) if args.test else None
    
    if args.test:
        logger.info("=" * 60)
        logger.info("🔔 테스트 모드 활성화 (Read-Prod, Write-Test) 🔔")
        logger.info("저장용 테스트 테이블을 준비합니다...")
        logger.info("=" * 60)
        try:
            # (가정) test_utils.py가 db_manager.py의 PRODUCTION_TABLES에
            # 'trading_calendar'를 추가했거나, 'include_calendar'를 지원함.
            test_env.setup_test_tables(include_calendar=True)
            logger.info("테스트 테이블(trading_calendar_test, minute_ohlcv_test 등) 준비 완료.")
        except TypeError:
            logger.warning("! 경고: 'test_utils.py'가 'include_calendar' 옵션을 지원하지 않습니다.")
            logger.warning("! 'db_manager.py'의 'PRODUCTION_TABLES' 리스트에 'trading_calendar'를 추가해야 합니다.")
            test_env.setup_test_tables()
            logger.warning("! 'trading_calendar_test' 테이블이 생성되지 않았다면 Step 1이 실패합니다.")
        except Exception as e:
            logger.critical(f"테스트 테이블 준비 실패: {e}", exc_info=True)
            sys.exit(1)
            
    try:
        # Step 0: 대상 종목 선정
        target_stocks = get_target_stocks(
            db, args.quarter, args.market, args.stocks, args.test
        )
        if not target_stocks:
            logger.warning("백필 대상 종목이 없습니다. 작업을 종료합니다.")
            sys.exit(0)

        # Step 1: 과거 거래일 동기화
        _sync_trading_calendar_history(db, start_date, args.test, test_env)

        # Step 2: 최신/휴장일 동기화
        if kis_api:
             _sync_trading_calendar_recent(kis_api, db, args.test)
        else:
            logger.info("--- [2/5] KIS API가 초기화되지 않아 최신 캘린더 동기화를 건너뜁니다. ---")

        # Step 3: [v6] '완전/일부 누락일' 탐지
        missing_map = _detect_missing_and_partial_days(
            db, target_stocks, start_date, end_date, args.test, test_env
        )
        
        if not missing_map:
            logger.info("🎉 모든 대상 종목의 분봉 데이터가 최신 상태입니다. (누락 없음)")
            logger.info("백필 작업을 종료합니다.")
            sys.exit(0)

        # Step 4: [v6] '가장 이른 공백일' 작업 목록 생성
        job_list = _find_earliest_missing_date(missing_map)
        
        if not job_list:
            logger.warning("공백일은 탐지되었으나, 작업(Job) 생성에 실패했습니다.")
            sys.exit(1)
            
        # Step 5: [v6] 배치 수집 및 일괄 저장
        _execute_backfill_jobs(api, db, job_list, missing_map, args.test, test_env)
        
        logger.info("=" * 60)
        logger.info("✅ 모든 분봉 데이터 백필 작업 완료")
        logger.info("=" * 60)
        
        if args.test:
             logger.info(f"테스트 데이터가 '{test_env.get_test_table_name('minute_ohlcv')}' 테이블에 저장되었습니다.")
             logger.info("데이터 확인 후, 'python test_utils.py'를 실행하여 테스트 테이블을 정리하세요.")

    except Exception as e:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()