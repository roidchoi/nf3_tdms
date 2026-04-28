#
# tasks/daily_task.py
#
"""
일일 데이터 업데이트 태스크 (PRD Phase 6 아키텍처)
- daily_update.py의 실제 로직을 FastAPI/APScheduler 백그라운드 태스크로 이식
- PRD 4.1.2에 따라 job_statuses 딕셔너리를 실시간으로 업데이트
- tqdm 스타일의 지능형 로그 추가
"""
import logging
import time
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any

# --- [이식] daily_update 소스코드.md의 임포트 ---
from collectors.kiwoom_rest import KiwoomREST
from collectors.kis_rest import KisREST
from collectors.db_manager import DatabaseManager
from collectors.factor_calculator import calculate_factors
from collectors import utils, target_selector
from collectors.exceptions import TokenAuthError  # (신규) 치명적 인증 에러
from test_utils import TestEnvironment
# ----------------------------------------------

# 로거 설정 (모듈 레벨)
logger = logging.getLogger(__name__)


def run_daily_update(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    일일 데이터 업데이트 실행 함수 (PRD 4.1.2 기반)
    
    :param job_statuses: 전역 상태 딕셔너리 (FastAPI에서 전달)
    :param test_mode: 테스트 모드 여부
    """
    job_id = "daily_update"
    start_time = datetime.now()
    today = start_time.date()
    
    # --- [PRD 4.1.2] 상태 초기화 ---
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "0/4",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"작업 시작 (Test Mode: {test_mode})",
        "stocks_processed": 0,
        "total_stocks": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        # --- [이식] daily_update.py main()의 객체 초기화 ---
        logger.info(f"[{job_id}] Kiwoom API 초기화...")
        api = KiwoomREST(mock=test_mode, log_level=3)
        
        logger.info(f"[{job_id}] KIS API 초기화...")
        kis_api = KisREST(mock=test_mode, log_level=1)
        
        logger.info(f"[{job_id}] DatabaseManager 초기화...")
        db = DatabaseManager()
        
        test_env = TestEnvironment(db, logger) if test_mode else None
        
        # 테스트 모드 초기 설정
        if test_mode:
            logger.info(f"[{job_id}] 테스트 모드 설정: 테스트 테이블 구성")
            test_env.setup_test_tables()
            test_env.simulate_data_corruption()
        # ----------------------------------------------

        # --- [Phase 0/4] 거래일 확인 ---
        job_statuses[job_id].update({
            "phase": "0/4",
            "phase_name": "거래일 확인",
            "progress": 5,
            "last_log": "KIS API로 캘린더 확인 중..."
        })
        if not _check_trading_day(kis_api, db, logger, today):
            logger.info(f"[{job_id}] 오늘은 휴장일입니다. 작업을 종료합니다.")
            job_statuses[job_id].update({
                "is_running": False,
                "last_status": "skipped (휴장일)",
                "end_time": datetime.now().isoformat(),
                "duration": f"{(datetime.now() - start_time).total_seconds():.1f}초"
            })
            return # 함수 종료
        
        # --- [Phase 1/4] 종목 정보 갱신 ---
        job_statuses[job_id].update({
            "phase": "1/4",
            "phase_name": "종목 정보 갱신",
            "progress": 25,
            "last_log": "Kiwoom API로 KOSPI/KOSDAQ 종목 갱신 중..."
        })
        _update_stock_info(api, db, logger, test_mode, test_env)
        
        # --- [Phase 2/4] 팩터 및 원본 시세 동기화 ---
        job_statuses[job_id].update({
            "phase": "2/4",
            "phase_name": "팩터 및 시세 동기화",
            "progress": 50,
            "last_log": "N일치 팩터 및 시세 동기화 시작..."
        })
        # (이식) _sync_factors_and_prices가 job_statuses를 업데이트하도록 전달
        _sync_factors_and_prices(
            api, db, logger, today, test_mode, test_env, 
            job_statuses, job_id
        )
        
        # --- [Phase 3/4] 분봉 수집 ---
        job_statuses[job_id].update({
            "phase": "3/4",
            "phase_name": "분봉 수집",
            "progress": 75,
            "last_log": "선별 종목 분봉 수집 시작..."
        })
        # (이식) _collect_minute_data가 job_statuses를 업데이트하도록 전달
        _collect_minute_data(
            api, db, logger, today, test_mode, test_env,
            job_statuses, job_id
        )

        # --- [Phase 4/5] 시스템 상태 업데이트 ---
        job_statuses[job_id].update({
            "phase": "4/5",
            "phase_name": "시스템 상태 업데이트",
            "progress": 90,
            "last_log": "시스템 마일스톤 기록 중..."
        })
        _update_system_status(db, logger, today)

        # --- [Phase 5/5] KRX 시가총액 데이터 수집 (신규) ---
        job_statuses[job_id].update({
            "phase": "5/5",
            "phase_name": "KRX 시가총액 데이터 수집",
            "progress": 95,
            "last_log": "pykrx로 시가총액 데이터 수집 중..."
        })

        from collectors.krx_loader import KRXLoader

        krx_loader = KRXLoader(logger)

        # [중요] Today 데이터 수집 (장 마감 후 실행이므로 당일 데이터 수집)
        today_str = today.strftime('%Y%m%d')

        try:
            market_cap_data = krx_loader.get_market_cap_data(today_str)
            if market_cap_data:
                count = db.upsert_daily_market_cap(market_cap_data)
                logger.info(f"[{job_id}] KRX 시가총액 데이터 {count}건 저장 완료 (날짜: {today_str})")
                job_statuses[job_id]["last_log"] = f"시가총액 {count}건 저장 완료"
            else:
                logger.warning(f"[{job_id}] KRX 시가총액 데이터 없음 (날짜: {today_str}, 휴장일 가능)")
                job_statuses[job_id]["last_log"] = "시가총액 데이터 없음 (휴장일)"
        except Exception as e:
            logger.error(f"[{job_id}] KRX 시가총액 수집 실패: {e}", exc_info=True)
            job_statuses[job_id]["last_log"] = f"시가총액 수집 실패: {str(e)}"
            # (non-critical이므로 작업 실패로 처리하지 않고 계속)

        # --- [Phase 6/6] 수정주가 일봉 DB 갱신 (신규) ---
        job_statuses[job_id].update({
            "phase": "6/6",
            "phase_name": "수정주가 일봉 DB 갱신",
            "progress": 98,
            "last_log": "daily_ohlcv_adjusted 갱신 시작..."
        })
        adj_table = job_statuses[job_id].pop('_adj_table', 'daily_ohlcv_adjusted')
        _update_adjusted_ohlcv(db, logger, today, adj_table, job_statuses, job_id)

        # --- [PRD 4.1.2] 완료 상태 ---
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # (신규) 인증 에러로 중단되었는지 확인
        if job_statuses[job_id].get("last_status") == "error":
            # 이미 에러 상태로 설정되었으면 성공 처리 건너뜀
            logger.warning(
                f"[{job_id}] 작업이 인증 에러로 중단되었습니다. "
                f"성공 처리를 건너뜁니다."
            )
            return

        final_msg = f"일일 업데이트 성공적으로 완료 (소요시간: {duration/60:.1f}분)"

        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초 ({duration/60:.1f}분)",
            "last_log": final_msg
        })
        logger.info(f"✅ [{job_id}] {final_msg}")

    except Exception as e:
        logger.critical(f"[{job_id}] 치명적 오류 발생: {e}", exc_info=True)
        # --- [PRD 4.1.2] 실패 상태 ---
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now().isoformat()
        })
    
    finally:
        # --- [PRD 4.1.2] (안전장치) 항상 is_running = False 보장 ---
        job_statuses[job_id]["is_running"] = False

#
# --- (이식) daily_update.py의 헬퍼 함수들 ---
#

def _check_trading_day(kis_api: KisREST, db: DatabaseManager, logger: logging.Logger, today: date) -> bool:
    """
    거래일 캘린더 확인 (daily_update.py 원본 로직)
    """
    logger.info("--- [0/4] 거래일 캘린더 확인 ---")
    try:
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
        
        if needs_refresh:
            logger.info("캘린더 캐시가 만료되어 KIS API로 갱신합니다.")
            success = utils.update_trading_calendar(kis_api, db)
            if not success:
                logger.warning("캘린더 갱신 실패. DB 캐시로만 작업합니다.")
        
        today_info = db._execute_query(
            "SELECT opnd_yn FROM trading_calendar WHERE dt = %s;",
            (today,), fetch='one'
        )
        
        if not today_info:
            logger.critical(f"[{today}] 거래일 정보를 DB에서 찾을 수 없습니다.")
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


def _update_stock_info(api: KiwoomREST, db: DatabaseManager, logger: logging.Logger,
                       test_mode: bool, test_env: TestEnvironment):
    """
    종목 정보 갱신 (daily_update.py 원본 로직)
    """
    logger.info("--- [1/4] 종목 정보 갱신 ---")
    try:
        kospi_raw = api.get_stock_info(market_type='0')
        kosdaq_raw = api.get_stock_info(market_type='10')
        
        kospi_filtered = [s for s in kospi_raw if s.get('marketName') == '거래소']
        kosdaq_filtered = [s for s in kosdaq_raw if s.get('marketName') == '코스닥']
        
        kospi_transformed = utils.transform_data(kospi_filtered, 'kiwoom', 'stock_info')
        kosdaq_transformed = utils.transform_data(kosdaq_filtered, 'kiwoom', 'stock_info')
        
        for item in kospi_transformed:
            item.update({'market_type': 'KOSPI', 'status': 'listed'})
        for item in kosdaq_transformed:
            item.update({'market_type': 'KOSDAQ', 'status': 'listed'})
        
        all_stocks = kospi_transformed + kosdaq_transformed
        
        if test_mode:
            all_stocks = test_env.filter_test_stocks(all_stocks)
            table_name = test_env.get_test_table_name('stock_info')
            logger.info(f"테스트: {len(all_stocks)}개 종목만 갱신")
        else:
            table_name = 'stock_info'
        
        db.upsert_stock_info(all_stocks, table_name=table_name)
        logger.info("✅ 종목 정보 갱신 완료")
    
    except Exception as e:
        logger.error("종목 정보 갱신 실패", exc_info=True)
        raise # 상위 try-except로 전파


def _sync_factors_and_prices(api: KiwoomREST, db: DatabaseManager, logger: logging.Logger,
                              today: date, test_mode: bool, test_env: TestEnvironment,
                              job_statuses: Dict, job_id: str): # [수정] PRD 4.1.2를 위한 파라미터 추가
    """
    팩터 및 원본 시세 동기화 (daily_update.py 원본 로직)
    [수정] tqdm -> job_statuses 업데이트로 변경
    """
    logger.info("--- [2/4] 팩터 및 원본 시세 동기화 ---")
    
    N_DAYS_LOOKBACK = 10
    N_DAYS_AGO_STR = (today - timedelta(days=N_DAYS_LOOKBACK)).strftime('%Y%m%d')
    N_DAYS_RECENT = 10
    
    # ... (테이블명 결정 로직 - 원본과 동일) ...
    if test_mode:
        stock_table = test_env.get_test_table_name('stock_info')
        raw_table = test_env.get_test_table_name('daily_ohlcv')
        factor_table = test_env.get_test_table_name('price_adjustment_factors')
        adj_table = test_env.get_test_table_name('daily_ohlcv_adjusted')  # (신규)
        price_source = 'KIS_TEST'
    else:
        stock_table = 'stock_info'
        raw_table = 'daily_ohlcv'
        factor_table = 'price_adjustment_factors'
        adj_table = 'daily_ohlcv_adjusted'  # (신규)
        price_source = 'KIS'  # (수정) KIWOOM → KIS

    # (신규) 일봉 조회에 사용할 날짜 문자열
    today_str = today.strftime('%Y%m%d')

    recent_event_map = db.get_recent_event_stocks_map(
        days=N_DAYS_RECENT, table_name=factor_table
    )
    if recent_event_map:
        logger.info(f"최근 {N_DAYS_RECENT}일 내 이벤트 종목: {len(recent_event_map)}개")
    
    all_stocks = db.get_all_stock_codes(active_only=True, table_name=stock_table)
    logger.info(f"총 {len(all_stocks)}개 종목 동기화 시작")
    
    # [수정] tqdm -> job_statuses 업데이트
    total = len(all_stocks)
    job_statuses[job_id]["total_stocks"] = total
    loop_start_time = time.time()
    
    for idx, stk_cd in enumerate(all_stocks):
        
        # --- [통합] PRD 4.1.2 실시간 상태 업데이트 ---
        if idx % 50 == 0: # 10종목마다 업데이트
            progress = 50 + (idx / total * 25)  # Phase 2는 50% ~ 75%
            
            elapsed = time.time() - loop_start_time
            if elapsed == 0: elapsed = 1e-6 
            
            items_per_sec = (idx + 1) / elapsed
            
            if items_per_sec == 0:
                eta_str = "N/A"
            else:
                eta_seconds = (total - (idx + 1)) / items_per_sec
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
            
            progress_msg = (
                f"[{job_id}] ({idx+1}/{total}) "
                f"[{items_per_sec:.1f}it/s, ETA: {eta_str}] "
                f"... (현재: {stk_cd})"
            )
            
            # (신규) logger.info로 유용한 로그 출력
            logger.info(progress_msg)

            job_statuses[job_id].update({
                "progress": progress,
                "stocks_processed": idx,
                "last_log": progress_msg
            })
        # ----------------------------------------
            
        try:
            # --- [수정] KIS API로 수정/원본 일봉 수집 ---
            # KIS: adj_price='0' = 수정주가, adj_price='1' = 원본주가 (키움과 반대)
            adj_data_api = kis_api.fetch_daily_price(
                stk_cd, N_DAYS_AGO_STR, today_str, adj_price='0'
            )
            raw_data_api = kis_api.fetch_daily_price(
                stk_cd, N_DAYS_AGO_STR, today_str, adj_price='1'
            )

            if not raw_data_api or not adj_data_api:
                logger.debug(f"[{stk_cd}] KIS API 응답 데이터가 부족하여 건너뜁니다.")
                continue

            # stk_cd 추가 (KIS 응답에는 종목코드 미포함)
            for item in raw_data_api: item['stk_cd'] = stk_cd
            for item in adj_data_api: item['stk_cd'] = stk_cd

            # (수정) 'kiwoom' → 'kis' 소스로 변환, 날짜순 정렬 보장
            std_raw_df = pd.DataFrame(
                utils.transform_data(raw_data_api, 'kis', 'daily_ohlcv')
            ).sort_values('dt').reset_index(drop=True)
            std_adj_df = pd.DataFrame(
                utils.transform_data(adj_data_api, 'kis', 'daily_ohlcv')
            ).sort_values('dt').reset_index(drop=True)
            
            if std_raw_df.empty or std_adj_df.empty:
                logger.debug(f"[{stk_cd}] 변환된 데이터가 비어있어 건너뜁니다.")
                continue
            
            db.upsert_ohlcv_data(raw_table, std_raw_df.to_dict('records'))
            
            adj_df_renamed = std_adj_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
            raw_df_renamed = std_raw_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
            df_merged = pd.merge(adj_df_renamed, raw_df_renamed, on='dt', how='inner')
            
            oldest_adj = std_adj_df.iloc[0]['cls_prc']
            oldest_raw = std_raw_df.iloc[0]['cls_prc']
            
            calculated_factors = []
            if oldest_adj == oldest_raw:
                if stk_cd in recent_event_map:
                    db_factors = db.get_factors_by_date_range(
                        stk_cd, std_adj_df.iloc[0]['dt'], today, table_name=factor_table
                    )
                    obsolete_dates = [f['event_dt'] for f in db_factors]
                    if obsolete_dates:
                        db.delete_adjustment_factors(stk_cd, obsolete_dates, table_name=factor_table)
                        logger.info(f"[{stk_cd}] {len(obsolete_dates)}개 팩터 삭제 (이벤트 사라짐)")
                    del recent_event_map[stk_cd]
                continue
            
            calculated_factors = calculate_factors(df_merged, stk_cd, price_source)
            
            if calculated_factors:
                for f in calculated_factors:
                    ratio = f.get('price_ratio', 0)
                    f['price_ratio'] = round(1.0 / ratio, 10) if ratio > 0 else 0.0
                    
            if calculated_factors:
                db.upsert_adjustment_factors(calculated_factors, table_name=factor_table)
                logger.debug(f"[{stk_cd}] {len(calculated_factors)}개 팩터 UPSERT")
            
            db_factors = db.get_factors_by_date_range(
                stk_cd, std_adj_df.iloc[0]['dt'], today, table_name=factor_table
            )
            calculated_dates = {f['event_dt'] for f in calculated_factors}
            db_dates = {f['event_dt'] for f in db_factors}
            obsolete_dates = list(db_dates - calculated_dates)
            if obsolete_dates:
                db.delete_adjustment_factors(stk_cd, obsolete_dates, table_name=factor_table)
                logger.info(f"[{stk_cd}] {len(obsolete_dates)}개 팩터 삭제 (N일 검증)")

            if stk_cd in recent_event_map:
                del recent_event_map[stk_cd]

        except TokenAuthError as e:
            # 치명적 인증 에러 → 작업 즉시 중단 (Fail-Fast)
            logger.critical(
                f"❌ [{job_id}] Kiwoom API 인증 복구 불가 에러 발생. 작업을 즉시 중단합니다."
            )
            logger.critical(f"원인: {e}")

            # job_statuses 상태를 'error'로 업데이트
            job_statuses[job_id].update({
                "is_running": False,
                "last_status": "error",
                "end_time": datetime.now().isoformat(),
                "last_log": f"Kiwoom API 인증 실패로 작업 중단: {str(e)}",
                "progress": 0
            })

            # 작업 즉시 중단 (함수 종료)
            return

        except Exception as e:
            logger.error(f"[{stk_cd}] 팩터 동기화 오류(KIS): {e}", exc_info=False)
            # (일반 오류는 다음 종목으로 계속)
    
    # (신규) 루프 종료 직후 최종 진행률 로깅
    loop_elapsed = time.time() - loop_start_time
    final_progress_msg = (
        f"[{job_id}] ({total}/{total}) "
        f"팩터/시세 동기화 완료. (소요시간: {time.strftime('%H:%M:%S', time.gmtime(loop_elapsed))})"
    )
    logger.info(final_progress_msg)    
    
    # Loop 2: API 오류 추정 종목 정리 (원본 로직 동일)
    if recent_event_map:
        logger.info(f"--- [2.5/4] API 오류 추정 종목 팩터 검증 ({len(recent_event_map)}개) ---")
        job_statuses[job_id]["last_log"] = f"API 오류 추정 {len(recent_event_map)}개 검증"
        
        # ... (테이블명 재확인 - 원본과 동일) ...
        if test_mode:
            fetch_raw_table = test_env.get_test_table_name('daily_ohlcv')
            fetch_adj_table = test_env.get_test_table_name('daily_ohlcv_adjusted_legacy')
            fetch_stock_table = test_env.get_test_table_name('stock_info')
        else:
            fetch_raw_table = 'daily_ohlcv'
            fetch_adj_table = 'daily_ohlcv_adjusted_legacy'
            fetch_stock_table = 'stock_info'

        # [수정] tqdm -> 단순 루프
        for stk_cd in recent_event_map.keys():
            try:
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
    
    logger.info("✅ 팩터 및 원본 시세 동기화 완료 (KIS 소스)")

    # (신규) Phase 4 말미에 adj_table 정보를 job_statuses에 전달 (Phase 6에서 사용)
    job_statuses[job_id]['_adj_table'] = adj_table


def _collect_minute_data(api: KiwoomREST, db: DatabaseManager, logger: logging.Logger,
                         today: date, test_mode: bool, test_env: TestEnvironment,
                         job_statuses: Dict, job_id: str): # [수정] PRD 4.1.2를 위한 파라미터 추가
    """
    분봉 수집 (daily_update.py 원본 로직)
    [수정] tqdm -> job_statuses 업데이트로 변경
    tqdm 스타일의 지능형 로그 추가
    """
    logger.info("--- [3/4] 분봉 데이터 수집 ---")
    
    current_quarter_str = f"{today.year}Q{(today.month - 1) // 3 + 1}"
    
    # ... (테이블명 결정 - 원본과 동일) ...
    if test_mode:
        target_table = test_env.get_test_table_name('minute_target_history')
        minute_table = test_env.get_test_table_name('minute_ohlcv')
    else:
        target_table = 'minute_target_history'
        minute_table = 'minute_ohlcv'
    
    all_target_stocks = []
    
    # ... (시장별 대상 확인 로직 - 원본과 동일) ...
    for market in ['KOSPI', 'KOSDAQ']:
        target_history = db.get_minute_target_history(
            quarter=current_quarter_str, market=market, table_name=target_table
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
    
    # [수정] tqdm -> job_statuses 및 로깅 변수
    success_count = 0
    total = len(all_target_stocks)
    job_statuses[job_id]["total_stocks"] = total # total_stocks를 분봉 기준으로 덮어씀
    loop_start_time = time.time()

    for idx, code in enumerate(all_target_stocks):
        
        # --- [통합] PRD 4.1.2 실시간 상태 업데이트 ---
        if idx % 20 == 0: # 20종목마다 업데이트
            progress = 75 + (idx / total * 20)  # Phase 3는 75% ~ 95%

            elapsed = time.time() - loop_start_time
            if elapsed == 0: elapsed = 1e-6
            
            # (sleep(0.5) 때문에 it/s가 낮게 나옴)
            items_per_sec = (idx + 1) / elapsed 
            
            if items_per_sec == 0:
                eta_str = "N/A"
            else:
                eta_seconds = (total - (idx + 1)) / items_per_sec
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))

            progress_msg = (
                f"[{job_id}] ({idx+1}/{total}) "
                f"[{items_per_sec:.1f}it/s, ETA: {eta_str}] "
                f"... (현재: {code})"
            )
            
            # (신규) logger.info로 유용한 로그 출력
            logger.info(progress_msg)

            job_statuses[job_id].update({
                "progress": progress,
                "stocks_processed": idx,
                "last_log": progress_msg
            })
        # ----------------------------------------
            
        try:
            minute_data = api.get_minute_chart(code, start_date=today.strftime('%Y%m%d'))
            if minute_data:
                for item in minute_data:
                    item['stk_cd'] = code
                transformed = utils.transform_data(minute_data, 'kiwoom', 'minute_ohlcv')
                db.upsert_ohlcv_data(minute_table, transformed)
                success_count += 1
            time.sleep(0.5)  # Kiwoom API Rate Limit

        except TokenAuthError as e:
            # 치명적 인증 에러 → 작업 즉시 중단 (Fail-Fast)
            logger.critical(
                f"❌ [{job_id}] Kiwoom API 인증 복구 불가 에러 발생. 작업을 즉시 중단합니다."
            )
            logger.critical(f"원인: {e}")

            # job_statuses 상태를 'error'로 업데이트
            job_statuses[job_id].update({
                "is_running": False,
                "last_status": "error",
                "end_time": datetime.now().isoformat(),
                "last_log": f"Kiwoom API 인증 실패로 작업 중단: {str(e)}",
                "progress": 0
            })

            # 루프 즉시 중단
            break

        except Exception as e:
            # 일반 에러 → 로그만 남기고 다음 종목으로 계속
            logger.warning(f"'{code}' 분봉 수집 실패: {e}")
    
    # (신규) 루프 종료 직후 최종 진행률 로깅
    loop_elapsed = time.time() - loop_start_time
    logger.info(
        f"✅ 분봉 수집 완료: {success_count}/{total}개 성공. "
        f"(소요시간: {time.strftime('%H:%M:%S', time.gmtime(loop_elapsed))})"
    )


def _update_system_status(db: DatabaseManager, logger: logging.Logger, today: date):
    """
    시스템 상태 업데이트 (daily_update.py 원본 로직)
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

#
# --- (제거) daily_update.py의 main() 및 if __name__ == '__main__' ---
# (이 파일은 더 이상 직접 실행되지 않음)
#


def _update_adjusted_ohlcv(db: DatabaseManager, logger: logging.Logger, today: date,
                            adj_table: str, job_statuses: dict, job_id: str):
    """
    [신규] Phase 6/6: daily_ohlcv_adjusted 일봉 DB 자동 갱신.
    오늘 + N_REFRESH_DAYS 범위를 SQL CTE로 일괄 재계산하여 UPSERT합니다.
    (pandas 미사용, DB 레벨 완전 처리)

    갱신 범위 전략:
      - 7일치 배치 재계산으로 이벤트 발생 팔터(liquid stock) 처리.
      - 오늘 데이터는 반드시 포함됨.
    """
    N_REFRESH_DAYS = 7  # 배치 갱신 범위: 오늘로부터 N일
    logger.info("--- [6/6] 수정주가 일봉 DB (daily_ohlcv_adjusted) 갱신 ---")

    start_date = today - timedelta(days=N_REFRESH_DAYS)
    end_date   = today

    try:
        n = db.refresh_adjusted_ohlcv_batch(
            start_date=start_date,
            end_date=end_date,
            dst_table=adj_table
        )
        msg = f"daily_ohlcv_adjusted {start_date}~{end_date} {n}건 갱신 완료"
        logger.info(f"✅ {msg}")
        job_statuses[job_id]["last_log"] = msg
    except Exception as e:
        # non-critical → 실패해도 전체 작업 실패로 처리하지 않음
        logger.error(f"daily_ohlcv_adjusted 갱신 실패: {e}", exc_info=True)
        job_statuses[job_id]["last_log"] = f"daily_ohlcv_adjusted 갱신 실패: {str(e)}"