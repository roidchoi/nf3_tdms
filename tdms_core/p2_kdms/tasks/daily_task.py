# tasks/daily_task.py

from datetime import date, timedelta
import pandas as pd
from typing import Dict, Any
from collectors.factor_calculator import calculate_factors

class DailyTask:
    """
    일일 데이터 수집 및 수정계수/수정주가 갱신 작업을 총괄하는 태스크 조정자.
    """

    def __init__(self, kis_client, ohlcv_repo, master_repo, factor_repo=None) -> None:
        self.kis_client = kis_client
        self.ohlcv_repo = ohlcv_repo
        self.master_repo = master_repo
        self.factor_repo = factor_repo

    def run(self, target_date: date) -> Dict[str, int]:
        """
        일일 데이터 수집 및 갱신 태스크를 실행합니다.
        순서: 
          1. KIS 마스터 다운로드 및 stock_info 업서트
          2. 활성 종목 리스트 대상 daily_ohlcv 수집 및 저장
          3. 수정계수(factors) 역산 및 저장 (factor_repo가 제공된 경우)
          4. 물리 수정주가 테이블(daily_ohlcv_adjusted) 갱신
        """
        collected = 0
        failed = 0
        skipped = 0

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

        # 5. 물리 수정주가 테이블(daily_ohlcv_adjusted) 일괄 갱신 (최근 30일 범위 배치)
        if self.factor_repo is not None:
            try:
                start_update_dt = target_date - timedelta(days=30)
                self.ohlcv_repo.refresh_adjusted_ohlcv_batch(start_update_dt, target_date, 'KIS')
            except Exception as re:
                print(f"Failed to refresh adjusted ohlcv physical table: {re}")

        return {"collected": collected, "failed": failed, "skipped": skipped}

