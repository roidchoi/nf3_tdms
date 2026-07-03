import os
import psycopg2
from datetime import date, datetime
from dotenv import load_dotenv
from p1_shared.utils.env_detector import EnvDetector

def get_conn(conf):
    return psycopg2.connect(host=conf["host"], port=conf["port"], dbname=conf["dbname"], 
                            user=conf["user"], password=conf["password"], connect_timeout=15)

def serialize(val):
    if val is None: return "NULL"
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return str(val)

def audit_database(conf, label):
    print(f"[{label}] 정밀 분석 시작...")
    conn = get_conn(conf)
    conn.autocommit = True # 개별 쿼리 실패가 전체에 영향 주지 않도록 설정
    cur = conn.cursor()
    
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    tables = [r[0] for r in cur.fetchall()]
    
    report = {}
    for table in tables:
        t_data = {"error": None}
        try:
            # A. 컬럼 스키마
            cur.execute(f"SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
            t_data["columns"] = cur.fetchall()
            
            # B. PK 정보
            cur.execute(f"SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name WHERE tc.table_name = '{table}' AND tc.constraint_type = 'PRIMARY KEY' ORDER BY kcu.ordinal_position")
            t_data["pk"] = cur.fetchall()
            
            # C. 인덱스 정보 (PK 포함 전체)
            cur.execute(f"SELECT indexname, indexdef FROM pg_indexes WHERE tablename = '{table}' ORDER BY indexname")
            t_data["indexes"] = cur.fetchall()
            
            # D. 첫/마지막 데이터 (정렬 기준 찾기)
            col_names = [c[0] for c in t_data["columns"]]
            sort_col = "dt" if "dt" in col_names else \
                       "stk_cd" if "stk_cd" in col_names else \
                       t_data["pk"][0][0] if t_data["pk"] else None
            
            t_data["first_row"] = None
            t_data["last_row"] = None
            if sort_col:
                cur.execute(f"SELECT * FROM {table} ORDER BY {sort_col} ASC LIMIT 1")
                first = cur.fetchone()
                if first: t_data["first_row"] = [serialize(v) for v in first]
                
                cur.execute(f"SELECT * FROM {table} ORDER BY {sort_col} DESC LIMIT 1")
                last = cur.fetchone()
                if last: t_data["last_row"] = [serialize(v) for v in last]
            
            # E. 하이퍼테이블 설정
            cur.execute(f"SELECT num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name = '{table}'")
            res = cur.fetchone()
            t_data["hyper_chunks"] = res[0] if res else None
            
        except Exception as e:
            t_data["error"] = str(e)
        
        report[table] = t_data
        
    conn.close()
    return report

def main():
    load_dotenv()
    env = EnvDetector()
    peer_ip = env.get_peer_host()
    local_ip = os.getenv("DEV_IP", "127.0.0.1") if env.detect() == "dev" else os.getenv("SERVER_IP", "127.0.0.1")

    db_name = os.getenv("POSTGRES_DB") or os.getenv("DEV_KDMS_DB_NAME") or os.getenv("SERVER_KDMS_DB_NAME") or "kdms_db"
    db_user = os.getenv("POSTGRES_USER") or os.getenv("DEV_KDMS_DB_USER") or os.getenv("SERVER_KDMS_DB_USER") or "roid"
    db_pw = os.getenv("POSTGRES_PASSWORD") or os.getenv("DEV_KDMS_DB_PASSWORD") or os.getenv("SERVER_KDMS_DB_PASSWORD") or "password"

    dev_conf = {"host": local_ip, "port": 5432, "dbname": db_name, "user": db_user, "password": db_pw, "label": "로컬PC"}
    srv_conf = {"host": peer_ip, "port": 5432, "dbname": db_name, "user": db_user, "password": db_pw, "label": "원격PC"}

    dev_report = audit_database(dev_conf, dev_conf["label"])
    srv_report = audit_database(srv_conf, srv_conf["label"])

    print("\n" + "="*145)
    print(f"{'Table Name':<32} | {'Schema':<7} | {'PK':<5} | {'Idx':<5} | {'First Data':<40} | {'Last Data':<40} | {'Hyper'}")
    print("="*145)

    all_tables = sorted(list(set(dev_report.keys()) | set(srv_report.keys())))
    for table in all_tables:
        d = dev_report.get(table, {"error": "Not Found"})
        s = srv_report.get(table, {"error": "Not Found"})
        
        if d.get("error") or s.get("error"):
            print(f"{table:<32} | [ERR] Dev: {d.get('error')} / Srv: {s.get('error')}")
            continue
            
        c_match = "✅" if d["columns"] == s["columns"] else "❌"
        p_match = "✅" if d["pk"] == s["pk"] else "❌"
        i_match = "✅" if d["indexes"] == s["indexes"] else "❌"
        f_match = "✅" if d["first_row"] == s["first_row"] else "❌"
        l_match = "✅" if d["last_row"] == s["last_row"] else "❌"
        h_match = "✅" if d["hyper_chunks"] == s["hyper_chunks"] else "⚠️"
        
        # 데이터 요약 (첫 35자만)
        f_str = str(d["first_row"])[:37] + ".." if d["first_row"] else "EMPTY"
        l_str = str(d["last_row"])[:37] + ".." if d["last_row"] else "EMPTY"
        
        print(f"{table:<32} | {c_match:<7} | {p_match:<5} | {i_match:<5} | {f_str:<40} | {l_str:<40} | {h_match} {f_match}/{l_match}")

    print("\n--- [불일치 세부 분석] ---")
    for table in all_tables:
        d = dev_report.get(table)
        s = srv_report.get(table)
        if not d or not s or d.get("error") or s.get("error"): continue
        
        diffs = []
        if d["columns"] != s["columns"]: diffs.append("스키마(컬럼/타입)")
        if d["pk"] != s["pk"]: diffs.append("Primary Key 구조")
        if d["indexes"] != s["indexes"]: 
            d_idx = set(d["indexes"]); s_idx = set(s["indexes"])
            diffs.append(f"인덱스 정의 (Dev에만 있음: {d_idx-s_idx}, Srv에만 있음: {s_idx-d_idx})")
        if d["first_row"] != s["first_row"]: diffs.append(f"첫 데이터 값 (Dev: {d['first_row']} vs Srv: {s['first_row']})")
        if d["last_row"] != s["last_row"]: diffs.append(f"끝 데이터 값 (Dev: {d['last_row']} vs Srv: {s['last_row']})")
        
        if diffs:
            print(f"\n[!] {table} 불일치 발견:")
            for df in diffs: print(f"  - {df}")

if __name__ == "__main__":
    main()
