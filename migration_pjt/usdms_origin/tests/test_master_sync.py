# ops/verify_master_sync.py
import sys
import os
import logging
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.collectors.master_sync import MasterSync
from backend.collectors.db_manager import DatabaseManager

# 환경변수 로드
load_dotenv(override=True)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def verify_master():
    print("DEBUG: Starting verify_master", flush=True)
    logger.info(">>> [Test] Master Sync 단독 실행 시작 <<<")
    
    print("DEBUG: Initializing components...", flush=True)
    sync = MasterSync()
    db = DatabaseManager()
    print("DEBUG: Components initialized. Running sync_daily...", flush=True)

    try:
        # 1. Master Sync 실행
        stats = sync.sync_daily()
        logger.info(f"✅ Master Sync 실행 완료. 통계: {stats}")

        # 2. DB 검증 (데이터가 제대로 들어갔는지 확인)
        logger.info(">>> [Test] DB 데이터 검증 중...")
        
        with db.get_cursor() as cur:
            # A. 신규 컬럼 (latest_name) 확인
            cur.execute("SELECT cik, latest_ticker, latest_name, exchange FROM us_ticker_master LIMIT 5")
            rows = cur.fetchall()
            
            logger.info("--- [Sample Data] ---")
            for r in rows:
                logger.info(f"CIK: {r['cik']} | Ticker: {r['latest_ticker']} | Name: {r['latest_name']} | Exch: {r['exchange']}")
            
            # B. 거래소 표준화 확인 (NMS 등이 없어야 함)
            cur.execute("""
                SELECT exchange, COUNT(*) as cnt 
                FROM us_ticker_master 
                GROUP BY exchange
            """)
            exch_stats = cur.fetchall()
            logger.info(f"--- [Exchange Stats] ---\n{exch_stats}")

        logger.info("✅ 검증 성공: 에러 없이 완료되었습니다.")

    except Exception as e:
        logger.error(f"❌ 검증 실패: {e}", exc_info=True)

if __name__ == "__main__":
    verify_master()