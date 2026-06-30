import os
import sys
from datetime import date

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

from dotenv import load_dotenv
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

from repositories.base import create_kdms_pool

def check_db():
    print("=== Checking daily_ohlcv data for amt & turn_rt ===")
    pool = create_kdms_pool()
    
    with pool.get_cursor() as cursor:
        # 1. 최근 30일 간의 전체 일봉 데이터 일자 및 총 건수, amt가 0인 건수, turn_rt가 0인 건수, amt가 NULL인 건수 조회
        query = """
            SELECT 
                dt,
                COUNT(*) as total_cnt,
                SUM(CASE WHEN amt = 0 THEN 1 ELSE 0 END) as amt_zero_cnt,
                SUM(CASE WHEN turn_rt = 0 THEN 1 ELSE 0 END) as turn_rt_zero_cnt,
                SUM(CASE WHEN amt IS NULL THEN 1 ELSE 0 END) as amt_null_cnt,
                SUM(CASE WHEN turn_rt IS NULL THEN 1 ELSE 0 END) as turn_rt_null_cnt
            FROM daily_ohlcv
            GROUP BY dt
            ORDER BY dt DESC
            LIMIT 40;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'Date':<12} | {'Total':<8} | {'Amt=0':<8} | {'TurnRt=0':<8} | {'Amt=Null':<8} | {'TurnRt=Null':<8}")
        print("-" * 70)
        for row in rows:
            print(f"{str(row[0]):<12} | {row[1]:<8} | {row[2]:<8} | {row[3]:<8} | {row[4]:<8} | {row[5]:<8}")
            
        # 2. 최근 0이 아닌 거래량이 존재하는데 amt나 turn_rt가 0인 샘플 5개 조회
        print("\n=== Sample of records with volume > 0 but amt = 0 or turn_rt = 0 ===")
        sample_query = """
            SELECT dt, stk_cd, cls_prc, vol, amt, turn_rt
            FROM daily_ohlcv
            WHERE vol > 0 AND (amt = 0 OR turn_rt = 0)
            ORDER BY dt DESC, stk_cd ASC
            LIMIT 10;
        """
        cursor.execute(sample_query)
        samples = cursor.fetchall()
        print(f"{'Date':<12} | {'StkCd':<8} | {'Close':<8} | {'Vol':<8} | {'Amt':<10} | {'TurnRt':<8}")
        print("-" * 65)
        for s in samples:
            print(f"{str(s[0]):<12} | {s[1]:<8} | {s[2]:<8} | {s[3]:<8} | {s[4]:<10} | {s[5]:<8}")

if __name__ == "__main__":
    check_db()
