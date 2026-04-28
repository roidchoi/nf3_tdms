# initial_build.py
"""
초기 데이터 구축 모듈
- 종목 마스터 구축
- 전체 일봉 데이터 수집
- 수정계수 팩터 구축
- 분봉 수집 대상 이력 구축
- 과거 분봉 데이터 마이그레이션

Usage:
    # Step 1: 종목 마스터 구축
    python initial_build.py --mode build_master [--test]
    
    # Step 2: 과거 일봉 수집
    python initial_build.py --mode seed_daily --market KOSPI [--test]
    
    # Step 3: 수정계수 구축
    python initial_build.py --mode build_factors [--test]
    
    # Step 4: 분봉 대상 이력 구축
    python initial_build.py --mode build_targets
    
    # Step 5: 레거시 분봉 마이그레이션
    python initial_build.py --mode migrate_legacy --quarter 2024Q4 --market KOSPI
    
    # Step 6: 마이그레이션 검증
    python initial_build.py --mode verify_migration --quarter 2024Q4 --market KOSPI
"""

import argparse
import sys
import time
import math
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
from tqdm import tqdm

from collectors.kiwoom_rest import KiwoomREST
from collectors.db_manager import DatabaseManager
from collectors.factor_calculator import calculate_factors
from collectors import utils, target_selector
from test_utils import TestEnvironment


def build_master(api: KiwoomREST, db: DatabaseManager, logger, test_mode: bool = False):
    """
    [Step 1] 종목 마스터 구축 및 수집 시간 추산
    
    :param api: KiwoomREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param test_mode: True면 테스트 테이블에 소수 종목만 저장
    """
    logger.info("=" * 60)
    logger.info(f"[Step 1] 종목 마스터 구축 {'(테스트 모드)' if test_mode else ''}")
    logger.info("=" * 60)
    
    test_env = TestEnvironment(db, logger) if test_mode else None
    
    try:
        # 1. 전체 종목 마스터 구축
        logger.info("--- [1/2] 전체 종목 마스터 구축 시작 ---")
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')
        
        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']
        
        # 중앙화된 변환기로 종목 정보 변환
        kospi_transformed = utils.transform_data(kospi_filtered, source='kiwoom', data_type='stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, source='kiwoom', data_type='stock_info')
        
        # 추가 정보 주입
        for item in kospi_transformed:
            item.update({'market_type': 'KOSPI', 'status': 'listed'})
        for item in kosdaq_transformed:
            item.update({'market_type': 'KOSDAQ', 'status': 'listed'})
        
        all_stocks = kospi_transformed + kosdaq_transformed
        
        # 테스트 모드: 소수 종목만 필터링
        if test_mode:
            test_env.setup_test_tables()
            all_stocks = test_env.filter_test_stocks(all_stocks)
            table_name = test_env.get_test_table_name('stock_info')
        else:
            table_name = 'stock_info'
        
        db.upsert_stock_info(all_stocks, table_name=table_name)
        logger.info(f"KOSPI {len(kospi_filtered)}개, KOSDAQ {len(kosdaq_filtered)}개 종목 마스터 저장 완료")
        
        if test_mode:
            logger.info(f"✅ 테스트: {len(all_stocks)}개 종목만 저장됨")
        
        # 2. 예상 소요 시간 계산
        logger.info("--- [2/2] 과거 데이터 수집 소요 시간 계산 ---")
        query = f"SELECT stk_cd, market_type, list_dt FROM {table_name};"
        all_stocks_from_db = db._execute_query(query, fetch='all')
        
        market_stats = {'KOSPI': {'requests': 0}, 'KOSDAQ': {'requests': 0}}
        today = date.today()
        
        for stock in all_stocks_from_db:
            if stock['list_dt'] and stock['market_type'] in market_stats:
                calendar_days = (today - stock['list_dt']).days
                trading_days_approx = calendar_days * (252 / 365.25)
                requests_needed = math.ceil(trading_days_approx / 600)
                market_stats[stock['market_type']]['requests'] += requests_needed
        
        for market, stats in market_stats.items():
            total_reqs = stats['requests']
            # 원본/수정주가 2번 호출, 요청당 0.5초 sleep
            total_seconds = total_reqs * 2 * 0.5
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            logger.info(f"[{market}] 과거 데이터 수집 예상: 총 {total_reqs:,}회 API 요청, 약 {hours}시간 {minutes}분 소요")
        
        logger.info("=" * 60)
        logger.info("✅ [Step 1] 완료. 다음: '--mode seed_daily --market [MARKET]'")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("종목 마스터 구축 중 오류 발생", exc_info=True)
        raise


def seed_daily_by_market(api: KiwoomREST, db: DatabaseManager, logger, 
                         market: str, test_mode: bool = False):
    """
    [Step 2] 시장별 과거 일봉 데이터 구축
    
    :param api: KiwoomREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param market: 'KOSPI' 또는 'KOSDAQ'
    :param test_mode: True면 테스트 테이블에서 소수 종목만 수집
    """
    logger.info("=" * 60)
    logger.info(f"[Step 2] {market} 시장 과거 일봉 구축 {'(테스트 모드)' if test_mode else ''}")
    logger.info("=" * 60)
    
    test_env = TestEnvironment(db, logger) if test_mode else None
    
    try:
        # 대상 종목 조회
        if test_mode:
            table_name = test_env.get_test_table_name('stock_info')
        else:
            table_name = 'stock_info'
        
        query = f"SELECT stk_cd FROM {table_name} WHERE market_type = %s;"
        codes_to_seed = [row['stk_cd'] for row in db._execute_query(query, (market,), fetch='all')]
        
        total = len(codes_to_seed)
        logger.info(f"총 {total}개 종목에 대한 과거 데이터 수집 시작")
        
        # 테이블명 결정
        if test_mode:
            raw_table = test_env.get_test_table_name('daily_ohlcv')
            adj_table = test_env.get_test_table_name('daily_ohlcv_adjusted_legacy')
        else:
            raw_table = 'daily_ohlcv'
            adj_table = 'daily_ohlcv_adjusted_legacy'
        
        # 종목별 수집
        for i, code in enumerate(tqdm(codes_to_seed, desc=f"{market} 일봉 수집")):
            try:
                # 원본 주가
                raw_data = api.get_daily_chart(code, start_date='19800101', 
                                               adjusted_price='0', max_requests=0)
                if raw_data:
                    for item in raw_data:
                        item['stk_cd'] = code
                    transformed_raw = utils.transform_data(raw_data, 'kiwoom', 'daily_ohlcv')
                    db.upsert_ohlcv_data(raw_table, transformed_raw)
                time.sleep(0.5)
                
                # 수정 주가
                adj_data = api.get_daily_chart(code, start_date='19800101',
                                               adjusted_price='1', max_requests=0)
                if adj_data:
                    for item in adj_data:
                        item['stk_cd'] = code
                    transformed_adj = utils.transform_data(adj_data, 'kiwoom', 'daily_ohlcv')
                    db.upsert_ohlcv_data(adj_table, transformed_adj)
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"'{code}' 종목 수집 중 오류: {e}", exc_info=False)
                continue
        
        logger.info("=" * 60)
        logger.info(f"✅ [Step 2] {market} 시장 완료")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"{market} 시장 일봉 구축 중 오류 발생", exc_info=True)
        raise


def build_all_factors(db: DatabaseManager, logger, test_mode: bool = False):
    """
    [Step 3] 마스터 수정계수 데이터베이스 구축
    
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param test_mode: True면 테스트 테이블의 데이터만 처리
    """
    logger.info("=" * 60)
    logger.info(f"[Step 3] 마스터 수정계수 구축 {'(테스트 모드)' if test_mode else ''}")
    logger.info("=" * 60)
    
    test_env = TestEnvironment(db, logger) if test_mode else None
    
    try:
        # 테이블명 결정
        if test_mode:
            stock_table = test_env.get_test_table_name('stock_info')
            raw_table = test_env.get_test_table_name('daily_ohlcv')
            adj_table = test_env.get_test_table_name('daily_ohlcv_adjusted_legacy')
            factor_table = test_env.get_test_table_name('price_adjustment_factors')
        else:
            stock_table = 'stock_info'
            raw_table = 'daily_ohlcv'
            adj_table = 'daily_ohlcv_adjusted_legacy'
            factor_table = 'price_adjustment_factors'
        
        # 종목 목록 조회
        query = f"SELECT stk_cd FROM {stock_table};"
        stock_list = [row['stk_cd'] for row in db._execute_query(query, fetch='all')]
        
        if not stock_list:
            logger.error(f"'{stock_table}' 테이블에 종목 정보가 없습니다.")
            return
        
        logger.info(f"총 {len(stock_list)}개 종목에 대한 수정계수 계산 시작")
        
        # 종목별 팩터 계산
        for stk_cd in tqdm(stock_list, desc="수정계수 계산"):
            try:
                # OHLCV 데이터 조회
                ohlcv_df = db.fetch_ohlcv_for_factor_calc(
                    stk_cd,
                    table_name_raw=raw_table,
                    table_name_adj=adj_table,
                    stock_info_table=stock_table
                )
                
                if ohlcv_df.empty:
                    logger.debug(f"[{stk_cd}] 시세 데이터가 없어 건너뜁니다.")
                    continue
                
                # 팩터 계산
                price_source = 'KIWOOM_TEST' if test_mode else 'KIWOOM'
                factors = calculate_factors(ohlcv_df, stk_cd, price_source)
                
                if not factors:
                    logger.debug(f"[{stk_cd}] 탐지된 수정계수가 없습니다.")
                    continue
                
                # DB 저장
                db.upsert_adjustment_factors(factors, table_name=factor_table)
                logger.debug(f"[{stk_cd}] {len(factors)}개 수정계수 저장")
                
            except Exception as e:
                logger.error(f"[{stk_cd}] 처리 중 오류: {e}", exc_info=False)
                continue
        
        logger.info("=" * 60)
        logger.info("✅ [Step 3] 마스터 수정계수 구축 완료")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("수정계수 구축 중 치명적 오류", exc_info=True)
        raise


def build_target_history(db: DatabaseManager, logger):
    """
    [Step 4] 과거 분봉 수집 대상 소급 선정 (2019Q4 ~ 2025Q4)
    
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    """
    logger.info("=" * 60)
    logger.info("[Step 4] 과거 분기별 분봉 수집 대상 선정")
    logger.info("=" * 60)
    
    # 대상 분기 목록
    historical_quarters = [
        (2019, 4),
        (2020, 1), (2020, 2), (2020, 3), (2020, 4),
        (2021, 1), (2021, 2), (2021, 3), (2021, 4),
        (2022, 1), (2022, 2), (2022, 3), (2022, 4),
        (2023, 1), (2023, 2), (2023, 3), (2023, 4),
        (2024, 1), (2024, 2), (2024, 3), (2024, 4),
        (2025, 1), (2025, 2), (2025, 3), (2025, 4),
    ]
    
    try:
        for year, quarter in tqdm(historical_quarters, desc="분기별 대상 선정"):
            quarter_str = f"{year}Q{quarter}"
            logger.info(f"--- {quarter_str} 대상 선정 시작 ---")
            
            # KOSPI
            kospi_targets = target_selector.get_target_stocks(db, year, quarter, 'KOSPI', 200)
            if kospi_targets:
                db.upsert_minute_target_history(kospi_targets)
                logger.info(f"{quarter_str} KOSPI {len(kospi_targets)}개 저장 완료")
            else:
                logger.warning(f"{quarter_str} KOSPI 대상 선정 실패")
            
            # KOSDAQ
            kosdaq_targets = target_selector.get_target_stocks(db, year, quarter, 'KOSDAQ', 400)
            if kosdaq_targets:
                db.upsert_minute_target_history(kosdaq_targets)
                logger.info(f"{quarter_str} KOSDAQ {len(kosdaq_targets)}개 저장 완료")
            else:
                logger.warning(f"{quarter_str} KOSDAQ 대상 선정 실패")
        
        logger.info("=" * 60)
        logger.info("✅ [Step 4] 완료. 다음: '--mode migrate_legacy'")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("대상 선정 중 치명적 오류", exc_info=True)
        raise


def migrate_minute_legacy(db: DatabaseManager, logger, quarter: str, market: str, source_dir: str):
    """
    [Step 5] SQLite 레거시 분봉 데이터를 TimescaleDB로 마이그레이션
    
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param quarter: 분기 문자열 (예: '2024Q4')
    :param market: 'KOSPI' 또는 'KOSDAQ'
    :param source_dir: SQLite 파일이 있는 디렉토리 경로
    """
    logger.info("=" * 60)
    logger.info(f"[Step 5] 레거시 분봉 마이그레이션: {quarter} {market}")
    logger.info("=" * 60)
    
    try:
        # 1. 대상 종목 조회
        target_rows = db.get_minute_target_history(quarter, market)
        if not target_rows:
            logger.error(f"'{quarter} {market}' 대상이 minute_target_history에 없습니다.")
            logger.error("먼저 '--mode build_targets'를 실행하세요.")
            return
        
        target_symbols = {row['symbol'] for row in target_rows}
        logger.info(f"{len(target_symbols)}개 종목 마이그레이션 시작")
        
        # 2. 분기에 해당하는 월 목록
        year = int(quarter[:4])
        q_num = int(quarter[5])
        months = [f"{year}{((q_num-1)*3 + i):02d}" for i in [1, 2, 3]]
        
        # 3. 월별 SQLite 파일 순회
        base_path = Path(source_dir)
        for yyyymm in tqdm(months, desc=f"{quarter} {market} 월별 처리"):
            db_file_name = f"kw_1m_{market.lower()}_{yyyymm}.db"
            db_path = base_path / db_file_name
            
            if not db_path.exists():
                logger.warning(f"[{yyyymm}] SQLite 파일 없음: {db_path}")
                continue
            
            conn_sqlite = None
            try:
                conn_sqlite = sqlite3.connect(db_path)
                logger.info(f"[{yyyymm}] 파일 연결 성공: {db_path}")
                
                # 종목별 데이터 추출
                for stk_cd in tqdm(target_symbols, desc=f"[{yyyymm}] 종목", leave=False):
                    table_name = f"a{stk_cd}"
                    try:
                        cursor = conn_sqlite.execute(f"SELECT * FROM {table_name}")
                        rows = cursor.fetchall()
                        if not rows:
                            continue
                        
                        # Kiwoom API 형식으로 변환
                        mock_api_batch = []
                        for row in rows:
                            mock_api_batch.append({
                                'stk_cd': stk_cd,
                                'cntr_tm': str(row[0]),
                                'open_pric': str(row[1]),
                                'high_pric': str(row[2]),
                                'low_pric': str(row[3]),
                                'cur_prc': str(row[4]),
                                'trde_qty': str(row[5])
                            })
                        
                        # 표준 변환 및 저장
                        transformed = utils.transform_data(mock_api_batch, 'kiwoom', 'minute_ohlcv')
                        if transformed:
                            db.upsert_ohlcv_data('minute_ohlcv', transformed)
                        
                    except sqlite3.OperationalError:
                        continue
                    except Exception as e:
                        logger.error(f"[{yyyymm}] {stk_cd}: {e}", exc_info=False)
            
            except Exception as e:
                logger.error(f"[{yyyymm}] 파일 처리 실패: {e}", exc_info=True)
            finally:
                if conn_sqlite:
                    conn_sqlite.close()
        
        logger.info("=" * 60)
        logger.info(f"✅ [Step 5] 완료: {quarter} {market}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("마이그레이션 중 치명적 오류", exc_info=True)
        raise


def verify_migration(db: DatabaseManager, logger, quarter: str, market: str, source_dir: str):
    """
    [Step 6] 마이그레이션 데이터 무결성 검증
    
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param quarter: 분기 문자열 (예: '2024Q4')
    :param market: 'KOSPI' 또는 'KOSDAQ'
    :param source_dir: SQLite 파일이 있는 디렉토리 경로
    """
    logger.info("=" * 60)
    logger.info(f"[검증] 마이그레이션 무결성 확인: {quarter} {market}")
    logger.info("=" * 60)
    
    try:
        # 대상 종목 및 기간
        target_rows = db.get_minute_target_history(quarter, market)
        if not target_rows:
            logger.error("대상 정보가 없습니다.")
            return
        
        target_symbols = {row['symbol'] for row in target_rows}
        year = int(quarter[:4])
        q_num = int(quarter[5])
        months = [f"{year}{((q_num-1)*3 + i):02d}" for i in [1, 2, 3]]
        
        q_start_month = (q_num - 1) * 3 + 1
        q_start_date = datetime(year, q_start_month, 1).date()
        q_end_date = (q_start_date + relativedelta(months=3)) - relativedelta(days=1)
        
        # SQLite 총 레코드 수
        sqlite_total = 0
        base_path = Path(source_dir)
        
        logger.info("--- [1/2] 원본(SQLite) 카운트 ---")
        for yyyymm in tqdm(months, desc="SQLite 스캔"):
            db_path = base_path / f"kw_1m_{market.lower()}_{yyyymm}.db"
            if not db_path.exists():
                continue
            
            conn = sqlite3.connect(db_path)
            try:
                for stk_cd in target_symbols:
                    try:
                        cursor = conn.execute(f"SELECT COUNT(*) FROM a{stk_cd}")
                        sqlite_total += cursor.fetchone()[0]
                    except sqlite3.OperationalError:
                        continue
            finally:
                conn.close()
        
        logger.info(f"SQLite 총 {sqlite_total:,}건")
        
        # TimescaleDB 총 레코드 수
        logger.info("--- [2/2] 대상(TimescaleDB) 카운트 ---")
        kst = ZoneInfo("Asia/Seoul")
        ts_start = datetime.combine(q_start_date, datetime.min.time(), tzinfo=kst)
        ts_end = datetime.combine(q_end_date, datetime.max.time(), tzinfo=kst)
        
        query = """
        SELECT COUNT(*) FROM minute_ohlcv
        WHERE stk_cd IN %s AND dt_tm >= %s AND dt_tm <= %s;
        """
        result = db._execute_query(query, (tuple(target_symbols), ts_start, ts_end), fetch='one')
        pg_total = result['count']
        
        logger.info(f"TimescaleDB 총 {pg_total:,}건")
        
        # 최종 비교
        logger.info("--- [결과] ---")
        if sqlite_total == pg_total:
            logger.info(f"✅ 검증 성공: 일치 ({sqlite_total:,}건)")
        else:
            logger.error(f"❌ 검증 실패: SQLite {sqlite_total:,}건, PG {pg_total:,}건")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("검증 중 오류 발생", exc_info=True)


def main():
    parser = argparse.ArgumentParser(
        description="KDMS 초기 데이터 구축",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Step 1: 종목 마스터 구축
  python initial_build.py --mode build_master
  python initial_build.py --mode build_master --test
  
  # Step 2: 과거 일봉 수집
  python initial_build.py --mode seed_daily --market KOSPI
  python initial_build.py --mode seed_daily --market KOSDAQ --test
  
  # Step 3: 수정계수 구축
  python initial_build.py --mode build_factors
  python initial_build.py --mode build_factors --test
  
  # Step 4: 분봉 대상 이력
  python initial_build.py --mode build_targets
  
  # Step 5: 레거시 마이그레이션
  python initial_build.py --mode migrate_legacy --quarter 2024Q4 --market KOSPI
  
  # Step 6: 마이그레이션 검증
  python initial_build.py --mode verify_migration --quarter 2024Q4 --market KOSPI
        """
    )
    
    parser.add_argument('--mode', type=str, required=True,
                       choices=['build_master', 'seed_daily', 'build_factors',
                               'build_targets', 'migrate_legacy', 'verify_migration'],
                       help='실행할 모드 선택')
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ'],
                       help='시장 선택 (seed_daily, migrate_legacy, verify_migration 모드에서 필수)')
    parser.add_argument('--quarter', type=str,
                       help='분기 지정 (예: 2024Q4) - migrate_legacy, verify_migration 모드에서 필수')
    parser.add_argument('--source-dir', type=str, default='./db_legacy',
                       help='SQLite 파일 디렉토리 경로 (기본값: ./db_legacy)')
    parser.add_argument('--test', action='store_true',
                       help='테스트 모드 활성화 (소수 종목으로 격리된 테스트)')
    
    args = parser.parse_args()
    
    # 로거 설정
    logger = utils.setup_logger('initial_build')
    
    logger.info("🚀 Kiwoom API 초기화...")
    api = KiwoomREST(mock=False, log_level=3)
    
    logger.info("🚀 DatabaseManager 초기화...")
    db = DatabaseManager()
    
    try:
        if args.mode == 'build_master':
            build_master(api, db, logger, test_mode=args.test)
        
        elif args.mode == 'seed_daily':
            if not args.market:
                logger.error("'seed_daily' 모드는 --market 인자가 필요합니다.")
                parser.print_help()
                sys.exit(1)
            seed_daily_by_market(api, db, logger, args.market, test_mode=args.test)
        
        elif args.mode == 'build_factors':
            build_all_factors(db, logger, test_mode=args.test)
        
        elif args.mode == 'build_targets':
            build_target_history(db, logger)
        
        elif args.mode == 'migrate_legacy':
            if not args.quarter or not args.market:
                logger.error("'migrate_legacy' 모드는 --quarter와 --market 인자가 필요합니다.")
                parser.print_help()
                sys.exit(1)
            migrate_minute_legacy(db, logger, args.quarter, args.market, args.source_dir)
        
        elif args.mode == 'verify_migration':
            if not args.quarter or not args.market:
                logger.error("'verify_migration' 모드는 --quarter와 --market 인자가 필요합니다.")
                parser.print_help()
                sys.exit(1)
            verify_migration(db, logger, args.quarter, args.market, args.source_dir)
    
    except Exception as e:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()