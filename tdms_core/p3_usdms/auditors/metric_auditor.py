# tdms_core/p3_usdms/auditors/metric_auditor.py
import logging
from contextlib import contextmanager
from typing import List, Dict, Any
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class MetricVerifier:
    def __init__(self, pool):
        self.pool = pool

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
            logger.error(f"Metric Auditor DB Query failed: {e}")
            raise e
        finally:
            self.pool.put_conn(conn)

    def verify_roe_logic(self, sample_limit: int = 500) -> List[Dict[str, Any]]:
        """
        ROE 산출 값과 (NetIncome / TotalEquity) 직접 계산 값 비교 검증 (오차 1% 초과 검출)
        """
        query = """
            SELECT m.cik, m.report_period, m.roe, s.net_income, s.total_equity
            FROM us_financial_metrics m
            JOIN us_standard_financials s 
              ON m.cik = s.cik AND m.report_period = s.report_period AND m.filed_dt = s.filed_dt
            WHERE m.roe IS NOT NULL
            LIMIT %s
        """
        failed_samples = []
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            metrics_roe = float(r['roe'])
            ni = float(r['net_income']) if r['net_income'] is not None else 0.0
            equity = float(r['total_equity']) if r['total_equity'] is not None else 0.0
            
            if not equity or equity == 0:
                continue
            
            calc_roe = ni / equity
            
            # Tolerance 1% (0.01)
            if abs(metrics_roe - calc_roe) > 0.01:
                failed_samples.append({
                    "cik": r['cik'],
                    "period": str(r['report_period']),
                    "metrics_roe": metrics_roe,
                    "calc_roe": calc_roe,
                    "diff": abs(metrics_roe - calc_roe)
                })
        return failed_samples

    def verify_valuation_logic(self, sample_limit: int = 500) -> List[Dict[str, Any]]:
        """
        시가총액 0 이하 및 극단적인 PE 비율 Outlier (PE > 10000 또는 PE < -10000) 검출
        """
        query = """
            SELECT dt, cik, mkt_cap, pe, pb
            FROM us_daily_valuation
            WHERE mkt_cap IS NOT NULL
            LIMIT %s
        """
        failed_samples = []
        with self.get_dict_cursor() as cur:
            if not cur:
                return []
            cur.execute(query, (sample_limit,))
            rows = cur.fetchall()
            
        for r in rows:
            mkt_cap = float(r['mkt_cap'])
            if mkt_cap <= 0:
                failed_samples.append({
                    "cik": r['cik'],
                    "dt": str(r['dt']),
                    "issue": "Negative Market Cap",
                    "val": mkt_cap
                })
                
            pe = r['pe']
            if pe is not None:
                pe = float(pe)
                if pe > 10000 or pe < -10000:
                    failed_samples.append({
                        "cik": r['cik'],
                        "dt": str(r['dt']),
                        "issue": "Extreme PE",
                        "val": pe
                    })
                
        return failed_samples
