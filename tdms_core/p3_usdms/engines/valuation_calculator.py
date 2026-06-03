import logging
import gc
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from p3_usdms.repositories.valuation_repo import ValuationRepo

logger = logging.getLogger(__name__)

class ValuationCalculator:
    def __init__(self, repo: ValuationRepo = None):
        self.repo = repo if repo else ValuationRepo()

    def calculate_and_save(self, cik: str, start_date=None, rebuild=False, latest_val_dates_cache: Dict[str, Any] = None) -> None:
        """
        특정 CIK의 PIT 가치평가 데이터를 계산하고 데이터베이스에 저장합니다.
        """
        # 1. 증분 계산(Incremental) 범위 처리
        latest_dt = None
        if not rebuild and start_date is None:
            if latest_val_dates_cache is not None:
                latest_dt = latest_val_dates_cache.get(cik)
            else:
                latest_dt = self.repo.get_latest_valuation_date(cik)

            if latest_dt:
                # 최신 날짜의 string 변환 또는 datetime 호환 포맷 지정
                start_date = str(latest_dt)
                logger.debug(f"[{cik}] Incremental start date detected (cache or DB): {start_date}")

        # 2. Raw 데이터 로드
        prices_raw = self.repo.load_prices(cik, start_date=start_date)
        
        # 증분(Incremental) 스킵 체크
        if not rebuild and latest_dt is not None and prices_raw:
            max_price_dt = max(p['dt'] for p in prices_raw)
            if str(max_price_dt) <= str(latest_dt):
                logger.debug(f"[{cik}] Daily valuations are already up-to-date (latest_dt: {latest_dt}). Skipping calculation.")
                return

        financials_raw = self.repo.load_financials(cik)
        shares_raw = self.repo.load_shares(cik)

        # 3. 데이터 유효성 검증
        if not prices_raw or not financials_raw:
            logger.debug(f"[{cik}] Insufficient data for valuation. Prices count: {len(prices_raw)}, Financials count: {len(financials_raw)}")
            return

        # 4. 판다스 데이터프레임 변환
        prices_df = pd.DataFrame(prices_raw)
        financials_df = pd.DataFrame(financials_raw)
        
        # 5. 주식수 Hybrid Fallback 수행
        if shares_raw:
            shares_df = pd.DataFrame(shares_raw)
        else:
            # 주식수 이력이 없는 경우, 재무 데이터의 shares_outstanding을 fallback으로 빌드
            fallback_shares = [
                {'filed_dt': f['filed_dt'], 'val': f['shares_outstanding']}
                for f in financials_raw
                if f.get('shares_outstanding') is not None
            ]
            if fallback_shares:
                shares_df = pd.DataFrame(fallback_shares)
            else:
                shares_df = pd.DataFrame(columns=['filed_dt', 'val'])

        if shares_df.empty:
            logger.debug(f"[{cik}] Shares outstanding history is entirely missing. Cannot compute market cap.")
            return

        # 6. 정렬 및 타입 캐스팅
        prices_df['dt'] = pd.to_datetime(prices_df['dt'])
        prices_df = prices_df.sort_values('dt').reset_index(drop=True)
        
        shares_df['filed_dt'] = pd.to_datetime(shares_df['filed_dt'])
        shares_df = shares_df.sort_values('filed_dt').reset_index(drop=True)
        
        financials_df['filed_dt'] = pd.to_datetime(financials_df['filed_dt'])
        financials_df = financials_df.sort_values('filed_dt').reset_index(drop=True)

        # 7. 재무 컬럼 데이터 타입 강제 캐스팅 (결측 방지 및 컬럼 누락 방어)
        numeric_financial_cols = [
            'net_income', 'total_equity', 'revenue', 'ebitda', 'ocf', 
            'total_debt', 'cash_and_equiv', 'shares_outstanding'
        ]
        for col in numeric_financial_cols:
            if col not in financials_df.columns:
                financials_df[col] = np.nan
            else:
                financials_df[col] = pd.to_numeric(financials_df[col], errors='coerce')

        # 8. TTM (연간화) 산출 공식 적용
        # fiscal_period가 'FY'면 원본값, 분기면 * 4 곱해 TTM을 시뮬레이션
        is_fy = financials_df['fiscal_period'] == 'FY'
        
        financials_df['net_income_ttm'] = np.where(is_fy, financials_df['net_income'], financials_df['net_income'] * 4)
        financials_df['revenue_ttm'] = np.where(is_fy, financials_df['revenue'], financials_df['revenue'] * 4)
        financials_df['ebitda_ttm'] = np.where(is_fy, financials_df['ebitda'], financials_df['ebitda'] * 4)
        financials_df['ocf_ttm'] = np.where(is_fy, financials_df['ocf'], financials_df['ocf'] * 4)

        # 9. Point-in-Time 매칭 (merge_asof backward)
        # 9-1. 가격 기준 주식수 매칭
        merged = pd.merge_asof(
            prices_df,
            shares_df[['filed_dt', 'val']],
            left_on='dt',
            right_on='filed_dt',
            direction='backward'
        )
        merged.rename(columns={'val': 'shares'}, inplace=True)
        if 'filed_dt' in merged.columns:
            merged.drop(columns=['filed_dt'], inplace=True)

        # 9-2. 재무 데이터 매칭
        merged = pd.merge_asof(
            merged,
            financials_df,
            left_on='dt',
            right_on='filed_dt',
            direction='backward'
        )

        # 10. 지표 계산
        merged['shares'] = pd.to_numeric(merged['shares'], errors='coerce')
        merged['cls_prc'] = pd.to_numeric(merged['cls_prc'], errors='coerce')
        
        # mkt_cap
        merged['mkt_cap'] = merged['cls_prc'] * merged['shares']

        # Safe division helper
        def safe_div_series(a, b):
            return np.where((b != 0) & pd.notna(b) & pd.notna(a), a / b, np.nan)

        # Pe, Pb, Ps, Pcr, EV/EBITDA
        merged['pe'] = safe_div_series(merged['mkt_cap'], merged['net_income_ttm'])
        merged['pb'] = safe_div_series(merged['mkt_cap'], merged['total_equity'])
        merged['ps'] = safe_div_series(merged['mkt_cap'], merged['revenue_ttm'])
        merged['pcr'] = safe_div_series(merged['mkt_cap'], merged['ocf_ttm'])
        
        # ev = mkt_cap + debt.fillna(0) - cash.fillna(0)
        debt_filled = merged['total_debt'].fillna(0.0)
        cash_filled = merged['cash_and_equiv'].fillna(0.0)
        merged['ev'] = merged['mkt_cap'] + debt_filled - cash_filled
        
        merged['ev_ebitda'] = safe_div_series(merged['ev'], merged['ebitda_ttm'])

        # 11. 결과 정제 및 Python None 치환
        cols_to_clean = ['mkt_cap', 'pe', 'pb', 'ps', 'pcr', 'ev_ebitda']
        for col in cols_to_clean:
            # inf / -inf 치환
            merged[col] = merged[col].replace([np.inf, -np.inf], np.nan)
            # pandas.notnull 값만 취하고 나머지는 None으로
            merged[col] = merged[col].where(pd.notnull(merged[col]), None)

        # 12. 튜플 리스트 가공 및 저장
        # (dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda)
        valuations_to_save = []
        
        def clean_val(v):
            return None if pd.isna(v) else float(v)

        for idx, row in merged.iterrows():
            # dt를 string(YYYY-MM-DD) 형식으로 변환
            dt_str = row['dt'].strftime('%Y-%m-%d')
            valuations_to_save.append((
                dt_str,
                cik,
                clean_val(row['mkt_cap']),
                clean_val(row['pe']),
                clean_val(row['pb']),
                clean_val(row['ps']),
                clean_val(row['pcr']),
                clean_val(row['ev_ebitda'])
            ))

        self.repo.save_valuations(valuations_to_save)
        logger.info(f"[{cik}] PIT Valuation computed & saved {len(valuations_to_save)} records (start_date={start_date}).")

        # 13. [메모리 최적화] 로컬 데이터프레임 파괴 및 GC 강제 구동
        del prices_df
        del financials_df
        del shares_df
        del merged
        gc.collect()
