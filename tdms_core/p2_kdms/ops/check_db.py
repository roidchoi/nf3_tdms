import sys
import os
from datetime import date

# PYTHONPATH 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared")

from repositories.base import create_kdms_pool

def run():
    try:
        pool = create_kdms_pool()
    except Exception as err:
        print(f"Failed to create pool: {err}")
        return

    # 테이블 목록 조회
    with pool.get_cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cursor.fetchall()]
    
    print("=== Detailed Tables Check ===")
    for t in tables:
        try:
            with pool.get_cursor() as cursor:
                # 1. 컬럼 목록 및 데이터 타입 조회
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    ORDER BY ordinal_position;
                """, (t,))
                cols = [f"{r[0]} ({r[1]})" for r in cursor.fetchall()]
                
                # 2. 레코드 수
                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cursor.fetchone()[0]
                
                print(f"\n- Table: {t} | Rows: {cnt}")
                print(f"  Columns: {', '.join(cols)}")
                
                # 3. 날짜 컬럼 자동 감지 후 날짜 범위 조회
                date_cols = [c.split(" (")[0] for c in cols if 'date' in c or 'time' in c or 'dt' in c]
                if date_cols:
                    # 'dt' 또는 'dt_tm' 또는 'event_dt'가 있으면 그것을 우선 사용
                    target_col = None
                    for dc in ['dt', 'dt_tm', 'event_dt']:
                        if dc in date_cols:
                            target_col = dc
                            break
                    if not target_col:
                        target_col = date_cols[0]
                        
                    cursor.execute(f"SELECT MIN({target_col}), MAX({target_col}) FROM {t}")
                    mn, mx = cursor.fetchone()
                    print(f"  Date Range ({target_col}): {mn} ~ {mx}")
                    
        except Exception as e:
            print(f"  Failed to query table {t}: {e}")
            try:
                with pool.get_cursor() as err_cursor:
                    err_cursor.connection.rollback()
            except Exception as rollback_err:
                print(f"  Failed to rollback: {rollback_err}")

if __name__ == '__main__':
    run()
