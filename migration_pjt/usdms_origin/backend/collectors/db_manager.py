import os
import logging
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, execute_values
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    _pool = None

    def __init__(self):
        if not DatabaseManager._pool:
            # Check if we are in Docker (env var usually set in docker-compose)
            # If not, use localhost from .env
            # Actually, docker-compose sets POSTGRES_HOST=timescaledb overrides .env
            # Local script uses .env directly.
            self.db_config = {
                'user': os.getenv('POSTGRES_USER', 'postgres'),
                'password': os.getenv('POSTGRES_PASSWORD', 'password'),
                'host': os.getenv('POSTGRES_HOST', 'localhost'),
                'port': os.getenv('POSTGRES_PORT', '5435'),
                'database': os.getenv('POSTGRES_DB', 'usdms_db')
            }
            # Log connection parameters, masking the password
            log_config = {k: v for k, v in self.db_config.items()}
            log_config['password'] = '********' # Mask password for logging
            logger.info(f"Connecting to DB with config: {log_config}")
            
            try:
                DatabaseManager._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    **self.db_config
                )
                logger.info("DB Connection Pool created successfully")
            except Exception as e:
                logger.error(f"DB Connection failed: {e}")
                raise

    @contextmanager
    def get_cursor(self):
        """
        Yields a RealDictCursor from a pooled connection.
        Commits on success, Rollbacks on error.
        """
        conn = self._pool.getconn()
        try:
            yield conn.cursor(cursor_factory=RealDictCursor)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB Query failed: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def get_cik_by_ticker(self, ticker: str) -> Optional[str]:
        """
        Get CIK for a given ticker (latest).
        """
        query = "SELECT cik FROM us_ticker_master WHERE latest_ticker = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (ticker,))
            res = cur.fetchone()
            if res:
                return res['cik']
            return None

    def close(self):
        if DatabaseManager._pool:
            try:
                DatabaseManager._pool.closeall()
            except Exception as e:
                logger.error(f"Error closing pool: {e}")
            finally:
                DatabaseManager._pool = None
                logger.info("DB Connection Pool closed and reset")

    # --- Master Data Methods ---

    def upsert_ticker_master(self, data_list: List[Dict[str, Any]]):
        """
        Batch upsert into us_ticker_master.
        data_list: List of dicts with keys (cik, latest_ticker, latest_name, exchange, is_active)
        """
        if not data_list:
            return

        query = """
            INSERT INTO us_ticker_master (cik, latest_ticker, latest_name, exchange, is_active, last_seen_dt)
            VALUES %s
            ON CONFLICT (cik) DO UPDATE SET
                latest_ticker = EXCLUDED.latest_ticker,
                latest_name = EXCLUDED.latest_name,
                exchange = EXCLUDED.exchange,
                is_active = EXCLUDED.is_active,
                last_seen_dt = EXCLUDED.last_seen_dt,
                updated_at = NOW()
        """
        
        # Prepare values
        values = [
            (
                d['cik'], 
                d.get('latest_ticker'), 
                d.get('latest_name'), 
                d.get('exchange'), 
                d.get('is_active', True),
                d.get('last_seen_dt')
            )
            for d in data_list
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Upserted {len(values)} records to us_ticker_master")

    def insert_ticker_history(self, data_list: List[Dict[str, Any]]):
        """
        Insert into us_ticker_history. Ignore duplicates.
        """
        if not data_list:
            return

        query = """
            INSERT INTO us_ticker_history (cik, ticker, start_dt, end_dt)
            VALUES %s
            ON CONFLICT (cik, ticker, start_dt) DO NOTHING
        """
        
        values = [
            (d['cik'], d['ticker'], d['start_dt'], d.get('end_dt', '9999-12-31'))
            for d in data_list
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Inserted {len(values)} records to us_ticker_history")

    # --- Financial Data Methods ---

    def delete_raw_facts_by_cik(self, cik: str):
        """
        Delete all raw facts for a specific CIK to prevent duplicates before bulk insert.
        Implements 'Overwrite per CIK' strategy.
        """
        query = "DELETE FROM us_financial_facts WHERE cik = %s;"
        with self.get_cursor() as cur:
            cur.execute(query, (cik,))
            logger.info(f"Deleted {cur.rowcount} records from us_financial_facts for CIK {cik}")

    def insert_financial_facts(self, data_list: List[Dict[str, Any]]):
        """
        Bulk insert raw financial facts.
        """
        if not data_list:
            return

        query = """
            INSERT INTO us_financial_facts (cik, tag, val, period_start, period_end, filed_dt, frame, fy, fp, form)
            VALUES %s
        """
        
        values = [
            (d['cik'], d['tag'], d['val'], d.get('period_start'), d['period_end'], d['filed_dt'], d.get('frame'), d.get('fy'), d.get('fp'), d.get('form'))
            for d in data_list
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Inserted {len(values)} records to us_financial_facts")

    def upsert_standard_financials(self, data_list: List[Dict[str, Any]]):
        """
        Bulk upsert standard financials.
        """
        if not data_list:
            return

        # Columns to insert
        cols = [
            'cik', 'report_period', 'filed_dt', 'fiscal_year', 'fiscal_period',
            'total_assets', 'current_assets', 'cash_and_equiv', 'inventory', 'account_receivable',
            'total_equity', 'retained_earnings',
            'total_liabilities', 'current_liabilities', 'total_debt',
            'shares_outstanding',
            'revenue', 'cogs', 'gross_profit',
            'sgna_expense', 'rnd_expense',
            'op_income', 'interest_expense', 'tax_provision', 'net_income',
            'ebitda',
            'ocf', 'capex', 'fcf'
        ]
        
        cols_str = ", ".join(cols)
        excluded_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c not in ['cik', 'report_period', 'filed_dt']])
        
        query = f"""
            INSERT INTO us_standard_financials ({cols_str})
            VALUES %s
            ON CONFLICT (cik, report_period, filed_dt) DO UPDATE SET
                {excluded_str}
        """
        
        values = []
        for d in data_list:
            row = tuple(d.get(c) for c in cols)
            values.append(row)

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Upserted {len(values)} records to us_standard_financials")

    def upsert_share_history(self, data_list: List[Dict[str, Any]]):
        """
        Bulk upsert share history.
        """
        if not data_list:
            return

        query = """
            INSERT INTO us_share_history (cik, filed_dt, val)
            VALUES %s
            ON CONFLICT (cik, filed_dt) DO UPDATE SET
                val = EXCLUDED.val,
                created_at = NOW()
        """
        
        values = [
            (d['cik'], d['filed_dt'], d['val'])
            for d in data_list
        ]

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Upserted {len(values)} records to us_share_history")

    # --- Market Data Methods ---

    def insert_daily_price(self, data_list: List[Dict[str, Any]]):
        if not data_list:
            return
        
        # Use execute_values for speed
        query = """
            INSERT INTO us_daily_price (dt, cik, ticker, open_prc, high_prc, low_prc, cls_prc, vol, amt)
            VALUES %s
            ON CONFLICT (dt, cik) DO UPDATE SET
            open_prc = EXCLUDED.open_prc,
            high_prc = EXCLUDED.high_prc,
            low_prc = EXCLUDED.low_prc,
            cls_prc = EXCLUDED.cls_prc,
            vol = EXCLUDED.vol,
            amt = EXCLUDED.amt
    """
        values = [
            (d['dt'], d['cik'], d['ticker'], d['open_prc'], d['high_prc'], d['low_prc'], d['cls_prc'], d['vol'], d['amt'])
            for d in data_list
        ]
        
        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            # logger.info(f"Inserted {len(values)} price records") # Too verbose

    def upsert_price_factors(self, data_list: List[Dict[str, Any]]):
        if not data_list:
            return

        query = """
            INSERT INTO us_price_adjustment_factors (cik, event_dt, factor_val, event_type, matched_info)
            VALUES %s
            ON CONFLICT (cik, event_dt, event_type) DO UPDATE SET
                factor_val = EXCLUDED.factor_val,
                matched_info = EXCLUDED.matched_info
        """
        # Deduplicate in Python to avoid batch errors
        unique_map = {}
        for d in data_list:
            key = (d['cik'], d['event_dt'], d['event_type'])
            unique_map[key] = d
            
        clean_list = list(unique_map.values())
        
        values = [
            (d['cik'], d['event_dt'], d['factor_val'], d['event_type'], d.get('matched_info'))
            for d in clean_list
        ]
        
        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Upserted {len(values)} price factors")

    # --- Valuation Methods ---

    def upsert_valuation_ratios(self, data_list: List[Dict[str, Any]]):
        if not data_list:
            return

        cols = [
            'dt', 'cik', 'mkt_cap', 'pe_ratio', 'pb_ratio', 'ps_ratio', 'pcr_ratio', 
            'ev_ebitda', 'pfcf_ratio', 'gp_a_ratio'
        ]
        cols_str = ", ".join(cols)
        excluded_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c not in ['dt', 'cik']])

        query = f"""
            INSERT INTO us_valuation_ratios ({cols_str})
            VALUES %s
            ON CONFLICT (dt, cik) DO UPDATE SET
                {excluded_str}
        """
        
        values = []
        for d in data_list:
            row = tuple(d.get(c) for c in cols)
            values.append(row)

        with self.get_cursor() as cur:
            execute_values(cur, query, values)
            logger.info(f"Upserted {len(values)} valuation ratios")
