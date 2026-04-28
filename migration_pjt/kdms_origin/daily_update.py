# daily_update.py
"""
일일 데이터 업데이트 모듈
- 거래일 확인 (KIS API 캘린더)
- 종목 정보 갱신
- 팩터 및 원본 시세 동기화 (N일 룩백)
- 분봉 수집 (선별 종목)

Usage:
    # 운영 모드 (매일 자동 실행)
    python daily_update.py
    
    # 테스트 모드 (소수 종목으로 격리 테스트)
    python daily_update.py --test
"""

import argparse
import sys
import time
import pandas as pd
from datetime import date, datetime, timedelta
from tqdm import tqdm

from collectors.kiwoom_rest import KiwoomREST
from collectors.kis_rest import KisREST
from collectors.db_manager import DatabaseManager
from collectors.factor_calculator import calculate_factors
from collectors import utils, target_selector
from test_utils import TestEnvironment


def daily_update(api: KiwoomREST, kis_api: KisREST, db: DatabaseManager, 
                 logger, test_mode: bool = False):
    """
    일일 데이터 업데이트 메인 로직
    
    :param api: KiwoomREST API 인스턴스
    :param kis_api: KisREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param test_mode: True면 테스트 테이블 사용 및 소수 종목만 처리
    """
    today = date.today()
    logger.info("=" * 60)
    logger.info(f"[일일 업데이트] {today} {'(테스트 모드)' if test_mode else ''}")
    logger.info("=" * 60)
    
    test_env = TestEnvironment(db, logger) if test_mode else None
    
    # 테스트 모드 초기 설정
    if test_mode:
        test_env.setup_test_tables()
        # 테스트용 데이터 오염 시뮬레이션
        test_env.simulate_data_corruption()
    
    # --- [0/4] 거래일 확인 ---
    if not _check_trading_day(kis_api, db, logger, today):
        logger.info("오늘은 휴장일입니다. 작업을 종료합니다.")
        return
    
    # --- [1/4] 종목 정보 갱신 ---
    _update_stock_info(api, db, logger, test_mode, test_env)
    
    # --- [2/4] 팩터 및 원본 시세 동기화 ---
    _sync_factors_and_prices(api, db, logger, today, test_mode, test_env)
    
    # --- [3/4] 분봉 수집 ---
    _collect_minute_data(api, db, logger, today, test_mode, test_env)
    
    # --- [4/4] 시스템 상태 업데이트 ---
    _update_system_status(db, logger, today)
    
    logger.info("=" * 60)
    logger.info(f"✅ [일일 업데이트] {today} 완료")
    logger.info("=" * 60)


def _check_trading_day(kis_api: KisREST, db: DatabaseManager, logger, today: date) -> bool:
    """
    거래일 캘린더 확인
    
    :param kis_api: KisREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param today: 오늘 날짜
    :return: 거래일 여부 (True: 개장일, False: 휴장일)
    """
    logger.info("--- [0/4] 거래일 캘린더 확인 ---")
    
    try:
        # DB 캐시 확인
        latest_cached = db._execute_query(
            "SELECT MAX(dt) as max_dt FROM trading_calendar;", 
            fetch='one'
        )
        
        needs_refresh = True
        if latest_cached and latest_cached['max_dt']:
            days_remaining = (latest_cached['max_dt'] - today).days
            if days_remaining >= 7:
                needs_refresh = False
                logger.info(f"캘린더 캐시가 {days_remaining}일 남아있어 갱신을 건너뜁니다.")
        
        # 캐시 갱신
        if needs_refresh:
            logger.info("캘린더 캐시가 만료되어 KIS API로 갱신합니다.")
            success = utils.update_trading_calendar(kis_api, db)
            if not success:
                logger.warning("캘린더 갱신 실패. DB 캐시로만 작업합니다.")
        
        # 오늘 날짜 확인
        today_info = db._execute_query(
            "SELECT opnd_yn FROM trading_calendar WHERE dt = %s;",
            (today,), fetch='one'
        )
        
        if not today_info:
            logger.critical(f"[{today}] 거래일 정보를 DB에서 찾을 수 없습니다.")
            logger.critical("캘린더 갱신 실패 또는 KIS API 장애일 수 있습니다.")
            return False
        
        if today_info['opnd_yn'] == 'N':
            logger.info(f"오늘은 휴장일({today})입니다.")
            return False
        
        logger.info(f"오늘은 개장일({today})입니다. 수집 작업을 계속합니다.")
        return True
    
    except Exception as e:
        logger.error(f"거래일 확인 중 오류: {e}", exc_info=True)
        logger.error("안전 모드: 휴장일 확인에 실패하여 작업을 중단합니다.")
        return False


def _update_stock_info(api: KiwoomREST, db: DatabaseManager, logger,
                       test_mode: bool, test_env: TestEnvironment):
    """
    종목 정보 갱신
    
    :param api: KiwoomREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param test_mode: 테스트 모드 여부
    :param test_env: TestEnvironment 인스턴스 (test_mode가 True일 때)
    """
    logger.info("--- [1/4] 종목 정보 갱신 ---")
    
    try:
        # API 호출
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')
        
        # 필터링
        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']
        
        # 변환
        kospi_transformed = utils.transform_data(kospi_filtered, 'kiwoom', 'stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, 'kiwoom', 'stock_info')
        
        # 추가 정보 주입
        for item in kospi_transformed:
            item.update({'market_type': 'KOSPI', 'status': 'listed'})
        for item in kosdaq_transformed:
            item.update({'market_type': 'KOSDAQ', 'status': 'listed'})
        
        all_stocks = kospi_transformed + kosdaq_transformed
        
        # 테스트 모드: 소수 종목만 필터링
        if test_mode:
            all_stocks = test_env.filter_test_stocks(all_stocks)
            table_name = test_env.get_test_table_name('stock_info')
            logger.info(f"테스트: {len(all_stocks)}개 종목만 갱신")
        else:
            table_name = 'stock_info'
        
        # DB 저장
        db.upsert_stock_info(all_stocks, table_name=table_name)
        logger.info("✅ 종목 정보 갱신 완료")
    
    except Exception as e:
        logger.error("종목 정보 갱신 실패", exc_info=True)
        raise


def _sync_factors_and_prices(api: KiwoomREST, db: DatabaseManager, logger,
                              today: date, test_mode: bool, test_env: TestEnvironment):
    """
    팩터 및 원본 시세 동기화 (v8.1 로직)
    
    :param api: KiwoomREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param today: 오늘 날짜
    :param test_mode: 테스트 모드 여부
    :param test_env: TestEnvironment 인스턴스 (test_mode가 True일 때)
    """
    logger.info("--- [2/4] 팩터 및 원본 시세 동기화 ---")
    
    N_DAYS_LOOKBACK = 10
    N_DAYS_AGO_STR = (today - timedelta(days=N_DAYS_LOOKBACK)).strftime('%Y%m%d')
    N_DAYS_RECENT = 10
    
    # 테이블명 결정
    if test_mode:
        stock_table = test_env.get_test_table_name('stock_info')
        raw_table = test_env.get_test_table_name('daily_ohlcv')
        factor_table = test_env.get_test_table_name('price_adjustment_factors')
        price_source = 'KIWOOM_TEST'
    else:
        stock_table = 'stock_info'
        raw_table = 'daily_ohlcv'
        factor_table = 'price_adjustment_factors'
        price_source = 'KIWOOM'
    
    # (A) 최근 이벤트 종목 리스트업
    recent_event_map = db.get_recent_event_stocks_map(
        days=N_DAYS_RECENT, 
        table_name=factor_table
    )
    
    if recent_event_map:
        logger.info(f"최근 {N_DAYS_RECENT}일 내 이벤트 종목: {len(recent_event_map)}개")
    
    # (B) 전체 종목 조회
    all_stocks = db.get_all_stock_codes(active_only=True, table_name=stock_table)
    logger.info(f"총 {len(all_stocks)}개 종목 동기화 시작")
    
    # Loop 1: N일치 동기화
    for stk_cd in tqdm(all_stocks, desc="일일 팩터 동기화"):
        try:
            # API 호출
            adj_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR,
                                               adjusted_price='1', max_requests=0)
            raw_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR,
                                               adjusted_price='0', max_requests=0)
            
            if not raw_data_api or not adj_data_api:
                logger.debug(f"[{stk_cd}] API 응답 데이터가 부족하여 건너뜁니다.")
                continue
            
            # stk_cd 주입
            for item in raw_data_api: 
                item['stk_cd'] = stk_cd
            for item in adj_data_api: 
                item['stk_cd'] = stk_cd
            
            # 변환
            std_raw_df = pd.DataFrame(utils.transform_data(raw_data_api, 'kiwoom', 'daily_ohlcv'))
            std_adj_df = pd.DataFrame(utils.transform_data(adj_data_api, 'kiwoom', 'daily_ohlcv'))
            
            if std_raw_df.empty or std_adj_df.empty:
                logger.debug(f"[{stk_cd}] 변환된 데이터가 비어있어 건너뜁니다.")
                continue
            
            # (D) 원본 일봉 저장
            db.upsert_ohlcv_data(raw_table, std_raw_df.to_dict('records'))
            
            # (E) 팩터 계산 준비
            adj_df_renamed = std_adj_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
            raw_df_renamed = std_raw_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
            df_merged = pd.merge(adj_df_renamed, raw_df_renamed, on='dt', how='inner')
            
            # (F) 사전 필터링
            oldest_adj = std_adj_df.iloc[0]['cls_prc']
            oldest_raw = std_raw_df.iloc[0]['cls_prc']
            
            calculated_factors = []
            if oldest_adj == oldest_raw:
                # 이벤트가 없는 종목
                if stk_cd in recent_event_map:
                    # 사라진 이벤트 처리
                    db_factors = db.get_factors_by_date_range(
                        stk_cd, std_adj_df.iloc[0]['dt'], today,
                        table_name=factor_table
                    )
                    obsolete_dates = [f['event_dt'] for f in db_factors]
                    if obsolete_dates:
                        db.delete_adjustment_factors(stk_cd, obsolete_dates, table_name=factor_table)
                        logger.info(f"[{stk_cd}] {len(obsolete_dates)}개 팩터 삭제 (이벤트 사라짐)")
                    del recent_event_map[stk_cd]
                continue
            
            # (G) 팩터 계산
            calculated_factors = calculate_factors(df_merged, stk_cd, price_source)
            
            # (H) 팩터 갱신
            if calculated_factors:
                db.upsert_adjustment_factors(calculated_factors, table_name=factor_table)
                logger.debug(f"[{stk_cd}] {len(calculated_factors)}개 팩터 UPSERT")
            
            # (I) 사라진 팩터 삭제
            db_factors = db.get_factors_by_date_range(
                stk_cd, std_adj_df.iloc[0]['dt'], today,
                table_name=factor_table
            )
            calculated_dates = {f['event_dt'] for f in calculated_factors}
            db_dates = {f['event_dt'] for f in db_factors}
            obsolete_dates = list(db_dates - calculated_dates)
            if obsolete_dates:
                db.delete_adjustment_factors(stk_cd, obsolete_dates, table_name=factor_table)
                logger.info(f"[{stk_cd}] {len(obsolete_dates)}개 팩터 삭제 (N일 검증)")
            
            # (J) 작업 완료
            if stk_cd in recent_event_map:
                del recent_event_map[stk_cd]
        
        except Exception as e:
            logger.error(f"[{stk_cd}] 팩터 동기화 오류: {e}", exc_info=False)
    
    # Loop 2: API 오류 추정 종목 정리
    if recent_event_map:
        logger.info(f"--- [2.5/4] API 오류 추정 종목 팩터 검증 ({len(recent_event_map)}개) ---")
        
        # 테이블명 (재확인)
        if test_mode:
            fetch_raw_table = test_env.get_test_table_name('daily_ohlcv')
            fetch_adj_table = test_env.get_test_table_name('daily_ohlcv_adjusted_legacy')
            fetch_stock_table = test_env.get_test_table_name('stock_info')
        else:
            fetch_raw_table = 'daily_ohlcv'
            fetch_adj_table = 'daily_ohlcv_adjusted_legacy'
            fetch_stock_table = 'stock_info'
        
        for stk_cd in tqdm(recent_event_map.keys(), desc="오류 추정 팩터 정리"):
            try:
                # 전체 기간 재계산
                full_history_df = db.fetch_ohlcv_for_factor_calc(
                    stk_cd,
                    table_name_raw=fetch_raw_table,
                    table_name_adj=fetch_adj_table,
                    stock_info_table=fetch_stock_table
                )
                
                if full_history_df.empty:
                    logger.debug(f"[{stk_cd}] 전체 기간 데이터가 없어 건너뜁니다.")
                    continue
                
                true_factors = calculate_factors(full_history_df, stk_cd, price_source)
                true_dates = {f['event_dt'] for f in true_factors}
                
                obsolete_dates = [dt for dt in recent_event_map[stk_cd] if dt not in true_dates]
                if obsolete_dates:
                    db.delete_adjustment_factors(stk_cd, obsolete_dates, table_name=factor_table)
                    logger.info(f"[{stk_cd}] {len(obsolete_dates)}개 오류 팩터 삭제 (전체 검증)")
            
            except Exception as e:
                logger.error(f"[{stk_cd}] 팩터 정리 오류: {e}", exc_info=False)
    
    logger.info("✅ 팩터 및 원본 시세 동기화 완료")


def _collect_minute_data(api: KiwoomREST, db: DatabaseManager, logger,
                         today: date, test_mode: bool, test_env: TestEnvironment):
    """
    분봉 수집 (선별 종목)
    
    :param api: KiwoomREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param today: 오늘 날짜
    :param test_mode: 테스트 모드 여부
    :param test_env: TestEnvironment 인스턴스 (test_mode가 True일 때)
    """
    logger.info("--- [3/4] 분봉 데이터 수집 ---")
    
    current_quarter_str = f"{today.year}Q{(today.month - 1) // 3 + 1}"
    
    # 테이블명 결정
    if test_mode:
        target_table = test_env.get_test_table_name('minute_target_history')
        minute_table = test_env.get_test_table_name('minute_ohlcv')
    else:
        target_table = 'minute_target_history'
        minute_table = 'minute_ohlcv'
    
    all_target_stocks = []
    
    # 시장별 대상 확인
    for market in ['KOSPI', 'KOSDAQ']:
        target_history = db.get_minute_target_history(
            quarter=current_quarter_str,
            market=market,
            table_name=target_table
        )
        
        if target_history:
            logger.info(f"{current_quarter_str} {market} 기존 대상 {len(target_history)}개 재사용")
            all_target_stocks.extend([item['symbol'] for item in target_history])
        else:
            logger.info(f"{current_quarter_str} {market} 신규 대상 선정 중...")
            new_targets = target_selector.get_target_stocks(
                db, today.year, (today.month - 1) // 3 + 1, market, 200
            )
            if new_targets:
                db.upsert_minute_target_history(new_targets, table_name=target_table)
                all_target_stocks.extend([item['symbol'] for item in new_targets])
                logger.info(f"{current_quarter_str} {market} {len(new_targets)}개 신규 대상 저장")
            else:
                logger.warning(f"{current_quarter_str} {market} 신규 대상 선정 실패")
    
    if not all_target_stocks:
        logger.warning("분봉 수집 대상 종목이 없습니다.")
        return
    
    logger.info(f"총 {len(all_target_stocks)}개 종목 분봉 수집 시작")
    
    # 분봉 수집
    success_count = 0
    for code in tqdm(all_target_stocks, desc="일일 분봉 수집"):
        try:
            minute_data = api.get_minute_chart(code, start_date=today.strftime('%Y%m%d'))
            if minute_data:
                for item in minute_data:
                    item['stk_cd'] = code
                transformed = utils.transform_data(minute_data, 'kiwoom', 'minute_ohlcv')
                db.upsert_ohlcv_data(minute_table, transformed)
                success_count += 1
            time.sleep(0.5)  # Kiwoom API Rate Limit
        except Exception as e:
            logger.warning(f"'{code}' 분봉 수집 실패: {e}")
    
    logger.info(f"✅ 분봉 수집 완료: {success_count}/{len(all_target_stocks)}개 성공")


def _update_system_status(db: DatabaseManager, logger, today: date):
    """
    시스템 상태 업데이트
    
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param today: 오늘 날짜
    """
    logger.info("--- [4/4] 시스템 상태 업데이트 ---")
    
    try:
        milestone = db._execute_query(
            "SELECT 1 FROM system_milestones WHERE milestone_name = 'SYSTEM:LIVE:DAILY_COLLECTION'",
            fetch='one'
        )
        
        if not milestone:
            db.set_milestone(
                'SYSTEM:LIVE:DAILY_COLLECTION',
                today,
                "시스템 공식 일일 자동 수집 시작"
            )
            logger.info("시스템 마일스톤 설정 완료")
        else:
            logger.debug("시스템 마일스톤 이미 존재")
    except Exception as e:
        logger.error("마일스톤 업데이트 실패", exc_info=True)


def main():
    parser = argparse.ArgumentParser(
        description="KDMS 일일 데이터 업데이트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 운영 모드 (매일 자동 실행)
  python daily_update.py
  
  # 테스트 모드 (격리된 테이블에서 소수 종목만 처리)
  python daily_update.py --test
  
Cron 설정:
  # 매일 오후 7시 실행 (장 마감 후)
  0 19 * * * cd /path/to/kdms && python daily_update.py >> logs/cron.log 2>&1
        """
    )
    
    parser.add_argument('--test', action='store_true',
                       help='테스트 모드 활성화 (격리된 테이블에서 소수 종목만 처리)')
    
    args = parser.parse_args()
    
    # 로거 설정
    logger = utils.setup_logger('daily_update')
    
    logger.info("🚀 Kiwoom API 초기화...")
    api = KiwoomREST(mock=False, log_level=3)
    
    logger.info("🚀 KIS API 초기화...")
    try:
        kis_api = KisREST(mock=False, log_level=1)
    except Exception as e:
        logger.critical(f"KIS API 초기화 실패: {e}")
        logger.critical("휴장일 확인이 불가능합니다. 작업을 중단합니다.")
        sys.exit(1)
    
    logger.info("🚀 DatabaseManager 초기화...")
    db = DatabaseManager()
    
    try:
        daily_update(api, kis_api, db, logger, test_mode=args.test)
    except Exception as e:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()