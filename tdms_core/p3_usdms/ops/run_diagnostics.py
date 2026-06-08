# tdms_core/p3_usdms/ops/run_diagnostics.py
import os
import sys
import argparse
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

from p3_usdms.repositories.price_repo import PriceRepo
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.collectors.kis_us_client import KisUSClient

from p3_usdms.auditors.financial_auditor import FinancialDiagnostic
from p3_usdms.auditors.metric_auditor import MetricVerifier
from p3_usdms.auditors.price_auditor import PriceReproducer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_diagnostics(limit: int, tickers: List[str], start_date: str = None, end_date: str = None):
    logger.info("Starting USDMS System Diagnostics...")
    
    # 1. DB 커넥션 풀 획득
    price_repo = PriceRepo()
    pool = price_repo._pool
    
    if not pool:
        logger.error("❌ Database Connection Pool could not be established.")
        sys.exit(1)
        
    master_repo = MasterRepo(pool)
    
    # 2. KIS API 클라이언트 인스턴스 빌드
    app_key = os.environ.get("KIS_APP_KEY") or os.environ.get("KIS_APPKEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET") or os.environ.get("KIS_APPSECRET", "")
    account_no = os.environ.get("KIS_ACCOUNT_NO") or os.environ.get("KIS_CANO", "")
    is_mock = os.environ.get("KIS_MOCK", "false").lower() in ("true", "1", "yes")
    
    kis_client = KisUSClient(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        is_mock=is_mock
    )
    
    logger.info("=== [1] Financial Auditor Diagnostics ===")
    financial_auditor = FinancialDiagnostic(pool)
    
    # (1) 회계 항등식 검증
    logger.info(f"Checking accounting identity (limit: {limit})...")
    identity_failures = financial_auditor.check_accounting_identity(sample_limit=limit)
    identity_status = "PASS" if not identity_failures else f"FAIL ({len(identity_failures)} anomalies found)"
    logger.info(f"-> Accounting Identity: {identity_status}")
    if identity_failures:
        for idx, f in enumerate(identity_failures[:5]):
            logger.warning(f"   [{idx+1}] CIK: {f.get('cik')}, Period: {f.get('report_period')}, Assets: {f.get('total_assets')}, Liab+Equity: {f.get('total_liabilities', 0)+f.get('total_equity', 0)}, Diff%: {f.get('diff_pct'):.4f}%")
            
    # (2) 핵심 Null 값 비율 검증
    logger.info("Checking critical null ratios...")
    null_metrics = financial_auditor.check_critical_nulls()
    logger.info("-> Critical Nulls Status:")
    for m in null_metrics:
        status_icon = "✅" if m.get("status") == "GREEN" else "⚠️"
        logger.info(f"   {status_icon} {m.get('metric_name')}: Null Ratio = {m.get('null_ratio'):.2f}%, Threshold = {m.get('threshold_pct')}%, Status = {m.get('status')}")
        
    # (3) 공시 이격 검증
    logger.info("Checking historical leakage (report period vs fiscal year gap)...")
    leakage_failures = financial_auditor.check_historical_leakage()
    leakage_status = "PASS" if not leakage_failures else f"FAIL ({len(leakage_failures)} anomalies found)"
    logger.info(f"-> Historical Leakage: {leakage_status}")
    if leakage_failures:
        for idx, f in enumerate(leakage_failures[:5]):
            logger.warning(f"   [{idx+1}] CIK: {f.get('cik')}, Period: {f.get('report_period')}, Fiscal Year: {f.get('fiscal_year')}, Gap: {f.get('year_gap')} years")
            
    logger.info("\n=== [2] Metric Auditor Diagnostics ===")
    metric_auditor = MetricVerifier(pool)
    
    # (1) ROE 역산 오차 검증
    logger.info(f"Verifying ROE logic (limit: {limit})...")
    roe_failures = metric_auditor.verify_roe_logic(sample_limit=limit)
    roe_status = "PASS" if not roe_failures else f"FAIL ({len(roe_failures)} anomalies found)"
    logger.info(f"-> ROE Logic Consistency: {roe_status}")
    if roe_failures:
        for idx, f in enumerate(roe_failures[:5]):
            logger.warning(f"   [{idx+1}] CIK: {f.get('cik')}, Period: {f.get('report_period')}, ROE in DB: {f.get('db_roe')}%, Computed ROE: {f.get('computed_roe'):.2f}%")
            
    # (2) 가치평가 아웃라이어 검증
    logger.info(f"Verifying valuation logic and outliers (limit: {limit})...")
    valuation_failures = metric_auditor.verify_valuation_logic(sample_limit=limit)
    valuation_status = "PASS" if not valuation_failures else f"FAIL ({len(valuation_failures)} anomalies found)"
    logger.info(f"-> Valuation Outliers: {valuation_status}")
    if valuation_failures:
        for idx, f in enumerate(valuation_failures[:5]):
            logger.warning(f"   [{idx+1}] CIK: {f.get('cik')}, Period: {f.get('report_period')}, PE Ratio: {f.get('pe_ratio')}, Market Cap: {f.get('market_cap')}")
            
    logger.info("\n=== [3] Price Adjustment Auditor Diagnostics ===")
    price_auditor = PriceReproducer(pool, kis_client)
    
    if not tickers:
        # 디폴트로 검증할 주요 주식 목록 설정
        tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
        
    logger.info(f"Verifying price adjustment replication for tickers: {tickers}")
    price_results = {}
    for ticker in tickers:
        try:
            res = price_auditor.verify_ticker(ticker, start_dt=start_date, end_dt=end_date)
            price_results[ticker] = res
            status_icon = "✅" if res.get("status") == "PASS" else "❌"
            logger.info(f"   {status_icon} {ticker}: Status = {res.get('status')}, Max Error = {res.get('max_error_pct'):.4f}%, Checked Rows = {res.get('checked_rows')}")
            if res.get("status") == "FAIL" and res.get("anomaly_samples"):
                logger.warning(f"      First failure details: Date = {res['anomaly_samples'][0]['dt']}, Calc Price = {res['anomaly_samples'][0]['calc_price']}, KIS Price = {res['anomaly_samples'][0]['kis_price']}, Diff% = {res['anomaly_samples'][0]['diff_pct']:.4f}%")
        except Exception as e:
            logger.error(f"   ❌ {ticker}: Failed to perform audit. Error: {e}")
            price_results[ticker] = {"status": "ERROR", "error": str(e)}
            
    logger.info("\n=== [4] Data Freshness Status ===")
    # trading_calendar 기반 최신 수집 현황 간이 검증
    try:
        with pool.get_cursor() as cursor:
            cursor.execute("SELECT dt FROM trading_calendar WHERE opnd_yn = 'Y' ORDER BY dt DESC LIMIT 1")
            row = cursor.fetchone()
            latest_trading_date = row[0] if row else date.today()
            
            cursor.execute("SELECT COUNT(*) FROM us_daily_price WHERE dt = %s", (latest_trading_date,))
            collected_count = cursor.fetchone()[0]
            
            active_targets_count = len(master_repo.get_collect_targets())
            
            coverage = (collected_count / active_targets_count * 100.0) if active_targets_count > 0 else 0.0
            freshness_status = "GREEN" if coverage >= 95.0 else "RED"
            
            logger.info(f"-> Latest Trading Date: {latest_trading_date}")
            logger.info(f"-> Total Active Targets: {active_targets_count}")
            logger.info(f"-> Daily Collected Rows: {collected_count} (Coverage: {coverage:.2f}%)")
            logger.info(f"-> Freshness Status: {freshness_status}")
    except Exception as e:
        logger.error(f"❌ Failed to run data freshness status query: {e}")
        
    logger.info("\nDiagnostics Complete.")
    
    # 전체 오작동 검출 건수가 존재하면 비정상 코드 종료를 보낼 수 있음
    total_failures = len(identity_failures) + len(leakage_failures) + len(roe_failures) + len(valuation_failures)
    failed_tickers = [t for t, res in price_results.items() if res.get("status") == "FAIL"]
    total_failures += len(failed_tickers)
    
    if total_failures > 0:
        logger.warning(f"❌ Diagnostics failed with total {total_failures} data anomalies.")
        return False
    else:
        logger.info("✅ USDMS System Diagnostics completed with no anomalies found.")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="USDMS System Diagnostics Utility")
    parser.add_argument("--limit", type=int, default=100, help="Sample limit for database queries (default: 100)")
    parser.add_argument("--ticker", type=str, default="", help="Comma separated tickers to audit price adjustment (e.g. AAPL,MSFT)")
    parser.add_argument("--start-date", type=str, default=None, help="Start date for price audit (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="End date for price audit (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    ticker_list = [t.strip().upper() for t in args.ticker.split(",")] if args.ticker else []
    
    success = run_diagnostics(
        limit=args.limit,
        tickers=ticker_list,
        start_date=args.start_date,
        end_date=args.end_date
    )
    
    sys.exit(0 if success else 1)
