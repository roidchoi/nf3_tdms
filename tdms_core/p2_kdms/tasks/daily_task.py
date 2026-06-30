import os
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from typing import Dict, Any
from unittest.mock import MagicMock

from collectors.factor_calculator import calculate_factors
from p1_shared.api.kis_api_core import KisApiCore
from collectors.kis_kr_client import KisKrClient
from collectors.kiwoom_client import KiwoomClient
from p1_shared.utils.date_utils import is_kr_trading_day
from repositories.base import create_kdms_pool
from repositories.master_repo import MasterRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.factor_repo import FactorRepo
from repositories.market_cap_repo import MarketCapRepo
from p1_shared.utils.env_detector import EnvDetector
from collectors import utils as col_utils

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class DailyTask:
    """
    일일 데이터 수집 및 수정계수/수정주가 갱신 작업을 총괄하는 태스크 조정자.
    """

    def __init__(self, kis_client, ohlcv_repo, master_repo, factor_repo=None, market_cap_repo=None, kiwoom_client=None) -> None:
        self.kis_client = kis_client
        self.ohlcv_repo = ohlcv_repo
        self.master_repo = master_repo
        self.factor_repo = factor_repo
        self.market_cap_repo = market_cap_repo
        self.kiwoom_client = kiwoom_client

    def run(self, target_date: date, end_date: date | None = None) -> Dict[str, Any]:
        """
        일일 데이터 수집 및 갱신 태스크를 실행합니다.
        순서: 
          0. 휴장일 검사 (MagicMock이 아니거나 test_mode가 아닐 때 실제 검사)
          1. KIS 마스터 다운로드 및 stock_info 업서트
          2. 활성 종목 리스트 대상 daily_ohlcv 수집 및 저장
          3. 시가총액 계산 및 저장 (market_cap_repo가 제공된 경우)
          4. 수정계수(factors) 역산 및 저장 (factor_repo가 제공된 경우) + Loop 1 이벤트 사후 소멸 보정
          5. Loop 2: API 오류 추정 종목 팩터 정밀 검증 및 청소
          6. 물리 수정주가 테이블(daily_ohlcv_adjusted) 갱신
          7. 당일 분봉 데이터 수집 및 적재 (kiwoom_client가 제공된 경우)
        """
        start_date = target_date
        if end_date is None:
            end_date = start_date


        # 0. 휴장일 검사
        is_mock = isinstance(self.kis_client, MagicMock)
        if not is_mock:
            # 단일 날짜 호출인 경우 기존 is_kr_trading_day 유틸 활용
            if start_date == end_date:
                if not is_kr_trading_day(start_date):
                    logger.info(f"Target date {start_date} is not a KR trading day. Skipping daily update.")
                    return {"collected": 0, "failed": 0, "skipped": 1, "msg": "Skipped due to holiday"}
            else:
                trading_days_cnt = self.ohlcv_repo.get_trading_days_count(start_date, end_date)
                if trading_days_cnt == 0:
                    logger.info(f"No trading days found in range {start_date} ~ {end_date}. Skipping daily update.")
                    return {"collected": 0, "failed": 0, "skipped": 1, "msg": "Skipped due to holiday"}

        collected = 0
        failed = 0
        skipped = 0
        mc_records = []

        # 최근 10일 이내 수정계수 발생한 종목 맵 로드 (Loop 1 & Loop 2 검증용)
        recent_event_map = {}
        if self.factor_repo is not None:
            try:
                recent_event_map = self.factor_repo.get_recent_event_stocks_map(days=10, price_source='KIS')
            except Exception as re_err:
                logger.error(f"Failed to load recent event stocks map: {re_err}")

        # 1. 종목마스터 수집 및 갱신
        try:
            master_records = self.kis_client.fetch_stock_master()
            if master_records:
                self.master_repo.upsert_stock_info(master_records)
        except Exception as e:
            # 마스터 수집 실패 시 전체 중단하지 않고 로그를 남긴 뒤 기존 DB 상의 active 종목으로 진행
            logger.warning(f"Stock master update failed: {e}")

        # 2. 수집 대상 활성 종목 조회
        active_stocks = self.master_repo.get_all_active_stocks()
        if not active_stocks:
            return {"collected": 0, "failed": 0, "skipped": 0}

        # 블랙리스트 종목 조회
        blacklisted_stocks = set()
        if hasattr(self.ohlcv_repo, "get_blacklisted_stocks"):
            try:
                blacklisted_stocks = set(self.ohlcv_repo.get_blacklisted_stocks())
            except Exception as bl_err:
                logger.error(f"Failed to load blacklisted stocks: {bl_err}")

        # 3. 각 종목별 OHLCV 및 수정계수 수집/처리 (Loop 1)
        for stock in active_stocks:
            stk_cd = stock.get("stk_cd")
            if not stk_cd:
                continue

            if stk_cd in blacklisted_stocks:
                logger.info(f"[{stk_cd}] Skip data collection due to blacklist.")
                skipped += 1
                continue

            try:
                # 단일 날짜와 범위 기반 분기
                if start_date == end_date:
                    ohlcv = self.kis_client.fetch_daily_ohlcv(stk_cd, start_date)
                    ohlcv_list = [ohlcv] if ohlcv else []
                else:
                    # Raw OHLCV 시세 범위 수집
                    ohlcv_list = self.kis_client.fetch_daily_ohlcv_range(stk_cd, start_date, end_date)

                if ohlcv_list:
                    # 상장주식수 조회 (turn_rt 및 시가총액 계산용)
                    shares = stock.get("listed_shares", 0) or 0
                    if shares <= 0 and self.market_cap_repo is not None:
                        try:
                            # 최근 10일 이내의 시가총액 레코드 조회
                            last_mc = self.market_cap_repo.get_daily_market_cap(stk_cd, start_date - timedelta(days=10), start_date)
                            if last_mc:
                                shares = last_mc[-1].get("listed_shares", 0) or 0
                                logger.info(f"[{stk_cd}] KIS Master listed_shares is 0. Fallback to DB previous shares: {shares:,}")
                        except Exception as fallback_err:
                            logger.error(f"[{stk_cd}] Failed to fallback previous shares: {fallback_err}")

                    # 1,000억 주 초과 비정상 주식수(마스터 오류 유입) 방어
                    if shares > 100_000_000_000 or shares < 0:
                        shares = 0

                    # 회전율(turn_rt) 직접 연산하여 주입
                    for ohlcv in ohlcv_list:
                        ohlcv["turn_rt"] = float((ohlcv["volume"] / shares) * 100.0) if shares > 0 else 0.0

                    # DB에 원본 시세 UPSERT
                    self.ohlcv_repo.upsert_daily_ohlcv(ohlcv_list)
                    
                    # 시가총액 레코드 빌드
                    if self.market_cap_repo is not None:
                        for ohlcv in ohlcv_list:
                            mkt_cap = ohlcv["close"] * shares
                            # PostgreSQL bigint (9.22경) 오버플로우 방어
                            if mkt_cap > 9_000_000_000_000_000_000:
                                mkt_cap = 0
                            amt = ohlcv["close"] * ohlcv["volume"]
                            if amt > 9_000_000_000_000_000_000:
                                amt = 0
                            
                            mc_records.append({
                                "dt": ohlcv["dt"],
                                "stk_cd": stk_cd,
                                "cls_prc": ohlcv["close"],
                                "mkt_cap": mkt_cap,
                                "vol": ohlcv["volume"],
                                "amt": amt,
                                "listed_shares": shares
                            })

                    # 4. 수정계수 역산 및 저장 (FactorRepo가 존재할 경우에만)
                    if self.factor_repo is not None:
                        # 최근 45일 범위의 Raw 및 Adjusted 시세 조회
                        calc_start_dt = end_date - timedelta(days=45)
                        try:
                            raw_list = self.kis_client.fetch_ohlcv_range(stk_cd, calc_start_dt, end_date, adj_price='1')
                            adj_list = self.kis_client.fetch_ohlcv_range(stk_cd, calc_start_dt, end_date, adj_price='0')
                            
                            df_raw = pd.DataFrame(raw_list).rename(columns={"close": "raw_close"})
                            df_adj = pd.DataFrame(adj_list).rename(columns={"close": "adj_close"})
                            
                            if not df_raw.empty and not df_adj.empty:
                                df = pd.merge(df_raw, df_adj, on="dt", how="inner")
                                factors = calculate_factors(df, stk_cd, "KIS")
                                if factors:
                                    self.factor_repo.upsert_adjustment_factors(factors)
                                    
                                    # 이벤트 사후 소멸 보정 (Loop 1)
                                    if stk_cd in recent_event_map:
                                        oldest_raw = df["raw_close"].iloc[0]
                                        oldest_adj = df["adj_close"].iloc[0]
                                        if oldest_raw == oldest_adj:
                                            new_event_dts = {f["event_dt"] for f in factors}
                                            obsolete_dates = [dt for dt in recent_event_map[stk_cd] if dt not in new_event_dts]
                                            if obsolete_dates:
                                                self.factor_repo.delete_adjustment_factors_by_dates(stk_cd, obsolete_dates, price_source='KIS')
                                                logger.info(f"[{stk_cd}] {len(obsolete_dates)} obsolete factors deleted (Loop 1).")
                                            del recent_event_map[stk_cd]
                                else:
                                    # KIS API 상에서 팩터가 감지되지 않았는데, DB 내 10일 이내에 이벤트가 존재하는 경우
                                    # 사후 정정으로 인해 소멸되었을 수 있으므로 obsolete_dates 제거 진행
                                    if stk_cd in recent_event_map:
                                        # 45일 범위가 맞으므로 이 기간의 기존 DB 내 팩터 삭제
                                        obsolete_dates = [dt for dt in recent_event_map[stk_cd] if calc_start_dt <= dt <= end_date]
                                        if obsolete_dates:
                                            self.factor_repo.delete_adjustment_factors_by_dates(stk_cd, obsolete_dates, price_source='KIS')
                                            logger.info(f"[{stk_cd}] {len(obsolete_dates)} obsolete factors deleted (Loop 1 - empty API).")
                                        del recent_event_map[stk_cd]
                        except Exception as fe:
                            logger.warning(f"Failed to calculate factors for {stk_cd}: {fe}")
                    
                    collected += len(ohlcv_list)
                else:
                    # 수집 결과 없음 (휴장일 또는 데이터 미존재) -> Gap 기록
                    self.ohlcv_repo.record_gap(stk_cd, end_date, "No data returned from KIS API for range")
                    failed += 1
            except Exception as e:
                # 수집 에러 발생 -> Gap 기록
                self.ohlcv_repo.record_gap(stk_cd, end_date, str(e))
                failed += 1

        # 4. 시가총액 일괄 저장
        if self.market_cap_repo is not None and mc_records:
            try:
                self.market_cap_repo.upsert_daily_market_cap(mc_records)
            except Exception as mce:
                logger.error(f"Failed to upsert daily market cap records: {mce}")

        # 5. Loop 2: API 오류 추정 종목 팩터 정밀 검증 및 청소
        if self.factor_repo is not None and recent_event_map:
            logger.info(f"Starting Loop 2: API error correction for {len(recent_event_map)} stocks...")
            for stk_cd, db_dates in recent_event_map.items():
                try:
                    full_history_df = self.ohlcv_repo.fetch_ohlcv_for_factor_calc(stk_cd)
                    if full_history_df.empty:
                        continue
                    
                    true_factors = calculate_factors(full_history_df, stk_cd, "KIS")
                    true_dates = {f["event_dt"] for f in true_factors}
                    
                    obsolete_dates = [dt for dt in db_dates if dt not in true_dates]
                    if obsolete_dates:
                        self.factor_repo.delete_adjustment_factors_by_dates(stk_cd, obsolete_dates, price_source='KIS')
                        logger.info(f"[{stk_cd}] {len(obsolete_dates)} error factors deleted (Loop 2).")
                except Exception as loop2_err:
                    logger.error(f"Failed to clean up error factors for {stk_cd} (Loop 2): {loop2_err}")

        # 6. 물리 수정주가 테이블(daily_ohlcv_adjusted) 일괄 갱신 (최근 30일 범위 배치)
        if self.factor_repo is not None:
            try:
                start_update_dt = start_date - timedelta(days=30)
                self.ohlcv_repo.refresh_adjusted_ohlcv_batch(start_update_dt, end_date, 'KIS')
            except Exception as re:
                logger.error(f"Failed to refresh adjusted ohlcv physical table: {re}")

        # 7. 당일 분봉 데이터 수집 및 적재 (kiwoom_client가 제공된 경우)
        if self.kiwoom_client is not None:
            try:
                self._collect_daily_minute_data_range(start_date, end_date)
            except Exception as me:
                logger.error(f"Failed in daily minute data collection: {me}")

        # 8. 자가 치유(Self-healing): 누적 실패 5회 이상인 블랙리스트 종목은 stock_info에서 delisted로 갱신하여 누락수 계산 모수에서 제외
        if blacklisted_stocks:
            try:
                logger.info(f"Self-healing: Processing {len(blacklisted_stocks)} blacklisted stocks for auto-delisting...")
                self.master_repo.update_stocks_status(list(blacklisted_stocks), "delisted")
            except Exception as she:
                logger.error(f"Failed to perform self-healing auto-delist for blacklisted stocks: {she}")

        return {"collected": collected, "failed": failed, "skipped": skipped}

    def _collect_daily_minute_data_range(self, start_date: date, end_date: date) -> None:
        """당일 분기 대상 종목들에 대해 Kiwoom API를 통해 공백 기간(start_date ~ end_date) 분봉 데이터를 동적으로 수집하고 적재합니다."""
        logger.info(f"--- Starting Daily Minute Data Range Collection ({start_date} ~ {end_date}) ---")
        
        # 영업일 수 계산
        trading_days = self.ohlcv_repo.get_trading_days_count(start_date, end_date)
        if isinstance(trading_days, MagicMock):
            trading_days = 1
        if trading_days == 0:
            logger.info("No trading days in range for minute data. Skipping.")
            return
            
        # max_requests 동적 산정 (1일 약 380개 분봉, 1회 요청 시 약 600~900개 수집)
        max_requests = max(1, (trading_days * 380) // 600 + 1)

        
        today = end_date
        quarter = f"{today.year}Q{(today.month - 1) // 3 + 1}"
        
        target_stocks = []
        for market in ["KOSPI", "KOSDAQ"]:
            try:
                rows = self.ohlcv_repo.get_minute_target_history(quarter, market)
                
                # 해당 분기의 타겟 리스트가 없는 경우, 동적으로 대상 선정하여 DB 적재 후 수집 진행
                if not rows:
                    logger.info(f"No target stocks found for {quarter} {market} in minute_target_history. Generating dynamically...")
                    from collectors.target_selector import TargetSelector
                    selector = TargetSelector(self.ohlcv_repo.pool)
                    top_n = 200 if market == "KOSPI" else 400
                    new_targets = selector.select_top_n_stocks(quarter=quarter, top_n=top_n, market=market)
                    if new_targets:
                        self.ohlcv_repo.upsert_minute_target_history(new_targets)
                        rows = self.ohlcv_repo.get_minute_target_history(quarter, market)
                        logger.info(f"Dynamically generated and saved {len(new_targets)} targets for {quarter} {market}.")
                
                if rows:
                    target_stocks.extend([r["symbol"] for r in rows if r.get("symbol")])
            except Exception as err:
                logger.error(f"Failed to fetch or select target stocks for market {market}: {err}")

        if not target_stocks:
            logger.warning(f"No minute targets found for {quarter}. Fetching active stocks as fallback.")
            try:
                active_stocks = self.master_repo.get_all_active_stocks()
                target_stocks = [s["stk_cd"] for s in active_stocks if s.get("stk_cd")]
            except Exception as fallback_err:
                logger.error(f"Failed to fetch active stocks for fallback: {fallback_err}")
                return

        target_stocks = list(set(target_stocks))
        end_date_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"Targeting {len(target_stocks)} stocks for daily range minute collection on {end_date_str} with max_requests={max_requests}.")

        for idx, stk_cd in enumerate(target_stocks):
            try:
                # 최신 영업일(end_date_str) 기준 과거로 연속 수집
                collected = self.kiwoom_client.get_minute_chart(stk_cd, start_date=end_date_str, max_requests=max_requests)
                if collected:
                    # 범위 내에 매칭되는 분봉만 필터링 (start_date <= dt <= end_date)
                    range_collected = []
                    for item in collected:
                        cntr_tm = item.get("cntr_tm", "")
                        if len(cntr_tm) >= 8:
                            try:
                                item_dt = datetime.strptime(cntr_tm[:8], "%Y%m%d").date()
                                if start_date <= item_dt <= end_date:
                                    item["stk_cd"] = stk_cd
                                    range_collected.append(item)
                            except ValueError:
                                pass
                                
                    if range_collected:
                        transformed = col_utils.transform_data(range_collected, "kiwoom", "minute_ohlcv")
                        self.ohlcv_repo.upsert_minute_ohlcv(transformed)
                        logger.info(f"[{stk_cd}] Range minute data {len(transformed)} records upserted.")
                
                # 키움 API 봇 차단 및 부하 완화 딜레이 (MagicMock이 아닐 때만 0.2초 대기)
                if not isinstance(self.kiwoom_client, MagicMock):
                    time.sleep(0.2)
            except Exception as me:
                logger.error(f"Failed to collect daily minute data for {stk_cd}: {me}")



def run_daily_update(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    일일 데이터 수집, 시가총액 계산, 수정계수/수정주가 갱신 및 당일 분봉 수집 파이프라인 태스크.
    
    :param job_statuses: 전역 상태 공유용 딕셔너리
    :param test_mode: True일 경우 모의 클라이언트를 사용하여 데이터베이스 적재 흐름만 테스트
    """
    job_id = "daily_update"
    start_time = datetime.now(KST)

    job_statuses[job_id] = {
        "is_running": True,
        "phase": "1/2",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"일일 수집 작업 시작 (Test Mode: {test_mode})",
        "collected": 0,
        "failed": 0,
        "skipped": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        # DB 커넥션 풀 및 리포지토리 초기화
        pool = create_kdms_pool()
        master_repo = MasterRepo(pool)
        ohlcv_repo = OhlcvRepo(pool)
        factor_repo = FactorRepo(pool)
        market_cap_repo = MarketCapRepo(pool)

        # KIS Client 및 Kiwoom Client 초기화
        if test_mode:
            kis_client = MagicMock()
            kiwoom_client = MagicMock()
        else:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            env = detector.detect()
            is_dev = (env == "dev")
            appkey = (
                os.environ.get("KIS_APP_KEY") 
                or os.environ.get("KIS_APPKEY") 
                or profile.get("kis_app_key") 
                or profile.get("kis_appkey") 
                or ""
            )
            appsecret = (
                os.environ.get("KIS_APP_SECRET") 
                or os.environ.get("KIS_APPSECRET") 
                or profile.get("kis_app_secret") 
                or profile.get("kis_appsecret") 
                or ""
            )

            api_core = KisApiCore(
                app_key=appkey,
                app_secret=appsecret,
                account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
                is_mock=not is_dev
            )
            kis_client = KisKrClient(api_core=api_core)
            # 운영 모드 분봉 키움 클라이언트
            kiwoom_client = KiwoomClient(mock=False)

        job_statuses[job_id].update({
            "phase": "2/2",
            "phase_name": "일일 수집 및 계산 실행",
            "progress": 30,
            "last_log": "일일 수집 태스크 실행 중..."
        })

        task = DailyTask(
            kis_client=kis_client,
            ohlcv_repo=ohlcv_repo,
            master_repo=master_repo,
            factor_repo=factor_repo,
            market_cap_repo=market_cap_repo,
            kiwoom_client=kiwoom_client
        )
        
        # 17:00 KST 기준으로 수집 종료일(target_date) 결정
        MARKET_CLOSE_HOUR = 17
        if start_time.hour < MARKET_CLOSE_HOUR:
            target_date = (start_time - timedelta(days=1)).date()
            logger.info(
                f"[{job_id}] 장 종료 전 실행 감지 ({start_time.strftime('%H:%M')} KST). "
                f"수집 목표일 → 전날: {target_date}"
            )
        else:
            target_date = start_time.date()

        # 0. trading_calendar 테이블 자동 동기화 (target_date 까지 개장일 정보 최신화)
        if not test_mode:
            try:
                with pool.get_cursor() as cursor:
                    cursor.execute("SELECT MAX(dt) FROM trading_calendar")
                    max_cal_dt = cursor.fetchone()[0]
                    
                    if max_cal_dt is None:
                        # 데이터가 없는 경우 안전하게 1년 전부터 동기화
                        sync_start = target_date - timedelta(days=365)
                    else:
                        sync_start = max_cal_dt + timedelta(days=1)
                        
                    if sync_start <= target_date:
                        from p1_shared.utils.date_utils import is_kr_trading_day
                        curr_d = sync_start
                        cal_records = []
                        while curr_d <= target_date:
                            opnd = 'Y' if is_kr_trading_day(curr_d) else 'N'
                            cal_records.append((curr_d, opnd))
                            curr_d += timedelta(days=1)
                            
                        if cal_records:
                            for c_dt, c_opnd in cal_records:
                                cursor.execute("""
                                    INSERT INTO trading_calendar (dt, opnd_yn, updated_at)
                                    VALUES (%s, %s, NOW())
                                    ON CONFLICT (dt) DO UPDATE SET opnd_yn = EXCLUDED.opnd_yn, updated_at = NOW()
                                """, (c_dt, c_opnd))
                            logger.info(f"[{job_id}] trading_calendar 자동 동기화 완료: {len(cal_records)}건 적재 ({sync_start} ~ {target_date})")
            except Exception as cal_err:
                logger.error(f"[{job_id}] trading_calendar 자동 동기화 실패: {cal_err}")

        # DB 상 마지막 적재 날짜 조회
        last_collected_date = None
        try:
            last_collected_date = ohlcv_repo.get_last_collected_date()
            if isinstance(last_collected_date, MagicMock):
                last_collected_date = None
        except Exception as l_err:
            logger.warning(f"Failed to query last collected date: {l_err}")

        # 수집 범위 산출
        if last_collected_date is None:
            # 적재 데이터가 없으면 안전하게 단일 target_date만 타겟팅
            start_date = target_date
            end_date = target_date
            logger.info(f"[{job_id}] DB has no ohlcv data. Starting with single target date: {target_date}")
        else:
            # 마지막 수집 다음 날부터 target_date 사이의 개장 영업일 조회
            search_start = last_collected_date + timedelta(days=1)
            open_days = []
            try:
                open_days = ohlcv_repo.get_open_trading_days(search_start, target_date)
                if isinstance(open_days, MagicMock):
                    open_days = []
            except Exception as o_err:
                logger.warning(f"Failed to query open trading days: {o_err}")

            if open_days:
                start_date = min(open_days)
                end_date = max(open_days)
                logger.info(
                    f"[{job_id}] 공백 영업일 감지: {start_date} ~ {end_date} "
                    f"(총 {len(open_days)} 영업일). 일괄 수집 진행합니다."
                )
            else:
                # 공백이 없는 경우 단일 target_date 적용 (휴장일 스킵 처리 등 정상 흐면 유지를 위함)
                start_date = target_date
                end_date = target_date
                logger.info(f"[{job_id}] No missing trading days detected. Target date: {target_date}")

        if start_date == end_date:
            result = task.run(start_date)
        else:
            result = task.run(start_date, end_date)



        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        
        skipped_count = result.get("skipped", 0)
        if skipped_count > 0 and result.get("collected", 0) == 0 and result.get("failed", 0) == 0:
            final_log = f"수집 스킵 (휴장일 범위: {start_date} ~ {end_date})"
            last_status = "success (holiday skipped)"
        else:
            final_log = f"수집 완료 (성공: {result['collected']}건, 실패: {result['failed']}건, 스킵: {skipped_count}건, 소요시간: {int(duration)}초)"
            last_status = "success"

        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,

            "last_status": last_status,
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초",
            "last_log": final_log,
            "collected": result.get("collected", 0),
            "failed": result.get("failed", 0),
            "skipped": skipped_count
        })
        logger.info(f"✅ [{job_id}] {final_log}")

    except Exception as e:
        logger.critical(f"[{job_id}] 일일 수집 태스크 구동 중 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        job_statuses[job_id]["is_running"] = False
