# tdms_core/p2_kdms/ops/run_financial_manual.py
import sys
import os
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_financial_manual")

# 1. 루트 및 모듈 경로 바인딩
current_dir = os.path.dirname(os.path.abspath(__file__))
p2_kdms_path = os.path.abspath(os.path.join(current_dir, ".."))
pjt_root = os.path.abspath(os.path.join(current_dir, "..", "..")) # 01_nf3_tdms
p1_shared_path = os.path.join(pjt_root, "tdms_core", "p1_shared")

sys.path.insert(0, p2_kdms_path)
sys.path.insert(0, p1_shared_path)

# .env 로드
from p1_shared.utils.env_detector import EnvDetector
detector = EnvDetector()
detector.load_env_profile()

from tasks.financial_task import run_financial_update
from repositories.base import create_kdms_pool

def run_test():
    job_statuses = {}
    import os
    appkey = os.environ.get("KIS_APPKEY") or os.environ.get("KIS_APP_KEY", "")
    appsecret = os.environ.get("KIS_APPSECRET") or os.environ.get("KIS_APP_SECRET", "")
    logger.info(f"Loaded KIS_APPKEY: {appkey[:3]}...{appkey[-3:] if len(appkey) > 6 else ''} (Len: {len(appkey)})")
    logger.info(f"Loaded KIS_APPSECRET: {appsecret[:3]}...{appsecret[-3:] if len(appsecret) > 6 else ''} (Len: {len(appsecret)})")

    logger.info("Starting run_financial_update in REAL API BACKFILL mode (ALL STOCKS)...")
    
    # test_mode=False로 주어 실제 KIS API와 데이터베이스에서 전체 대상 종목을 조회하여 실행
    run_financial_update(job_statuses, test_mode=False)
    
    logger.info(f"Execution complete. status: {job_statuses}")
    
    # DB 결과 확인
    pool = create_kdms_pool()
    with pool.get_cursor() as cur:
        # 최근 2025년 11월 이후(202512 결산 등)에 해당하는 두 종목의 적재 내용 조회
        cur.execute("""
            SELECT stk_cd, stac_yymm, cras, total_aset, total_lblt, retrieved_at 
            FROM financial_statements 
            WHERE stk_cd IN ('005930', '000660') 
              AND stac_yymm >= '202511'
            ORDER BY stk_cd, stac_yymm, retrieved_at DESC
        """)
        statements = cur.fetchall()
        logger.info("=== DB Financial Statements Verification (stac_yymm >= 202511) ===")
        for row in statements:
            logger.info(f"Stk: {row[0]} | YearMonth: {row[1]} | CurrentAssets: {row[2]} | TotalAssets: {row[3]} | TotalLiabilities: {row[4]} | RetrievedAt: {row[5]}")

        cur.execute("""
            SELECT stk_cd, stac_yymm, roe_val, eps, bps, retrieved_at 
            FROM financial_ratios 
            WHERE stk_cd IN ('005930', '000660') 
              AND stac_yymm >= '202511'
            ORDER BY stk_cd, stac_yymm, retrieved_at DESC
        """)
        ratios = cur.fetchall()
        logger.info("=== DB Financial Ratios Verification (stac_yymm >= 202511) ===")
        for row in ratios:
            logger.info(f"Stk: {row[0]} | YearMonth: {row[1]} | ROE: {row[2]} | EPS: {row[3]} | BPS: {row[4]} | RetrievedAt: {row[5]}")

if __name__ == "__main__":
    run_test()
