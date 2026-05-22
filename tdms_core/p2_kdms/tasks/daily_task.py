import os
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from typing import Dict, Any
from unittest.mock import MagicMock

from collectors.factor_calculator import calculate_factors
from p1_shared.api.kis_api_core import KisApiCore
from collectors.kis_kr_client import KisKrClient
from repositories.base import create_kdms_pool
from repositories.master_repo import MasterRepo
from repositories.ohlcv_repo import OhlcvRepo
from repositories.factor_repo import FactorRepo
from repositories.market_cap_repo import MarketCapRepo
from p1_shared.utils.env_detector import EnvDetector

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

class DailyTask:
    """
    일일 데이터 수집 및 수정계수/수정주가 갱신 작업을 총괄하는 태스크 조정자.
    """

    def __init__(self, kis_client, ohlcv_repo, master_repo, factor_repo=None, market_cap_repo=None) -> None:
        self.kis_client = kis_client
        self.ohlcv_repo = ohlcv_repo
        self.master_repo = master_repo
        self.factor_repo = factor_repo
        self.market_cap_repo = market_cap_repo

    def run(self, target_date: date) -> Dict[str, int]:
        """
        일일 데이터 수집 및 갱신 태스크를 실행합니다.
        순서: 
          1. KIS 마스터 다운로드 및 stock_info 업서트
          2. 활성 종목 리스트 대상 daily_ohlcv 수집 및 저장
          3. 시가총액 계산 및 저장 (market_cap_repo가 제공된 경우)
          4. 수정계수(factors) 역산 및 저장 (factor_repo가 제공된 경우)
          5. 물리 수정주가 테이블(daily_ohlcv_adjusted) 갱신
        """
        collected = 0
        failed = 0
        skipped = 0
        mc_records = []

        # 1. 종목마스터 수집 및 갱신
        try:
            master_records = self.kis_client.fetch_stock_master()
            if master_records:
                self.master_repo.upsert_stock_info(master_records)
        except Exception as e:
            # 마스터 수집 실패 시 전체 중단하지 않고 로그를 남긴 뒤 기존 DB 상의 active 종목으로 진행
            print(f"Stock master update failed: {e}")

        # 2. 수집 대상 활성 종목 조회
        active_stocks = self.master_repo.get_all_active_stocks()
        if not active_stocks:
            return {"collected": 0, "failed": 0, "skipped": 0}

        # 3. 각 종목별 OHLCV 및 수정계수 수집/처리
        for stock in active_stocks:
            stk_cd = stock.get("stk_cd")
            if not stk_cd:
                continue

            try:
                # Raw OHLCV 시세 수집
                ohlcv = self.kis_client.fetch_daily_ohlcv(stk_cd, target_date)
                if ohlcv:
                    # DB에 원본 시세 UPSERT
                    self.ohlcv_repo.upsert_daily_ohlcv([ohlcv])
                    
                    # 시가총액 레코드 빌드
                    if self.market_cap_repo is not None:
                        shares = stock.get("listed_shares", 0) or 0
                        mkt_cap = ohlcv["close"] * shares
                        amt = ohlcv["close"] * ohlcv["volume"]
                        mc_records.append({
                            "dt": target_date,
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
                        start_dt = target_date - timedelta(days=45)
                        try:
                            raw_list = self.kis_client.fetch_ohlcv_range(stk_cd, start_dt, target_date, adj_price='1')
                            adj_list = self.kis_client.fetch_ohlcv_range(stk_cd, start_dt, target_date, adj_price='0')
                            
                            df_raw = pd.DataFrame(raw_list).rename(columns={"close": "raw_close"})
                            df_adj = pd.DataFrame(adj_list).rename(columns={"close": "adj_close"})
                            
                            if not df_raw.empty and not df_adj.empty:
                                df = pd.merge(df_raw, df_adj, on="dt", how="inner")
                                factors = calculate_factors(df, stk_cd, "KIS")
                                if factors:
                                    self.factor_repo.upsert_adjustment_factors(factors)
                        except Exception as fe:
                            # 수정계수 계산 실패 시 경고 출력 후 시세 수집 완료 처리 진행
                            print(f"Failed to calculate factors for {stk_cd}: {fe}")
                    
                    collected += 1
                else:
                    # 수집 결과 없음 (휴장일 또는 데이터 미존재) -> Gap 기록
                    self.ohlcv_repo.record_gap(stk_cd, target_date, "No data returned from KIS API")
                    failed += 1
            except Exception as e:
                # 수집 에러 발생 -> Gap 기록
                self.ohlcv_repo.record_gap(stk_cd, target_date, str(e))
                failed += 1

        # 4. 시가총액 일괄 저장
        if self.market_cap_repo is not None and mc_records:
            try:
                self.market_cap_repo.upsert_daily_market_cap(mc_records)
            except Exception as mce:
                print(f"Failed to upsert daily market cap records: {mce}")

        # 5. 물리 수정주가 테이블(daily_ohlcv_adjusted) 일괄 갱신 (최근 30일 범위 배치)
        if self.factor_repo is not None:
            try:
                start_update_dt = target_date - timedelta(days=30)
                self.ohlcv_repo.refresh_adjusted_ohlcv_batch(start_update_dt, target_date, 'KIS')
            except Exception as re:
                print(f"Failed to refresh adjusted ohlcv physical table: {re}")

        return {"collected": collected, "failed": failed, "skipped": skipped}


def run_daily_update(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    일일 데이터 수집, 시가총액 계산 및 수정계수/수정주가 갱신 파이프라인 태스크.
    
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
        "failed": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        # DB 커넥션 풀 및 리포지토리 초기화
        pool = create_kdms_pool()
        master_repo = MasterRepo(pool)
        ohlcv_repo = OhlcvRepo(pool)
        factor_repo = FactorRepo(pool)
        market_cap_repo = MarketCapRepo(pool)

        # KIS Client 초기화
        if test_mode:
            # 테스트 모드 시 모의 클라이언트 사용 (기존에 작성된 pytest 모킹 등을 활용)
            kis_client = MagicMock()
        else:
            detector = EnvDetector()
            profile = detector.load_env_profile()
            env = detector.detect()
            is_dev = (env == "dev")

            appkey = profile.get("kis_appkey") or os.environ.get("KIS_APPKEY", "")
            appsecret = profile.get("kis_appsecret") or os.environ.get("KIS_APPSECRET", "")

            api_core = KisApiCore(
                appkey=appkey,
                appsecret=appsecret,
                is_dev=is_dev
            )
            kis_client = KisKrClient(api_core=api_core)

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
            market_cap_repo=market_cap_repo
        )
        
        target_date = start_time.date()
        result = task.run(target_date)

        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        final_log = f"수집 완료 (성공: {result['collected']}건, 실패: {result['failed']}건, 소요시간: {int(duration)}초)"
        
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초",
            "last_log": final_log,
            "collected": result["collected"],
            "failed": result["failed"]
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



