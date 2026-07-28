import logging
import pandas as pd
import numpy as np
from typing import Any

logger = logging.getLogger(__name__)

class PriceEngine:
    def __init__(self, price_repo: Any) -> None:
        self.price_repo = price_repo

    def calculate_factors_from_ratio(self, cik: str, df: pd.DataFrame) -> None:
        """
        수정주가 비율 변동(Ratio = Adj Close / Close)을 추적하여 수정계수 산출 및 DB 적재.
        Formula: Factor = Ratio_t-1 / Ratio_t
        변화 감지 입계치: delta >= 1e-5
        """
        if 'Adj Close' not in df.columns or 'Close' not in df.columns:
            logger.warning(f"[{cik}] Missing Close or Adj Close for factor calc")
            return

        if df.empty:
            return

        # 날짜 오름차순 정렬 (과거 -> 미래)
        df = df.sort_index()
        
        # 1. Ratio 계산 (0 종가는 NaN 처리하여 ZeroDivision 방지)
        raw_close = df['Close'].replace(0, np.nan)
        ratio = df['Adj Close'] / raw_close
        
        # 2. 전일 비율 획득
        prev_ratio = ratio.shift(1)
        
        # 3. 변동 감지 (임계값 1e-5)
        delta = (ratio - prev_ratio).abs()
        events = df[delta >= 1e-5].copy()
        
        if events.empty:
            return

        factors = []
        for dt, row in events.iterrows():
            curr_r = ratio.loc[dt]
            prev_r = prev_ratio.loc[dt]
            
            # 분모 0 체크 및 NaN 체크
            if pd.isna(curr_r) or pd.isna(prev_r) or curr_r == 0:
                continue
                
            factor_val = prev_r / curr_r
            
            # date 타입 혹은 timestamp 대응
            event_date = dt.date() if hasattr(dt, 'date') else pd.to_datetime(dt).date()
            
            factors.append({
                'cik': cik,
                'event_dt': event_date,
                'factor_val': float(factor_val),
                'event_type': 'ADJUSTMENT',  # 순수 수학적 역산이므로 포괄 명명
                'matched_info': f"Ratio Change: {prev_r:.4f} -> {curr_r:.4f}"
            })
            
        # 4. DB Upsert (중복 제거 및 DB 반영)
        if factors:
            unique_factors = {}
            for f in factors:
                key = (f['cik'], f['event_dt'], f['event_type'])
                unique_factors[key] = f
            
            clean_factors = list(unique_factors.values())
            self.price_repo.upsert_price_factors(clean_factors)
            logger.debug(f"[{cik}] Calculated {len(clean_factors)} adjustment factors.")
