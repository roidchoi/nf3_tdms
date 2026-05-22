import sys
import time
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional, Any
from psycopg2.extras import execute_values

from collectors.kiwoom_client import KiwoomClient
from collectors import utils
from repositories.base import create_kdms_pool
from collectors.pub_data_client import PubDataClient
from repositories.market_cap_repo import MarketCapRepo

logger = logging.getLogger(__name__)

# 일부 누락일 탐지 기준 (360분 = 6시간)
PARTIAL_DAY_THRESHOLD = 360

class DatabaseManager:
    """테스트 코드 및 레거시 태스크 구조와의 호환을 위한 DB 매니저 어댑터 클래스."""
    
    def __init__(self) -> None:
        self.pool = create_kdms_pool()

    def _execute_query(self, query: str, params: tuple = (), fetch: str = None) -> Any:
        with self.pool.get_cursor() as cursor:
            cursor.execute(query, params)
            if fetch == 'all':
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            elif fetch == 'one':
                columns = [desc[0] for desc in cursor.description]
                row = cursor.fetchone()
                return dict(zip(columns, row)) if row else None
            return None

    def _get_connection(self):
        return self.pool.get_conn()

    def _release_connection(self, conn):
        self.pool.put_conn(conn)

    def upsert_ohlcv_data(self, table_name: str, data: list[dict]):
        if not data:
            return
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                columns = data[0].keys()
                if 'minute_ohlcv' in table_name:
                    conflict_keys = ['dt_tm', 'stk_cd']
                elif 'daily_ohlcv' in table_name:
                    conflict_keys = ['dt', 'stk_cd']
                else:
                    raise ValueError(f"지원하지 않는 테이블 이름입니다: {table_name}")
                
                update_columns = [col for col in columns if col not in conflict_keys]
                update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
                query = f"""
                    INSERT INTO {table_name} ({', '.join(columns)})
                    VALUES %s
                    ON CONFLICT ({', '.join(conflict_keys)}) DO UPDATE SET
                        {update_clause};
                """
                values = [[item.get(col) for col in columns] for item in data]
                execute_values(cur, query, values)
            conn.commit()
            logger.info(f"✅ 총 {len(data)}건의 데이터가 '{table_name}'에 성공적으로 UPSERT 되었습니다.")
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"'{table_name}' 데이터 UPSERT 중 에러 발생: {e}", exc_info=True)
            raise
        finally:
            self._release_connection(conn)


def run_backfill_minute_data(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    분봉 데이터 백필 실행 함수
    
    :param job_statuses: 전역 상태 딕셔너리
    :param test_mode: 테스트 모드 여부
    """
    job_id = "backfill_minute_data"
    start_time = datetime.now()
    
    # 상태 초기화
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
        logger.info(f"[{job_id}] Kiwoom API 초기화...")
        # 백필용 클라이언트 인스턴스 생성 (테스트모드에 따라 mock 여부 결정)
        api = KiwoomClient(mock=test_mode)
        
        logger.info(f"[{job_id}] DatabaseManager 초기화...")
        db = DatabaseManager()
        
        # 지난 8일간 ~ 어제
        start_date = date.today() - timedelta(days=8)
        end_date = date.today() - timedelta(days=1)
        logger.info(f"[{job_id}] 백필 대상 기간: {start_date} ~ {end_date}")
        
        job_statuses[job_id]["last_log"] = f"대상 기간: {start_date} ~ {end_date}"

        # Step 0: 대상 종목 선정
        job_statuses[job_id].update({
            "phase": "0/5",
            "phase_name": "대상 종목 선정",
            "progress": 5,
            "last_log": "백필 대상 종목 선정 중..."
        })
        target_stocks = get_target_stocks(db, test_mode=test_mode)
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
        _sync_trading_calendar_history(db, start_date)

        # Step 2: 최신 거래일 동기화 (기존 캘린더 유지하므로 로깅만 수행)
        job_statuses[job_id].update({
            "phase": "2/5",
            "phase_name": "최신 거래일 동기화",
            "progress": 15,
            "last_log": "최신 거래일 동기화 중..."
        })
        # KIS를 이용한 최근 거래일 동기화는 T-006 스케줄러로 이관하므로 여기서는 패스

        # Step 3: '완전/일부 누락일' 탐지
        job_statuses[job_id].update({
            "phase": "3/5",
            "phase_name": "누락일 탐지",
            "progress": 20,
            "last_log": "분봉 데이터와 거래일 캘린더 비교 중..."
        })
        missing_map = _detect_missing_and_partial_days(db, target_stocks, start_date, end_date)
        
        if not missing_map:
            logger.info(f"[{job_id}] 모든 대상 종목의 분봉 데이터가 최신 상태입니다. (누락 없음)")
            job_statuses[job_id].update({
                "is_running": False,
                "progress": 100,
                "last_status": "success (누락 없음)",
                "end_time": datetime.now().isoformat(),
                "duration": f"{(datetime.now() - start_time).total_seconds():.1f}초",
                "last_log": "모든 대상 종목의 분봉 데이터가 최신 상태입니다. (누락 없음)"
            })
            return

        # Step 4: '가장 이른 공백일' 작업 목록 생성
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
            
        job_statuses[job_id]["total_stocks"] = len(job_list)

        # Step 5: 배치 수집 및 일괄 저장
        job_statuses[job_id].update({
            "phase": "5/5",
            "phase_name": "데이터 백필 실행",
            "progress": 35,
            "last_log": "Kiwoom API 호출 시작..."
        })
        _execute_backfill_jobs(api, db, job_list, missing_map, test_mode, job_statuses, job_id)

        # 완료 상태
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
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now().isoformat()
        })
    finally:
        job_statuses[job_id]["is_running"] = False


def _sync_trading_calendar_history(db: DatabaseManager, start_date: date):
    """과거 거래일 동기화 (daily_ohlcv -> trading_calendar)"""
    logger.info("--- [1/5] 과거 거래일 동기화 시작 ---")
    read_table = 'daily_ohlcv'
    write_table = 'trading_calendar'
    
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
        db._release_connection(conn)


def _detect_missing_and_partial_days(
    db: DatabaseManager, 
    target_stocks: List[str], 
    start_date: date, 
    end_date: date
) -> Dict[str, Set[date]]:
    """'완전/일부 누락일' 탐지"""
    logger.info("--- [3/5] '완전/일부 누락일' 탐지 시작 ---")
    logger.info(f"'일부 누락' 기준: {PARTIAL_DAY_THRESHOLD}건 미만")

    calendar_read_table = 'trading_calendar'
    minute_read_table = 'minute_ohlcv'
    
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

    # 2. 기수집일 '건수' 맵 생성
    query_collected = f"""
        SELECT stk_cd, DATE(dt_tm) as dt, COUNT(*) as record_count
        FROM {minute_read_table}
        WHERE stk_cd = ANY(%s) AND DATE(dt_tm) BETWEEN %s AND %s
        GROUP BY 1, 2;
    """
    results = db._execute_query(query_collected, (target_stocks, start_date, end_date), fetch='all')
    
    collected_day_counts: Dict[str, Dict[date, int]] = {}
    for stk in target_stocks:
        collected_day_counts[stk] = {}
        
    for row in results:
        stk_cd = row['stk_cd']
        if stk_cd in collected_day_counts:
            collected_day_counts[stk_cd][row['dt']] = row['record_count']

    # 3. '완전/일부 누락' 공백일 맵 생성
    missing_map: Dict[str, Set[date]] = {}
    total_missing_days = 0
    total_partial_days = 0

    for stk_cd in target_stocks:
        stock_counts = collected_day_counts[stk_cd]
        missing_days = set()
        for day in all_trading_days:
            if day not in stock_counts:
                missing_days.add(day)
                total_missing_days += 1
            elif stock_counts[day] < PARTIAL_DAY_THRESHOLD:
                missing_days.add(day)
                total_partial_days += 1
        if missing_days:
            missing_map[stk_cd] = missing_days
    
    logger.info(f"✅ 공백일 탐지 완료: 총 {len(missing_map)}개 종목")
    logger.info(f"  - 완전 누락일: {total_missing_days}건")
    logger.info(f"  - 일부 누락일: {total_partial_days}건 (기준: {PARTIAL_DAY_THRESHOLD}건 미만)")
    return missing_map


def _find_earliest_missing_date(missing_map: Dict[str, Set[date]]) -> List[Tuple[str, date]]:
    """'가장 이른 공백일' 작업 목록 생성"""
    logger.info("--- [4/5] '가장 이른 공백일' 작업 목록 생성 ---")
    job_list: List[Tuple[str, date]] = []
    for stk_cd, missing_days_set in missing_map.items():
        if not missing_days_set:
            continue
        earliest_missing = min(missing_days_set)
        job_list.append((stk_cd, earliest_missing))
    logger.info(f"✅ '가장 이른 공백일' 기준 작업 {len(job_list)}개 생성 완료.")
    return job_list


def _parse_cntr_tm(cntr_tm: str) -> Optional[date]:
    try:
        return datetime.strptime(cntr_tm[:8], '%Y%m%d').date()
    except Exception:
        return None


def _execute_backfill_jobs(
    api: KiwoomClient, 
    db: DatabaseManager, 
    job_list: List[Tuple[str, date]],
    missing_map: Dict[str, Set[date]],
    test_mode: bool,
    job_statuses: Dict, 
    job_id: str
):
    """API 호출 -> 필터링 -> UPSERT"""
    logger.info("--- [5/5] 분봉 데이터 백필 작업 시작 ---")
    minute_write_table = 'minute_ohlcv'
    total_jobs = len(job_list)
    loop_start_time = time.time()
    
    for i, (stk_cd, earliest_missing_date) in enumerate(job_list):
        progress = 35 + (i / total_jobs * 65)  # Phase 5는 35% ~ 100%
        
        elapsed = time.time() - loop_start_time
        if elapsed == 0:
            elapsed = 1e-6
        items_per_sec = (i + 1) / elapsed
        eta_seconds = (total_jobs - (i + 1)) / items_per_sec if items_per_sec > 0 else 0
        eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
        
        progress_msg = (
            f"[{stk_cd}] API 호출 (기준일: {earliest_missing_date}) ({i+1}/{total_jobs}) "
            f"[{items_per_sec:.1f}it/s, ETA: {eta_str}]"
        )
        
        job_statuses[job_id].update({
            "progress": int(progress),
            "stocks_processed": i + 1,
            "last_log": progress_msg
        })
        logger.info(progress_msg)
        
        try:
            start_date_str = earliest_missing_date.strftime('%Y%m%d')
            all_collected_data = api.get_minute_chart(stk_cd, start_date=start_date_str, max_requests=30)
            if not all_collected_data:
                logger.warning(f"[{stk_cd}] API가 {start_date_str} 기준 데이터를 반환하지 않았습니다.")
                continue
            logger.info(f"[{stk_cd}] API 응답 수신: 총 {len(all_collected_data)}건")
        except Exception as e:
            logger.error(f"[{stk_cd}] API 호출 실패: {e}", exc_info=True)
            continue
            
        stk_missing_set = missing_map.get(stk_cd)
        if not stk_missing_set:
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
            
        try:
            transformed_batch = utils.transform_data(batch_to_process, 'kiwoom', 'minute_ohlcv')
            db.upsert_ohlcv_data(minute_write_table, transformed_batch)
            logger.info(f"✅ [{stk_cd}] {earliest_missing_date} 기준 {len(transformed_batch)}건 일괄 저장 완료.")
        except Exception as e:
            logger.error(f"[{stk_cd}] DB 일괄 저장 실패: {e}", exc_info=True)


def get_target_stocks(db: DatabaseManager, test_mode: bool) -> List[str]:
    """수집 대상 종목을 조회하여 반환"""
    if test_mode:
        logger.info("테스트 모드: 대상을 알려진 테스트 종목(['005930'])으로 한정합니다.")
        return ["005930"]

    read_table = 'minute_target_history'
    
    # 현재 분기 산출
    today = date.today()
    quarter = f"{today.year}Q{(today.month - 1) // 3 + 1}"
    
    logger.info(f"(운영) 대상 분기: {quarter}")
    
    query = f"SELECT DISTINCT symbol FROM {read_table} WHERE quarter = %s"
    results = db._execute_query(query, (quarter,), fetch='all')
    
    target_list = []
    if results:
        target_list = [row['symbol'] for row in results if row.get('symbol')]
        
    if not target_list:
        logger.warning(f"{quarter} 대상 종목이 {read_table}에 없습니다. 기본값으로 전체 활성 종목을 조회합니다.")
        # 만약 테이블에 없으면 전체 활성 종목이라도 수집을 시도하도록 안전장치 마련
        fallback_query = "SELECT DISTINCT stk_cd as symbol FROM stock_info WHERE active = true"
        results = db._execute_query(fallback_query, fetch='all')
        if results:
            target_list = [row['symbol'] for row in results if row.get('symbol')]
            
    logger.info(f"총 {len(target_list)}개 종목을 대상으로 백필을 시작합니다.")
    return target_list


def run_backfill_market_cap(
    job_statuses: Dict[str, Any],
    pub_client: PubDataClient,
    mc_repo: MarketCapRepo,
    start_date: date,
    end_date: date
):
    """
    공공데이터 API를 이용해 지정한 기간의 누락된 일별 시가총액 데이터를 수집 및 복구합니다.
    """
    job_id = "backfill_market_cap"
    start_time = datetime.now()

    # 상태 초기화
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "0/3",
        "phase_name": "초기화 및 누락일 감지",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": "백필 작업 시작 및 누락 영업일 조회 중...",
        "days_processed": 0,
        "total_days": 0
    }
    logger.info(f"[{job_id}] 시가총액 백필 작업 시작. (기간: {start_date} ~ {end_date})")

    try:
        # 1. 누락일 조회
        missing_dates = mc_repo.get_market_cap_missing_dates(start_date, end_date)
        if not missing_dates:
            logger.info(f"[{job_id}] 누락된 시가총액 영업일이 없습니다. 작업을 종료합니다.")
            job_statuses[job_id].update({
                "is_running": False,
                "progress": 100,
                "last_status": "success",
                "last_log": "누락된 시가총액 영업일이 없습니다. (이미 최신 상태)",
                "end_time": datetime.now().isoformat()
            })
            return

        total_days = len(missing_dates)
        job_statuses[job_id]["total_days"] = total_days
        job_statuses[job_id]["phase"] = "1/3"
        job_statuses[job_id]["phase_name"] = "시가총액 데이터 수집 및 적재"

        logger.info(f"[{job_id}] 누락 영업일 감지 완료: 총 {total_days}일 대상 수집 시작")

        for idx, target_date in enumerate(missing_dates):
            progress_val = int((idx / total_days) * 100)
            log_msg = f"날짜 {target_date} 수집 및 적재 중... ({idx + 1}/{total_days})"
            
            job_statuses[job_id].update({
                "progress": progress_val,
                "last_log": log_msg,
                "days_processed": idx + 1
            })
            logger.info(f"[{job_id}] {log_msg}")

            # API 호출
            records = pub_client.get_market_cap_by_date(target_date)
            if records:
                mc_repo.upsert_daily_market_cap(records)
                logger.info(f"✅ [{job_id}] {target_date} 시가총액 데이터 {len(records)}건 적재 완료")
            else:
                logger.warning(f"⚠️ [{job_id}] {target_date} 시가총액 데이터가 없거나 수집에 실패했습니다.")

            # 트래픽 분산 및 차단 회피를 위한 대기 (0.5초)
            time.sleep(0.5)

        # 완료 상태 업데이트
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "last_log": f"백필 완료: 총 {total_days}일 중 {total_days}일 처리 완료.",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초"
        })
        logger.info(f"✅ [{job_id}] 시가총액 백필 작업 성공 완료 (소요시간: {duration:.2f}초)")

    except Exception as e:
        logger.critical(f"[{job_id}] 시가총액 백필 중 치명적 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now().isoformat()
        })
    finally:
        job_statuses[job_id]["is_running"] = False

