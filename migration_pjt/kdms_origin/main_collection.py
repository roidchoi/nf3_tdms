# main_collection.py
import argparse
import pandas as pd
import sys
import time
import math
import json
from decimal import Decimal
import sqlite3 
from pathlib import Path
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
from collectors.kiwoom_rest import KiwoomREST
from collectors.kis_rest import KisREST, KisAPIError
from collectors.db_manager import DatabaseManager
from collectors import utils
from collectors import target_selector

from collectors.factor_calculator import calculate_factors
from tqdm import tqdm # 진행률 표시를 위한 tqdm 추가

def _filter_stock_list(stock_list: list[dict], market_name: str) -> list[dict]:
    """ Kiwoom API 응답에서 순수 주식 종목만 필터링 """
    # regDay 필드가 없는 경우 상장일 정보를 None으로 처리
    for stock in stock_list:
        stock['list_dt'] = datetime.strptime(stock['regDay'], '%Y%m%d').date() if stock.get('regDay') else None
    
    return [stock for stock in stock_list if stock.get('marketName') == market_name]

def run_build_master(api: KiwoomREST, db: DatabaseManager, logger):
    """ [Mode] 1단계: 종목 마스터 구축 및 수집 시간 추산 """
    logger.info("========== [Mode: build_master] 시작 ==========")
    
    try:
        # 1. 종목 마스터 구축
        logger.info("--- [1/2] 전체 종목 마스터 구축 시작 ---")
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')

        #kospi_filtered = _filter_stock_list(kospi_raw, '거래소')
        #kosdaq_filtered = _filter_stock_list(kosdaq_raw, '코스닥')

        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']

        # 👇 [핵심 수정] 필터링된 데이터를 DB 스키마에 맞게 변환
        logger.info("중앙화된 변환기로 종목 정보 변환 시작...")
        kospi_transformed = utils.transform_data(kospi_filtered, source='kiwoom', data_type='stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, source='kiwoom', data_type='stock_info')

        # 변환 후 추가 정보(market_type, status) 주입
        for item in kospi_transformed:
            item['market_type'] = 'KOSPI'
            item['status'] = 'listed'
        for item in kosdaq_transformed:
            item['market_type'] = 'KOSDAQ'
            item['status'] = 'listed'

        all_stocks_to_db = kospi_transformed + kosdaq_transformed
        db.upsert_stock_info(all_stocks_to_db)
        
        logger.info(f"KOSPI {len(kospi_filtered)}개, KOSDAQ {len(kosdaq_filtered)}개 종목 마스터 저장 완료.")

        # 2. 예상 소요 시간 계산
        logger.info("--- [2/2] 과거 데이터 수집 소요 시간 계산 시작 ---")
        all_stocks_from_db = db._execute_query("SELECT stk_cd, market_type, list_dt FROM stock_info;", fetch='all')
        
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
            logger.info(f"[{market}] 과거 데이터 수집 예상: 총 {total_reqs:,}회 API 요청, 약 {hours}시간 {minutes}분 소요 예상")

        logger.info("========== [Mode: build_master] 성공. 다음 단계: '--mode seed_daily_market --market [MARKET]' 실행 ==========")

    except Exception as e:
        logger.error("마스터 구축 중 심각한 에러 발생", exc_info=True)
        raise

def run_seed_daily_market(api: KiwoomREST, db: DatabaseManager, logger, market: str):
    """ [Mode] 2단계: 시장별 과거 일봉 데이터 구축 """
    logger.info(f"========== [Mode: seed_daily_market, Market: {market}] 시작 ==========")
    
    codes_to_seed = [
        row['stk_cd'] for row in 
        db._execute_query("SELECT stk_cd FROM stock_info WHERE market_type = %s;", (market,), fetch='all')
    ]
    total = len(codes_to_seed)
    logger.info(f"총 {total}개 종목에 대한 과거 데이터 수집을 시작합니다.")

    for i, code in enumerate(codes_to_seed):
        try:
            logger.info(f"[{i+1}/{total}] '{code}' 종목 데이터 수집 중...")
            raw_data = api.get_daily_chart(code, start_date='19800101', adjusted_price='0', max_requests=0)

            if raw_data: 
                for item in raw_data:
                    item['stk_cd'] = code
                transformed_raw_data = utils.transform_data(raw_data, source='kiwoom', data_type='daily_ohlcv')
                db.upsert_ohlcv_data('daily_ohlcv', transformed_raw_data)
            time.sleep(0.5)

            adj_data = api.get_daily_chart(code, start_date='19800101', adjusted_price='1', max_requests=0)
            if adj_data: 
                for item in adj_data:
                    item['stk_cd'] = code
                transformed_adj_data = utils.transform_data(adj_data, source='kiwoom', data_type='daily_ohlcv')
                db.upsert_ohlcv_data('daily_ohlcv_adjusted_legacy', transformed_adj_data)
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"'{code}' 종목 데이터 수집 중 에러 발생", exc_info=True)
            continue
            
    logger.info(f"========== [Mode: seed_daily_market, Market: {market}] 성공적으로 완료 ==========")

def run_daily_update(api: KiwoomREST, kis_api: KisREST, db: DatabaseManager, logger):
    """ [Mode] 일일 데이터 업데이트 (매일 실행) """
    logger.info(f"========== [Mode: daily_update] {date.today()} 작업 시작 ==========")
    today = date.today()

    # 지능형 휴장일 확인 (로컬 캐시 우선) ---
    try:
        logger.info("--- [0/4] 거래일 캘린더 확인 ---")
        
        # 1. DB 캐시에서 가장 마지막 날짜 확인
        # (init.sql에 trading_calendar 테이블이 생성됨)
        latest_cached_row = db._execute_query("SELECT MAX(dt) as max_dt FROM trading_calendar;", fetch='one')
        
        needs_refresh = True
        if latest_cached_row and latest_cached_row['max_dt']:
            days_remaining = (latest_cached_row['max_dt'] - today).days
            if days_remaining >= 7: # 캐시가 7일 이상 남아있으면 갱신 불필요
                needs_refresh = False
        
        # 2. 캐시가 비어있거나 7일 이내 만료 시 갱신
        if needs_refresh:
            logger.info("거래일 캘린더 캐시가 만료되었거나(7일 미만) 비어있습니다. KIS API를 통해 갱신합니다.")
            
            # utils.py에 추가된 함수 호출
            success = utils.update_trading_calendar(kis_api, db) 
            if not success:
                logger.warning("KIS API 캘린더 갱신에 실패했습니다. DB 캐시로만 작업을 시도합니다.")
        
        # 3. 오늘 날짜로 작업 실행 여부 최종 결정
        today_info = db._execute_query("SELECT opnd_yn FROM trading_calendar WHERE dt = %s;", (today,), fetch='one')

        if not today_info:
            logger.critical(f"[{today}] 거래일 정보를 로컬 DB에서 찾을 수 없습니다.")
            logger.critical("캘린더 갱신 실패 또는 KIS API 장애일 수 있습니다. 수집 작업을 중단합니다.")
            return # 작업 중단
        
        if today_info['opnd_yn'] == 'N':
            logger.info(f"오늘은 휴장일({today})입니다. 일일 수집 작업을 건너뜁니다.")
            return # 작업 종료
        
        logger.info(f"오늘은 개장일({today})입니다. 일일 수집 작업을 계속합니다.")

    except Exception as e:
        logger.error(f"거래일 확인 중 예외 발생: {e}", exc_info=True)
        logger.error("안전 모드: 휴장일 확인에 실패하여 수집 작업을 중단합니다.")
        return # 작업 중단
    
    # N일 검증 창 (Kiwoom API 600건 응답 고려)
    N_DAYS_LOOKBACK = 10 
    N_DAYS_AGO_STR = (today - timedelta(days=N_DAYS_LOOKBACK)).strftime('%Y%m%d')
    
    # N일 이내 최근 이벤트 감지 (오류 제거용)
    N_DAYS_RECENT = 10 

    # --- 1. 메타데이터 갱신 (종목 정보) ---
    logger.info("--- [1/4] 종목 정보 갱신 시작 ---")
    try:
        # (기존 run_build_master 로직과 동일)
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')
        
        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']

        kospi_transformed = utils.transform_data(kospi_filtered, source='kiwoom', data_type='stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, source='kiwoom', data_type='stock_info')

        for item in kospi_transformed: item.update({'market_type': 'KOSPI', 'status': 'listed'})
        for item in kosdaq_transformed: item.update({'market_type': 'KOSDAQ', 'status': 'listed'})

        db.upsert_stock_info(kospi_transformed + kosdaq_transformed)
        logger.info("종목 정보 갱신 완료.")
    except Exception as e:
        logger.error("종목 정보 갱신 중 에러 발생", exc_info=True)
        return

    # --- 2. 팩터 및 원본 시세 동기화 ---
    logger.info("--- [2/4] 팩터 및 원본 시세 동기화 시작 ---")
    
    # (A) 최근 N일 이내 이벤트가 기록된 종목 리스트업
    recent_event_map = db.get_recent_event_stocks_map(days=N_DAYS_RECENT)
    
    all_stocks = db.get_all_stock_codes(active_only=True)
    
    for stk_cd in tqdm(all_stocks, desc="일일 팩터 동기화 중"):
        try:
            # (B) N일치 원본/수정 주가 동시 수집
            adj_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR, adjusted_price='1', max_requests=0)
            raw_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR, adjusted_price='0', max_requests=0)

            if not raw_data_api or not adj_data_api:
                logger.warning(f"[{stk_cd}] API 시세가 부족하여 건너뜁니다.")
                continue

            # utils.transform_data 전에 'stk_cd' 주입
            for item in raw_data_api: item['stk_cd'] = stk_cd
            for item in adj_data_api: item['stk_cd'] = stk_cd
            
            std_raw_df = pd.DataFrame(
                utils.transform_data(raw_data_api, 'kiwoom', 'daily_ohlcv')
            )
            std_adj_df = pd.DataFrame(
                utils.transform_data(adj_data_api, 'kiwoom', 'daily_ohlcv')
            )

            if std_raw_df.empty or std_adj_df.empty:
                logger.warning(f"[{stk_cd}] 변환된 시세 데이터가 없어 건너뜁니다.")
                continue

            # (D) [v8.1] 원본 일봉만 DB에 UPSERT (유일한 시세 저장)
            db.upsert_ohlcv_data('daily_ohlcv', std_raw_df.to_dict('records'))

            # (E) [v8.1] 팩터 계산을 위한 DataFrame 준비
            adj_df_renamed = std_adj_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
            raw_df_renamed = std_raw_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
            df_merged = pd.merge(adj_df_renamed, raw_df_renamed, on='dt', how='inner')

            # (F) [v8.1] 사전 필터링 (가장 오래된 날짜 비교)
            oldest_adj_prc = std_adj_df.iloc[0]['cls_prc']
            oldest_raw_prc = std_raw_df.iloc[0]['cls_prc']
            
            calculated_factors = []
            if oldest_adj_prc == oldest_raw_prc:
                # 이벤트가 전혀 없는 종목.
                # [예외 처리] 단, 최근 이벤트 리스트(A)에 있었다면 '사라진 이벤트'임
                if stk_cd in recent_event_map:
                    db_factors = db.get_factors_by_date_range(stk_cd, std_adj_df.iloc[0]['dt'], today)
                    obsolete_dates = [f['event_dt'] for f in db_factors]
                    if obsolete_dates:
                        db.delete_adjustment_factors(stk_cd, obsolete_dates)
                    del recent_event_map[stk_cd] # 작업 완료, 리스트에서 제거
                
                continue # 다음 종목으로

            # (G) [v8.1] (필터링 통과) 팩터 계산 로직 실행
            calculated_factors = calculate_factors(df_merged, stk_cd, 'KIWOOM')
            
            # (H) [v8.1] 팩터 갱신 (신규/변경)
            if calculated_factors:
                db.upsert_adjustment_factors(calculated_factors)

            # (I) [v8.1] '사라진' 팩터 삭제
            db_factors = db.get_factors_by_date_range(stk_cd, std_adj_df.iloc[0]['dt'], today)
            calculated_dates = {f['event_dt'] for f in calculated_factors}
            db_dates = {f['event_dt'] for f in db_factors}
            obsolete_dates = list(db_dates - calculated_dates)
            
            if obsolete_dates:
                db.delete_adjustment_factors(stk_cd, obsolete_dates)

            # (J) [v8.1] 작업 완료, 리스트에서 제거
            if stk_cd in recent_event_map:
                del recent_event_map[stk_cd]

        except Exception as e:
            logger.error(f"[{stk_cd}] 팩터 동기화 중 오류 발생: {e}", exc_info=False)
            
    # --- 3. (신규) '사라진' 팩터 정리 (Loop 2) ---
    if recent_event_map:
        logger.info(f"--- [3/4] API 통신 오류 추정 종목 팩터 검증 시작 ({len(recent_event_map)}개) ---")
        
        for stk_cd, event_dates_in_db in tqdm(recent_event_map.items(), desc="오류 추정 팩터 정리 중"):
            try:
                # (I) 해당 종목의 "전체 기간" 팩터 재계산
                full_history_df = db.fetch_ohlcv_for_factor_calc(stk_cd)
                if full_history_df.empty:
                    continue
                    
                true_factors_calc = calculate_factors(full_history_df, stk_cd, 'KIWOOM')
                true_factor_dates = {f['event_dt'] for f in true_factors_calc}
                
                obsolete_dates = [] # 삭제할 날짜 목록
                for event_dt in event_dates_in_db: # DB에 N일 이내로 기록됐던 이벤트 날짜
                    if event_dt not in true_factor_dates:
                        obsolete_dates.append(event_dt)
                
                # (J) 오류 팩터 일괄 삭제
                if obsolete_dates:
                    db.delete_adjustment_factors(stk_cd, obsolete_dates)
                    
            except Exception as e:
                logger.error(f"[{stk_cd}] 팩터 정리 중 오류 발생: {e}", exc_info=False)

    # --- 4. (기존) 분봉 수집 및 시스템 상태 업데이트 ---
    logger.info("--- [4/4] 분봉 수집 및 시스템 상태 업데이트 시작 ---")
    
    # 4-1. 선별 종목 분봉 수집
    logger.info("분봉 데이터 수집 중...")
    current_quarter_str = f"{today.year}Q{(today.month - 1) // 3 + 1}"
    all_targets_stocks = []

    for market in ['KOSPI', 'KOSDAQ']:
        logger.info(f"'{current_quarter_str}' {market} 시장 대상 확인...")
        target_history = db.get_minute_target_history(quarter=current_quarter_str, market=market)
        
        if target_history:
            logger.info(f"기존에 선정된 대상 {len(target_history)}개를 재사용합니다.")
            all_targets_stocks.extend([item['symbol'] for item in target_history])
        else:
            logger.info(f"새 분기의 첫 실행일이므로 {market} 대상을 새로 선정하여 DB에 저장합니다.")
            new_targets = target_selector.get_target_stocks(db, today.year, (today.month - 1) // 3 + 1, market, 200)
            if new_targets:
                db.upsert_minute_target_history(new_targets)
                all_targets_stocks.extend([item['symbol'] for item in new_targets])
            else:
                logger.warning(f"{market} 시장의 신규 대상을 선정하지 못했습니다.")
    
    for code in tqdm(all_targets_stocks, desc="일일 분봉 수집 중"):
        try:
            minute_data = api.get_minute_chart(code, start_date=today.strftime('%Y%m%d'))
            if minute_data:
                # --- [★핵심 수정★] ---
                # 분봉 데이터에도 'stk_cd' 주입
                for item in minute_data: item['stk_cd'] = code
                # --- [★수정 완료★] ---
                transformed_minute_data = utils.transform_data(minute_data, source='kiwoom', data_type='minute_ohlcv')
                db.upsert_ohlcv_data('minute_ohlcv', transformed_minute_data)
            time.sleep(0.5) # Kiwoom API Rate Limit
        except Exception as e:
            logger.warning(f"'{code}' 분봉 수집 실패: {e}")
            
    # 4-2. 시스템 상태 업데이트
    try:
        milestone = db._execute_query("SELECT 1 FROM system_milestones WHERE milestone_name = 'SYSTEM:LIVE:DAILY_COLLECTION'", fetch='one')
        if not milestone:
            db.set_milestone('SYSTEM:LIVE:DAILY_COLLECTION', today, "시스템 공식 일일 자동 수집 시작")
    except Exception as e:
        logger.error("마일스톤 업데이트 중 에러 발생", exc_info=True)

    logger.info(f"========== [Mode: daily_update] {date.today()} 작업 성공적으로 완료 ==========")

def build_all_factors(db: DatabaseManager, logger: logging.Logger):
    """
    [Phase 1] 마스터 수정계수 구축
    DB에 저장된 모든 종목의 전체 시세 이력을 바탕으로
    수정계수를 역산하여 price_adjustment_factors 테이블에 저장합니다.
    """
    logger.info("🚀 Phase 1: 마스터 수정계수 데이터베이스 구축을 시작합니다.")
    
    try:
        # 1. db_manager에서 전체 종목 코드 리스트 가져오기
        # (active_only=False로 설정하여 상장폐지된 종목도 포함, 전체 이력 구축)
        stock_list_codes = db.get_all_stock_codes(active_only=False)
        
        if not stock_list_codes:
            logger.error("stock_master 테이블에 종목 정보가 없습니다. 스크립트를 종료합니다.")
            return
            
        logger.info(f"총 {len(stock_list_codes)}개 종목에 대한 수정계수 계산을 시작합니다.")

        # 2. 각 종목을 순회하며 팩터 계산 및 저장 (tqdm으로 진행률 표시)
        for stk_cd in tqdm(stock_list_codes, desc="전체 종목 팩터 계산 중"):
            try:
                # 3. DB에서 계산용 OHLCV 데이터 조회 (교집합 기간 보장)
                ohlcv_df = db.fetch_ohlcv_for_factor_calc(stk_cd)
                
                if ohlcv_df.empty:
                    logger.debug(f"[{stk_cd}] 원본/수정 시세 데이터가 없어 건너뜁니다.")
                    continue
                
                # 4. 팩터 계산 (KIWOOM 시세 기준)
                factors = calculate_factors(ohlcv_df, stk_cd, 'KIWOOM')
                
                if not factors:
                    logger.debug(f"[{stk_cd}] 탐지된 수정계수가 없습니다.")
                    continue
                    
                # 5. DB에 팩터 저장 (UPSERT)
                db.upsert_adjustment_factors(factors)
                # 너무 많은 로그를 방지하기 위해 DEBUG 레벨로 변경 (tqdm이 주 진행률 표시)
                logger.debug(f"[{stk_cd}] {len(factors)}개의 수정계수를 저장했습니다.")

            except Exception as e:
                logger.error(f"[{stk_cd}] 처리 중 오류 발생: {e}", exc_info=False)
                # 한 종목에서 오류가 나더라도 다음 종목으로 계속 진행
                continue

        logger.info("✅ Phase 1: 마스터 수정계수 데이터베이스 구축을 성공적으로 완료했습니다.")

    except Exception as e:
        logger.error(f"마스터 수정계수 구축 중 치명적인 오류 발생: {e}", exc_info=True)

# -----------------------------------------------------------------
# 테스트 모드 관련 설정 및 함수
# -----------------------------------------------------------------
TEST_SUFFIX = '_test'
TEST_STOCKS = ['005930', '035720'] # 삼성전자, 카카오

def run_pipeline_test(api: KiwoomREST, db: DatabaseManager, logger: logging.Logger):
    """
    [Mode] Test: 격리된 환경에서 'Phase 2 (v8.1)' 로직을 테스트합니다.
    1. (Setup) 테스트 테이블 생성
    2. (Setup) 테스트 종목 마스터, 전체 시세, 전체 팩터 구축
    3. (Simulate) DB 데이터 오염 (UPSERT 검증용 / DELETE 검증용)
    4. (Test) v8.1 일일 동기화 로직 실행 (자동 복구 검증)
    5. (Test) 분봉 수집 로직 실행
    """
    logger.info("========== [Mode: test] v10.2 로직 테스트 시작 ==========")
    
    # --- [테스트 Setup 1-3단계] 테스트 환경 및 초기 데이터 구축 ---
    try:
        logger.info("--- [1/6] 테스트용 임시 테이블 생성 ---")
        db.setup_test_tables(suffix=TEST_SUFFIX)

        logger.info("--- [2/6] 테스트 종목 마스터 구축 ---")
        # (API에서 전체 호출 후, TEST_STOCKS로 필터링하여 저장)
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')
        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']
        kospi_transformed = utils.transform_data(kospi_filtered, source='kiwoom', data_type='stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, source='kiwoom', data_type='stock_info')
        for item in kospi_transformed: item.update({'market_type': 'KOSPI', 'status': 'listed'})
        for item in kosdaq_transformed: item.update({'market_type': 'KOSDAQ', 'status': 'listed'})
        all_stocks_to_db = kospi_transformed + kosdaq_transformed
        test_stocks_to_db = [s for s in all_stocks_to_db if s.get('stk_cd') in TEST_STOCKS]
        db.upsert_stock_info(test_stocks_to_db, table_name=f'stock_info{TEST_SUFFIX}')

        logger.info("--- [3/6] 테스트 종목 초기 시세 및 팩터 구축 ---")
        for stk_cd in tqdm(TEST_STOCKS, desc="초기 데이터 구축 중"):
            # 1. 시세 수집 (전체 기간)
            raw_ohlcv = api.get_daily_chart(stk_cd, start_date=None, adjusted_price='0', max_requests=0)
            for item in raw_ohlcv:
                item['stk_cd'] = stk_cd
            adj_ohlcv = api.get_daily_chart(stk_cd, start_date=None, adjusted_price='1', max_requests=0)
            for item in adj_ohlcv:
                item['stk_cd'] = stk_cd
            if not raw_ohlcv or not adj_ohlcv: continue
            
            std_raw = utils.transform_data(raw_ohlcv, 'kiwoom', 'daily_ohlcv')
            std_adj = utils.transform_data(adj_ohlcv, 'kiwoom', 'daily_ohlcv')
            
            db.upsert_ohlcv_data(table_name=f'daily_ohlcv{TEST_SUFFIX}', data=std_raw)
            db.upsert_ohlcv_data(table_name=f'daily_ohlcv_adjusted_legacy{TEST_SUFFIX}', data=std_adj)
            
            # 2. 초기 팩터 계산
            adj_df = pd.DataFrame(std_adj)[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
            raw_df = pd.DataFrame(std_raw)[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
            df_merged = pd.merge(adj_df, raw_df, on='dt', how='inner')
            
            factors = calculate_factors(df_merged, stk_cd, 'KIWOOM_TEST')
            if factors:
                db.upsert_adjustment_factors(factors, table_name=f'price_adjustment_factors{TEST_SUFFIX}')
        
        logger.info("✅ 테스트 초기 데이터 구축 완료.")

    except Exception as e:
        logger.critical("테스트 환경 구축 중 치명적인 오류 발생", exc_info=True)
        return # 테스트 중단

    # --- [테스트 Setup 3.5단계] 데이터 오염 시뮬레이션 ---
    try:
        logger.info("--- [3.5/6] v8.1 로직 검증을 위해 데이터 오염 시뮬레이션 ---")
        #t_minus_2_dt = date.today() - timedelta(days=2)
        t_minus_3_dt = date.today() - timedelta(days=3)

        # 시뮬레이션 B (DELETE 검증): '005930'의 t-3일자에 '가짜' 팩터 삽입
        logger.info(f"  (Sim B) '005930'의 {t_minus_3_dt} 날짜에 가짜 팩터(99.0) 삽입...")
        fake_factor = {
            'stk_cd': '005930',
            'event_dt': t_minus_3_dt,
            'price_ratio': 99.0,
            'volume_ratio': 1/99.0,
            'price_source': 'KIWOOM_TEST',
            'details': json.dumps({"reason": "Fake factor for DELETE test"})
        }
        db.upsert_adjustment_factors([fake_factor], table_name=f'price_adjustment_factors{TEST_SUFFIX}')
        
        logger.info("✅ 데이터 오염 시뮬레이션 완료.")

    except Exception as e:
        logger.critical("데이터 오염 시뮬레이션 중 오류 발생", exc_info=True)
        return

    # --- [테스트 Test 4-5단계] v8.1 동기화 로직 검증 ---
    logger.info(f"--- [4/6] v8.1 일일 동기화 로직 테스트 시작 ---")
    
    try:
        today = date.today()
        N_DAYS_LOOKBACK = 10 
        N_DAYS_AGO_STR = (today - timedelta(days=N_DAYS_LOOKBACK)).strftime('%Y%m%d')
        
        # (A) 'price_adjustment_factors_test' 테이블에서 최근 이벤트 조회
        recent_event_map = db.get_recent_event_stocks_map(
            days=N_DAYS_LOOKBACK, 
            table_name=f'price_adjustment_factors{TEST_SUFFIX}'
        )
        
        # (B) 'stock_info_test' 테이블에서 테스트 대상 조회 (TEST_STOCKS 2개만 반환됨)
        test_stocks_from_db = db.get_all_stock_codes(
            active_only=True, 
            table_name=f'stock_info{TEST_SUFFIX}'
        )
        
        for stk_cd in tqdm(test_stocks_from_db, desc="v8.1 동기화 검증 중"):
            try:
                # (C) N일치(10일) 원본/수정 주가 동시 수집
                adj_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR, adjusted_price='1', max_requests=0)
                for item in adj_data_api:
                    item['stk_cd'] = stk_cd
                raw_data_api = api.get_daily_chart(stk_cd, start_date=N_DAYS_AGO_STR, adjusted_price='0', max_requests=0)
                for item in raw_data_api:
                    item['stk_cd'] = stk_cd

                if not raw_data_api or not adj_data_api: continue

                # --- (Sim A) UPSERT 검증 (API 응답 데이터 오염) ---
                if stk_cd == '035720':
                    t_minus_2_dt_str = (today - timedelta(days=2)).strftime('%Y%m%d')
                    found = False
                    for item in adj_data_api:
                        if item.get('dt') == t_minus_2_dt_str:
                            logger.info(f"  (Sim A) '035720'의 {t_minus_2_dt_str} API 응답 오염 (가상 팩터 0.98 적용)...")
                            original_prc = int(item['cur_prc'])
                            item['cur_prc'] = str(int(round(original_prc * 0.98))) # 2% 강제 하향
                            found = True
                            break
                    if not found:
                        logger.warning(f"  (Sim A) '035720'의 {t_minus_2_dt_str} 데이터가 API 응답에 없어 오염 실패.")
                # --- (Sim A 완료) ---

                # (D) [v8.1] API 응답 -> 표준 DF로 변환
                std_raw_df = pd.DataFrame(utils.transform_data(raw_data_api, 'kiwoom', 'daily_ohlcv'))
                std_adj_df = pd.DataFrame(utils.transform_data(adj_data_api, 'kiwoom', 'daily_ohlcv'))

                if std_raw_df.empty or std_adj_df.empty: continue
                
                # (E) [v8.1] 원본 일봉 저장 (테스트 테이블에)
                db.upsert_ohlcv_data(f'daily_ohlcv{TEST_SUFFIX}', std_raw_df.to_dict('records'))

                # (F) [v8.1] 팩터 계산을 위한 DataFrame 준비
                adj_df_renamed = std_adj_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
                raw_df_renamed = std_raw_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
                df_merged = pd.merge(adj_df_renamed, raw_df_renamed, on='dt', how='inner')
                
                # (G) [v8.1] 사전 필터링
                is_different = (std_adj_df['cls_prc'] != std_raw_df['cls_prc']).any()

                calculated_factors = []
                if is_different:
                    logger.info(f"[{stk_cd}] N일 내 가격 불일치 감지. 팩터 정밀 계산 실행.")
                    calculated_factors = calculate_factors(df_merged, stk_cd, 'KIWOOM_TEST')
                    
                    if calculated_factors:
                        # (H) [v8.1] (필터링 통과) 팩터 갱신 (신규/변경)
                        # (Sim A: 035720의 가상 팩터(0.98)가 여기서 UPSERT되어야 함)
                        db.upsert_adjustment_factors(
                            calculated_factors, 
                            table_name=f'price_adjustment_factors{TEST_SUFFIX}'
                        )
                
                # (I) [v8.1] '사라진' 팩터 삭제 (N일 기간 대상)
                db_factors = db.get_factors_by_date_range(
                    stk_cd, (today - timedelta(days=N_DAYS_LOOKBACK)), today,
                    table_name=f'price_adjustment_factors{TEST_SUFFIX}'
                )
                calculated_dates = {f['event_dt'] for f in calculated_factors}
                db_dates = {f['event_dt'] for f in db_factors}
                
                obsolete_dates = list(db_dates - calculated_dates)
                
                if obsolete_dates:
                    # (Sim B: 005930의 가짜 팩터(99.0)가 여기서 DELETE되어야 함)
                    db.delete_adjustment_factors(
                        stk_cd, obsolete_dates,
                        table_name=f'price_adjustment_factors{TEST_SUFFIX}'
                    )

                # (J) [v8.1] 작업 완료, 리스트에서 제거
                if stk_cd in recent_event_map:
                    del recent_event_map[stk_cd]

            except Exception as e:
                logger.error(f"[{stk_cd}] v8.1 동기화 중 오류: {e}", exc_info=False)
        
        # --- [테스트 5단계] '사라진' 팩터 정리 (Loop 2) ---
        if recent_event_map:
            logger.info(f"--- [5/6] '사라진' 팩터(오류) 검증 및 삭제 ({len(recent_event_map)}개) ---")
            for stk_cd, event_dates_in_db in tqdm(recent_event_map.items(), desc="오류 추정 팩터 정리 중"):
                try:
                    # (전체 기간 재계산으로 교차 검증)
                    full_history_df = db.fetch_ohlcv_for_factor_calc(
                        stk_cd,
                        table_name_raw=f'daily_ohlcv{TEST_SUFFIX}',
                        table_name_adj=f'daily_ohlcv_adjusted_legacy{TEST_SUFFIX}',
                        stock_info_table=f'stock_info{TEST_SUFFIX}'
                    )
                    if full_history_df.empty: continue
                        
                    true_factors_calc = calculate_factors(full_history_df, stk_cd, 'KIWOOM_TEST')
                    true_factor_dates = {f['event_dt'] for f in true_factors_calc}
                    obsolete_dates = [dt for dt in event_dates_in_db if dt not in true_factor_dates]
                    
                    if obsolete_dates:
                        db.delete_adjustment_factors(
                            stk_cd, obsolete_dates,
                            table_name=f'price_adjustment_factors{TEST_SUFFIX}'
                        )
                except Exception as e:
                    logger.error(f"[{stk_cd}] 팩터 정리 중 오류: {e}", exc_info=False)

    except Exception as e:
        logger.critical("v8.1 동기화 테스트 중 치명적인 오류 발생", exc_info=True)
        # 이 단계에서 실패해도 분봉 테스트는 진행
        
    # --- [테스트 6단계] 분봉 수집 로직 테스트 ---
    try:
        logger.info("--- [6/6] 분봉 수집 로직 테스트 시작 ---")
        
        # (A) 대상 선정 시뮬레이션
        current_quarter_str = f"{today.year}Q{(today.month - 1) // 3 + 1}"
        new_targets = [
            {'quarter': current_quarter_str, 'market': 'KOSPI', 'symbol': '005930', 'avg_trade_value': 999, 'rank': 1},
            {'quarter': current_quarter_str, 'market': 'KOSPI', 'symbol': '035720', 'avg_trade_value': 888, 'rank': 2}
        ]
        db.upsert_minute_target_history(new_targets, table_name=f'minute_target_history{TEST_SUFFIX}')
        
        # (B) 분봉 수집 실행 (run_daily_update의 4단계 로직 재사용)
        all_targets_stocks = db.get_minute_target_history(
            quarter=current_quarter_str, 
            market='KOSPI',
            table_name=f'minute_target_history{TEST_SUFFIX}'
        )
        all_targets_stocks = [t['symbol'] for t in all_targets_stocks]
        
        for code in tqdm(all_targets_stocks, desc="테스트 분봉 수집 중"):
            minute_data = api.get_minute_chart(code, start_date=today.strftime('%Y%m%d'))
            if minute_data:
                for item in minute_data: item['stk_cd'] = code
                transformed_minute_data = utils.transform_data(minute_data, source='kiwoom', data_type='minute_ohlcv')
                # (C) 저장
                db.upsert_ohlcv_data(table_name=f'minute_ohlcv{TEST_SUFFIX}', data=transformed_minute_data)
            time.sleep(0.5) # Kiwoom API Rate Limit
        
        logger.info("✅ 분봉 수집 로직 테스트 완료.")
        
    except Exception as e:
        logger.critical("분봉 수집 테스트 중 치명적인 오류 발생", exc_info=True)
        
    # --- 테스트 종료 ---
    logger.info("✅ [Mode: test] v10.2 전체 테스트 완료. '--mode cleanup_test'로 정리하세요.")

def run_cleanup_test(db: DatabaseManager, logger: logging.Logger):
    """
    [Mode] Cleanup Test: 테스트 모드에서 생성된 임시 테이블을 모두 삭제합니다.
    """
    logger.info("========== [Mode: cleanup_test] 테스트 데이터 정리 시작 ==========")
    try:
        db.cleanup_test_tables(suffix=TEST_SUFFIX)
        logger.info("✅ 모든 테스트용 임시 테이블이 성공적으로 삭제되었습니다.")
    except Exception as e:
        logger.critical("테스트 데이터 정리 중 치명적인 오류 발생", exc_info=True)

def _compare_financial_data(api_data: dict, db_data: dict, columns: list[str], logger: logging.Logger) -> bool:
    """
    [Phase 4-B Helper] API 신규 버전과 DB 최신 버전의 필드를 비교합니다.
    (v5.3: 변경 감지 시 WARNING 로그 출력)
    """
    if db_data is None:
        return True  # DB에 없음 = 신규 데이터 = 변경됨

    for col in columns:
        api_value = api_data.get(col)
        db_value = db_data.get(col)
        
        # [데이터 정합성] 0, 0.0, None은 모두 '없음'으로 동일 취급
        if api_value in (None, 0, 0.0): api_value = None
        if db_value in (None, 0, 0.0): db_value = None
            
        # [v5.2] DB의 Decimal 타입을 float으로 변환
        if isinstance(db_value, (int, float, Decimal)):
             db_value = float(db_value)
        if isinstance(api_value, (int, float)):
             api_value = float(api_value)

        # [v5.3] 비교 실패 시, 원인 로그를 WARNING 레벨로 출력
        if api_value != db_value:
            logger.warning(
                f"[{api_data.get('stk_cd')}/{api_data.get('stac_yymm')}] 변경 감지:"
                f" (Column: {col}, API_Type: {type(api_value)}, API_Value: {api_value}, "
                f"DB_Type: {type(db_value)}, DB_Value: {db_value})"
            )
            return True # 변경 감지
            
    return False  # 변경 없음

# kis 기업 재무정보 수집
def run_update_financials(kis_api: KisREST, db: DatabaseManager, logger: logging.Logger, target_stocks: list[str] = None):
    """
    [Mode] Phase 4-B: KIS 재무정보 수집 및 PIT 버전 관리 (v5.3 - 최종 수정본)
   
    """
    logger.info("========== [Mode: update_financials] 시작 ==========")
    
    # 1. 대상 종목 결정
    if target_stocks:
        logger.info(f"--stocks 인자로 {len(target_stocks)}개 종목을 대상으로 합니다.")
    else:
        logger.info("--stocks 인자가 없어, DB의 전체 상장 종목을 대상으로 합니다.")
        target_stocks = db.get_all_stock_codes(active_only=True)
        logger.info(f"총 {len(target_stocks)}개 상장 종목 조회 완료.")

    statements_to_insert = []
    ratios_to_insert = []

    # 2. 종목 순회
    for stk_cd in tqdm(target_stocks, desc="재무정보 수집 및 비교 중"):
        try:
            # 3. KIS API 일괄 호출
            all_fin_data = kis_api.fetch_all_financial_data(stk_cd, div_cls_code='1')

            # 4. API별로 변환 및 'stac_yymm'을 키로 하는 맵 생성
            api_maps = {}
            for api_name, data_list in all_fin_data.items():
                if not data_list or not isinstance(data_list, list):
                    continue
                
                # utils.transform_data로 API 응답을 변환
                transformed_list = utils.transform_data(data_list, 'kis', api_name)
                
                # 'stac_yymm'을 키로 하는 딕셔너리 생성
                api_maps[api_name] = {item['stac_yymm']: item for item in transformed_list}

            # 5. 모든 'stac_yymm' 키 수집
            all_yymm = set()
            for m in api_maps.values():
                all_yymm.update(m.keys())

            if not all_yymm:
                logger.warning(f"[{stk_cd}] API 응답 데이터가 비어있어 건너뜁니다.")
                continue

            # 6. 'stac_yymm' 기준으로 모든 재무 데이터를 하나의 레코드로 병합
            for yymm in all_yymm:
                
                # --- API 신규 버전 (병합된 레코드) ---
                api_statement_record = {'stk_cd': stk_cd, 'stac_yymm': yymm, 'div_cls_code': '1'}
                api_ratio_record = {'stk_cd': stk_cd, 'stac_yymm': yymm, 'div_cls_code': '1'}
                
                # 7개 API 맵에서 데이터를 꺼내 병합
                api_statement_record.update(api_maps.get('balance_sheet', {}).get(yymm, {}))
                api_statement_record.update(api_maps.get('income_statement', {}).get(yymm, {}))
                
                api_ratio_record.update(api_maps.get('financial_ratio', {}).get(yymm, {}))
                api_ratio_record.update(api_maps.get('profit_ratio', {}).get(yymm, {}))
                api_ratio_record.update(api_maps.get('other_major_ratios', {}).get(yymm, {}))
                api_ratio_record.update(api_maps.get('stability_ratio', {}).get(yymm, {}))
                api_ratio_record.update(api_maps.get('growth_ratio', {}).get(yymm, {}))

                # --- DB 최신 버전 (비교 대상) ---
                db_statement = db.get_latest_financial_statement(stk_cd, yymm, '1')
                db_ratio = db.get_latest_financial_ratio(stk_cd, yymm, '1')

                # 7. 변경 감지 (PIT)
                # (DB 스키마 정의)
                statement_cols = [
                    'cras', 'fxas', 'total_aset', 'flow_lblt', 'fix_lblt', 'total_lblt',
                    'cpfn', 'total_cptl', 'sale_account', 'sale_cost', 'sale_totl_prfi',
                    'bsop_prti', 'op_prfi', 'thtr_ntin'
                ]
                ratio_cols = [
                    'grs', 'bsop_prfi_inrt', 'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps',
                    'rsrv_rate', 'lblt_rate', 'cptl_ntin_rate', 'self_cptl_ntin_inrt',
                    'sale_ntin_rate', 'sale_totl_rate', 'eva', 'ebitda', 'ev_ebitda',
                    'bram_depn', 'crnt_rate', 'quck_rate', 'equt_inrt', 'totl_aset_inrt'
                ]

                # [v5.3] logger 인자 전달
                if _compare_financial_data(api_statement_record, db_statement, statement_cols, logger):
                    logger.debug(f"[{stk_cd}] {yymm} 재무제표 변경 감지. INSERT 대상 추가.")
                    statements_to_insert.append(api_statement_record)
                
                # [v5.3] logger 인자 전달
                if _compare_financial_data(api_ratio_record, db_ratio, ratio_cols, logger):
                    logger.debug(f"[{stk_cd}] {yymm} 재무비율 변경 감지. INSERT 대상 추가.")
                    ratios_to_insert.append(api_ratio_record)

        except KisAPIError as e:
            logger.error(f"[{stk_cd}] KIS API 오류 발생: {e} (Code: {e.error_code})")
            continue
        except Exception as e:
            logger.error(f"[{stk_cd}] 재무정보 처리 중 예외 발생: {e}", exc_info=True)
            continue

    # 8. 일괄 저장 (Loop 종료 후)
    logger.info("전체 종목 비교 완료. DB 일괄 INSERT 시작...")
    if statements_to_insert:
        db.insert_financial_statements(statements_to_insert)
    else:
        logger.info("신규/변경된 재무제표 데이터가 없습니다.")

    if ratios_to_insert:
        db.insert_financial_ratios(ratios_to_insert)
    else:
        logger.info("신규/변경된 재무비율 데이터가 없습니다.")

    logger.info("========== [Mode: update_financials] 성공적으로 완료 ==========")

def run_build_target_history(db: DatabaseManager, logger: logging.Logger):
    """
    [Mode] Phase 5 (v5): 과거 분봉 마이그레이션 대상 소급 선정
    
    target_selector.py를 사용하여 
    2019Q4 ~ 2025Q4 기간의 수집 대상을
    minute_target_history 테이블에 저장합니다.
    """
    logger.info("========== [Mode: build_target_history] 시작 ==========")
    logger.info("과거 분기별 분봉 수집 대상(minute_target_history) 소급 선정을 시작합니다.")

    # [v5] 1단계: (N-1분기 데이터로 N분기 대상) 선정 대상 분기 목록
    # 2019Q3 데이터 -> 2019Q4 대상
    # ...
    # 2025Q3 데이터 -> 2025Q4 대상
    historical_quarters = [
        # (Year, Quarter)
        (2019, 4),
        (2020, 1), (2020, 2), (2020, 3), (2020, 4),
        (2021, 1), (2021, 2), (2021, 3), (2021, 4),
        (2022, 1), (2022, 2), (2022, 3), (2022, 4),
        (2023, 1), (2023, 2), (2023, 3), (2023, 4),
        (2024, 1), (2024, 2), (2024, 3), (2024, 4),
        (2025, 1), (2025, 2), (2025, 3), (2025, 4),
    ]

    try:
        for year, quarter in tqdm(historical_quarters, desc="과거 분기별 대상 선정 중"):
            quarter_str = f"{year}Q{quarter}"
            logger.info(f"--- {quarter_str} 대상 선정 작업 시작 ---")
            
            # 1. KOSPI 대상 선정
            # target_selector.py는 year, quarter를 받으면 자동으로 직전 분기를 계산함
            kospi_targets = target_selector.get_target_stocks(
                db, year, quarter, 'KOSPI', 200 #
            )
            if kospi_targets:
                db.upsert_minute_target_history(kospi_targets)
                logger.info(f"{quarter_str} KOSPI {len(kospi_targets)}개 대상 저장 완료.")
            else:
                logger.warning(f"{quarter_str} KOSPI 대상을 선정하지 못했습니다. (직전 분기 일봉 데이터 확인 필요)")

            # 2. KOSDAQ 대상 선정
            kosdaq_targets = target_selector.get_target_stocks(
                db, year, quarter, 'KOSDAQ', 400 #
            )
            if kosdaq_targets:
                db.upsert_minute_target_history(kosdaq_targets)
                logger.info(f"{quarter_str} KOSDAQ {len(kosdaq_targets)}개 대상 저장 완료.")
            else:
                logger.warning(f"{quarter_str} KOSDAQ 대상을 선정하지 못했습니다. (직전 분기 일봉 데이터 확인 필요)")

    except Exception as e:
        logger.error(f"과거 분기 대상 선정 중 치명적인 오류 발생: {e}", exc_info=True)
        raise

    logger.info("========== [Mode: build_target_history] 성공적으로 완료 ==========")
    logger.info("다음 단계: '--mode migrate_minute_legacy --quarter [YYYYQN] --market [MARKET]' 실행")

def run_migrate_minute_legacy(db: DatabaseManager, logger: logging.Logger, 
                            quarter: str, market: str, source_dir: str):
    """
    [Mode] Phase 5 (v5): db_legacy/의 SQLite 데이터를 TimescaleDB로 마이그레이션
    
   
    """
    logger.info(f"========== [Mode: migrate_minute_legacy] 시작 ({quarter} {market}) ==========")
    
    # 1. (v5) 대상 종목 조회
    try:
        target_rows = db.get_minute_target_history(quarter, market)
        if not target_rows:
            logger.error(f"'{quarter} {market}'의 수집 대상이 'minute_target_history'에 없습니다.")
            logger.error("먼저 '--mode build_target_history'를 실행해야 합니다.")
            return
        
        target_symbols = {row['symbol'] for row in target_rows}
        logger.info(f"'{quarter} {market}' 대상 {len(target_symbols)}개 종목 마이그레이션 시작...")
        
    except Exception as e:
        logger.error(f"DB에서 '{quarter} {market}' 대상 조회 실패: {e}", exc_info=True)
        return

    # 2. (v5) 분기에 해당하는 월 목록 생성 (예: 2019Q4 -> [201910, 201911, 201912])
    try:
        year = int(quarter[:4])
        q_num = int(quarter[5])
        months = [f"{year}{((q_num-1)*3 + i):02d}" for i in [1, 2, 3]]
    except Exception as e:
        logger.error(f"잘못된 분기 형식입니다: {quarter}. (예: 2024Q4) - {e}")
        return

    # 3. (v5) 월별 SQLite 파일 순회
    base_path = Path(source_dir) # 예: 'db_legacy'
    
    for yyyymm in tqdm(months, desc=f"{quarter} {market} 월별 처리 중"):
        db_file_name = f"kw_1m_{market.lower()}_{yyyymm}.db"
        db_path = base_path / db_file_name
        
        # 4. (v5) 파일 누락 처리
        if not db_path.exists():
            logger.warning(f"[{yyyymm}] SQLite 파일 없음: {db_path} (Skip)")
            continue

        conn_sqlite = None
        try:
            conn_sqlite = sqlite3.connect(db_path)
            logger.info(f"[{yyyymm}] SQLite 파일 연결 성공: {db_path}")

            # 5. (v5) 대상 종목별 데이터 추출
            for stk_cd in tqdm(target_symbols, desc=f"[{yyyymm}] 종목 처리 중", leave=False):
                table_name = f"a{stk_cd}"
                
                try:
                    # 6. (v5) SQLite 행 추출
                    cursor = conn_sqlite.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchall()
                    
                    if not rows:
                        continue
                        
                    # 7. (v5) Kiwoom API 모의 형식으로 변환
                    mock_api_batch = []
                    for row in rows:
                        # (index, open, high, low, close, volume)
                        mock_api_response = {
                            'stk_cd': stk_cd,
                            'cntr_tm': str(row[0]), # YYYYMMDDHHmmss
                            'open_pric': str(row[1]),
                            'high_pric': str(row[2]),
                            'low_pric': str(row[3]),
                            'cur_prc': str(row[4]),
                            'trde_qty': str(row[5])
                        }
                        mock_api_batch.append(mock_api_response)

                    # 8. (v5) 표준 변환 (KST 적용)
                    transformed_data = utils.transform_data(mock_api_batch, 'kiwoom', 'minute_ohlcv')
                    
                    # 9. (v5) TimescaleDB에 UPSERT
                    if transformed_data:
                        db.upsert_ohlcv_data('minute_ohlcv', transformed_data)
                
                except sqlite3.OperationalError:
                    # (테이블 누락 처리)
                    logger.debug(f"[{yyyymm}] {stk_cd}: SQLite 테이블 '{table_name}' 없음 (Skip)")
                except Exception as e:
                    logger.error(f"[{yyyymm}] {stk_cd}: 처리 중 오류: {e}", exc_info=False)

        except Exception as e:
            logger.error(f"[{yyyymm}] SQLite 파일 처리 중 오류: {e}", exc_info=True)
        finally:
            if conn_sqlite:
                conn_sqlite.close()

    logger.info(f"========== [Mode: migrate_minute_legacy] 성공적으로 완료 ({quarter} {market}) ==========")
    logger.info("다음 단계: '--mode verify_migration --quarter [YYYYQN] --market [MARKET]' 실행")

def run_verify_migration(db: DatabaseManager, logger: logging.Logger, 
                         quarter: str, market: str, source_dir: str):
    """
    [Mode] Phase 5 (v5): SQLite 마이그레이션 데이터 무결성 검증
    
   
    """
    logger.info(f"========== [Mode: verify_migration] 시작 ({quarter} {market}) ==========")
    
    # 1. 대상 종목 조회 (migrate_legacy와 동일)
    try:
        target_rows = db.get_minute_target_history(quarter, market)
        if not target_rows:
            logger.error(f"'{quarter} {market}'의 수집 대상이 'minute_target_history'에 없습니다.")
            return
        
        target_symbols = {row['symbol'] for row in target_rows}
        logger.info(f"'{quarter} {market}' 대상 {len(target_symbols)}개 종목 검증 시작...")
        
    except Exception as e:
        logger.error(f"DB에서 '{quarter} {market}' 대상 조회 실패: {e}", exc_info=True)
        return

    # 2. 분기에 해당하는 월 및 날짜 범위 계산
    try:
        year = int(quarter[:4])
        q_num = int(quarter[5])
        months = [f"{year}{((q_num-1)*3 + i):02d}" for i in [1, 2, 3]]
        
        q_start_month = (q_num - 1) * 3 + 1
        q_start_date = datetime(year, q_start_month, 1).date()
        q_end_date = (q_start_date + relativedelta(months=3)) - relativedelta(days=1)
        
    except Exception as e:
        logger.error(f"잘못된 분기 형식입니다: {quarter}. (예: 2024Q4) - {e}")
        return

    # 3. (v5) 원본 (SQLite) 레코드 수 집계
    sqlite_total_count = 0
    base_path = Path(source_dir)
    
    logger.info("--- [1/3] 원본(SQLite) 데이터 카운트 시작 ---")
    for yyyymm in tqdm(months, desc=f"{quarter} {market} SQLite 스캔 중"):
        db_file_name = f"kw_1m_{market.lower()}_{yyyymm}.db"
        db_path = base_path / db_file_name
        
        if not db_path.exists():
            logger.warning(f"[{yyyymm}] SQLite 파일 없음: {db_path} (Skip)")
            continue

        conn_sqlite = None
        try:
            conn_sqlite = sqlite3.connect(db_path)
            for stk_cd in target_symbols:
                table_name = f"a{stk_cd}"
                try:
                    cursor = conn_sqlite.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    sqlite_total_count += count
                except sqlite3.OperationalError:
                    continue # 테이블 없음
        except Exception as e:
            logger.error(f"[{yyyymm}] SQLite 파일 처리 중 오류: {e}", exc_info=True)
        finally:
            if conn_sqlite:
                conn_sqlite.close()
                
    logger.info(f"--- [1/3] 원본(SQLite) 데이터 총 {sqlite_total_count}건 집계 완료 ---")

    # 4. (v5) 대상 (TimescaleDB) 레코드 수 집계
    logger.info("--- [2/3] 대상(TimescaleDB) 데이터 카운트 시작 ---")
    try:
        # target_symbols 리스트를 SQL의 IN (...) 절에 맞게 튜플로 변환
        target_symbols_tuple = tuple(target_symbols)
        
        # 쿼리 생성
        query = f"""
        SELECT COUNT(*) 
        FROM minute_ohlcv
        WHERE stk_cd IN %s
          AND dt_tm >= %s
          AND dt_tm <= %s;
        """
        
        # TimescaleDB는 KST 기준, q_start_date/q_end_date는 date 객체
        # KST ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        ts_start = datetime.combine(q_start_date, datetime.min.time(), tzinfo=kst)
        ts_end = datetime.combine(q_end_date, datetime.max.time(), tzinfo=kst)

        pg_result = db._execute_query(
            query, 
            (target_symbols_tuple, ts_start, ts_end), 
            fetch='one'
        )
        pg_total_count = pg_result['count']
        logger.info(f"--- [2/3] 대상(TimescaleDB) 데이터 총 {pg_total_count}건 집계 완료 ---")
        
    except Exception as e:
        logger.error(f"TimescaleDB 카운트 중 오류 발생: {e}", exc_info=True)
        return

    # 5. (v5) 최종 비교
    logger.info("--- [3/3] 최종 무결성 검증 ---")
    if sqlite_total_count == pg_total_count:
        logger.info(f"✅ [검증 성공] {quarter} {market}: 원본(SQLite) {sqlite_total_count}건, 대상(PG) {pg_total_count}건 (일치)")
    else:
        logger.error(f"❌ [검증 실패] {quarter} {market}: 원본(SQLite) {sqlite_total_count}건, 대상(PG) {pg_total_count}건 (불일치)")

    logger.info(f"========== [Mode: verify_migration] 성공적으로 완료 ({quarter} {market}) ==========")

def main():
    parser = argparse.ArgumentParser(description="KDMS 데이터 수집 시스템")
    
    # [수정] 'update_financials' 추가
    parser.add_argument('--mode', type=str, 
                        choices=['build_master', 'seed_daily_market', 'daily_update',
                                 'build_factors', 'build_target_history',
                                 'migrate_minute_legacy', 'verify_migration', 'update_financials',
                                 'test', 'cleanup_test'], 
                        default='daily_update')
                        
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ'], 
                        help="'seed_daily_market' 모드에서 사용할 시장")
    
    # [신규] --stocks 인자 추가
    parser.add_argument('--stocks', type=str, nargs='+', 
                        help="'update_financials' 모드에서 특정 종목만 지정 (예: 005930 035720)")
                        
    args = parser.parse_args()

    logger = utils.setup_logger('main_collection')
    
    # [수정] KIS API 초기화 로직 (이전 단계에서 이미 적용됨)
    logger.info("Kiwoom API (시세/팩터) 초기화...")
    api = KiwoomREST(mock=False, log_level=3)
    
    logger.info("KIS API (휴장일/재무) 초기화...")
    kis_api = None
    try:
        kis_api = KisREST(mock=False, log_level=1) #
    except Exception as e:
        logger.error(f"KIS API 초기화 실패: {e}. 휴장일/재무 기능이 제한될 수 있습니다.")
    
    logger.info("DatabaseManager 초기화...")
    db = DatabaseManager()

    try:
        if args.mode == 'build_master':
            run_build_master(api, db, logger)
            
        elif args.mode == 'seed_daily_market':
            if not args.market:
                logger.error("'seed_daily_market' 모드를 사용하려면 --market 인자(KOSPI 또는 KOSDAQ)가 반드시 필요합니다.")
                sys.exit(1)
            run_seed_daily_market(api, db, logger, args.market)
            
        elif args.mode == 'daily_update':
            if not kis_api:
                logger.critical("KIS API가 초기화되지 않아 휴장일 확인이 불가능합니다. 'daily_update' 작업을 중단합니다.")
                sys.exit(1)
            run_daily_update(api, kis_api, db, logger)
            
        elif args.mode == 'build_factors':
            logger.info("="*50)
            logger.info("수정계수 마스터 데이터 구축 모드를 시작합니다.")
            logger.info("="*50)
            build_all_factors(db, logger)
            
        # [신규] 'update_financials' 모드 처리
        elif args.mode == 'update_financials':
            if not kis_api:
                logger.critical("KIS API가 초기화되지 않아 재무정보 수집이 불가능합니다. 'update_financials' 작업을 중단합니다.")
                sys.exit(1)
            logger.info("="*50)
            logger.info("KIS 재무정보 수집 모드를 시작합니다.")
            logger.info("="*50)
            run_update_financials(kis_api, db, logger, args.stocks)
        
        # [신규] 'build_target_history' 모드 처리
        elif args.mode == 'build_target_history':
            logger.info("="*50)
            logger.info("Phase 5 (v5): 과거 분봉 수집 대상 소급 선정을 시작합니다.")
            logger.info("="*50)
            run_build_target_history(db, logger)
        
        # [신규] 'migrate_minute_legacy' 모드 처리
        elif args.mode == 'migrate_minute_legacy':
            if not args.quarter or not args.market:
                logger.error("'migrate_minute_legacy' 모드는 --quarter와 --market 인자가 반드시 필요합니다.")
                sys.exit(1)
            logger.info("="*50)
            logger.info(f"Phase 5 (v5): SQLite 마이그레이션 시작 ({args.quarter} {args.market})")
            logger.info("="*50)
            run_migrate_minute_legacy(db, logger, args.quarter, args.market, args.source_dir)

        # [신규] 'verify_migration' 모드 (자리만 마련)
        elif args.mode == 'verify_migration':
            if not args.quarter or not args.market:
                logger.error("'verify_migration' 모드는 --quarter와 --market 인자가 반드시 필요합니다.")
                sys.exit(1)
            logger.info("="*50)
            logger.info(f"Phase 5 (v5): 마이그레이션 검증 시작 ({args.quarter} {args.market})")
            logger.info("="*50)
            run_verify_migration(db, logger, args.quarter, args.market, args.source_dir)
                        
        elif args.mode == 'test':
            logger.info("="*50)
            logger.info("파이프라인 테스트 모드를 시작합니다. (데이터 격리)")
            logger.info("="*50)
            run_pipeline_test(api, db, logger)
            
        elif args.mode == 'cleanup_test':
            logger.info("="*50)
            logger.info("테스트 모드 데이터 정리를 시작합니다.")
            logger.info("="*50)
            run_cleanup_test(db, logger)
            
    except Exception as e:
        logger.critical("메인 프로세스에서 처리되지 않은 예외 발생", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()