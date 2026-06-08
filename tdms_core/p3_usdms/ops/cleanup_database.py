import sys
import logging
from dotenv import load_dotenv

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared")

# .env 로드
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_database")

from p3_usdms.repositories.base import BaseRepository

def run_cleanup():
    logger.info("=== Starting USDMS Database Cleanup Process ===")
    
    # 1. DB 커넥션 풀 참조
    try:
        repo = BaseRepository()
        pool = repo._pool
        logger.info("Database connection pool reference obtained successfully.")
    except Exception as err:
        logger.critical(f"Failed to access database pool: {err}")
        return

    # 2. DROP할 대상 테스트/임시 테이블 리스트
    target_tables = [
        "us_daily_price_test",
        "us_daily_valuation_test",
        "us_financial_facts_test",
        "us_financial_metrics_test",
        "us_price_adjustment_factors_test",
        "us_share_history_test",
        "us_standard_financials_test",
        "us_ticker_history_test",
        "us_ticker_master_test",
        "us_collection_blacklist_test",
        "trading_calendar_test"
    ]
    
    conn = None
    try:
        conn = pool.get_conn()
        conn.autocommit = True
        
        with conn.cursor() as cursor:
            # 병렬 락 한도 이슈 방지를 위해 설정 조정
            cursor.execute("SET max_parallel_workers_per_gather = 0;")
            
            for table in target_tables:
                logger.info(f"Checking table existence: {table}...")
                
                # 테이블 존재 여부 확인
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                          AND table_name = %s
                    );
                """, (table,))
                exists = cursor.fetchone()[0]
                
                if exists:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    rows = cursor.fetchone()[0]
                    
                    # Timescale Hypertable 등 자식 파티션 확인
                    cursor.execute("""
                        SELECT inhrelid::regclass::text AS child_table
                        FROM pg_inherits
                        WHERE inhparent = %s::regclass;
                    """, (table,))
                    chunks = [r[0] for r in cursor.fetchall()]
                    
                    if chunks:
                        logger.info(f"Table {table} is partitioned with {len(chunks)} chunks. Dropping chunks one by one...")
                        for idx, chunk in enumerate(chunks):
                            try:
                                parts = chunk.split('.')
                                if len(parts) == 2:
                                    escaped_chunk = f'"{parts[0]}"."{parts[1]}"'
                                else:
                                    escaped_chunk = f'"{chunk}"'
                                cursor.execute(f"DROP TABLE IF EXISTS {escaped_chunk};")
                            except Exception as chunk_err:
                                logger.warning(f"Failed to drop chunk {chunk}: {chunk_err}")
                    
                    if rows > 50000 and not chunks:
                        logger.info(f"Table {table} has many rows ({rows}). Truncating first to release lock load...")
                        try:
                            cursor.execute(f"TRUNCATE TABLE {table};")
                        except Exception:
                            cursor.execute(f"TRUNCATE TABLE {table} CASCADE;")
                    
                    logger.info(f"Dropping table {table}...")
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS {table};")
                    except Exception:
                        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    
                    logger.info(f"Successfully dropped table {table}.")
                else:
                    logger.info(f"Table {table} does not exist. Skipping.")
                    
        logger.info("=== Database Cleanup Process Completed Successfully ===")
        
    except Exception as e:
        logger.error(f"Error occurred during database cleanup: {e}", exc_info=True)
    finally:
        if conn:
            try:
                conn.autocommit = False
            except Exception:
                pass
            pool.put_conn(conn)

if __name__ == '__main__':
    run_cleanup()
