import os
import sys
from datetime import date

# tdms_core 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# p2_kdms 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from p2_kdms.repositories.base import create_kdms_pool

def main():
    pool = create_kdms_pool()
    
    print("=== 1. 삼성전자(005930) 일자별 분봉 데이터 개수 (11/17 ~ 11/25) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT dt_tm::date as d, COUNT(*)
            FROM minute_ohlcv
            WHERE stk_cd = '005930'
              AND dt_tm BETWEEN '2025-11-17 00:00:00' AND '2025-11-25 23:59:59'
            GROUP BY d
            ORDER BY d
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 2. SK하이닉스(000660) 일자별 분봉 데이터 개수 (11/17 ~ 11/25) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT dt_tm::date as d, COUNT(*)
            FROM minute_ohlcv
            WHERE stk_cd = '000660'
              AND dt_tm BETWEEN '2025-11-17 00:00:00' AND '2025-11-25 23:59:59'
            GROUP BY d
            ORDER BY d
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 3. 전체 종목 대상 일자별 분봉 데이터 총 적재 수 (11/17 ~ 11/25) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT dt_tm::date as d, COUNT(DISTINCT stk_cd), COUNT(*)
            FROM minute_ohlcv
            WHERE dt_tm BETWEEN '2025-11-17 00:00:00' AND '2025-11-25 23:59:59'
            GROUP BY d
            ORDER BY d
        """)
        for r in cursor.fetchall():
            print(f"날짜: {r[0]} | 수집된 종목수: {r[1]} | 총 분봉 개수: {r[2]}")

    print("\n=== 4. 11/21 분봉이 존재하는 종목들의 시장 구분(market_type) 집계 ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT s.market_type, COUNT(DISTINCT m.stk_cd)
            FROM minute_ohlcv m
            JOIN stock_info s ON m.stk_cd = s.stk_cd
            WHERE m.dt_tm BETWEEN '2025-11-21 00:00:00' AND '2025-11-21 23:59:59'
            GROUP BY s.market_type
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 5. 11/21 분봉 수집 성공 종목 샘플 5개와 일봉 amt 여부 ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT m.stk_cd, s.stk_nm, d.amt
            FROM minute_ohlcv m
            JOIN stock_info s ON m.stk_cd = s.stk_cd
            LEFT JOIN daily_ohlcv d ON m.stk_cd = d.stk_cd AND d.dt = '2025-11-21'
            WHERE m.dt_tm BETWEEN '2025-11-21 00:00:00' AND '2025-11-21 23:59:59'
            LIMIT 5
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 6. 11/21 분봉 수집 실패 종목 샘플 5개와 일봉 amt 여부 ===")
    with pool.get_cursor() as cursor:
        # 2025Q4 타겟이었으나 11/21 분봉이 없는 종목
        cursor.execute("""
            SELECT t.symbol, s.stk_nm, d.amt
            FROM minute_target_history t
            JOIN stock_info s ON t.symbol = s.stk_cd
            LEFT JOIN daily_ohlcv d ON t.symbol = d.stk_cd AND d.dt = '2025-11-21'
            WHERE t.quarter = '2025Q4'
              AND t.symbol NOT IN (
                  SELECT DISTINCT stk_cd 
                  FROM minute_ohlcv 
                  WHERE dt_tm BETWEEN '2025-11-21 00:00:00' AND '2025-11-21 23:59:59'
              )
            LIMIT 5
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 7. minute_target_history의 전체 적재 현황 집계 ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT quarter, market, COUNT(*), MIN(rank), MAX(rank)
            FROM minute_target_history
            GROUP BY quarter, market
            ORDER BY quarter, market
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 9. stock_info 테이블 적재 현황 샘플 (15개) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT stk_cd, stk_nm, list_dt, m_vol, cap, update_dt
            FROM stock_info
            LIMIT 15
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 10. stock_info의 cap 누락 상태 점검 (상장 주식 대상) ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT market_type, COUNT(*), 
                   COUNT(CASE WHEN cap IS NULL THEN 1 END) as null_cap,
                   COUNT(CASE WHEN cap = 0 THEN 1 END) as zero_cap
            FROM stock_info
            WHERE status = 'listed'
            GROUP BY market_type
        """)
        for r in cursor.fetchall():
            print(r)

    print("\n=== 11. KOSPI/KOSDAQ 일반 상장 종목 중 cap이 NULL이거나 0인 종목 샘플 10개 ===")
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT stk_cd, stk_nm, market_type, m_vol, cap
            FROM stock_info
            WHERE status = 'listed'
              AND (cap IS NULL OR cap = 0)
              AND market_type IN ('KOSPI', 'KOSDAQ')
              AND stk_nm NOT LIKE '%ETF%'
              AND stk_nm NOT LIKE '%ETN%'
            LIMIT 10
        """)
        for r in cursor.fetchall():
            print(r)

if __name__ == "__main__":
    main()
