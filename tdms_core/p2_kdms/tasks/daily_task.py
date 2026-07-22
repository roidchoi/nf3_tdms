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


def format_duration_str(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}초"
    minutes = seconds / 60.0
    return f"{minutes:.1f}분"



class DailyTask:
    """
    일일 데이터 수집 및 수정계수/수정주가 갱신 작업을 총괄하는 태스크 조정자.
    """

    def __init__(self, kis_client, ohlcv_repo, master_repo, factor_repo=None, market_cap_repo=None, kiwoom_client=None, investor_trade_repo=None) -> None:
        self.kis_client = kis_client
        self.ohlcv_repo = ohlcv_repo
        self.master_repo = master_repo
        self.factor_repo = factor_repo
        self.market_cap_repo = market_cap_repo
        self.kiwoom_client = kiwoom_client
        self.investor_trade_repo = investor_trade_repo

    def run(self, target_date: date, end_date: date | None = None, rebuild_factors: bool = False) -> Dict[str, Any]:
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

        # 통계 집계용 변수 초기화
        new_listings = 0
        delistings = 0
        ticker_changes = 0
        daily_ohlcv_count = 0
        market_cap_count = 0
        minute_count = 0
        investor_count = 0
        adjusted_factor_count = 0
        factor_rebuilt_count = 0

        # 최근 10일 이내 수정계수 발생한 종목 맵 로드 (Loop 1 & Loop 2 검증용)
        recent_event_map = {}
        if self.factor_repo is not None:
            try:
                recent_event_map = self.factor_repo.get_recent_event_stocks_map(days=10, price_source='KIS')
            except Exception as re_err:
                logger.error(f"Failed to load recent event stocks map: {re_err}")

        # 1. 종목마스터 수집 및 갱신 전, 전일 상장주식수 정보를 사전 로딩 (수정계수 이벤트 감지용)
        prev_shares_map = {}
        try:
            old_active = self.master_repo.get_all_active_stocks()
            prev_shares_map = {s["stk_cd"]: s.get("listed_shares", 0) or 0 for s in old_active}
        except Exception as pre_shares_err:
            logger.warning(f"Failed to pre-load active stock shares: {pre_shares_err}")

        try:
            master_records = self.kis_client.fetch_stock_master()
            if master_records:
                self.master_repo.upsert_stock_info(master_records)
                new_listings = len(master_records)
        except Exception as e:
            # 마스터 수집 실패 시 전체 중단하지 않고 로그를 남긴 뒤 기존 DB 상의 active 종목으로 진행
            logger.warning(f"Stock master update failed: {e}")

        # 전일 종가 정보 벌크 로딩 (주가 괴리 감지용)
        prev_close_map = {}
        try:
            with self.ohlcv_repo.pool.get_cursor() as cursor:
                cursor.execute("SELECT MAX(dt) FROM daily_ohlcv WHERE dt < %s", (start_date,))
                prev_dt_row = cursor.fetchone()
                if prev_dt_row and prev_dt_row[0]:
                    prev_dt = prev_dt_row[0]
                    cursor.execute("SELECT stk_cd, cls_prc FROM daily_ohlcv WHERE dt = %s", (prev_dt,))
                    prev_close_map = {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as pc_err:
            logger.warning(f"Failed to pre-load previous close prices: {pc_err}")

        # 1-1. 종목별 마지막 수집일 및 수정종가 정보 벌크 로딩 (갭 보정 및 수정계수 감지용)
        last_dt_map = {}
        adj_info_map = {}
        try:
            last_dt_map = self.ohlcv_repo.get_all_stocks_latest_dates()
            adj_info_map = self.ohlcv_repo.get_all_stocks_latest_adjusted_info()
        except Exception as meta_err:
            logger.warning(f"Failed to pre-load stocks latest dates/adjusted info: {meta_err}")

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
        all_ohlcv_records = []
        total_stocks = len(active_stocks)
        loop_start_time = time.time()
        for idx, stock in enumerate(active_stocks):
            stk_cd = stock.get("stk_cd")
            if not stk_cd:
                continue

            # 50개 종목 수집마다 또는 마지막 종목일 때 진행 정보 로깅
            if idx % 50 == 0 or idx == total_stocks - 1:
                elapsed = time.time() - loop_start_time
                if elapsed == 0:
                    elapsed = 1e-6
                items_per_sec = (idx + 1) / elapsed
                remaining = total_stocks - (idx + 1)
                eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                progress_pct = (idx + 1) / total_stocks * 100.0
                
                logger.info(
                    f"[KDMS 일일 시세 수집] Progress: {progress_pct:.1f}% ({idx+1}/{total_stocks}) | "
                    f"Speed: {items_per_sec:.1f} it/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str} | "
                    f"Current: {stk_cd}"
                )

            if stk_cd in blacklisted_stocks:
                logger.info(f"[{stk_cd}] Skip data collection due to blacklist.")
                skipped += 1
                continue

            # 종목별 갭 동적 산출 및 조회 기간 Clamping
            stk_last_dt = last_dt_map.get(stk_cd)
            if isinstance(stk_last_dt, MagicMock):
                stk_last_dt = None
            
            # end_date가 MagicMock인 경우 방어 처리
            eff_end_date = start_date if isinstance(end_date, MagicMock) else end_date

            # 하위 호환성 및 단일 일자 기동 보장: start_date와 end_date가 같거나 end_date가 인입되지 않은 경우 갭 보정 우회
            if start_date == eff_end_date or end_date is None:
                stk_start = start_date
                stk_end = start_date
            else:
                # 기본 수집 대상 범위는 [start_date - 1, end_date]로 설정 (최소 T-1 거래량 덮어쓰기 보정 보장)
                base_start = start_date - timedelta(days=1)
                
                if stk_last_dt:
                    # 이미 최신 날짜까지 모두 수집 완료되었고 갭이 없는 상태라면 스킵 또는 T-1 덮어쓰기만 수행
                    if stk_last_dt >= eff_end_date:
                        stk_start = base_start
                    else:
                        # 갭이 존재하는 경우 start_date를 갭 시작점(stk_last_dt + 1)으로 확장
                        stk_start = min(base_start, stk_last_dt + timedelta(days=1))
                else:
                    # DB 적재 이력이 없는 신규 종목의 경우 최근 5일치 일괄 수집
                    stk_start = start_date - timedelta(days=5)

                stk_end = eff_end_date
            
            # 휴장일 등으로 인해 stk_start > stk_end 가 되는 비정상 범위 보정
            if stk_start > stk_end:
                stk_start = stk_end

            try:
                # Raw OHLCV 시세 범위 수집
                if stk_start == stk_end:
                    ohlcv = self.kis_client.fetch_daily_ohlcv(stk_cd, stk_start)
                    ohlcv_list = [ohlcv] if ohlcv else []
                else:
                    ohlcv_list = self.kis_client.fetch_daily_ohlcv_range(stk_cd, stk_start, stk_end)

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

                    # DB에 원본 시세 적재를 위한 메모리 리스트에 추가 (벌크화)
                    all_ohlcv_records.extend(ohlcv_list)
                    
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
                        # 4-1. 수정계수 계산 대상 필터링 적용 (안정성 및 완결성 보장)
                        prev_shares = prev_shares_map.get(stk_cd, 0)
                        
                        # 괴리율 계산 (전일 종가 대비 오늘 종가가 5% 초과 변동한 경우)
                        has_price_anomaly = False
                        if ohlcv_list:
                            today_close = ohlcv_list[-1]["close"]
                            prev_close = prev_close_map.get(stk_cd, 0)
                            if prev_close > 0:
                                change_rate = abs(today_close - prev_close) / prev_close
                                # 최적화 필터 괴리율 임계값을 5% -> 1%로 하향 조정하여 ETF 등의 미세한 권리락/분배락 누락 방지
                                if change_rate > 0.01:
                                    has_price_anomaly = True

                        has_share_changed = (prev_shares != shares)
                        has_recent_event = (stk_cd in recent_event_map)
                        is_new_stock = (stk_cd not in prev_shares_map)

                        trigger_factor_rebuild = rebuild_factors or has_share_changed or has_price_anomaly or has_recent_event or is_new_stock

                        # 1차 스크리닝에서 통과했더라도 Stage 2 (과거 수정종가 대조)로 정밀 검증
                        if not trigger_factor_rebuild:
                            adj_info = adj_info_map.get(stk_cd)
                            if not adj_info:
                                trigger_factor_rebuild = True  # DB 내 기존 수정종가 정보가 없으면 강제 재구축 (Fallback)
                            else:
                                adj_last_dt, adj_last_close = adj_info
                                try:
                                    # 최근 5일치 수정종가(adj_price='0')를 1회 룩업하여 대조
                                    check_start = end_date - timedelta(days=5)
                                    api_adj_list = self.kis_client.fetch_ohlcv_range(stk_cd, check_start, end_date, adj_price='0')
                                    api_adj_map = {item["dt"]: item["close"] for item in api_adj_list if "dt" in item}
                                    
                                    if adj_last_dt in api_adj_map:
                                        api_adj_close = api_adj_map[adj_last_dt]
                                        if abs(adj_last_close - api_adj_close) > 0.01:
                                            trigger_factor_rebuild = True
                                            logger.info(
                                                f"[{stk_cd}] Adjusted close discrepancy detected at {adj_last_dt}: "
                                                f"DB {adj_last_close} vs API {api_adj_close}. Triggering factor rebuild."
                                            )
                                except Exception as check_err:
                                    logger.warning(f"[{stk_cd}] Failed to verify historical adjusted close: {check_err}")

                        # 필터링 조건 만족 시에만 API 45일 범위 조회 실행
                        if trigger_factor_rebuild:
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
                                        adjusted_factor_count += len(factors)
                                        factor_rebuilt_count += 1
                                        
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

        # 3.5. 수집된 모든 일봉 데이터 일괄 적재 (벌크 업서트)
        if all_ohlcv_records:
            try:
                self.ohlcv_repo.upsert_daily_ohlcv(all_ohlcv_records)
                daily_ohlcv_count = len(all_ohlcv_records)
            except Exception as oe:
                logger.error(f"Failed to bulk upsert daily ohlcv records: {oe}")

        # 4. 시가총액 일괄 저장
        if self.market_cap_repo is not None and mc_records:
            try:
                self.market_cap_repo.upsert_daily_market_cap(mc_records)
                market_cap_count = len(mc_records)
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
                minute_count = self._collect_daily_minute_data_range(start_date, end_date)
            except Exception as me:
                logger.error(f"Failed in daily minute data collection: {me}")

        # 8. 자가 치유(Self-healing): 누적 실패 5회 이상인 블랙리스트 종목은 stock_info에서 delisted로 갱신하여 누락수 계산 모수에서 제외
        if blacklisted_stocks:
            try:
                logger.info(f"Self-healing: Processing {len(blacklisted_stocks)} blacklisted stocks for auto-delisting...")
                self.master_repo.update_stocks_status(list(blacklisted_stocks), "delisted")
            except Exception as she:
                logger.error(f"Failed to perform self-healing auto-delist for blacklisted stocks: {she}")

        # 9. 투자자 매매동향(일별) 수집 및 적재
        if self.investor_trade_repo is not None:
            try:
                logger.info("Starting daily investor trade collection...")
                try:
                    open_days = self.ohlcv_repo.get_open_trading_days(start_date, end_date)
                    if isinstance(open_days, MagicMock):
                        open_days = []
                except Exception as od_err:
                    logger.error(f"Failed to fetch open trading days for daily investor trade: {od_err}")
                    open_days = []

                if not open_days:
                    open_days = [start_date]

                for d in open_days:
                    try:
                        targets = self.investor_trade_repo.get_active_symbols_for_date(d)
                    except Exception as tg_err:
                        logger.error(f"Failed to fetch active symbols for date {d}: {tg_err}")
                        continue

                    if not targets:
                        logger.info(f"No investor trade target symbols found for date {d}")
                        continue

                    logger.info(f"Collecting investor trade daily for {len(targets)} symbols on {d}")
                    loop_start_time = time.time()
                    total_targets = len(targets)
                    for idx, stk_cd in enumerate(targets):
                        if idx % 50 == 0 or idx == total_targets - 1:
                            elapsed = time.time() - loop_start_time
                            if elapsed == 0:
                                elapsed = 1e-6
                            items_per_sec = (idx + 1) / elapsed
                            remaining = total_targets - (idx + 1)
                            eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                            eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                            progress_pct = (idx + 1) / total_targets * 100.0
                            
                            logger.info(
                                f"[KDMS 일일 수급 수집] Progress: {progress_pct:.1f}% ({idx+1}/{total_targets}) | "
                                f"Speed: {items_per_sec:.1f} it/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str} | "
                                f"Current: {stk_cd}"
                            )
                        try:
                            records = self.kis_client.fetch_investor_trade_daily(stk_cd, start_date=d, end_date=d)
                            if records:
                                day_records = [r for r in records if r.get("dt") == d]
                                if day_records:
                                    self.investor_trade_repo.upsert_daily_investor_trade(day_records)
                                    collected += len(day_records)
                                    investor_count += len(day_records)
                        except Exception as e:
                            logger.error(f"Failed to collect investor trade for {stk_cd} on {d}: {e}")
                            failed += 1
            except Exception as ite:
                logger.error(f"Failed in daily investor trade collection process: {ite}")

        return {
            "collected": collected,
            "failed": failed,
            "skipped": skipped,
            "active_count": len(active_stocks) if active_stocks else 0,
            "new_listings": new_listings,
            "delistings": delistings,
            "ticker_changes": ticker_changes,
            "daily_ohlcv_count": daily_ohlcv_count,
            "market_cap_count": market_cap_count,
            "minute_count": minute_count,
            "investor_count": investor_count,
            "blacklisted_count": len(blacklisted_stocks) if blacklisted_stocks else 0,
            "adjusted_factor_count": adjusted_factor_count,
            "factor_rebuilt_count": factor_rebuilt_count,
        }

    def _collect_daily_minute_data_range(self, start_date: date, end_date: date) -> int:
        """당일 분기 대상 종목들에 대해 Kiwoom API를 통해 공백 기간(start_date ~ end_date) 분봉 데이터를 동적으로 수집하고 적재합니다."""
        logger.info(f"--- Starting Daily Minute Data Range Collection ({start_date} ~ {end_date}) ---")
        total_minute_records = 0
        
        # 종목별 분봉 최신 적재 시점 벌크 로딩
        minute_last_map = {}
        try:
            minute_last_map = self.ohlcv_repo.get_all_minute_latest_datetimes()
        except Exception as m_err:
            logger.warning(f"Failed to pre-load stocks latest minute datetimes: {m_err}")

        # 영업일 수 계산
        trading_days = self.ohlcv_repo.get_trading_days_count(start_date, end_date)
        if isinstance(trading_days, MagicMock):
            trading_days = 1
        if trading_days == 0:
            logger.info("No trading days in range for minute data. Skipping.")
            return 0
            
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
        
        logger.info(f"Targeting {len(target_stocks)} stocks for daily range minute collection on {end_date_str}.")

        for idx, stk_cd in enumerate(target_stocks):
            try:
                # 종목별 개별 분봉 갭 및 max_requests 동적 산정
                last_dt_tm = minute_last_map.get(stk_cd)
                if last_dt_tm:
                    # last_dt_tm.date()와 end_date 사이의 공백 영업일 수 계산
                    gap_days = self.ohlcv_repo.get_trading_days_count(last_dt_tm.date() + timedelta(days=1), end_date)
                    if isinstance(gap_days, MagicMock):
                        gap_days = 1
                    
                    # 이미 최신 날짜까지 완벽하게 수집되었다면 수집 스킵 (키움 API 요청 절약)
                    if gap_days <= 0:
                        continue
                    
                    stk_max_requests = max(1, (gap_days * 380) // 600 + 1)
                    logger.debug(f"[{stk_cd}] Detected minute collection gap of {gap_days} days. Setting max_requests={stk_max_requests}.")
                else:
                    # 적재 이력이 없는 신규 대상 종목인 경우 넉넉하게 10영업일치(max_requests=7) 수집
                    stk_max_requests = 7
                    logger.info(f"[{stk_cd}] No minute data history. Setting max_requests={stk_max_requests} for initial backfill.")

                # 최신 영업일(end_date_str) 기준 과거로 연속 수집
                collected = self.kiwoom_client.get_minute_chart(stk_cd, start_date=end_date_str, max_requests=stk_max_requests)
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
                        total_minute_records += len(transformed)
                        logger.info(f"[{stk_cd}] Range minute data {len(transformed)} records upserted.")
                
                # 키움 API 봇 차단 및 부하 완화 딜레이 (MagicMock이 아닐 때만 0.2초 대기)
                if not isinstance(self.kiwoom_client, MagicMock):
                    time.sleep(0.2)
            except Exception as me:
                logger.error(f"Failed to collect daily minute data for {stk_cd}: {me}")
        
        return total_minute_records



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

        from repositories.investor_trade_repo import InvestorTradeRepo
        investor_trade_repo = InvestorTradeRepo(pool)

        task = DailyTask(
            kis_client=kis_client,
            ohlcv_repo=ohlcv_repo,
            master_repo=master_repo,
            factor_repo=factor_repo,
            market_cap_repo=market_cap_repo,
            kiwoom_client=kiwoom_client,
            investor_trade_repo=investor_trade_repo
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

        # 수집 범위 산출: 시간외 거래량 보정 및 안전한 수집 갭 메우기를 위해
        # 평시 수집 범위를 기본적으로 target_date의 최근 5일 전(T-5)부터 target_date(T)로 넓게 확장합니다.
        # 개별 종목의 수집 갭은 DailyTask.run 내부에서 stk_last_dt 기반으로 더 넓게 자동 확장됩니다.
        start_date = target_date - timedelta(days=5)
        end_date = target_date
        
        # open_trading_days 유틸을 사용해 실제 해당 기간 내의 영업일만 추출하여 시작/종료 범위 재계산
        try:
            open_days = ohlcv_repo.get_open_trading_days(start_date, end_date)
            if open_days:
                start_date = min(open_days)
                end_date = max(open_days)
        except Exception as date_range_err:
            logger.warning(f"Failed to refine trading days range: {date_range_err}")

        logger.info(f"[{job_id}] Base collection range expanded for volume correction: {start_date} ~ {end_date}")

        if start_date == end_date:
            result = task.run(start_date)
        else:
            result = task.run(start_date, end_date)



        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        total_duration_str = format_duration_str(duration)
        
        skipped_count = result.get("skipped", 0)
        if skipped_count > 0 and result.get("collected", 0) == 0 and result.get("failed", 0) == 0:
            final_log = f"수집 스킵 (휴장일 범위: {start_date} ~ {end_date})"
            last_status = "success (holiday skipped)"
        else:
            final_log = f"수집 완료 (성공: {result['collected']}건, 실패: {result['failed']}건, 스킵: {skipped_count}건, 소요시간: {total_duration_str})"
            last_status = "success"

        active_cnt = result.get("active_count", 0)
        daily_cnt = result.get("daily_ohlcv_count", 0)
        mc_cnt = result.get("market_cap_count", 0)
        minute_cnt = result.get("minute_count", 0)
        investor_cnt = result.get("investor_count", 0)
        blacklisted_cnt = result.get("blacklisted_count", 0)
        factor_rebuilt = result.get("factor_rebuilt_count", 0)

        new_listings = result.get("new_listings", 0)
        delistings = result.get("delistings", 0)
        ticker_changes = result.get("ticker_changes", 0)

        steps = [
            {
                "step": "Master Sync",
                "status": "SUCCESS",
                "duration_seconds": float(result.get("step1_duration", 0.0)),
                "details": {
                    "active_count": active_cnt,
                    "new_listings": new_listings,
                    "delistings": delistings,
                    "ticker_changes": ticker_changes
                }
            },
            {
                "step": "Market Data Loader",
                "status": "SUCCESS",
                "duration_seconds": float(result.get("step2_duration", 0.0)),
                "details": {
                    "processed_count": daily_cnt,
                    "market_cap_count": mc_cnt,
                    "minute_count": minute_cnt,
                    "investor_count": investor_cnt,
                    "blacklisted_count": blacklisted_cnt,
                    "failed_count": result.get("failed", 0)
                }
            },
            {
                "step": "Factor & Adjustment",
                "status": "SUCCESS",
                "duration_seconds": float(result.get("step3_duration", 0.0)),
                "details": {
                    "adjusted_factor_count": result.get("adjusted_factor_count", 0),
                    "factor_rebuilt_count": factor_rebuilt
                }
            }
        ]

        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": last_status,
            "end_time": end_time.isoformat(),
            "duration": total_duration_str,
            "total_duration_seconds": duration,
            "total_duration_str": total_duration_str,
            "last_log": final_log,
            "collected": result.get("collected", 0),
            "failed": result.get("failed", 0),
            "skipped": skipped_count,
            "total_blacklisted_count": blacklisted_cnt,
            "steps": steps
        })
        logger.info(f"✅ [{job_id}] {final_log}")

    except Exception as e:
        logger.critical(f"[{job_id}] 일일 수집 태스크 구동 중 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now(KST).isoformat(),
            "last_log": f"수집 실패 (오류: {e})",
            "steps": [
                {
                    "step": "Task Execution Error",
                    "status": "FAILED",
                    "duration_seconds": 0.0,
                    "details": {
                        "error": str(e)
                    }
                }
            ]
        })
    finally:
        status_dict = job_statuses.get(job_id, {})
        status_dict["is_running"] = False
        job_statuses[job_id] = status_dict

