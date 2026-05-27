import sys
import os
import logging
from collections import defaultdict

current_dir = os.path.dirname(os.path.abspath(__file__))
p2_kdms_path = os.path.abspath(os.path.join(current_dir, ".."))
pjt_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
sys.path.insert(0, p2_kdms_path)
sys.path.insert(0, os.path.join(pjt_root, "tdms_core", "p1_shared"))

from p1_shared.utils.env_detector import EnvDetector
detector = EnvDetector()
detector.load_env_profile()
from repositories.base import create_kdms_pool

logging.basicConfig(level=logging.INFO, format="%(message)s")

def check_nulls():
    pool = create_kdms_pool()
    with pool.get_cursor() as cur:
        # statements 확인
        cur.execute("""
            SELECT * FROM financial_statements 
            WHERE stac_yymm >= '202511'
        """)
        statements = cur.fetchall()
        stmt_cols = [desc[0] for desc in cur.description]
        
        logging.info(f"=== Financial Statements ({len(statements)} rows) Null Check ===")
        stmt_null_counts = defaultdict(int)
        for row in statements:
            for col_name, val in zip(stmt_cols, row):
                if val is None:
                    stmt_null_counts[col_name] += 1
                    
        for col in stmt_cols:
            nulls = stmt_null_counts[col]
            if nulls > 0:
                logging.info(f"  [WARN] {col:<15}: {nulls}/{len(statements)} are NULL")
            else:
                logging.info(f"  [OK]   {col:<15}: 0 NULLs")
                
        # ratios 확인
        cur.execute("""
            SELECT * FROM financial_ratios 
            WHERE stac_yymm >= '202511'
        """)
        ratios = cur.fetchall()
        ratio_cols = [desc[0] for desc in cur.description]
        
        logging.info(f"\n=== Financial Ratios ({len(ratios)} rows) Null Check ===")
        ratio_null_counts = defaultdict(int)
        for row in ratios:
            for col_name, val in zip(ratio_cols, row):
                if val is None:
                    ratio_null_counts[col_name] += 1
                    
        for col in ratio_cols:
            nulls = ratio_null_counts[col]
            if nulls > 0:
                logging.info(f"  [WARN] {col:<20}: {nulls}/{len(ratios)} are NULL")
            else:
                logging.info(f"  [OK]   {col:<20}: 0 NULLs")

if __name__ == "__main__":
    check_nulls()
