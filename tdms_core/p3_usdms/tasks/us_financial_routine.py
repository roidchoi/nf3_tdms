import os
import sys
import json
import logging
import time
import asyncio
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Set, Tuple
from zoneinfo import ZoneInfo

from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.blacklist_repo import BlacklistRepo
from p3_usdms.utils.blacklist_manager import BlacklistManager
from p3_usdms.collectors.sec_client import SECClient
from p3_usdms.collectors.financial_parser import FinancialParser
from p3_usdms.engines.metric_calculator import MetricCalculator
from p3_usdms.engines.valuation_calculator import ValuationCalculator
from p3_usdms.utils.silent_logger import SilentLoopContext

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
TARGET_ROOT_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K", "8-K"}

class UsFinancialRoutine:
    def __init__(self, master_repo=None, blacklist_repo=None, blacklist_mgr=None):
        self.master_repo = master_repo or MasterRepo()
        self.blacklist_repo = blacklist_repo or BlacklistRepo()
        self.blacklist_mgr = blacklist_mgr or BlacklistManager(repo=self.blacklist_repo)
        
        self.sec_client = SECClient()
        self.fin_parser = FinancialParser()
        self.metric_calc = MetricCalculator()
        self.val_calc = ValuationCalculator()
        
        self.db = self.master_repo

    def _root_form(self, form_type: str) -> str:
        return form_type.split("/")[0].strip()

    def fetch_master_idx(self, d: date) -> List[Dict[str, Any]]:
        """
        해당 일자의 daily master.idx 를 받아 레코드 리스트로 반환.
        반환: records = [{'cik','form','date','file','accession'}...]
              파일이 없거나 오류 발생 시 빈 리스트 반환
        """
        qtr = (d.month - 1) // 3 + 1
        url = (f"https://www.sec.gov/Archives/edgar/daily-index/"
               f"{d.year}/QTR{qtr}/master.{d.strftime('%Y%m%d')}.idx")
        
        headers = self.sec_client.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        # Rate Limiting
        self.sec_client._enforce_rate_limit()
        
        try:
            resp = self.sec_client.session.get(url, headers=headers, timeout=self.sec_client.timeout + 10)
            if resp.status_code == 403:
                logger.debug(f"Got 403 Forbidden for daily master.idx on {d}. Treating as empty.")
                return []
            if resp.status_code == 404:
                logger.debug(f"Daily index not found for {d} (HTTP 404). Weekend/Holiday?")
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Failed to fetch daily master.idx for {d}: {e}")
            return []

        records = []
        started = False
        for line in resp.text.splitlines():
            if line.startswith("----"):
                started = True
                continue
            if not started or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) != 5:
                continue
            cik, name, form, filed, fname = [p.strip() for p in parts]
            if not cik.isdigit():
                continue
            m = re.search(r"(\d{10}-\d{2}-\d{6})", fname)
            records.append({
                "cik": cik.zfill(10),
                "form": form,
                "date": filed,
                "file": fname,
                "accession": m.group(1) if m else None,
            })
        return records

    async def run(self, test_limit: int = None, target_date: date = None, force_all: bool = False) -> Dict[str, Any]:
        """
        US Financial 수집 루틴 오케스트레이터.
        """
        if target_date is None:
            target_date = datetime.now(KST).date()

        start_time = datetime.now(KST)
        from p3_usdms.config import get_settings
        log_dir = get_settings().LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        
        # 테스트 환경인 경우 테스트 로그 파일로 경로 격리하여 프로덕션 로그 오염 방지
        is_test = os.environ.get("TDMS_ENV") == "test" or "pytest" in sys.modules
        log_filename = "daily_routine_test.log" if is_test else "daily_routine.log"
        log_filepath = os.path.join(log_dir, log_filename)
        
        file_handler = None
        root_logger = logging.getLogger()
        
        # 기존 동일한 파일에 연결된 FileHandler가 있는지 검사하여 재사용 또는 생성
        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename == os.path.abspath(log_filepath):
                file_handler = handler
                break
                
        if not file_handler:
            file_handler = logging.FileHandler(log_filepath, mode="a", encoding="utf-8")
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        logger.info(f"Starting US Financial Routine (Target Date: {target_date}, force_all={force_all})")

        report = {
            "routine": "us_financial",
            "start_time": start_time.isoformat(),
            "status": "RUNNING",
            "steps": []
        }

        try:
            # 차단 유예기간(쿨다운)이 만료된 종목 자동 차단 해제
            released_cnt = self.blacklist_mgr.auto_release_expired_blocks()
            if isinstance(released_cnt, int) and released_cnt > 0:
                logger.info(f"[Blacklist Auto-Release] Cool-off expired for {released_cnt} CIKs. Unblocked successfully.")

            target_ciks = []
            
            if force_all:
                logger.info("force_all is True. Targeting all active tickers in master.")
                all_targets = self.master_repo.get_collect_targets()
                target_ciks = [t['cik'] for t in all_targets if not self.blacklist_mgr.is_blacklisted(t['cik'])]
                if test_limit:
                    target_ciks = target_ciks[:test_limit]
            else:
                # 1. 5일 오버랩 daily master.idx 스캔
                logger.info(f"Scanning SEC daily index for the past 5 days (T-5 to T-1 relative to {target_date})...")
                index_filings = []
                idx_fetch_failures = 0
                success_dates = []
                
                for offset in range(5, 0, -1):
                    scan_d = target_date - timedelta(days=offset)
                    records = self.fetch_master_idx(scan_d)
                    if not records:
                        idx_fetch_failures += 1
                        logger.debug(f"Could not load daily index for {scan_d} (or empty). Skipping this date.")
                        continue
                    
                    # Target Form 필터링
                    filtered = [r for r in records if self._root_form(r["form"]) in TARGET_ROOT_FORMS]
                    index_filings.extend(filtered)
                    success_dates.append(scan_d.strftime('%Y-%m-%d'))

                logger.info(
                    f"[SEC Index Scan] T-5 ~ T-1 스캔 완료. 로드 성공: {len(success_dates)}/5일 "
                    f"({', '.join(success_dates) if success_dates else '없음'}), "
                    f"식별된 대상 공시 서식 건수: 총 {len(index_filings)}건"
                )

                # 5일치 index 파일 중 단 한 개도 다운로드받지 못한 경우 -> Notice 로그 후 당일 배치 스킵
                if idx_fetch_failures == 5:
                    logger.error("Failed to download daily SEC index files for all of the past 5 days. Skipping financial routine execution.")
                    report["steps"].append({
                        "step": "SEC Index Download",
                        "status": "FAILED",
                        "duration_seconds": (datetime.now(KST) - start_time).total_seconds(),
                        "error": "All 5 index files failed to download (weekend/holiday, network error or index delay)."
                    })
                    report["status"] = "SKIPPED"
                    self._save_report(report)
                    return report

                if not index_filings:
                    logger.info("No target form filings found in the scanned 5 days. Nothing to collect.")
                else:
                    # 2. DB 미적재 공시 차집합 필터링
                    # 중복 제거
                    unique_filings = {}
                    for f in index_filings:
                        unique_filings[(f['cik'], f['date'])] = f
                    
                    ciks_in_idx = list(set(cik for cik, _ in unique_filings.keys()))
                    dates_in_idx = list(set(dt for _, dt in unique_filings.keys()))
                    
                    # DB 적재 내역 벌크 조회
                    db_filings = set()
                    if ciks_in_idx and dates_in_idx:
                        db_query = """
                            SELECT DISTINCT cik, filed_dt::text
                            FROM us_standard_financials
                            WHERE cik = ANY(%s) AND filed_dt::text = ANY(%s)
                        """
                        try:
                            with self.db.get_cursor() as cur:
                                cur.execute(db_query, (ciks_in_idx, dates_in_idx))
                                rows = cur.fetchall()
                                for r in rows:
                                    if isinstance(r, dict):
                                        db_filings.add((r['cik'], r['filed_dt']))
                                    else:
                                        db_filings.add((r[0], str(r[1])))
                        except Exception as e:
                            logger.error(f"Failed to query existing standard financials: {e}")

                    # 차집합 필터링
                    missing_ciks = set()
                    for (cik, filed_dt), f in unique_filings.items():
                        if (cik, filed_dt) not in db_filings:
                            missing_ciks.add(cik)
                    
                    # 수집 대상 종목 리스트 획득 (is_collect_target = True)
                    collect_targets = self.master_repo.get_collect_targets()
                    collect_target_ciks = {t['cik'].zfill(10) for t in collect_targets}
                    
                    # 블랙리스트 및 실제 수집 대상 종목 필터링
                    target_ciks = [
                        cik for cik in missing_ciks 
                        if cik.zfill(10) in collect_target_ciks and not self.blacklist_mgr.is_blacklisted(cik)
                    ]
                    if test_limit:
                        target_ciks = target_ciks[:test_limit]
                        
                    logger.info(f"Identified {len(target_ciks)} CIKs with pending filings after differential filtering, collect-target checks and blacklist checks.")

            # 3. 핀포인트 facts 수집 기동
            ingested_ciks = []
            if target_ciks:
                step_start = datetime.now(KST)
                logger.info(f"[Step 3] SEC Filing Financial Parsing for {len(target_ciks)} CIKs...")
                try:
                    silent_parser_modules = [
                        "p3_usdms.collectors.financial_parser",
                        "p3_usdms.collectors.sec_client",
                        "urllib3",
                        "requests"
                    ]
                    with SilentLoopContext(silent_parser_modules):
                        success_count, ingested_ciks = await asyncio.to_thread(self.fin_parser.run, ciks=target_ciks)
                    
                    step_status = "SUCCESS"
                    if len(target_ciks) > 0 and success_count == 0:
                        step_status = "FAILED"
                        logger.error(f"[Step 3] All {len(target_ciks)} target CIKs failed to process (e.g. HTTP 429 block). Flagging step as FAILED.")
                    
                    report["steps"].append({
                        "step": "Financial Parser",
                        "status": step_status,
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "details": {
                            "processed_count": len(target_ciks), 
                            "success_count": success_count,
                            "ingested_count": len(ingested_ciks)
                        }
                    })
                except Exception as e:
                    logger.error(f"[Step 3] Financial Parser failed: {e}", exc_info=True)
                    report["steps"].append({
                        "step": "Financial Parser",
                        "status": "FAILED",
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "error": str(e)
                    })

                # 4. 계산 엔진 벌크 기동
                step_start = datetime.now(KST)
                
                # 전체 활성 CIK 목록 추출 및 블랙리스트 제외 (가치평가 계산용 전체 대상)
                all_targets = self.master_repo.get_collect_targets()
                all_active_ciks = [t['cik'] for t in all_targets if not self.blacklist_mgr.is_blacklisted(t['cik'])]
                if test_limit:
                    all_active_ciks = all_active_ciks[:test_limit]

                logger.info(f"[Step 4] Calculating Financial Metrics for {len(ingested_ciks)} ingested CIKs & Daily Valuations for {len(all_active_ciks)} CIKs...")
                try:
                    # CIK별 최신 가치평가 날짜 사전 벌크 적재 캐시 구축
                    latest_val_dates_cache = {}
                    if self.val_calc and hasattr(self.val_calc.repo, "get_all_latest_valuation_dates"):
                        try:
                            latest_val_dates_cache = self.val_calc.repo.get_all_latest_valuation_dates(all_active_ciks)
                            logger.info(f"Loaded {len(latest_val_dates_cache)} latest valuation dates into memory cache.")
                        except Exception as cache_err:
                            logger.warning(f"Failed to load latest valuation dates bulk cache: {cache_err}")

                    silent_calc_modules = [
                        "p3_usdms.engines.metric_calculator",
                        "p3_usdms.engines.valuation_calculator"
                    ]
                    with SilentLoopContext(silent_calc_modules):
                        chunk_size = 100
                        # 1) Metric Calculator (실제 데이터 적재 성공 종목만 핀포인트 계산)
                        metric_total = len(ingested_ciks)
                        if metric_total > 0:
                            metric_start_time = time.time()
                            for idx, i in enumerate(range(0, metric_total, chunk_size)):
                                chunk = ingested_ciks[i:i + chunk_size]
                                await asyncio.to_thread(self.metric_calc.calculate_and_save_bulk, chunk, rebuild=False, chunk_size=chunk_size)
                                processed = min(i + chunk_size, metric_total)
                                elapsed = time.time() - metric_start_time
                                elapsed = max(elapsed, 1e-6)
                                items_per_sec = processed / elapsed
                                remaining = metric_total - processed
                                eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                                progress_pct = (processed / metric_total) * 100.0
                                
                                logger.info(
                                    f"[Step 4] Metric Calculation Progress: {progress_pct:.1f}% ({processed}/{metric_total}) | "
                                    f"Speed: {items_per_sec:.1f} symbols/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str}"
                                )
                                await asyncio.sleep(0.01)
                            
                        # 2) Valuation Calculator (전체 활성 종목 대상)
                        val_total = len(all_active_ciks)
                        if val_total > 0:
                            val_start_time = time.time()
                            for idx, i in enumerate(range(0, val_total, chunk_size)):
                                chunk = all_active_ciks[i:i + chunk_size]
                                chunk_cache = {cik: latest_val_dates_cache[cik] for cik in chunk if cik in latest_val_dates_cache}
                                await asyncio.to_thread(self.val_calc.calculate_and_save_bulk, chunk, rebuild=False, chunk_size=chunk_size, latest_val_dates_cache=chunk_cache)
                                processed = min(i + chunk_size, val_total)
                                elapsed = time.time() - val_start_time
                                elapsed = max(elapsed, 1e-6)
                                items_per_sec = processed / elapsed
                                remaining = val_total - processed
                                eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                                progress_pct = (processed / val_total) * 100.0
                                
                                logger.info(
                                    f"[Step 4] Valuation Calculation Progress: {progress_pct:.1f}% ({processed}/{val_total}) | "
                                    f"Speed: {items_per_sec:.1f} symbols/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str}"
                                )
                                await asyncio.sleep(0.01)
                    
                    report["steps"].append({
                        "step": "Metric & Valuation Calculation",
                        "status": "SUCCESS",
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "details": {
                            "metric_target_count": len(ingested_ciks),
                            "valuation_target_count": len(all_active_ciks)
                        }
                    })
                except Exception as e:
                    logger.error(f"[Step 4] Metric & Valuation Calculation failed: {e}", exc_info=True)
                    report["steps"].append({
                        "step": "Metric & Valuation Calculation",
                        "status": "FAILED",
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "error": str(e)
                    })

                # 5. 재무 관련 Health Check & 격리 (Valuation Anomalies)
                step_start = datetime.now(KST)
                logger.info("[Step 5] Performing Valuation Ingestion Health Checks & Data Isolation...")
                try:
                    anomalies = await asyncio.to_thread(self._detect_valuation_anomalies, target_date)
                    report["steps"].append({
                        "step": "Health Check & Isolation",
                        "status": "SUCCESS",
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "details": {
                            "anomalies_found": len(anomalies),
                            "quarantined_targets": list(set(a["ticker"] for a in anomalies))
                        }
                    })
                except Exception as e:
                    logger.error(f"[Step 5] Health Check & Isolation failed: {e}", exc_info=True)
                    report["steps"].append({
                        "step": "Health Check & Isolation",
                        "status": "FAILED",
                        "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                        "error": str(e)
                    })
            else:
                logger.info("No pending target CIKs to collect. Financial Routine completed immediately.")
                report["steps"].append({
                    "step": "Ingestion",
                    "status": "SUCCESS",
                    "duration_seconds": 0,
                    "details": {"processed_count": 0}
                })

            # 최종 리포트 마감 및 영속화
            end_time = datetime.now(KST)
            report["end_time"] = end_time.isoformat()
            report["total_duration_seconds"] = (end_time - start_time).total_seconds()
            
            has_failed_step = any(s["status"] == "FAILED" for s in report["steps"])
            report["status"] = "FAILED" if has_failed_step else "SUCCESS"
            
            self._save_report(report)
            logger.info(f"Financial routine completed with status: {report['status']}")
            return report
            
        finally:
            if file_handler:
                file_handler.close()
                root_logger.removeHandler(file_handler)

    def _detect_valuation_anomalies(self, target_date: date) -> List[Dict[str, Any]]:
        """
        수집 기준일(target_date)에 적재된 가치평가 데이터를 분석하여 오염 데이터를 식별하고 격리(삭제/롤백)합니다.
        """
        anomalies = []

        val_query = """
            SELECT t.cik, t.latest_ticker, v_today.pe as today_pe, v_yesterday.pe as yesterday_pe
            FROM us_ticker_master t
            JOIN us_daily_valuation v_today ON t.cik = v_today.cik AND v_today.dt = %s
            JOIN us_daily_valuation v_yesterday ON t.cik = v_yesterday.cik AND v_yesterday.dt = %s - INTERVAL '1 day'
        """

        with self.db.get_cursor() as cur:
            cur.execute(val_query, (target_date, target_date))
            val_rows = cur.fetchall()
            for r in val_rows:
                if isinstance(r, dict):
                    cik = r['cik']
                    today_pe = r['today_pe']
                    yesterday_pe = r['yesterday_pe']
                else:
                    cik = r[0]
                    today_pe = r[2]
                    yesterday_pe = r[3]
                    
                if today_pe and yesterday_pe and yesterday_pe > 0 and today_pe > 0:
                    ratio = today_pe / yesterday_pe
                    if ratio > 2.0 or ratio < 0.5:
                        anomalies.append({
                            "cik": cik, "ticker": cik, "type": "VALUATION_JUMP",
                            "detail": f"PE changed from {yesterday_pe} to {today_pe} ({ratio:.2f}x)"
                        })

        if anomalies:
            logger.warning(f"Valuation check detected {len(anomalies)} anomalies! Isolating records...")
            with self.db.get_cursor() as cur:
                for anomaly in anomalies:
                    cik = anomaly["cik"]
                    logger.warning(f"Isolating valuation data for CIK {cik} due to {anomaly['type']}")
                    
                    # 1. 가치평가 삭제
                    cur.execute("DELETE FROM us_daily_valuation WHERE cik = %s AND dt = %s", (cik, target_date))
                    
                    # 데이터 이상 유발 사유로 실패 카운팅 및 지속 시 블랙리스트 자동 편입
                    self.blacklist_mgr.record_failure(
                        cik=cik,
                        reason_code="PARSE_ERROR_CRITICAL",
                        detail=f"HealthCheck isolated: {anomaly['type']} - {anomaly['detail']}"
                    )

        return anomalies

    def _save_report(self, report: Dict[str, Any]) -> None:
        """실행 리포트를 logs 폴더에 JSON 파일로 저장합니다."""
        from p3_usdms.config import get_settings
        log_dir = get_settings().LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        
        filename = f"{report['routine']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(log_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=4, ensure_ascii=False)
            logger.info(f"Routine execution report saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write execution report file: {e}")
