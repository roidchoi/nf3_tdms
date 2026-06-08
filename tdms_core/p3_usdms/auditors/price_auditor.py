# tdms_core/p3_usdms/auditors/price_auditor.py
import logging
import pandas as pd
import numpy as np
from datetime import datetime, date
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

KNOWN_EXCEPTIONS = {
    "NVDA": {"threshold": 2.0, "reason": "Historical drift since 2007"},
}
DEFAULT_THRESHOLD = 0.1

class PriceReproducer:
    def __init__(self, pool, kis_us_client):
        self.pool = pool
        self.kis = kis_us_client

    @contextmanager
    def get_dict_cursor(self):
        """DbConnectionPool에서 RealDictCursor를 제공하는 컨텍스트 매니저"""
        if not self.pool:
            yield None
            return
        conn = self.pool.get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Price Auditor DB Query failed: {e}")
            raise e
        finally:
            self.pool.put_conn(conn)

    def verify_ticker(self, ticker: str, start_dt: str = None, end_dt: str = None) -> Dict[str, Any]:
        """
        Verify Price Reproduction for a single ticker.
        1. Fetch Local Raw Prices & Factors.
        2. Fetch KIS Adj Close (Truth).
        3. Calculate Local Adj = Raw * Product(Factors).
        4. Compare.
        """
        cik = self._get_cik_by_ticker(ticker)
        if not cik:
            return {"status": "FAIL", "msg": "CIK not found"}

        # 1. Fetch Local Data
        raw_df = self._fetch_local_prices(cik, start_dt, end_dt)
        factors = self._fetch_local_factors(cik)
        
        if raw_df.empty:
            return {"status": "SKIP", "msg": "No local price data"}

        # 2. Fetch KIS Data (Truth)
        # KIS API get_ohlcv는 하이픈 없는 YYYYMMDD 형식을 기대하므로 포맷팅 수행
        kis_start = start_dt.replace('-', '') if start_dt else None
        kis_end = end_dt.replace('-', '') if end_dt else None
        try:
            kis_df = self.kis.get_ohlcv(ticker, start_date=kis_start, end_date=kis_end, add_adjusted=True)
        except Exception as e:
            return {"status": "ERROR", "msg": f"KIS API Error: {e}"}

        if kis_df.empty or 'Adj Close' not in kis_df.columns:
            return {"status": "SKIP", "msg": "No KIS data or Adj Close missing"}

        # 3. Align Data
        raw_df.index = pd.to_datetime(raw_df.index)
        kis_df.index = pd.to_datetime(kis_df.index)
        
        # Merge on Date
        merged = raw_df[['cls_prc']].join(kis_df[['Adj Close']], how='inner')
        if merged.empty:
             return {"status": "FAIL", "msg": "No overlapping dates"}
             
        # 4. Calculate Local Adj Close
        merged = merged.sort_index(ascending=True) # Old -> New
        dates_asc = merged.index.date
        raw_asc = merged['cls_prc'].values
        
        # event_dt 별 수정계수 맵 작성 (동일 날짜 중복 처리)
        factor_map = {}
        for f in factors:
            ed = f['event_dt']
            if isinstance(ed, str):
                ed = datetime.strptime(ed[:10], "%Y-%m-%d").date()
            elif isinstance(ed, (datetime, date)):
                ed = ed if isinstance(ed, date) else ed.date()
            
            val = float(f['factor_val'])
            factor_map[ed] = factor_map.get(ed, 1.0) * val
            
        cum_factor = 1.0
        
        # Reverse to iterate New -> Old
        dates_desc = dates_asc[::-1]
        raw_desc = raw_asc[::-1]
        calc_desc = []
        
        for i, dt in enumerate(dates_desc):
            calc_desc.append(raw_desc[i] * cum_factor)
            if dt in factor_map:
                cum_factor *= factor_map[dt]
                
        # Reverse back
        local_adj = np.array(calc_desc[::-1])
        merged['Local_Adj'] = local_adj
        merged['Error_Pct'] = (abs(merged['Local_Adj'] - merged['Adj Close']) / merged['Adj Close']) * 100
        
        max_err = merged['Error_Pct'].max()
        mean_err = merged['Error_Pct'].mean()
        
        # Determine Threshold
        exception_info = KNOWN_EXCEPTIONS.get(ticker)
        threshold = exception_info['threshold'] if exception_info else DEFAULT_THRESHOLD
        
        # Check Fail Condition
        failed_rows = merged[merged['Error_Pct'] > threshold]
        
        # Determine Status
        if max_err < threshold or failed_rows.empty: 
            status = "PASS"
            if exception_info:
                status += " (Exception Applied)"
        else:
            status = "FAIL"
            
        # Serialize failed samples (Only those above threshold)
        failed_list = []
        for idx, row in failed_rows.head(5).iterrows():
            failed_list.append({
                "dt": idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx),
                "cls_prc": float(row['cls_prc']),
                "Adj Close": float(row['Adj Close']),
                "Local_Adj": float(row['Local_Adj']),
                "Error_Pct": float(row['Error_Pct'])
            })

        result = {
            "status": status,
            "max_error": round(float(max_err), 4) if not np.isnan(max_err) else 0.0,
            "mean_error": round(float(mean_err), 4) if not np.isnan(mean_err) else 0.0,
            "sample_count": len(merged),
            "failed_count": len(failed_rows),
            "failed_samples": failed_list,
            "threshold_used": threshold
        }
        
        return result

    def _get_cik_by_ticker(self, ticker: str) -> str:
        query = "SELECT cik FROM us_ticker_master WHERE latest_ticker = %s LIMIT 1"
        with self.get_dict_cursor() as cur:
            if not cur:
                return None
            cur.execute(query, (ticker,))
            res = cur.fetchone()
            if res:
                return res['cik']
            return None

    def _fetch_local_prices(self, cik: str, start_dt: str, end_dt: str) -> pd.DataFrame:
        query = """
            SELECT dt, cls_prc 
            FROM us_daily_price 
            WHERE cik = %s 
        """
        params = [cik]
        if start_dt:
            query += " AND dt >= %s"
            params.append(start_dt)
        if end_dt:
            query += " AND dt <= %s"
            params.append(end_dt)
        query += " ORDER BY dt ASC"
        
        with self.get_dict_cursor() as cur:
            if not cur:
                return pd.DataFrame()
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        df = df.set_index('dt')
        return df

    def _fetch_local_factors(self, cik: str) -> List[Dict[str, Any]]:
        query = "SELECT event_dt, factor_val FROM us_price_adjustment_factors WHERE cik = %s"
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query, (cik,))
            return cur.fetchall()
