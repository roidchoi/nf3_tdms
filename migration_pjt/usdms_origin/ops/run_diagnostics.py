import logging
import json
import os
import sys
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Dict, Any, List
from dotenv import load_dotenv

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from backend.collectors.db_manager import DatabaseManager
from backend.auditors.price_auditor import PriceReproducer
from backend.auditors.financial_auditor import FinancialDiagnostic
from backend.auditors.metric_auditor import MetricVerifier

# Load env
load_dotenv(override=True)

# Logging Setup
LOG_DIR = os.path.join(parent_dir, "logs/db_health/deep_diagnostic")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class DeepDiagnostic:
    def __init__(self):
        self.db = DatabaseManager()
        self.reproducer = PriceReproducer()
        self.fin_diag = FinancialDiagnostic(self.db)
        self.metric_diag = MetricVerifier(self.db)
        self.report = {
            "meta": {
                "report_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "type": "DEEP_DIAGNOSTIC",
                "duration_ms": 0
            },
            "summary": {
                "status": "GREEN",
                "total_checks": 0,
                "failed_checks": 0,
                "critical_count": 0
            },
            "details": []
        }
        self.start_time = datetime.now()

    def run(self):
        logger.info("Starting Deep Diagnostic Run...")
        
        # 1. Metadata Checks
        self.check_master_consistency()
        self.check_history_integrity()
        
        # 2. Market Data Checks
        self.check_price_validity()
        self.check_ohlc_logic()
        
        # 3. Financial & Valuation Checks
        self.check_financial_integrity()
        self.check_valuation_logic()
        
        # 4. Reproduction Verification (Sampled)
        self.check_price_reproduction(sample_rate=0.01) # 1% sample for speed, or fixed count
        
        # Finalize
        self.finalize_report()

    def add_result(self, category: str, check_name: str, status: str, severity: str, logic: str, failed_samples: List[Dict]):
        res = {
            "category": category,
            "check_name": check_name,
            "status": status,
            "severity": severity,
            "logic": logic,
            "failed_samples": failed_samples
        }
        self.report["details"].append(res)
        
        self.report["summary"]["total_checks"] += 1
        if status != "PASS":
            self.report["summary"]["failed_checks"] += 1
            if severity == "CRITICAL":
                self.report["summary"]["critical_count"] += 1
                self.report["summary"]["status"] = "RED"
            elif self.report["summary"]["status"] != "RED":
                self.report["summary"]["status"] = "YELLOW"
                
        logger.info(f"[{status}] {check_name} ({len(failed_samples)} items)")

    def check_master_consistency(self):
        """Check for active targets, duplicates, coverage."""
        with self.db.get_cursor() as cur:
            # 1. Target Validity (Active but no exchange info?)
            # Simplified: Check for tickers with NULL exchange in master?
            # us_ticker_master schema: cik, ticker, name, exchange, is_active...
            pass
            
            # 2. Duplicate Tickers
            cur.execute("""
                SELECT latest_ticker, COUNT(*) 
                FROM us_ticker_master 
                WHERE is_active = true 
                GROUP BY latest_ticker 
                HAVING COUNT(*) > 1
            """)
            dupes = cur.fetchall()
            self.add_result(
                category="METADATA",
                check_name="duplicate_tickers",
                status="FAIL" if dupes else "PASS",
                severity="CRITICAL",
                logic="Count(latest_ticker) > 1 where active=true",
                failed_samples=[{"ticker": r['latest_ticker'], "count": r['count']} for r in dupes]
            )

    def check_history_integrity(self):
        """Check for gaps or orphans in ticker history."""
        # Skipping complex history gap check for now (requires complex SQL).
        pass

    def check_price_validity(self):
        """Check for 0 or negative prices."""
        with self.db.get_cursor() as cur:
            cur.execute("""
                SELECT dt, ticker, open_prc, cls_prc 
                FROM us_daily_price 
                WHERE open_prc <= 0 OR high_prc <= 0 OR low_prc <= 0 OR cls_prc <= 0
                LIMIT 10
            """)
            rows = cur.fetchall()
            
            # Convert Query rows to dict
            samples = []
            if rows:
                samples = [{"dt": str(r['dt']), "ticker": r['ticker'], "cls_prc": float(r['cls_prc'])} for r in rows]

            self.add_result(
                category="MARKET_DATA",
                check_name="negative_prices",
                status="FAIL" if rows else "PASS",
                severity="CRITICAL",
                logic="OHLC <= 0",
                failed_samples=samples
            )

    def check_ohlc_logic(self):
        """Check High < Low, etc."""
        with self.db.get_cursor() as cur:
            cur.execute("""
                SELECT dt, ticker, high_prc, low_prc 
                FROM us_daily_price 
                WHERE high_prc < low_prc
                LIMIT 10
            """)
            rows = cur.fetchall()
            samples = []
            if rows:
                samples = [{"dt": str(r['dt']), "ticker": r['ticker'], "high": float(r['high_prc']), "low": float(r['low_prc'])} for r in rows]
                
            self.add_result(
                category="MARKET_DATA",
                check_name="ohlc_logic_high_low",
                status="FAIL" if rows else "PASS",
                severity="CRITICAL",
                logic="High < Low",
                failed_samples=samples
            )

    def check_financial_integrity(self):
        """Check Financials (Accounting Identity, Nulls, Leakage)."""
        # 1. Accounting Identity
        fails = self.fin_diag.check_accounting_identity()
        self.add_result("FINANCIAL", "accounting_identity", "FAIL" if fails else "PASS", "CRITICAL", "Assets = Liab + Equity", fails)
        
        # 2. Critical Nulls
        fails = self.fin_diag.check_critical_nulls()
        self.add_result("FINANCIAL", "critical_nulls", "FAIL" if fails else "PASS", "WARNING", "Nulls < 5%", fails)

        # 3. Historical Leakage
        fails = self.fin_diag.check_historical_leakage()
        self.add_result("FINANCIAL", "year_drift", "FAIL" if fails else "PASS", "CRITICAL", "FiscalYear vs ReportPeriod match", fails)

    def check_valuation_logic(self):
        """Check Valuation Metrics (ROE Reverse Calc, Ranges)."""
        # 1. ROE Logic
        fails = self.metric_diag.verify_roe_logic()
        self.add_result("METRICS", "roe_reverse_calc", "FAIL" if fails else "PASS", "WARNING", "Metrics.ROE approx NetIncome/Equity", fails)

        # 2. Valuation Range
        fails = self.metric_diag.verify_valuation_logic()
        self.add_result("VALUATION", "valuation_outliers", "FAIL" if fails else "PASS", "WARNING", "MktCap > 0 & Normal PE", fails)

    def check_price_reproduction(self, sample_rate=0.01):
        """Run PriceReproducer on a sample of tickers."""
        # Select Random Sample
        with self.db.get_cursor() as cur:
            cur.execute("SELECT latest_ticker FROM us_ticker_master WHERE is_active = true")
            all_tickers = [r['latest_ticker'] for r in cur.fetchall()]
        
        # Fixed targets + Random
        targets = ['AAPL', 'NVDA'] # Important ones
        
        # Verify if they exist in DB
        # If not, skip
        
        valid_targets = []
        # Check if AAPL/NVDA in all_tickers
        if 'AAPL' in all_tickers: valid_targets.append('AAPL')
        if 'NVDA' in all_tickers: valid_targets.append('NVDA')

        # Add random 3 tickers if available
        others = [t for t in all_tickers if t not in valid_targets]
        if others:
            # Deterministic for test? Or pure random. Random is fine.
            import random
            random.shuffle(others)
            valid_targets.extend(others[:3])
            
        logger.info(f"Running Price Reproduction Check on {len(valid_targets)} tickers...")
        
        failed_tickers = []
        
        for ticker in valid_targets:
            res = self.reproducer.verify_ticker(ticker)
            if res['status'] == 'FAIL':
                failed_tickers.append({
                    "ticker": ticker,
                    "max_error": res.get('max_error'),
                    "failed_count": res.get('failed_count'),
                    "sample": res.get('failed_samples', [])[:1] # Just 1 sample
                })
        
        self.add_result(
            category="REPRODUCTION",
            check_name="adj_close_reproduction",
            status="FAIL" if failed_tickers else "PASS",
            severity="CRITICAL",
            logic="Calculated Adj != KIS Adj (Error > 0.1%)",
            failed_samples=failed_tickers
        )

    def finalize_report(self):
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds() * 1000
        self.report["meta"]["duration_ms"] = int(duration)
        
        filename = f"deep_diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(LOG_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, indent=2, default=str)
            
        logger.info(f"\nDeep Diagnostic Completed. Report: {filepath}")
        logger.info(f"Status: {self.report['summary']['status']}")

if __name__ == "__main__":
    diag = DeepDiagnostic()
    diag.run()
