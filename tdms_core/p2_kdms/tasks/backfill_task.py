import sys
import time
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional, Any
from zoneinfo import ZoneInfo
from psycopg2.extras import execute_values

from collectors.kiwoom_client import KiwoomClient
from collectors.kis_kr_client import KisKrClient
from collectors.factor_calculator import calculate_factors
from collectors import utils
from repositories.base import create_kdms_pool
from collectors.pub_data_client import PubDataClient
from repositories.market_cap_repo import MarketCapRepo
from repositories.master_repo import MasterRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.factor_repo import FactorRepo

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

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
        if conn is not None:
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


def run_backfill_minute_data(
    job_statuses: Dict[str, Any], 
    test_mode: bool = False,
    start_date: date = None,
    end_date: date = None
):
    """
    분봉 데이터 백필 실행 함수
    
    :param job_statuses: 전역 상태 딕셔너리
    :param test_mode: 테스트 모드 여부
    :param start_date: 백필 시작 날짜 (기본값: 지난 8일전)
    :param end_date: 백필 종료 날짜 (기본값: 어제)
    """
    job_id = "backfill_minute_data"
    start_time = datetime.now(KST)
    
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
        
        # 지정되지 않은 경우 .env 설정값 혹은 기본 30일 적용
        import os
        from p1_shared.utils.env_detector import EnvDetector
        try:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            backfill_days = int(profile.get("kdms_backfill_days") or os.environ.get("KDMS_BACKFILL_DAYS", 30))
        except Exception:
            backfill_days = 30

        if start_date is None:
            start_date = date.today() - timedelta(days=backfill_days)
        if end_date is None:
            # 장 종료 후 시점(오후 4시 이후)이면 당일까지, 그렇지 않으면 전일까지
            now_hour = datetime.now(KST).hour
            if now_hour >= 16:
                end_date = date.today()
            else:
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
                "end_time": datetime.now(KST).isoformat(),
                "duration": f"{(datetime.now(KST) - start_time).total_seconds():.1f}초",
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
        _execute_backfill_jobs(api, db, job_list, missing_map, test_mode, job_statuses, job_id, end_date=end_date)

        # 완료 상태
        end_time = datetime.now(KST)
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
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        status_dict = job_statuses.get(job_id, {})
        status_dict["is_running"] = False
        job_statuses[job_id] = status_dict


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
    """'완전/일부 누락일' 탐지 (하이브리드 알고리즘 적용)"""
    logger.info("--- [3/5] '완전/일부 누락일' 탐지 시작 ---")
    logger.info(f"'일부 누락' 개수 기준: {PARTIAL_DAY_THRESHOLD}건 미만")
    logger.info("오탐 방지를 위해 일봉 거래량 대조 오차 5% 이하 종목은 정상으로 판단합니다.")

    # 1. 캘린더 개장일 및 일봉/분봉 실시간 요약 bulk 조회 (LEFT JOIN 구조)
    query = """
        SELECT 
            tc.dt,
            s.stk_cd,
            COALESCE(d.vol, 0) as daily_volume,
            COALESCE(m.record_count, 0) as record_count,
            COALESCE(m.sum_min_vol, 0) as sum_min_vol
        FROM trading_calendar tc
        CROSS JOIN (
            SELECT unnest(%s::varchar[]) as stk_cd
        ) s
        LEFT JOIN daily_ohlcv d ON d.stk_cd = s.stk_cd AND d.dt = tc.dt
        LEFT JOIN (
            SELECT stk_cd, DATE(dt_tm) as dt, COUNT(*) as record_count, SUM(vol) as sum_min_vol
            FROM minute_ohlcv
            WHERE stk_cd = ANY(%s) 
              AND dt_tm >= %s::timestamp 
              AND dt_tm < (%s::date + INTERVAL '1 day')::timestamp
            GROUP BY 1, 2
        ) m ON m.stk_cd = s.stk_cd AND m.dt = tc.dt
        WHERE tc.opnd_yn = 'Y' 
          AND tc.dt BETWEEN %s AND %s
        ORDER BY s.stk_cd, tc.dt;
    """
    
    results = db._execute_query(
        query, 
        (target_stocks, target_stocks, start_date, end_date, start_date, end_date), 
        fetch='all'
    )
    
    if not results:
        logger.warning("탐지 기간 내 개장일 또는 수집 대조 정보가 없습니다.")
        return {}

    # 2. 하이브리드 기준(개수 또는 거래량 오차) 적용하여 누락 판단
    missing_map: Dict[str, Set[date]] = {}
    total_missing_days = 0
    total_partial_days = 0

    for row in results:
        stk_cd = row['stk_cd']
        day = row['dt']
        daily_vol = row['daily_volume']
        rec_cnt = row['record_count']
        sum_min_vol = row['sum_min_vol']
        
        is_normal = False
        
        # 조건 1: 분봉 적재 건수가 기준치(360) 이상인 경우 정상
        if rec_cnt >= PARTIAL_DAY_THRESHOLD:
            is_normal = True
        else:
            # 조건 2: 거래가 매우 희소하여 건수는 적지만, 거래량 합산이 일봉 거래량과 오차 5% 이하인 경우 정상 구제
            if daily_vol == 0:
                is_normal = (rec_cnt == 0)
            else:
                diff_pct = abs(daily_vol - sum_min_vol) / daily_vol
                if diff_pct <= 0.05:
                    is_normal = True

        if not is_normal:
            if stk_cd not in missing_map:
                missing_map[stk_cd] = set()
            missing_map[stk_cd].add(day)
            if rec_cnt == 0:
                total_missing_days += 1
            else:
                total_partial_days += 1

    logger.info(f"✅ 공백일 탐지 완료: 총 {len(missing_map)}개 종목")
    logger.info(f"  - 완전 누락일: {total_missing_days}건")
    logger.info(f"  - 일부 누락일 (오차 > 5%): {total_partial_days}건")
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
    job_id: str,
    end_date: Optional[date] = None
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
        
        stk_missing_set = missing_map.get(stk_cd)
        if not stk_missing_set:
            continue

        # 실제 백필이 필요한 영업일 갭 크기에 맞춰 max_requests 동적 제한 (API 조회 한도 최적화)
        if end_date:
            try:
                query = """
                    SELECT COUNT(*) as count 
                    FROM trading_calendar 
                    WHERE dt >= %s AND dt <= %s AND opnd_yn = 'Y';
                """
                res = db._execute_query(query, (earliest_missing_date, end_date), fetch='all')
                gap_days = res[0]['count'] if res else 1
            except Exception as ce:
                logger.warning(f"[{stk_cd}] 영업일 수 계산 쿼리 실패: {ce}")
                gap_days = (end_date - earliest_missing_date).days + 1
        else:
            gap_days = (date.today() - earliest_missing_date).days + 1
            
        if gap_days <= 0:
            gap_days = 1
        stk_max_requests = min(30, max(1, (gap_days * 380) // 600 + 1))

        try:
            start_date_str = earliest_missing_date.strftime('%Y%m%d')
            logger.info(f"[{stk_cd}] Fetching minute chart from {start_date_str} with max_requests={stk_max_requests}")
            all_collected_data = api.get_minute_chart(stk_cd, start_date=start_date_str, max_requests=stk_max_requests)
            if not all_collected_data:
                logger.warning(f"[{stk_cd}] API가 {start_date_str} 기준 데이터를 반환하지 않았습니다.")
                continue
            logger.info(f"[{stk_cd}] API 응답 수신: 총 {len(all_collected_data)}건")
        except Exception as e:
            logger.error(f"[{stk_cd}] API 호출 실패: {e}", exc_info=True)
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
        logger.warning(f"{quarter} 대상 종목이 {read_table}에 없습니다. 동적으로 대상을 선정하여 DB에 적재합니다.")
        try:
            from collectors.target_selector import TargetSelector
            selector = TargetSelector(db.pool)
            
            # KOSPI 200개, KOSDAQ 400개
            new_targets = []
            for market in ["KOSPI", "KOSDAQ"]:
                top_n = 200 if market == "KOSPI" else 400
                market_targets = selector.select_top_n_stocks(quarter=quarter, top_n=top_n, market=market)
                if market_targets:
                    new_targets.extend(market_targets)
            
            if new_targets:
                insert_query = """
                    INSERT INTO minute_target_history (quarter, market, symbol, avg_trade_value, rank)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (quarter, market, symbol) DO UPDATE SET
                        avg_trade_value = EXCLUDED.avg_trade_value,
                        rank = EXCLUDED.rank;
                """
                conn = db._get_connection()
                try:
                    with conn.cursor() as cur:
                        for t in new_targets:
                            cur.execute(insert_query, (t['quarter'], t['market'], t['symbol'], t['avg_trade_value'], t['rank']))
                    conn.commit()
                    logger.info(f"동적으로 생성된 {len(new_targets)}개 종목을 {read_table}에 저장 완료했습니다.")
                except Exception as ie:
                    conn.rollback()
                    logger.error(f"동적 타겟 적재 중 오류 발생: {ie}")
                finally:
                    db._release_connection(conn)
                
                # 저장 후 다시 조회
                results = db._execute_query(query, (quarter,), fetch='all')
                if results:
                    target_list = [row['symbol'] for row in results if row.get('symbol')]
        except Exception as err:
            logger.error(f"동적 타겟 선정 중 오류 발생: {err}")
            
    if not target_list:
        logger.warning("동적 타겟 선정 실패 또는 대상 없음. 기본값으로 전체 활성 종목을 조회합니다.")
        fallback_query = "SELECT DISTINCT stk_cd as symbol FROM stock_info WHERE status = 'listed' AND (delist_dt IS NULL OR delist_dt > CURRENT_DATE)"
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
    start_time = datetime.now(KST)

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
                "end_time": datetime.now(KST).isoformat()
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
        end_time = datetime.now(KST)
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
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        status_dict = job_statuses.get(job_id, {})
        status_dict["is_running"] = False
        job_statuses[job_id] = status_dict


def run_backfill_daily_data(
    job_statuses: Dict[str, Any], 
    test_mode: bool = False,
    start_date: date = None,
    end_date: date = None
):
    """
    일봉 데이터 중간 누락 검출 및 핀포인트 백필 실행 함수
    """
    job_id = "backfill_daily_data"
    start_time = datetime.now(KST)
    
    # 상태 초기화
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "0/3",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"일봉 백필 작업 시작 (Test Mode: {test_mode})",
        "stocks_processed": 0,
        "total_stocks": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        # 날짜 자동 산정
        import os
        from p1_shared.utils.env_detector import EnvDetector
        try:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            backfill_days = int(profile.get("kdms_backfill_days") or os.environ.get("KDMS_BACKFILL_DAYS", 30))
        except Exception:
            backfill_days = 30

        if start_date is None:
            start_date = date.today() - timedelta(days=backfill_days)
        if end_date is None:
            # 장 종료 후 시점(오후 4시 이후)이면 당일까지, 그렇지 않으면 전일까지
            now_hour = datetime.now(KST).hour
            if now_hour >= 16:
                end_date = date.today()
            else:
                end_date = date.today() - timedelta(days=1)
        
        logger.info(f"[{job_id}] 백필 대상 기간: {start_date} ~ {end_date}")
        job_statuses[job_id]["last_log"] = f"대상 기간: {start_date} ~ {end_date}"

        # 리포지토리 및 클라이언트 초기화
        db = DatabaseManager()
        from p1_shared.api.kis_api_core import KisApiCore
        from unittest.mock import MagicMock
        
        master_repo = MasterRepo(db.pool)
        ohlcv_repo = OhlcvRepo(db.pool)
        factor_repo = FactorRepo(db.pool)
        market_cap_repo = MarketCapRepo(db.pool)
        
        if test_mode:
            kis_client = MagicMock()
        else:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            env = detector.detect()
            is_dev = (env == "dev")
            appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
            appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
            
            api_core = KisApiCore(
                app_key=appkey,
                app_secret=appsecret,
                account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
                is_mock=not is_dev
            )
            kis_client = KisKrClient(api_core=api_core)

        # Step 1: 대상 종목 목록 조회
        job_statuses[job_id].update({
            "phase": "1/3",
            "phase_name": "대상 종목 선정 및 누락일 감지",
            "progress": 10,
            "last_log": "대상 종목 정보 로딩..."
        })
        
        # 전체 활성 종목 대상
        active_stocks = master_repo.get_all_active_stocks()
        target_stocks = [s["stk_cd"] for s in active_stocks if s.get("stk_cd")]
        if test_mode and not target_stocks:
            target_stocks = ["005930"]
        elif test_mode:
            target_stocks = target_stocks[:5]
            
        logger.info(f"[{job_id}] 총 {len(target_stocks)}개 활성 종목을 대상으로 일봉 중간 누락 검출 시작")

        # Step 2: 일봉 중간 누락일 검출 (Outer Join 방식)
        query_missing = """
            SELECT 
                tc.dt,
                s.stk_cd
            FROM trading_calendar tc
            CROSS JOIN (
                SELECT unnest(%s::varchar[]) as stk_cd
            ) s
            LEFT JOIN daily_ohlcv d ON d.stk_cd = s.stk_cd AND d.dt = tc.dt
            WHERE tc.opnd_yn = 'Y' 
              AND tc.dt BETWEEN %s AND %s
              AND d.stk_cd IS NULL
            ORDER BY s.stk_cd, tc.dt;
        """
        results = db._execute_query(query_missing, (target_stocks, start_date, end_date), fetch='all')
        
        missing_map: Dict[str, List[date]] = {}
        for row in results:
            stk = row['stk_cd']
            if stk not in missing_map:
                missing_map[stk] = []
            missing_map[stk].append(row['dt'])
            
        # Step 2-2: 수정 비율(price_adjustment_factors) 누락 검출 및 백필 대상 추가 (전일 대비 변동 1% 이상 & 팩터 누락 기준)
        query_missing_factors = """
            SELECT d1.stk_cd, d1.dt
            FROM daily_ohlcv d1
            JOIN daily_ohlcv d2 ON d2.stk_cd = d1.stk_cd AND d2.dt = (
                SELECT max(dt) FROM daily_ohlcv WHERE stk_cd = d1.stk_cd AND dt < d1.dt
            )
            LEFT JOIN price_adjustment_factors f ON f.stk_cd = d1.stk_cd AND f.event_dt = d1.dt
            WHERE d1.dt BETWEEN %s AND %s
              AND d2.cls_prc > 0
              AND abs(d1.cls_prc - d2.cls_prc)::float / d2.cls_prc > 0.01
              AND f.stk_cd IS NULL
              AND d1.stk_cd = ANY(%s::varchar[]);
        """
        factor_results = db._execute_query(query_missing_factors, (start_date, end_date, target_stocks), fetch='all')
        if factor_results:
            logger.info(f"[{job_id}] 수정 비율(price_adjustment_factors) 누락 건 감지: {len(factor_results)}건. 백필 대상에 병합합니다.")
            for row in factor_results:
                stk = row['stk_cd']
                dt_val = row['dt']
                if stk not in missing_map:
                    missing_map[stk] = []
                if dt_val not in missing_map[stk]:
                    missing_map[stk].append(dt_val)
            
        if not missing_map:
            logger.info(f"[{job_id}] 모든 대상 종목의 일봉 데이터가 최신 상태입니다. (누락 없음)")
            job_statuses[job_id].update({
                "is_running": False,
                "progress": 100,
                "last_status": "success (누락 없음)",
                "end_time": datetime.now(KST).isoformat(),
                "last_log": "모든 대상 종목의 일봉 데이터가 최신 상태입니다. (누락 없음)"
            })
            return

        total_stocks = len(missing_map)
        job_statuses[job_id]["total_stocks"] = total_stocks
        job_statuses[job_id].update({
            "phase": "2/3",
            "phase_name": "일봉 수집 및 보정 실행",
            "progress": 30,
            "last_log": f"총 {total_stocks}개 종목 누락 데이터 백필 기동 시작..."
        })
        
        # Step 3: 종목별 핀포인트 백필 수집 실행
        import pandas as pd
        from collectors.factor_calculator import calculate_factors
        
        collected_cnt = 0
        failed_cnt = 0
        
        for idx, (stk_cd, missing_days) in enumerate(missing_map.items()):
            progress_val = 30 + int((idx / total_stocks) * 60)
            log_msg = f"[{stk_cd}] 일봉 백필 중 ({idx+1}/{total_stocks})"
            job_statuses[job_id].update({
                "progress": progress_val,
                "stocks_processed": idx + 1,
                "last_log": log_msg
            })
            logger.info(f"[{job_id}] {log_msg}")

            min_dt = min(missing_days)
            max_dt = max(missing_days)
            
            try:
                # KIS API 호출
                if test_mode:
                    # Mock 데이터 적재
                    mock_records = []
                    for day in missing_days:
                        mock_records.append({
                            "stk_cd": stk_cd,
                            "dt": day,
                            "opn_prc": 50000,
                            "clse_prc": 50500,
                            "hg_prc": 51000,
                            "lw_prc": 49900,
                            "vol": 100000,
                            "trd_amt": 5000000000
                        })
                    ohlcv_repo.upsert_daily_ohlcv(mock_records)
                    collected_cnt += len(mock_records)
                else:
                    # KIS API 범위 조회 (list[dict] 반환)
                    api_records = kis_client.fetch_daily_ohlcv_range(stk_cd, start_date=min_dt, end_date=max_dt)
                    if api_records:
                        filtered_records = []
                        for rec in api_records:
                            rec_dt = rec.get("dt")
                            if isinstance(rec_dt, str):
                                rec_dt = datetime.strptime(rec_dt, "%Y-%m-%d").date()
                            
                            if rec_dt in missing_days:
                                filtered_records.append({
                                    "stk_cd": stk_cd,
                                    "dt": rec_dt,
                                    "open": rec.get("open"),
                                    "close": rec.get("close"),
                                    "high": rec.get("high"),
                                    "low": rec.get("low"),
                                    "volume": rec.get("volume"),
                                    "amt": rec.get("amt"),
                                    "turn_rt": 0.0
                                })
                        
                        if filtered_records:
                            ohlcv_repo.upsert_daily_ohlcv(filtered_records)
                            collected_cnt += len(filtered_records)
                            
                            # 수정계수 재빌드 및 물리 수정주가 테이블 동기화
                            calc_start_dt = min_dt - timedelta(days=45)
                            try:
                                raw_list = kis_client.fetch_ohlcv_range(stk_cd, calc_start_dt, max_dt, adj_price='1')
                                adj_list = kis_client.fetch_ohlcv_range(stk_cd, calc_start_dt, max_dt, adj_price='0')
                                
                                df_raw = pd.DataFrame(raw_list).rename(columns={"close": "raw_close"})
                                df_adj = pd.DataFrame(adj_list).rename(columns={"close": "adj_close"})
                                
                                if not df_raw.empty and not df_adj.empty:
                                    df = pd.merge(df_raw, df_adj, on="dt", how="inner")
                                    factors = calculate_factors(df, stk_cd, "KIS")
                                    if factors:
                                        factor_repo.upsert_adjustment_factors(factors)
                            except Exception as fe:
                                logger.warning(f"[{stk_cd}] 수정계수 역산 실패: {fe}")
                            
                            ohlcv_repo.refresh_adjusted_ohlcv_batch(
                                min_dt - timedelta(days=5),
                                max_dt,
                                'KIS'
                            )
                            logger.info(f"✅ [{stk_cd}] {min_dt} ~ {max_dt} 범위 {len(filtered_records)}건 백필 및 팩터 소급 갱신 완료")
            except Exception as e:
                logger.error(f"[{stk_cd}] 일봉 백필 실패: {e}", exc_info=True)
                failed_cnt += 1

        # Step 4: 완료 처리
        job_statuses[job_id].update({
            "phase": "3/3",
            "phase_name": "일봉 백필 마무리",
            "progress": 100,
            "last_log": "백필 작업 완료 처리 중..."
        })

        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초",
            "last_log": f"일봉 백필 완료 (성공: {total_stocks - failed_cnt}종목, 실패: {failed_cnt}종목, 수집: {collected_cnt}건)"
        })
        logger.info(f"✅ [{job_id}] 일봉 백필 작업 완료 (소요시간: {duration:.2f}초)")

    except Exception as e:
        logger.critical(f"[{job_id}] 치명적 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        status_dict = job_statuses.get(job_id, {})
        status_dict["is_running"] = False
        job_statuses[job_id] = status_dict


def run_backfill_investor_trade(
    job_statuses: Dict[str, Any], 
    test_mode: bool = False,
    start_date: date = None,
    end_date: date = None
):
    """
    투자자 매매동향(일별) 백필 실행 함수
    
    :param job_statuses: 전역 상태 딕셔너리
    :param test_mode: 테스트 모드 여부
    :param start_date: 백필 시작 날짜 (기본값: 2020-01-02로 고정)
    :param end_date: 백필 종료 날짜 (기본값: 전일 혹은 오늘)
    """
    job_id = "backfill_investor_trade"
    start_time = datetime.now(KST)
    
    # 상태 초기화
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "0/3",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"작업 시작 (Test Mode: {test_mode})",
        "stocks_processed": 0,
        "total_stocks": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        db = DatabaseManager()
        from p1_shared.api.kis_api_core import KisApiCore
        from p1_shared.utils.env_detector import EnvDetector
        from unittest.mock import MagicMock
        from repositories.investor_trade_repo import InvestorTradeRepo
        import os
        
        # 분봉 수집 시작 시점인 2020-01-02를 하한선으로 고정 (Clamping)
        MIN_LIMIT_DATE = date(2020, 1, 2)
        
        if start_date is None:
            start_date = MIN_LIMIT_DATE
        else:
            start_date = max(start_date, MIN_LIMIT_DATE)
            
        if end_date is None:
            now_hour = datetime.now(KST).hour
            if now_hour >= 16:
                end_date = date.today()
            else:
                end_date = date.today() - timedelta(days=1)
        
        logger.info(f"[{job_id}] 백필 대상 기간: {start_date} ~ {end_date}")
        job_statuses[job_id]["last_log"] = f"대상 기간: {start_date} ~ {end_date}"

        # 클라이언트 초기화
        if test_mode:
            kis_client = MagicMock()
        else:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            env = detector.detect()
            is_dev = (env == "dev")
            appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
            appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
            
            api_core = KisApiCore(
                app_key=appkey,
                app_secret=appsecret,
                account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
                is_mock=not is_dev
            )
            kis_client = KisKrClient(api_core=api_core)

        trade_repo = InvestorTradeRepo(db.pool)

        # Step 1: 대상 종목 및 누락 영업일 감지
        job_statuses[job_id].update({
            "phase": "1/3",
            "phase_name": "누락 데이터 감지",
            "progress": 10,
            "last_log": "DB에서 분기별 수집 대상 대비 누락일 추출 중..."
        })

        query_missing = """
            SELECT 
                tc.dt,
                mth.symbol AS stk_cd
            FROM trading_calendar tc
            JOIN minute_target_history mth ON 
                mth.quarter = (EXTRACT(YEAR FROM tc.dt) || 'Q' || ((EXTRACT(MONTH FROM tc.dt)::int - 1) / 3 + 1))
            LEFT JOIN daily_investor_trade dit ON 
                dit.stk_cd = mth.symbol AND dit.dt = tc.dt
            WHERE tc.opnd_yn = 'Y'
              AND tc.dt BETWEEN %s AND %s
              AND dit.stk_cd IS NULL
            ORDER BY mth.symbol, tc.dt;
        """
        results = db._execute_query(query_missing, (start_date, end_date), fetch='all')
        
        missing_map: Dict[str, List[date]] = {}
        for row in results:
            stk = row['stk_cd']
            if stk not in missing_map:
                missing_map[stk] = []
            missing_map[stk].append(row['dt'])
            
        if not missing_map:
            logger.info(f"[{job_id}] 모든 대상 종목의 투자자 매매동향 데이터가 최신 상태입니다. (누락 없음)")
            job_statuses[job_id].update({
                "is_running": False,
                "progress": 100,
                "last_status": "success (누락 없음)",
                "end_time": datetime.now(KST).isoformat(),
                "last_log": "모든 대상 종목의 투자자 매매동향 데이터가 최신 상태입니다. (누락 없음)"
            })
            return

        total_stocks = len(missing_map)
        job_statuses[job_id]["total_stocks"] = total_stocks
        job_statuses[job_id].update({
            "phase": "2/3",
            "phase_name": "투자자 매매동향 수집 실행",
            "progress": 30,
            "last_log": f"총 {total_stocks}개 종목 누락 데이터 백필 시작..."
        })

        collected_cnt = 0
        failed_cnt = 0

        for idx, (stk_cd, missing_days) in enumerate(missing_map.items()):
            progress_val = 30 + int((idx / total_stocks) * 60)
            log_msg = f"[{stk_cd}] 수급 백필 중 ({idx+1}/{total_stocks})"
            job_statuses[job_id].update({
                "progress": progress_val,
                "stocks_processed": idx + 1,
                "last_log": log_msg
            })
            logger.info(f"[{job_id}] {log_msg}")

            min_dt = min(missing_days)
            max_dt = max(missing_days)

            try:
                if test_mode:
                    mock_records = []
                    for day in missing_days:
                        mock_rec = {
                            "dt": day,
                            "stk_cd": stk_cd,
                            "stck_clpr": 50000,
                            "prdy_vrss": 500,
                            "prdy_vrss_sign": "2",
                            "prdy_ctrt": 1.0,
                            "acml_vol": 100000,
                            "acml_tr_pbmn": 5000000000,
                            "stck_oprc": 49500,
                            "stck_hgpr": 50500,
                            "stck_lwpr": 49000
                        }
                        # 공통/세부 주체별 필드들도 0으로 mock 처리하여 적재 가능하도록 함
                        for sub in ["prsn", "frgn", "orgn", "scrt", "insu", "fund", "bank", "ivtr", "mrbn", "pe_fund", "etc", "etc_corp", "etc_orgt"]:
                            qty_key = f"{sub}_ntby_vol" if sub in ["pe_fund", "etc_corp", "etc_orgt"] else f"{sub}_ntby_qty"
                            mock_rec[f"{sub}_seln_vol"] = 1000
                            mock_rec[f"{sub}_shnu_vol"] = 1000
                            mock_rec[qty_key] = 0
                            mock_rec[f"{sub}_seln_tr_pbmn"] = 50000000
                            mock_rec[f"{sub}_shnu_tr_pbmn"] = 50000000
                            mock_rec[f"{sub}_ntby_tr_pbmn"] = 0
                        for sub in ["frgn_reg", "frgn_nreg"]:
                            mock_rec[f"{sub}_askp_qty"] = 1000
                            mock_rec[f"{sub}_bidp_qty"] = 1000
                            mock_rec[f"{sub}_ntby_qty"] = 0
                            mock_rec[f"{sub}_askp_pbmn"] = 50000000
                            mock_rec[f"{sub}_bidp_pbmn"] = 50000000
                            mock_rec[f"{sub}_ntby_pbmn"] = 0
                        
                        mock_records.append(mock_rec)
                    trade_repo.upsert_daily_investor_trade(mock_records)
                    collected_cnt += len(mock_records)
                else:
                    api_records = kis_client.fetch_investor_trade_daily(stk_cd, start_date=min_dt, end_date=max_dt)
                    if api_records:
                        filtered_records = [
                            rec for rec in api_records if rec.get("dt") in missing_days
                        ]
                        if filtered_records:
                            trade_repo.upsert_daily_investor_trade(filtered_records)
                            collected_cnt += len(filtered_records)
                            logger.info(f"✅ [{stk_cd}] {min_dt} ~ {max_dt} 범위 {len(filtered_records)}건 백필 완료")
            except Exception as e:
                logger.error(f"[{stk_cd}] 투자자 매매동향 백필 실패: {e}", exc_info=True)
                failed_cnt += 1

        # Step 3: 완료 처리
        job_statuses[job_id].update({
            "phase": "3/3",
            "phase_name": "수급 백필 마무리",
            "progress": 100,
            "last_log": "백필 작업 완료 처리 중..."
        })

        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초",
            "last_log": f"수급 백필 완료 (성공: {total_stocks - failed_cnt}종목, 실패: {failed_cnt}종목, 수집: {collected_cnt}건)"
        })
        logger.info(f"✅ [{job_id}] 투자자 매매동향 백필 작업 완료 (소요시간: {duration:.2f}초)")

    except Exception as e:
        logger.critical(f"[{job_id}] 치명적 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        status_dict = job_statuses.get(job_id, {})
        status_dict["is_running"] = False
        job_statuses[job_id] = status_dict



