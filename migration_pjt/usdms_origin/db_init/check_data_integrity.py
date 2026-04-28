import sys
import os
import asyncio
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager

class IntegrityAuditor:
    def __init__(self):
        self.db = DatabaseManager()
        self.report = []

    def log(self, msg):
        print(msg)
        self.report.append(msg)

    def check_cik_format(self):
        self.log("\n[1. CIK Format Check]")
        with self.db.get_cursor() as cur:
            # Check Master
            cur.execute("SELECT count(*) FROM us_ticker_master WHERE length(cik) != 10 OR cik !~ '^\d+$'")
            res_master = cur.fetchone()['count']
            
            # Check History
            cur.execute("SELECT count(*) FROM us_ticker_history WHERE length(cik) != 10 OR cik !~ '^\d+$'")
            res_history = cur.fetchone()['count']
            
            if res_master == 0:
                self.log("  - Master: PASS (All CIKs are 10-digit numeric strings)")
            else:
                self.log(f"  - Master: FAIL (Found {res_master} invalid CIKs)")
                
            if res_history == 0:
                self.log("  - History: PASS (All CIKs are 10-digit numeric strings)")
            else:
                self.log(f"  - History: FAIL (Found {res_history} invalid CIKs)")

    def check_dates(self):
        self.log("\n[2. Date Check (History PIT)]")
        with self.db.get_cursor() as cur:
            # Start Date Not 1980-01-01
            cur.execute("SELECT count(*) FROM us_ticker_history WHERE start_dt != '1980-01-01'")
            res_start = cur.fetchone()['count']
            
            # End Date Not 9999-12-31
            cur.execute("SELECT count(*) FROM us_ticker_history WHERE end_dt != '9999-12-31'")
            res_end = cur.fetchone()['count']
            
            if res_start == 0:
                 self.log("  - start_dt: PASS (All records start at 1980-01-01)")
            else:
                 self.log(f"  - start_dt: FAIL (Found {res_start} records not starting at 1980-01-01)")
                 
            if res_end == 0:
                 self.log("  - end_dt: PASS (All records end at 9999-12-31)")
            else:
                 self.log(f"  - end_dt: FAIL (Found {res_end} records not ending at 9999-12-31)")

    def check_exchanges(self):
        self.log("\n[3. Exchange Check]")
        ALLOWED = {'NASDAQ', 'NYSE', 'AMEX', 'OTC', 'OTHER'}
        with self.db.get_cursor() as cur:
            cur.execute("SELECT DISTINCT exchange FROM us_ticker_master")
            rows = cur.fetchall()
            found = set([r['exchange'] for r in rows if r['exchange']])
            
            invalid = found - ALLOWED
            if not invalid:
                self.log(f"  - PASS (All exchanges are valid: {found})")
            else:
                self.log(f"  - FAIL (Found invalid exchanges: {invalid})")

    def check_metadata_stats(self):
        self.log("\n[4. Metadata State Check]")
        cols = ['sector', 'industry', 'market_cap', 'current_price']
        with self.db.get_cursor() as cur:
            cur.execute("SELECT count(*) as total FROM us_ticker_master")
            total = cur.fetchone()['total']
            self.log(f"  - Total Active Rows: {total}")
            
            for col in cols:
                cur.execute(f"SELECT count({col}) as populated FROM us_ticker_master")
                populated = cur.fetchone()['populated']
                nulls = total - populated
                self.log(f"  - {col}: Populated {populated} / Null {nulls} ({int(populated/total*100)}%)")

    def check_exceptions(self):
        self.log("\n[5. Exception Map Check]")
        TARGETS = {
            '0001652044': 'GOOGL',
            '0001067983': 'BRK-B',
            '0001336917': 'UAA',
            '0001754301': 'FOXA'
        }
        with self.db.get_cursor() as cur:
            cur.execute("SELECT cik, latest_ticker, exchange FROM us_ticker_master WHERE cik = ANY(%s)", (list(TARGETS.keys()),))
            rows = cur.fetchall()
            
            for row in rows:
                cik = row['cik']
                actual = row['latest_ticker']
                expected = TARGETS[cik]
                status = "PASS" if actual == expected else "FAIL"
                self.log(f"  - CIK {cik}: Expected {expected}, Got {actual} ({row['exchange']}) -> {status}")

    def run(self):
        self.log(">>> Starting Database Integrity Audit...")
        self.check_cik_format()
        self.check_dates()
        self.check_exchanges()
        self.check_metadata_stats()
        self.check_exceptions()
        self.log("\n>>> Audit Complete.")

if __name__ == "__main__":
    auditor = IntegrityAuditor()
    auditor.run()
