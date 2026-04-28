# truncate_financials.py
# Phase 4-B 재무 테이블 2개를 초기화(TRUNCATE)하는 유틸리티 스크립트

import logging
import sys
from dotenv import load_dotenv

try:
    # db_manager.py에서 DatabaseManager 클래스 임포트
    #
    from collectors.db_manager import DatabaseManager
    import utils # 로거 설정을 위해
except ImportError as e:
    print(f"Import Error: {e}", file=sys.stderr)
    print("이 스크립트는 KDMS 프로젝트 루트 디렉토리에서 실행해야 합니다.", file=sys.stderr)
    sys.exit(1)

# 로거 설정
logger = utils.setup_logger('truncate_util', level=logging.INFO)

def truncate_financial_tables():
    """
    financial_statements와 financial_ratios 테이블을 TRUNCATE합니다.
    """
    logger.info("========== [Util: Truncate Financials] 시작 ==========")
    
    # 1. 대상 테이블 (init.sql에 정의됨)
    SQL_STATEMENTS = "TRUNCATE TABLE financial_statements RESTART IDENTITY;"
    SQL_RATIOS = "TRUNCATE TABLE financial_ratios RESTART IDENTITY;"
    
    db = None
    conn = None
    
    try:
        db = DatabaseManager()
        
        # 2. DB 연결 (db_manager.py의 _get_connection 메서드 사용)
        #
        conn = db._get_connection()
        logger.info("데이터베이스 연결 성공. TRUNCATE 실행...")

        # 3. 트랜잭션 내에서 TRUNCATE 실행
        with conn.cursor() as cur:
            cur.execute(SQL_STATEMENTS)
            logger.info(f"Executing: {SQL_STATEMENTS}")
            cur.execute(SQL_RATIOS)
            logger.info(f"Executing: {SQL_RATIOS}")
        
        # 4. 변경 사항 커밋
        conn.commit() #
        
        logger.info("-" * 50)
        logger.info("✅ 성공: financial_statements 테이블 초기화 완료.")
        logger.info("✅ 성공: financial_ratios 테이블 초기화 완료.")
        logger.info("--------------------------------------------------")

    except Exception as e:
        if conn:
            conn.rollback() #
        logger.error(f"❌ 테이블 초기화 중 오류 발생: {e}", exc_info=True)
    finally:
        if conn:
            conn.close() #
        logger.info("========== [Util: Truncate Financials] 종료 ==========")

if __name__ == "__main__":
    # .env 파일 로드 (DB 접속 정보)
    load_dotenv()
    truncate_financial_tables()