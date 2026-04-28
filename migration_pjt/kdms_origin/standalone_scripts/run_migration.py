"""
standalone_scripts/run_migration.py

psql이 없는 환경에서 SQL 마이그레이션 파일을 실행합니다.
.env의 DB 접속 정보를 사용하며 psycopg2로 직접 연결합니다.

실행 방법 (00_kdms/ 폴더, 가상환경 활성화 상태):
    python standalone_scripts/run_migration.py migrations/006_add_daily_ohlcv_adjusted.sql
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv

load_dotenv()

def run_migration(sql_file_path: str):
    # DB 접속 정보 로드 (.env 기준)
    conn_params = {
        "host":     os.getenv("POSTGRES_HOST", "localhost"),
        "port":     int(os.getenv("POSTGRES_PORT", 5432)),
        "dbname":   os.getenv("POSTGRES_DB",   "kdms_db"),
        "user":     os.getenv("POSTGRES_USER",  "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }

    print(f"[연결 정보]")
    print(f"  host   : {conn_params['host']}")
    print(f"  port   : {conn_params['port']}")
    print(f"  dbname : {conn_params['dbname']}")
    print(f"  user   : {conn_params['user']}")
    print()

    # SQL 파일 읽기
    if not os.path.exists(sql_file_path):
        print(f"[ERROR] SQL 파일을 찾을 수 없습니다: {sql_file_path}")
        sys.exit(1)

    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print(f"[실행] {sql_file_path}")
    print("-" * 60)

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True  # CREATE TABLE / CREATE INDEX / DO $$ 등 DDL은 autocommit

        with conn.cursor() as cur:
            cur.execute(sql_content)
            # 서버 NOTICE 메시지 출력
            for notice in conn.notices:
                print(f"  {notice.strip()}")

        print()
        print("✅ 마이그레이션 완료!")

    except psycopg2.Error as e:
        print(f"\n[ERROR] DB 오류: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python standalone_scripts/run_migration.py <SQL 파일 경로>")
        print("예시 : python standalone_scripts/run_migration.py migrations/006_add_daily_ohlcv_adjusted.sql")
        sys.exit(1)

    run_migration(sys.argv[1])
