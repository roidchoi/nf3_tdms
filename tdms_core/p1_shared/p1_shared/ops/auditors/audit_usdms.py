import os
import psycopg2
from dotenv import load_dotenv
from p1_shared.utils.env_detector import EnvDetector

TABLES = [
    "us_ticker_master", "us_daily_price", "us_daily_valuation", "us_financial_facts",
    "us_financial_metrics", "us_price_adjustment_factors", "us_share_history",
    "us_standard_financials", "us_ticker_history", "us_collection_blacklist"
]

def run_simple_audit():
    load_dotenv()
    env = EnvDetector()
    peer_ip = env.get_peer_host()
    local_ip = os.getenv("DEV_IP", "127.0.0.1") if env.detect() == "dev" else os.getenv("SERVER_IP", "127.0.0.1")

    # USDMS 포트는 5433 고정
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_pw = os.getenv("POSTGRES_PASSWORD", "password")

    dev_db = {"host": local_ip, "port": 5433, "user": db_user, "password": db_pw, "dbname": "usdms_db"}
    srv_db = {"host": peer_ip, "port": 5433, "user": db_user, "password": db_pw, "dbname": "usdms_db"}

    try:
        dev_conn = psycopg2.connect(**dev_db)
        srv_conn = psycopg2.connect(**srv_db)
    except Exception as e:
        print(f"DB 접속 실패: {e}")
        return
        
    print(f"\n{'Table Name':<30} | {'Dev Count':>12} | {'Srv Count':>12} | {'Match'}")
    print("-" * 75)
    
    for table in TABLES:
        try:
            with dev_conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                dev_count = cur.fetchone()[0]
            with srv_conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                srv_count = cur.fetchone()[0]
            
            match = "✅" if dev_count == srv_count else "❌"
            print(f"{table:<30} | {dev_count:>12,} | {srv_count:>12,} | {match}")
        except Exception as e:
            print(f"{table:<30} | Error: {str(e)}")
            dev_conn.rollback()
            srv_conn.rollback()
            
    dev_conn.close()
    srv_conn.close()

if __name__ == "__main__":
    run_simple_audit()
