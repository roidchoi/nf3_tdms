import sys
import logging
from dotenv import load_dotenv

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared")

# .env 로드
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_database")

from repositories.base import create_kdms_pool

def run_cleanup():
    logger.info("=== Starting KDMS Database Cleanup Process ===")
    
    # 1. DB 커넥션 풀 생성
    try:
        pool = create_kdms_pool()
        logger.info("Database connection pool established successfully.")
    except Exception as err:
        logger.critical(f"Failed to create database pool: {err}")
        return

    # 2. DROP할 대상 테이블 리스트
    target_tables = [
        "daily_ohlcv_adjusted_legacy",
        "daily_ohlcv_adjusted_legacy_test",
        "daily_ohlcv_test",
        "minute_ohlcv_test",
        "minute_target_history_test",
        "price_adjustment_factors_test",
        "stock_info_test",
        "trading_calendar_test"
    ]
    
    conn = None
    try:
        conn = pool.get_conn()
        # Enable autocommit to run each query in its own transaction,
        # preventing locks from accumulating and causing "out of shared memory"
        conn.autocommit = True
        
        with conn.cursor() as cursor:
            # Disable parallel gather to bypass out of shared memory lock issue
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
                    # 행 수 및 크기 파악해 로깅
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    rows = cursor.fetchone()[0]
                    
                    # Check if the table is partitioned (e.g. Timescale Hypertable)
                    cursor.execute("""
                        SELECT inhrelid::regclass::text AS child_table
                        FROM pg_inherits
                        WHERE inhparent = %s::regclass;
                    """, (table,))
                    chunks = [r[0] for r in cursor.fetchall()]
                    
                    if chunks:
                        logger.info(f"Table {table} is partitioned with {len(chunks)} chunks. Dropping chunks one by one to avoid lock limit...")
                        for idx, chunk in enumerate(chunks):
                            if idx % 100 == 0:
                                logger.info(f"  Dropping chunk progress: {idx}/{len(chunks)}...")
                            try:
                                parts = chunk.split('.')
                                if len(parts) == 2:
                                    escaped_chunk = f'"{parts[0]}"."{parts[1]}"'
                                else:
                                    escaped_chunk = f'"{chunk}"'
                                cursor.execute(f"DROP TABLE IF EXISTS {escaped_chunk};")
                            except Exception as chunk_err:
                                logger.warning(f"Failed to drop chunk {chunk}: {chunk_err}")
                    
                    # Truncate remains if any
                    if rows > 100000 and not chunks:
                        logger.info(f"Table {table} has many rows ({rows}). Truncating first to release lock load...")
                        try:
                            cursor.execute(f"TRUNCATE TABLE {table};")
                        except Exception as tr_err:
                            logger.warning(f"Truncate without cascade failed: {tr_err}. Retrying with CASCADE...")
                            cursor.execute(f"TRUNCATE TABLE {table} CASCADE;")
                    
                    logger.info(f"Dropping table {table}...")
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS {table};")
                    except Exception as drop_err:
                        logger.warning(f"Drop without cascade failed: {drop_err}. Retrying with CASCADE...")
                        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    
                    logger.info(f"Successfully dropped table {table}.")
                else:
                    logger.info(f"Table {table} does not exist. Skipping.")
                    
        logger.info("=== Database Cleanup Process Completed Successfully ===")
        
    except Exception as e:
        logger.error(f"Error occurred during database cleanup: {e}", exc_info=True)
    finally:
        if conn:
            # Reset autocommit to default (False) before returning to connection pool
            try:
                conn.autocommit = False
            except Exception:
                pass
            pool.put_conn(conn)

if __name__ == '__main__':
    run_cleanup()
