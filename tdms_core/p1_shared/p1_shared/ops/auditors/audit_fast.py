import os
import psycopg2
from dotenv import load_dotenv
from p1_shared.utils.env_detector import EnvDetector

def get_db_stats_light(host, port, dbname, user, password, label):
    print(f"[{label}] {host} 접속 시도 중...")
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=5)
        cur = conn.cursor()
        
        # pg_class를 사용하여 빠르게 통계 추출 (Lock 최소화)
        cur.execute("""
            SELECT 
                relname as table_name,
                reltuples::bigint as row_count,
                pg_table_size(c.oid) as data_size,
                pg_indexes_size(c.oid) as index_size
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' 
              AND c.relkind = 'r'
            ORDER BY relname;
        """)
        rows = cur.fetchall()
        
        stats = {}
        for r in rows:
            table, row_count, data_size, index_size = r
            
            # 컬럼 수만 따로 조회
            cur.execute(f"SELECT count(*) FROM information_schema.columns WHERE table_name = '{table}'")
            col_count = cur.fetchone()[0]
            
            stats[table] = {
                "rows": row_count,
                "data_size": data_size,
                "index_size": index_size,
                "cols": col_count
            }
            
        conn.close()
        return stats
    except Exception as e:
        print(f"[{label}] 에러 발생: {e}")
        return None

def main():
    load_dotenv()
    env = EnvDetector()
    peer_ip = env.get_peer_host()
    local_ip = os.getenv("DEV_IP", "127.0.0.1") if env.detect() == "dev" else os.getenv("SERVER_IP", "127.0.0.1")

    # .env 환경 변수 기반으로 설정 구성
    db_name = os.getenv("POSTGRES_DB", "kdms_db")
    db_user = os.getenv("POSTGRES_USER", "roid")
    db_pw = os.getenv("POSTGRES_PASSWORD", "password")

    dev_conf = {"host": local_ip, "port": 5432, "dbname": db_name, "user": db_user, "password": db_pw, "label": "로컬PC"}
    srv_conf = {"host": peer_ip, "port": 5432, "dbname": db_name, "user": db_user, "password": db_pw, "label": "원격PC"}

    dev_stats = get_db_stats_light(**dev_conf)
    srv_stats = get_db_stats_light(**srv_conf)

    if not dev_stats or not srv_stats:
        print("조회 실패로 검증을 중단합니다.")
        return

    print("\n" + "="*100)
    print(f"{'Table Name':<35} | {'Cols':<4} | {'Dev Rows':>12} | {'Srv Rows':>12} | {'Match'}")
    print("-" * 100)
    
    all_tables = sorted(list(set(dev_stats.keys()) | set(srv_stats.keys())))
    
    for table in all_tables:
        d = dev_stats.get(table)
        s = srv_stats.get(table)
        
        if not d or not s:
            print(f"{table:<35} | MISSING in {'Dev' if not d else 'Srv'}")
            continue
            
        col_match = "✅" if d['cols'] == s['cols'] else "❌"
        # pg_class.reltuples는 근사치이므로 완전히 같지 않을 수 있으나, 양측이 동기화 직후라면 유사해야 함
        row_diff = abs((d['rows'] or 0) - (s['rows'] or 0))
        # 1% 이내 오차면 O로 표시 (추정치이므로)
        row_match = "✅" if row_diff < max(d['rows'], s['rows']) * 0.01 else "⚠️"
        
        print(f"{table:<35} | {d['cols']:<2}{col_match} | {d['rows']:>12,} | {s['rows']:>12,} | {row_match}")

if __name__ == "__main__":
    main()
