import os
import sys
from datetime import date

# tdms_core 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from p2_kdms.repositories.base import create_kdms_pool

def main():
    pool = create_kdms_pool()
    
    print("=== 1. minute_target_history에서 2025Q4, 2026Q1의 타겟 수와 삼성전자(005930) 존재 여부 ===")
    with pool.get_cursor() as cursor:
        # 2025Q4 KOSPI 개수
        cursor.execute("SELECT COUNT(*) FROM minute_target_history WHERE quarter = '2025Q4' AND market = 'KOSPI'")
        count_q4 = cursor.fetchone()[0]
        print(f"2025Q4 KOSPI 타겟 개수: {count_q4}")
        
        # 삼성전자 존재 여부
        cursor.execute("SELECT * FROM minute_target_history WHERE quarter = '2025Q4' AND symbol = '005930'")
        row = cursor.fetchone()
        print(f"2025Q4 삼성전자 존재 여부: {row}")
        
        # 2026Q1 KOSPI 개수
        cursor.execute("SELECT COUNT(*) FROM minute_target_history WHERE quarter = '2026Q1' AND market = 'KOSPI'")
        count_q5 = cursor.fetchone()[0]
        print(f"2026Q1 KOSPI 타겟 개수: {count_q5}")
        
        # 2026Q1 삼성전자 존재 여부
        cursor.execute("SELECT * FROM minute_target_history WHERE quarter = '2026Q1' AND symbol = '005930'")
        row_q5 = cursor.fetchone()
        print(f"2026Q1 삼성전자 존재 여부: {row_q5}")

    print("\n=== 2. 2025Q4, 2026Q1 전체 KOSPI 타겟 종목 상위 20개 리스트 ===")
    with pool.get_cursor() as cursor:
        cursor.execute("SELECT symbol, avg_trade_value, rank FROM minute_target_history WHERE quarter = '2025Q4' AND market = 'KOSPI' ORDER BY rank LIMIT 20")
        print("2025Q4 KOSPI Top 20:")
        for r in cursor.fetchall():
            print(r)
            
        cursor.execute("SELECT symbol, avg_trade_value, rank FROM minute_target_history WHERE quarter = '2026Q1' AND market = 'KOSPI' ORDER BY rank LIMIT 20")
        print("\n2026Q1 KOSPI Top 20:")
        for r in cursor.fetchall():
            print(r)

    print("\n=== 3. daily_ohlcv에서 삼성전자(005930)의 기간별 데이터 수와 평균 amt ===")
    with pool.get_cursor() as cursor:
        # 2025Q3 (7/1 ~ 9/30)
        cursor.execute("SELECT COUNT(*), AVG(amt), COUNT(CASE WHEN amt IS NULL THEN 1 END) FROM daily_ohlcv WHERE stk_cd = '005930' AND dt BETWEEN '2025-07-01' AND '2025-09-30'")
        row = cursor.fetchone()
        print(f"2025Q3 (7/1 ~ 9/30) - 총 건수: {row[0]}, 평균 거래대금: {row[1]}, amt가 NULL인 건수: {row[2]}")
        
        # 2025Q4 (10/1 ~ 12/31)
        cursor.execute("SELECT COUNT(*), AVG(amt), COUNT(CASE WHEN amt IS NULL THEN 1 END) FROM daily_ohlcv WHERE stk_cd = '005930' AND dt BETWEEN '2025-10-01' AND '2025-12-31'")
        row = cursor.fetchone()
        print(f"2025Q4 (10/1 ~ 12/31) - 총 건수: {row[0]}, 평균 거래대금: {row[1]}, amt가 NULL인 건수: {row[2]}")
        
    print("\n=== 4. 2025-11-20 부근의 삼성전자 일봉 시세 데이터 샘플 (11/17 ~ 11/25) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("SELECT dt, open_prc, high_prc, low_prc, cls_prc, vol, amt, turn_rt FROM daily_ohlcv WHERE stk_cd = '005930' AND dt BETWEEN '2025-11-17' AND '2025-11-25' ORDER BY dt")
        for r in cursor.fetchall():
            print(r)

if __name__ == "__main__":
    main()
