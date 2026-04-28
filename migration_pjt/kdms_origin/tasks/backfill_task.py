#
# tasks/backfill_task.py
#
"""
분봉 데이터 백필(Backfill) 태스크 (PRD Phase 6 아키텍처)
- backfill_minute_data.py의 실제 로직을 FastAPI/APScheduler 백그라운드 태스크로 이식
- PRD 4.1.2에 따라 job_statuses 딕셔너리를 실시간으로 업데이트
"""

import sys
import time
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional, Any
from collections import defaultdict
from psycopg2.extras import execute_values

# --- [이식] backfill_minute_data 소스코드.md의 임포트 ---
from collectors.kiwoom_rest import KiwoomREST
from collectors.kis_rest import KisREST
from collectors.db_manager import DatabaseManager
from collectors import utils
from test_utils import TestEnvironment
# ----------------------------------------------

# 로거 설정 (모듈 레벨)
logger = logging.getLogger(__name__)

# [v6] 일부 누락일 탐지 기준 (360분 = 6시간)
PARTIAL_DAY_THRESHOLD = 360


def run_backfill_minute_data(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    분봉 데이터 백필 실행 함수 (PRD 4.1.2 기반)
    
    :param job_statuses: 전역 상태 딕셔너리 (FastAPI에서 전달)
    :param test_mode: 테스트 모드 여부
    """
    job_id = "backfill_minute_data"
    start_time = datetime.now()
    
    # --- [PRD 4.1.2] 상태 초기화 ---
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "0/5",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"작업 시작 (Test Mode: {test_mode})",
        "stocks_processed": 0,
        "total_stocks": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        # --- [이식] main()의 객체 초기화 ---
        logger.info(f"[{job_id}] Kiwoom API 초기화...")
        api = KiwoomREST(mock=False, log_level=3) # 백필은 항상 실 API 사용 (mock=False)
        
        logger.info(f"[{job_id}] KIS API 초기화...")
        kis_api = KisREST(mock=False, log_level=1)
        
        logger.info(f"[{job_id}] DatabaseManager 초기화...")
        db = DatabaseManager()
        
        test_env = TestEnvironment(db, logger) if test_mode else None
        
        if test_mode:
            logger.info(f"[{job_id}] 테스트 모드: Read-Prod, Write-Test 테이블 구성")
            # (test_utils.py가 'trading_calendar'를 포함하도록 수정되었다고 가정)
            test_env.setup_test_tables(include_calendar=True)
        # ----------------------------------------------
        
        # --- [수정] 날짜 범위 동적 설정 ---
        # 매주 실행되므로, 지난 1주일(7일) + 안전 여유분(1일) 포함 최근 8일간만 점검
        start_date = date.today() - timedelta(days=8)
        end_date = date.today() - timedelta(days=1) # (어제)
        logger.info(f"[{job_id}] 백필 대상 기간: {start_date} ~ {end_date}")
        
        job_statuses[job_id]["last_log"] = f"대상 기간: {start_date} ~ {end_date}"

        # Step 0: 대상 종목 선정
        job_statuses[job_id].update({
            "phase": "0/5",
            "phase_name": "대상 종목 선정",
            "progress": 5,
            "last_log": "백필 대상 종목 선정 중..."
        })
        target_stocks = get_target_stocks(
            db, quarter=None, market=None, stocks=None, test_mode=test_mode
        )
        if not target_stocks:
            logger.warning(f"[{job_id}] 백필 대상 종목이 없습니다. 작업 종료.")
            raise ValueError("백필 대상 종목이 없습니다.")
        
        job_statuses[job_id]["total_stocks"] = len(target_stocks)

        # Step 1: 과거 거래일 동기화
        job_statuses[job_id].update({
            "phase": "1/5",
            "phase_name": "과거 거래일 동기화",
            "progress": 10,
            "last_log": "daily_ohlcv -> trading_calendar 동기화 중..."
        })
        _sync_trading_calendar_history(db, start_date, test_mode, test_env)

        # Step 2: 최신/휴장일 동기화
        job_statuses[job_id].update({
            "phase": "2/5",
            "phase_name": "최신 거래일 동기화",
            "progress": 15,
            "last_log": "KIS API -> trading_calendar 동기화 중..."
        })
        _sync_trading_calendar_recent(kis_api, db, test_mode)

        # Step 3: [v6] '완전/일부 누락일' 탐지
        job_statuses[job_id].update({
            "phase": "3/5",
            "phase_name": "누락일 탐지",
            "progress": 20,
            "last_log": "분봉 데이터와 거래일 캘린더 비교 중..."
        })
        missing_map = _detect_missing_and_partial_days(
            db, target_stocks, start_date, end_date, test_mode, test_env
        )
        
        if not missing_map:
            logger.info(f"[{job_id}] 🎉 모든 대상 종목의 분봉 데이터가 최신 상태입니다. (누락 없음)")
            job_statuses[job_id].update({
                "is_running": False,
                "progress": 100,
                "last_status": "success (누락 없음)",
                "end_time": datetime.now().isoformat(),
                "duration": f"{(datetime.now() - start_time).total_seconds():.1f}초"
            })
            return # 작업 완료

        # Step 4: [v6] '가장 이른 공백일' 작업 목록 생성
        job_statuses[job_id].update({
            "phase": "4/5",
            "phase_name": "작업 목록 생성",
            "progress": 30,
            "last_log": "'가장 이른 공백일' 기준 작업 목록 생성 중..."
        })
        job_list = _find_earliest_missing_date(missing_map)
        
        if not job_list:
            logger.warning(f"[{job_id}] 공백일은 탐지되었으나, 작업(Job) 생성에 실패했습니다.")
            raise ValueError("공백일 탐지 후 작업 생성 실패")
            
        job_statuses[job_id]["total_stocks"] = len(job_list) # (실제 작업할 종목 수로 갱신)

        # Step 5: [v6] 배치 수집 및 일괄 저장
        job_statuses[job_id].update({
            "phase": "5/5",
            "phase_name": "데이터 백필 실행",
            "progress": 35,
            "last_log": "Kiwoom API 호출 시작..."
        })
        _execute_backfill_jobs(
            api, db, job_list, missing_map, test_mode, test_env,
            job_statuses, job_id # [수정] 상태 객체 전달
        )

        # --- [신규] 시가총액 누락일 자동 복구 ---
        try:
            _backfill_market_cap_gaps(db, job_statuses, job_id)
        except Exception as e:
            logger.error(f"[{job_id}] 시가총액 누락일 복구 실패: {e}", exc_info=True)
            # (non-critical이므로 작업 실패로 처리하지 않고 계속)

        # --- [PRD 4.1.2] 완료 상태 ---
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초 ({duration/60:.1f}분)",
            "last_log": "분봉 백필 성공적으로 완료"
        })
        logger.info(f"✅ [{job_id}] 모든 분봉 데이터 백필 작업 완료 (소요시간: {duration:.2f}초)")

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
# --- (이식) backfill_minute_data.py의 헬퍼 함수들 ---
#

def _sync_trading_calendar_history(db: DatabaseManager, start_date: date, test_mode: bool, test_env: Optional[TestEnvironment]):
    """Step 1: 과거 거래일 동기화 (원본 로직)"""
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
        
        conn = db._get_connection() # (수정) db_manager.py가 풀을 사용하므로
        with conn.cursor() as cur:
            execute_values(cur, upsert_query, calendar_data)
        conn.commit()
        logger.info(f"✅ 과거 개장일 {len(calendar_data)}건 캘린더 동기화 완료 ({write_table}).")

    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"과거 거래일 동기화 실패: {e}", exc_info=True)
        raise
    finally:
        db._release_connection(conn) # (수정) conn.close() -> _release_connection


def _sync_trading_calendar_recent(kis_api: KisREST, db: DatabaseManager, test_mode: bool):
    """Step 2: 최신/휴장일 동기화 (원본 로직)"""
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
    """Step 3: [v6] '완전/일부 누락일' 탐지 (원본 로직)"""
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
                missing_map[stk_cd].add(day)
                total_missing_days += 1
            elif stock_counts[day] < PARTIAL_DAY_THRESHOLD:
                missing_map[stk_cd].add(day)
                total_partial_days += 1
    
    logger.info(f"✅ 공백일 탐지 완료: 총 {len(missing_map)}개 종목")
    logger.info(f"  - 완전 누락일: {total_missing_days}건")
    logger.info(f"  - 일부 누락일: {total_partial_days}건 (기준: {PARTIAL_DAY_THRESHOLD}건 미만)")
    return missing_map


def _find_earliest_missing_date(missing_map: Dict[str, Set[date]]) -> List[Tuple[str, date]]:
    """Step 4: [v6] '가장 이른 공백일' 작업 목록 생성 (원본 로직)"""
    logger.info("--- [4/5] '가장 이른 공백일' 작업 목록 생성 ---")
    job_list: List[Tuple[str, date]] = []
    for stk_cd, missing_days_set in missing_map.items():
        if not missing_days_set:
            continue
        earliest_missing = min(missing_days_set)
        job_list.append((stk_cd, earliest_missing))
    logger.info(f"✅ '가장 이른 공백일' 기준 작업 {len(job_list)}개 생성 완료.")
    return job_list


def _parse_cntr_tm(cntr_tm: str) -> date:
    """분봉 'cntr_tm' 문자열에서 날짜 객체를 빠르게 파싱 (원본 로직)"""
    try:
        return datetime.strptime(cntr_tm[:8], '%Y%m%d').date()
    except Exception:
        return None


def _execute_backfill_jobs(api: KiwoomREST, db: DatabaseManager, 
                           job_list: List[Tuple[str, date]],
                           missing_map: Dict[str, Set[date]],
                           test_mode: bool,
                           test_env: Optional[TestEnvironment],
                           job_statuses: Dict, job_id: str): # [수정] PRD 4.1.2
    """Step 5: [v6] API 호출 -> 필터링 -> UPSERT (tqdm -> job_statuses)"""
    logger.info("--- [5/5] 분봉 데이터 백필 작업 시작 (API 1회/종목) ---")
    
    if test_mode:
        minute_write_table = test_env.get_test_table_name('minute_ohlcv')
    else:
        minute_write_table = 'minute_ohlcv'
    logger.info(f"Write Target: {minute_write_table} ({'테스트' if test_mode else '운영'})")
        
    total_jobs = len(job_list)
    
    # [수정] tqdm -> job_statuses
    for i, (stk_cd, earliest_missing_date) in enumerate(job_list):
        
        # --- [통합] PRD 4.1.2 실시간 상태 업데이트 ---
        progress = 35 + (i / total_jobs * 65)  # Phase 5는 35% ~ 100%
        job_statuses[job_id].update({
            "progress": progress,
            "stocks_processed": i,
            "last_log": f"[{stk_cd}] API 호출 (기준일: {earliest_missing_date}) ({i+1}/{total_jobs})"
        })
        # ----------------------------------------
            
        logger.info(f"--- 작업 ({i+1}/{total_jobs}): [{stk_cd}] / 기준일: {earliest_missing_date} ---")
        
        # 1. [v6] 종목당 1회 API 호출
        try:
            start_date_str = earliest_missing_date.strftime('%Y%m%d')
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
            item_date = _parse_cntr_tm(item.get('cntr_tm'))
            if item_date and item_date in stk_missing_set:
                item['stk_cd'] = stk_cd
                batch_to_process.append(item)
        
        if not batch_to_process:
            logger.info(f"[{stk_cd}] API 응답 {len(all_collected_data)}건 중 실제 공백일 데이터가 없습니다.")
            continue
        logger.info(f"[{stk_cd}] {len(all_collected_data)}건 중 {len(batch_to_process)}건 필터링 완료.")

        # 3. [v6] 필터링된 데이터 변환 및 일괄 UPSERT
        try:
            transformed_batch = utils.transform_data(batch_to_process, 'kiwoom', 'minute_ohlcv')
            db.upsert_ohlcv_data(minute_write_table, transformed_batch)
            logger.info(f"✅ [{stk_cd}] {earliest_missing_date} 기준 {len(transformed_batch)}건 일괄 저장 완료.")
        
        except Exception as e:
            logger.error(f"[{stk_cd}] DB 일괄 저장 실패: {e}", exc_info=True)


def get_target_stocks(db: DatabaseManager, 
                      quarter: Optional[str], 
                      market: Optional[str], 
                      stocks: Optional[List[str]], 
                      test_mode: bool) -> List[str]:
    """수집 대상 종목을 필터링하여 반환 (원본 로직)"""
    
    if stocks: # (test_mode=True일 때, --stocks가 우선)
        logger.info(f"지정된 종목 {stocks}를 대상으로 합니다.")
        return stocks

    if test_mode:
        # (test_utils.py가 TestEnvironment.get_test_stock_codes()를 제공한다고 가정)
        test_env = TestEnvironment(db, logger)
        target_list = test_env.get_test_stock_codes()
        logger.info(f"테스트 모드: 대상을 알려진 테스트 종목({target_list})으로 한정합니다.")
        return target_list

    # (운영 모드: 스케줄 실행 시)
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
        # (sys.exit(1) 대신 예외 발생)
        raise ValueError(f"{quarter} {market or ''} 대상 종목 없음")
        
    logger.info(f"총 {len(target_list)}개 종목을 대상으로 백필을 시작합니다.")
    return target_list


def _backfill_market_cap_gaps(db: DatabaseManager, job_statuses: Dict, job_id: str):
    """
    [신규] daily_market_cap 테이블의 누락일 자동 복구

    - 검사 범위: 최근 30일
    - 영업일과 DB 데이터 비교하여 누락일 감지
    - 누락일 자동 재수집 (pykrx)
    - Rate limiting: time.sleep(1)
    """
    from collectors.krx_loader import KRXLoader

    logger.info("--- [부가 작업] KRX 시가총액 누락일 자동 복구 시작 ---")

    # 검사 범위: 최근 30일
    end_date = date.today() - timedelta(days=1)  # 어제까지
    start_date = end_date - timedelta(days=30)   # 최근 30일

    logger.info(f"검사 기간: {start_date} ~ {end_date} (최근 30일)")

    try:
        # 1. 누락일 조회
        missing_dates = db.get_market_cap_missing_dates(start_date, end_date)

        if not missing_dates:
            logger.info("✅ 시가총액 데이터 누락 없음 (최근 30일)")
            return

        logger.info(f"⚠️ 시가총액 누락일 {len(missing_dates)}일 감지: {missing_dates[:5]}...")

        # 2. 누락일 재수집
        krx_loader = KRXLoader(logger)
        success_count = 0
        skip_count = 0

        for idx, missing_date in enumerate(missing_dates, start=1):
            date_str = missing_date.strftime('%Y%m%d')

            try:
                # 상태 업데이트
                job_statuses[job_id]["last_log"] = f"시가총액 보정 중: {date_str} ({idx}/{len(missing_dates)})"

                # pykrx 호출
                data = krx_loader.get_market_cap_data(date_str)

                if not data:
                    skip_count += 1
                    logger.warning(f"[{idx}/{len(missing_dates)}] {date_str}: 데이터 없음 (휴장일)")
                else:
                    count = db.upsert_daily_market_cap(data)
                    success_count += 1
                    logger.info(f"[{idx}/{len(missing_dates)}] {date_str}: {count}건 복구 완료")

                # Rate limiting (IP 차단 방지)
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"[{idx}/{len(missing_dates)}] {date_str}: 복구 실패 - {e}")
                continue

        logger.info(f"✅ 시가총액 누락일 복구 완료: 성공 {success_count}일, 스킵 {skip_count}일")

    except Exception as e:
        logger.error(f"시가총액 누락일 복구 중 오류: {e}", exc_info=True)
        raise

#
# --- (제거) backfill_minute_data.py의 main() 및 if __name__ == '__main__' ---
#