import os
import sys
import psycopg2

sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
from repositories.base import create_kdms_pool

def test():
    pool = create_kdms_pool()
    
    # 1. stock_info 컬럼 조회
    with pool.get_cursor() as cursor:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stock_info';")
        cols = [r[0] for r in cursor.fetchall()]
        print(f"stock_info columns: {cols}")
        
    query_count = """
        SELECT CASE WHEN s.stk_cd IS NULL THEN 'Not in stock_info' ELSE 'In stock_info' END, COUNT(*)
        FROM daily_ohlcv o
        LEFT JOIN stock_info s ON o.stk_cd = s.stk_cd
        WHERE o.dt = '2026-06-26' AND (o.amt = 0 OR o.amt IS NULL) AND o.vol > 0
        GROUP BY 1;
    """
    
    query = """
        SELECT o.stk_cd, s.stk_nm, o.vol, o.amt, o.turn_rt
        FROM daily_ohlcv o
        LEFT JOIN stock_info s ON o.stk_cd = s.stk_cd
        WHERE o.dt = '2026-06-26' AND (o.amt = 0 OR o.amt IS NULL) AND o.vol > 0
        LIMIT 20;
    """
    
    with pool.get_cursor() as cursor:
        cursor.execute(query_count)
        print("=== Market distribution of AMT=0/NULL records on 2026-06-26 ===")
        for row in cursor.fetchall():
            print(f"Market: {row[0]} | Count: {row[1]}")
            
        cursor.execute(query)
        print("\n=== Sample of AMT=0/NULL records on 2026-06-26 ===")
        for row in cursor.fetchall():
            print(f"Code: {row[0]} | Name: {row[1]} | Vol: {row[2]} | Amt: {row[3]} | TurnRt: {row[4]}")

if __name__ == "__main__":
    test()
