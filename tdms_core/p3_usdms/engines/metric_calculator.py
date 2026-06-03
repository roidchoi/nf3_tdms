import logging
import gc
from datetime import date
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from p3_usdms.repositories.valuation_repo import ValuationRepo

logger = logging.getLogger(__name__)

class MetricCalculator:
    def __init__(self, repo: ValuationRepo = None):
        self.repo = repo if repo else ValuationRepo()

    def calculate_and_save(self, cik: str, rebuild: bool = False, 
                           latest_fin_dates_cache: Dict[str, Any] = None, 
                           latest_met_dates_cache: Dict[str, Any] = None) -> None:
        """
        특정 CIK의 재무비율 및 YoY 성장률을 계산하여 데이터베이스에 저장합니다.
        """
        # 증분(Incremental) 스킵 체크
        if not rebuild:
            if latest_fin_dates_cache is not None:
                latest_financial = latest_fin_dates_cache.get(cik)
            else:
                latest_financial = self.repo.get_latest_financial_filed_date(cik)

            if latest_met_dates_cache is not None:
                latest_metric = latest_met_dates_cache.get(cik)
            else:
                latest_metric = self.repo.get_latest_metric_filed_date(cik)

            if latest_financial and latest_metric and str(latest_financial) == str(latest_metric):
                logger.debug(f"[{cik}] Metrics are already up-to-date (cache or DB: {latest_financial}). Skipping calculation.")
                return

        # 1. 재무 데이터 로드
        financials_raw = self.repo.load_financials(cik)
        if not financials_raw:
            logger.debug(f"[{cik}] No financials found for metric calculation.")
            return

        df = pd.DataFrame(financials_raw)

        # 2. 수치 필드 데이터 타입 강제 캐스팅 (컬럼 누락 방어 포함)
        numeric_cols = [
            'total_assets', 'current_assets', 'cash_and_equiv', 'inventory', 'account_receivable',
            'total_equity', 'retained_earnings', 'total_liabilities', 'current_liabilities', 'total_debt',
            'shares_outstanding', 'revenue', 'cogs', 'gross_profit',
            'sgna_expense', 'rnd_expense', 'op_income', 'interest_expense', 'tax_provision', 'net_income',
            'ebitda', 'ocf', 'capex', 'fcf'
        ]
        for col in numeric_cols:
            if col not in df.columns:
                df[col] = np.nan
            else:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Safe division helper
        def safe_div(a, b):
            return np.where((b != 0) & pd.notna(b) & pd.notna(a), a / b, np.nan)

        # 3. Profitability 연산
        df['roe'] = safe_div(df['net_income'], df['total_equity'])
        df['roa'] = safe_div(df['net_income'], df['total_assets'])
        
        # ROIC = Op Income / (Total Equity + Total Debt)
        total_debt_filled = df['total_debt'].fillna(0.0)
        df['roic'] = safe_div(df['op_income'], (df['total_equity'] + total_debt_filled))
        
        df['op_margin'] = safe_div(df['op_income'], df['revenue'])
        df['net_margin'] = safe_div(df['net_income'], df['revenue'])

        # 4. Quality & Stability 연산
        df['gp_a_ratio'] = safe_div(df['gross_profit'], df['total_assets'])
        df['debt_ratio'] = safe_div(df['total_liabilities'], df['total_assets'])
        df['current_ratio'] = safe_div(df['current_assets'], df['current_liabilities'])
        df['interest_coverage'] = safe_div(df['op_income'], df['interest_expense'])

        # 5. YoY 성장률 연산
        if 'fiscal_year' in df.columns and 'fiscal_period' in df.columns:
            # 유효한 fiscal_year 및 fiscal_period 필터링
            valid_idx = df['fiscal_year'].notna() & df['fiscal_period'].notna()
            valid_df = df[valid_idx].copy()
            
            # 전년 동기(T-1) 비교 시, 각 기간별 가장 늦게 공시된 '최종본'을 기준 인덱스로 삼기 위함
            # filed_dt 오름차순으로 정렬한 뒤 중복을 제거하면 가장 최신 filed_dt만 남음
            valid_df = valid_df.sort_values('filed_dt')
            ref_df = valid_df.drop_duplicates(subset=['fiscal_year', 'fiscal_period'], keep='last')
            ref_df = ref_df.set_index(['fiscal_year', 'fiscal_period'])

            # prev_fy 컬럼을 생성하여 merge key로 활용
            df['prev_fy'] = df['fiscal_year'] - 1
            
            # T-1년 동기와 조인
            merged = df.merge(
                ref_df[['revenue', 'op_income', 'net_income', 'shares_outstanding']],
                left_on=['prev_fy', 'fiscal_period'],
                right_index=True,
                how='left',
                suffixes=('', '_prev')
            )

            # 매출액 성장률 & 영업이익 성장률
            df['rev_growth_yoy'] = safe_div((merged['revenue'] - merged['revenue_prev']), merged['revenue_prev'].abs())
            df['op_growth_yoy'] = safe_div((merged['op_income'] - merged['op_income_prev']), merged['op_income_prev'].abs())

            # EPS 성장률 (EPS = Net Income / Shares Outstanding)
            eps_curr = safe_div(merged['net_income'], merged['shares_outstanding'])
            eps_prev = safe_div(merged['net_income_prev'], merged['shares_outstanding_prev'])
            
            df['eps_growth_yoy'] = safe_div((eps_curr - eps_prev), np.abs(eps_prev))
            
            # 임시 컬럼 삭제
            df.drop(columns=['prev_fy'], errors='ignore', inplace=True)
            del merged
            del valid_df
            del ref_df
        else:
            df['rev_growth_yoy'] = np.nan
            df['op_growth_yoy'] = np.nan
            df['eps_growth_yoy'] = np.nan

        # 6. 결과 정제 및 Python None 치환 (DB 적재 규격화)
        cols_to_clean = [
            'roe', 'roa', 'roic', 'op_margin', 'net_margin',
            'gp_a_ratio', 'debt_ratio', 'current_ratio', 'interest_coverage',
            'rev_growth_yoy', 'op_growth_yoy', 'eps_growth_yoy'
        ]
        for col in cols_to_clean:
            if col in df.columns:
                df[col] = df[col].replace([np.inf, -np.inf], np.nan)
                df[col] = df[col].where(pd.notnull(df[col]), None)

        # 7. 튜플 리스트 가공 및 저장
        metrics_to_save = []
        
        def clean_val(v):
            return None if pd.isna(v) else float(v)

        for idx, row in df.iterrows():
            # report_period 가 date 또는 string일 수 있으므로 포맷 보정
            report_period_str = row['report_period']
            if isinstance(report_period_str, (pd.Timestamp, date)):
                report_period_str = report_period_str.strftime('%Y-%m-%d')
                
            filed_dt_str = row['filed_dt']
            if isinstance(filed_dt_str, (pd.Timestamp, date)):
                filed_dt_str = filed_dt_str.strftime('%Y-%m-%d')

            metrics_to_save.append((
                cik,
                report_period_str,
                filed_dt_str,
                clean_val(row['roe']),
                clean_val(row['roa']),
                clean_val(row['roic']),
                clean_val(row['op_margin']),
                clean_val(row['net_margin']),
                clean_val(row['gp_a_ratio']),
                clean_val(row['debt_ratio']),
                clean_val(row['current_ratio']),
                clean_val(row['interest_coverage']),
                clean_val(row['rev_growth_yoy']),
                clean_val(row['op_growth_yoy']),
                clean_val(row['eps_growth_yoy'])
            ))

        self.repo.save_metrics(metrics_to_save)
        logger.info(f"[{cik}] Financial Metrics computed & saved {len(metrics_to_save)} records.")

        # 8. [메모리 최적화] 로컬 데이터프레임 소멸 및 GC 구동
        del df
        gc.collect()
