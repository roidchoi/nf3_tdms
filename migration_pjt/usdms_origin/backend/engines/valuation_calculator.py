import logging
import pandas as pd
import numpy as np
from backend.collectors.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

class ValuationCalculator:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager if db_manager else DatabaseManager()

    def calculate_and_save(self, cik: str, start_date=None):
        # Define target columns for TTM and Metrics early
        target_cols = ['net_income', 'revenue', 'ebitda', 'ocf']

        # 1. Load Data
        prices = self._load_prices(cik, start_date)
        if prices.empty:
            logger.debug(f"[{cik}] No prices found.")
            return

        # For financials/shares, we might need older data for lookback filling, 
        # but for calculation we mainly care about the target window. 
        # However, merge_asof needs enough history. 
        # Let's load full history for sparse tables (financials/shares) as they are small,
        # but restrict prices which are heavy.
        financials = self._load_financials(cik)
        if financials.empty:
            logger.debug(f"[{cik}] No financials found.")
            return

        shares = self._load_shares(cik)
        
        # [Strategy Update] Hybrid Fallback
        # 주식 수 이력(Share History)이 없으면, 재무제표(Financials)의 주식 수를 사용
        if shares.empty:
            if 'shares_outstanding' in financials.columns and not financials['shares_outstanding'].isna().all():
                # Financials에서 주식 수 추출 (filed_dt 기준)
                shares = financials[['filed_dt', 'shares_outstanding']].rename(
                    columns={'shares_outstanding': 'val'}
                ).dropna()
            else:
                logger.debug(f"[{cik}] No shares found.")
                return
        
        # [Critical Fix] Ensure DateTime Types for merge_asof
        prices['dt'] = pd.to_datetime(prices['dt'])
        shares['filed_dt'] = pd.to_datetime(shares['filed_dt'])
        financials['filed_dt'] = pd.to_datetime(financials['filed_dt'])
        
        # [Critical Fix] Enforce Numeric Types to prevent TypeError (None division)
        # Shares
        shares['val'] = pd.to_numeric(shares['val'], errors='coerce')
        
        # Financials
        fin_numeric_cols = ['total_equity', 'total_debt', 'cash_and_equiv'] + [f'{c}_ttm' for c in target_cols]
        for col in fin_numeric_cols:
             if col in financials.columns:
                 financials[col] = pd.to_numeric(financials[col], errors='coerce')
        
        prices['cls_prc'] = pd.to_numeric(prices['cls_prc'], errors='coerce')

        # 2. Pre-processing
        prices = prices.sort_values('dt')
        shares = shares.sort_values('filed_dt')
        financials = financials.sort_values('filed_dt')

        # TTM / Annualize Logic (Ensure numeric BEFORE this if possible)
        # Actually TTM logic uses financial cols.
        # Let's move TTM logic AFTER numeric conversion? 
        # But 'target_cols' are used in loop.
        # Wait, TTM calculation involves multplication.
        # So we should convert target_cols to numeric BEFORE TTM calculation.
        
        # Re-ordering for safety:
        # 1. Convert Base Columns
        base_cols = ['net_income', 'revenue', 'ebitda', 'ocf', 'total_equity', 'total_debt', 'cash_and_equiv']
        for col in base_cols:
            if col in financials.columns:
                financials[col] = pd.to_numeric(financials[col], errors='coerce')

        # 2. Calc TTM
        for col in target_cols:
            if col in financials.columns:
                # Multiply by 4 if needed (vectorized safe with NaN)
                financials[f'{col}_ttm'] = np.where(
                    financials['fiscal_period'] == 'FY',
                    financials[col],
                    financials[col] * 4
                )
            else:
                financials[f'{col}_ttm'] = np.nan # Use NaN instead of None
        
        # 3. PIT Matching (Merge Asof)

        # 3. PIT Matching (Merge Asof)
        # 3.1 Match Shares
        merged = pd.merge_asof(
            prices, 
            shares[['filed_dt', 'val']].rename(columns={'filed_dt': 'share_date', 'val': 'shares'}),
            left_on='dt', 
            right_on='share_date', 
            direction='backward'
        )
        
        # 3.2 Match Financials
        fin_cols = ['filed_dt', 'total_equity', 'total_debt', 'cash_and_equiv'] + [f'{c}_ttm' for c in target_cols]
        merged = pd.merge_asof(
            merged,
            financials[fin_cols].rename(columns={'filed_dt': 'fin_date'}),
            left_on='dt',
            right_on='fin_date',
            direction='backward'
        )

        # 4. Calculate Metrics
        merged['cik'] = cik  # CIK 명시

        # Market Cap
        merged['mkt_cap'] = merged['cls_prc'] * merged['shares']
        
        # Safe Division Helper
        def safe_div(a, b):
            # b가 0이거나 NaN이면 None 반환
            return np.where((b != 0) & (pd.notnull(b)), a / b, None)

        # Ratios
        merged['pe'] = safe_div(merged['mkt_cap'], merged['net_income_ttm'])
        merged['pb'] = safe_div(merged['mkt_cap'], merged['total_equity'])
        merged['ps'] = safe_div(merged['mkt_cap'], merged['revenue_ttm'])
        merged['pcr'] = safe_div(merged['mkt_cap'], merged['ocf_ttm']) # PCR Logic Added

        # EV / EBITDA
        merged['total_debt'] = pd.to_numeric(merged['total_debt'], errors='coerce')
        merged['cash_and_equiv'] = pd.to_numeric(merged['cash_and_equiv'], errors='coerce')
        
        ev = merged['mkt_cap'] + merged['total_debt'].fillna(0) - merged['cash_and_equiv'].fillna(0)
        merged['ev_ebitda'] = safe_div(ev, merged['ebitda_ttm'])

        # 5. Filter & Save
        valid_rows = merged.dropna(subset=['mkt_cap'])
        
        if not valid_rows.empty:
            self._save_valuation(valid_rows)
        else:
            logger.warning(f"[{cik}] No valid valuation rows generated (Check overlaps).")

    def _load_prices(self, cik: str, start_date=None) -> pd.DataFrame:
        if start_date:
            query = "SELECT dt, cls_prc FROM us_daily_price WHERE cik = %s AND dt >= %s"
            params = (cik, start_date)
        else:
            query = "SELECT dt, cls_prc FROM us_daily_price WHERE cik = %s"
            params = (cik,)
            
        with self.db.get_cursor() as cur:
            cur.execute(query, params)
            return pd.DataFrame(cur.fetchall())

    def _load_shares(self, cik: str) -> pd.DataFrame:
        query = "SELECT filed_dt, val FROM us_share_history WHERE cik = %s"
        with self.db.get_cursor() as cur:
            cur.execute(query, (cik,))
            return pd.DataFrame(cur.fetchall())
            
    def _load_financials(self, cik: str) -> pd.DataFrame:
        # Load ocf for PCR
        query = """
            SELECT filed_dt, fiscal_period, 
                   net_income, total_equity, revenue, ebitda, ocf,
                   total_debt, cash_and_equiv, shares_outstanding
            FROM us_standard_financials 
            WHERE cik = %s
        """
        with self.db.get_cursor() as cur:
            cur.execute(query, (cik,))
            return pd.DataFrame(cur.fetchall())

    def _save_valuation(self, df: pd.DataFrame):
        # NaN 처리
        df = df.replace({np.nan: None})
        
        # 전체 데이터를 튜플 리스트로 변환
        all_data = [
            (
                row['dt'], 
                row['cik'], 
                row['mkt_cap'], 
                row['pe'], 
                row['pb'], 
                row['ps'], 
                row['pcr'], 
                row['ev_ebitda']
            )
            for _, row in df.iterrows()
        ]
        
        query = """
            INSERT INTO us_daily_valuation (dt, cik, mkt_cap, pe, pb, ps, pcr, ev_ebitda)
            VALUES %s
            ON CONFLICT (dt, cik) DO UPDATE SET
                mkt_cap = EXCLUDED.mkt_cap,
                pe = EXCLUDED.pe,
                pb = EXCLUDED.pb,
                ps = EXCLUDED.ps,
                pcr = EXCLUDED.pcr,
                ev_ebitda = EXCLUDED.ev_ebitda
        """
        
        # [Critical Fix] Batch Insert
        # TimescaleDB 청크 Lock 제한(64개)을 피하기 위해 
        # 데이터를 200개(약 1년치 영업일)씩 나누어 저장합니다.
        BATCH_SIZE = 50
        
        try:
            for i in range(0, len(all_data), BATCH_SIZE):
                batch = all_data[i : i + BATCH_SIZE]
                with self.db.get_cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur, query, batch)
        except Exception as e:
            # 배치 저장 중 에러 발생 시 로그 남기고 상위로 던짐
            logger.error(f"Batch insert failed: {e}")
            raise e