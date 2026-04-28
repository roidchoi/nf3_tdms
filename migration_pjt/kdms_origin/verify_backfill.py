# verify_backfill.py
"""
'backfill_minute_data.py --test' 작업 결과 검증 스크립트 (v2 - 스팟 체크 기능 추가)

두 가지 모드로 작동:
1. --validate: 지정 기간 전체의 데이터 정합성(수량)을 검증.
2. --spot-check: 특정 날짜 경계의 데이터 연속성(품질)을 육안 검증.

Usage (Validation):
    # backfill을 실행했던 것과 동일한 파라미터로 실행
    python verify_backfill.py --validate --start-date 2025-07-01 --end-date 2025-10-31
    
Usage (Spot Check):
    # 2025-10-01 (신규 수집일)의 데이터 연속성을 검증 (이전 거래일과 비교)
    python verify_backfill.py --spot-check 2025-10-01 --stocks 005930 035720
"""

import argparse
import sys
from datetime import date, datetime
from typing import List, Dict, Set, Optional
from collections import defaultdict

# [!] 스팟 체크용 rich 임포트
from rich.console import Console
from rich.table import Table

# KDMS 프로젝트 모듈 임포트
from collectors.db_manager import DatabaseManager
from collectors import utils
from test_utils import TestEnvironment

# 로거 설정
logger = utils.setup_logger('verify_backfill')

# [v6] backfill 스크립트와 동일한 기준 사용
PARTIAL_DAY_THRESHOLD = 360


def _get_target_stocks(db: DatabaseManager, stocks: Optional[List[str]]) -> List[str]:
    """검증 대상 종목 반환 (테스트 모드 로직만 사용)"""
    
    if stocks:
        logger.info(f"지정된 종목 {stocks}를 대상으로 검증합니다.")
        return stocks

    known_test_stocks = {'005930', '035720'}
    logger.info(f"기본 테스트 종목({known_test_stocks})으로 검증합니다.")
    
    read_table = 'minute_target_history'
    query = f"SELECT DISTINCT symbol FROM {read_table} WHERE symbol = ANY(%s)"
    results = db._execute_query(query, (list(known_test_stocks),), fetch='all')
    target_list = [row['symbol'] for row in results]
    
    if not target_list:
        logger.warning(f"테스트 종목 {known_test_stocks}가 {read_table}에 없습니다.")
    return target_list


# --- [1] Validation Mode Functions ---

def _get_expected_gaps(db: DatabaseManager, 
                        test_env: TestEnvironment,
                        target_stocks: List[str], 
                        start_date: date, 
                        end_date: date) -> Dict[str, Set[date]]:
    """[Problem] 'backfill'이 해결했어야 할 '완전/일부 누락일' 목록을 탐지합니다."""
    logger.info("--- [Validation] '예상 공백' 탐지 중... (Prod: minute_ohlcv) ---")
    
    calendar_read_table = test_env.get_test_table_name('trading_calendar')
    minute_read_table = 'minute_ohlcv' 

    query_calendar = f"""
        SELECT dt FROM {calendar_read_table}
        WHERE opnd_yn = 'Y' AND dt BETWEEN %s AND %s;
    """
    results = db._execute_query(query_calendar, (start_date, end_date), fetch='all')
    all_trading_days: Set[date] = {row['dt'] for row in results}
    
    if not all_trading_days:
        logger.warning(f"{calendar_read_table}에 탐지 기간 내 거래일 정보가 없습니다.")
        return {}

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

    missing_map: Dict[str, Set[date]] = defaultdict(set)
    for stk_cd in target_stocks:
        stock_counts = collected_day_counts[stk_cd]
        for day in all_trading_days:
            if day not in stock_counts:
                missing_map[stk_cd].add(day) # '완전 누락'
            elif stock_counts[day] < PARTIAL_DAY_THRESHOLD:
                missing_map[stk_cd].add(day) # '일부 누락'
    
    count = sum(len(s) for s in missing_map.values())
    logger.info(f"✅ '예상 공백' {count}일(건) 탐지 완료.")
    return missing_map


def _get_actual_results(db: DatabaseManager, 
                        test_env: TestEnvironment,
                        target_stocks: List[str], 
                        start_date: date, 
                        end_date: date) -> Dict[str, Dict[date, int]]:
    """[Solution] 'backfill' 작업의 '실제 결과'를 'minute_ohlcv_test'에서 조회합니다."""
    logger.info("--- [Validation] '실제 결과' 조회 중... (Test: minute_ohlcv_test) ---")
    
    minute_write_table = test_env.get_test_table_name('minute_ohlcv')

    query_actual = f"""
        SELECT stk_cd, DATE(dt_tm) as dt, COUNT(*) as record_count
        FROM {minute_write_table}
        WHERE stk_cd = ANY(%s) AND DATE(dt_tm) BETWEEN %s AND %s
        GROUP BY 1, 2;
    """
    results = db._execute_query(query_actual, (target_stocks, start_date, end_date), fetch='all')
    
    actual_day_counts: Dict[str, Dict[date, int]] = defaultdict(dict)
    for row in results:
        actual_day_counts[row['stk_cd']][row['dt']] = row['record_count']
        
    count = sum(len(d) for d in actual_day_counts.values())
    logger.info(f"✅ '실제 결과' {count}일(건) 조회 완료.")
    return actual_day_counts


def _run_validation(db: DatabaseManager, 
                    test_env: TestEnvironment, 
                    target_stocks: List[str], 
                    start_date: date, 
                    end_date: date):
    """(모드 1) 전체 정합성 검증 실행"""
    
    # Step 1: '예상 공백' (Problem) 맵 생성
    expected_gaps_map = _get_expected_gaps(
        db, test_env, target_stocks, start_date, end_date
    )

    # Step 2: '실제 결과' (Solution) 맵 생성
    actual_results_map = _get_actual_results(
        db, test_env, target_stocks, start_date, end_date
    )
    
    logger.info("--- [Validation] '예상'과 '실제' 비교 검증 시작 ---")
    failures = []

    # Step 3.1: (검증 1) '예상 공백'이 제대로 채워졌는지 확인
    for stk_cd in target_stocks:
        expected_days = expected_gaps_map.get(stk_cd, set())
        actual_days_data = actual_results_map.get(stk_cd, {})
        
        if not expected_days and not actual_days_data.get(start_date):
            logger.info(f"[{stk_cd}] 탐지된 공백 없음, 실제 저장된 데이터 없음 (정상).")
            continue

        for day in expected_days:
            if day not in actual_days_data:
                failures.append(f"❌ [실패] [{stk_cd}] {day}: '공백/일부'였으나 테스트 DB에 전혀 저장되지 않음.")
            elif actual_days_data[day] < PARTIAL_DAY_THRESHOLD:
                failures.append(f"❌ [실패] [{stk_cd}] {day}: 저장되었으나 여전히 '일부 누락' 상태임 (_test count: {actual_days_data[day]}).")
    
    # Step 3.2: (검증 2) '정상'이었던 날짜가 오염(저장)되지 않았는지 확인
    for stk_cd in target_stocks:
        expected_days = expected_gaps_map.get(stk_cd, set())
        actual_days_data = actual_results_map.get(stk_cd, {})

        for day in actual_days_data.keys():
            if day not in expected_days:
                failures.append(f"❌ [실패] [{stk_cd}] {day}: '정상'이었던 날짜가 테스트 DB에 저장됨 (데이터 오염).")

    # --- 최종 결과 ---
    logger.info("=" * 60)
    if not failures:
        logger.info("✅ [검증 성공] Backfill 작업이 정확하게 수행되었습니다.")
    else:
        logger.error(f"❌ [검증 실패] {len(failures)}건의 불일치 항목이 발견되었습니다:")
        for f in failures:
            logger.error(f)
        sys.exit(1)


# --- [2] Spot Check Mode Functions ---

def _find_previous_trading_day(db: DatabaseManager, test_env: TestEnvironment, check_date: date) -> Optional[date]:
    """check_date 기준 이전 거래일을 'trading_calendar_test'에서 찾습니다."""
    
    calendar_table = test_env.get_test_table_name('trading_calendar')
    query = f"""
        SELECT dt FROM {calendar_table}
        WHERE dt < %s AND opnd_yn = 'Y'
        ORDER BY dt DESC
        LIMIT 1;
    """
    result = db._execute_query(query, (check_date,), fetch='one')
    
    return result['dt'] if result else None


def _run_spot_check(db: DatabaseManager, 
                    test_env: TestEnvironment, 
                    target_stocks: List[str], 
                    check_date: date):
    """(모드 2) 데이터 연속성 스팟 체크 실행"""
    
    logger.info(f"--- [스팟 체크] {check_date}의 데이터 연속성 검증 ---")
    
    prev_date = _find_previous_trading_day(db, test_env, check_date)
    if not prev_date:
        logger.error(f"'{check_date}'의 이전 거래일을 'trading_calendar_test'에서 찾을 수 없습니다.")
        logger.error("'backfill_minute_data.py --test'를 먼저 실행하여 캘린더를 채워야 합니다.")
        sys.exit(1)
        
    logger.info(f"비교 대상: {prev_date} (Prod) vs {check_date} (Test)")

    prod_table = 'minute_ohlcv'
    test_table = test_env.get_test_table_name('minute_ohlcv')
    console = Console()

    for stk_cd in target_stocks:
        logger.info(f"\n--- [{stk_cd}] 스팟 체크 ---")
        
        # 1. 이전 거래일 (운영 DB) - 마지막 5개
        query_prev = f"""
            SELECT dt_tm, cls_prc, vol 
            FROM {prod_table} 
            WHERE stk_cd = %s AND DATE(dt_tm) = %s 
            ORDER BY dt_tm DESC 
            LIMIT 5
        """
        prev_data = db._execute_query(query_prev, (stk_cd, prev_date), fetch='all')

        # 2. 신규 수집일 (테스트 DB) - 처음 5개
        query_new = f"""
            SELECT dt_tm, cls_prc, vol 
            FROM {test_table} 
            WHERE stk_cd = %s AND DATE(dt_tm) = %s 
            ORDER BY dt_tm ASC 
            LIMIT 5
        """
        new_data = db._execute_query(query_new, (stk_cd, check_date), fetch='all')

        if not prev_data and not new_data:
            logger.warning(f"[{stk_cd}] {prev_date}(Prod)와 {check_date}(Test) 모두 데이터가 없습니다.")
            continue

        # 3. Rich Table로 출력
        table = Table(title=f"[{stk_cd}] 데이터 연속성 (Spot Check)", show_header=True, header_style="bold magenta")
        table.add_column("Source Table", style="dim", width=20)
        table.add_column("Timestamp", style="cyan", width=25)
        table.add_column("Close Price", justify="right", style="green")
        table.add_column("Volume", justify="right", style="blue")

        # 이전 데이터 (시간순 정렬을 위해 뒤집음)
        for row in reversed(prev_data):
            table.add_row(f"{prod_table}", f"{row['dt_tm']}", f"{row['cls_prc']:,}", f"{row['vol']:,}")
        
        # 구분선
        table.add_row("--- (Data Boundary) ---", "---", "---", "---")

        # 신규 데이터
        for row in new_data:
            # 신규 수집된 데이터임을 강조
            table.add_row(f"[bold]{test_table}[/bold]", f"{row['dt_tm']}", f"{row['cls_prc']:,}", f"{row['vol']:,}")
        
        console.print(table)
        logger.info(f"[{stk_cd}] 위 테이블에서 {prev_date} 15:30 (장 마감)과 {check_date} 09:00 (장 시작)의 가격 연속성을 확인하세요.")


def main():
    parser = argparse.ArgumentParser(
        description="KDMS 백필(Backfill) 작업 검증 스크립트 (v6)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # [v2] 두 모드(validate, spot-check) 중 하나를 필수로 선택
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--validate', action='store_true',
                            help="전체 기간 정합성(수량) 검증 (기본 모드)")
    mode_group.add_argument('--spot-check', type=str, dest='spot_check_date', metavar='YYYY-MM-DD',
                            help="특정 날짜의 데이터 연속성(품질) 스팟 체크")
    
    # --validate 모드용 인자
    parser.add_argument('--start-date', type=str,
                       help="검증 시작일 (YYYY-MM-DD) (--validate 모드에서 필수)")
    parser.add_argument('--end-date', type=str,
                       help="검증 종료일 (YYYY-MM-DD) (--validate 모드에서 필수)")
    
    # 공통 인자
    parser.add_argument('--stocks', nargs='+',
                       help='(선택) 특정 종목 코드 목록 (e.g., 005930 035720).')

    args = parser.parse_args()

    # --- 객체 초기화 ---
    logger.info("🚀 DatabaseManager 및 TestEnvironment 초기화...")
    db = DatabaseManager()
    test_env = TestEnvironment(db, logger) 
    
    try:
        # Step 0: 대상 종목 확정
        target_stocks = _get_target_stocks(db, args.stocks)
        if not target_stocks:
            logger.error("검증할 대상 종목이 없습니다.")
            sys.exit(1)

        # --- 모드 분기 ---
        if args.validate:
            # (모드 1) 전체 검증
            if not args.start_date or not args.end_date:
                logger.error("--validate 모드를 사용하려면 --start-date와 --end-date가 모두 필요합니다.")
                sys.exit(1)
            
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
            
            if start_date > end_date:
                logger.critical("시작일이 종료일보다 늦을 수 없습니다.")
                sys.exit(1)
                
            _run_validation(db, test_env, target_stocks, start_date, end_date)

        elif args.spot_check_date:
            # (모드 2) 스팟 체크
            try:
                check_date = datetime.strptime(args.spot_check_date, '%Y-%m-%d').date()
            except ValueError:
                logger.critical("--spot-check 날짜 형식이 잘못되었습니다. 'YYYY-MM-DD' 형식을 사용하세요.")
                sys.exit(1)
                
            _run_spot_check(db, test_env, target_stocks, check_date)

    except Exception as e:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()