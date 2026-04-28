import sys
import os
import psycopg2
from dotenv import load_dotenv

# Project Root Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.collectors.db_manager import DatabaseManager

def audit_table(cursor, table_name):
    print(f"\n[Table: {table_name}]")
    cursor.execute(f"""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_name = '{table_name}'
        ORDER BY ordinal_position;
    """)
    rows = cursor.fetchall()
    if not rows:
        print("  (Table not found or empty info)")
    for r in rows:
        print(f"  - {r['column_name']}: {r['data_type']}" + (f"({r['character_maximum_length']})" if r['character_maximum_length'] else "") + f" [Null: {r['is_nullable']}]")

    # Check Primary Key
    cursor.execute(f"""
        SELECT kcu.column_name
        FROM information_schema.key_column_usage kcu
        JOIN information_schema.table_constraints tc
        ON kcu.constraint_name = tc.constraint_name
        WHERE kcu.table_name = '{table_name}' AND tc.constraint_type = 'PRIMARY KEY';
    """)
    pks = cursor.fetchall()
    print(f"  * Primary Key: {[p['column_name'] for p in pks]}")

def main():
    print(">>> Auditing DB Schema...")
    db = DatabaseManager()
    with db.get_cursor() as cur:
        audit_table(cur, 'us_ticker_master')
        audit_table(cur, 'us_ticker_history')

if __name__ == "__main__":
    main()
