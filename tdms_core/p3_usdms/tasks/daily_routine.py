import os
import json
import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.blacklist_repo import BlacklistRepo
from p3_usdms.utils.blacklist_manager import BlacklistManager
from p3_usdms.collectors.master_sync import MasterSync
from p3_usdms.collectors.market_data_loader import MarketDataLoader
from p3_usdms.collectors.financial_parser import FinancialParser
from p3_usdms.engines.metric_calculator import MetricCalculator
from p3_usdms.engines.valuation_calculator import ValuationCalculator
from p1_shared.utils.date_utils import is_us_trading_day

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

class DailyRoutine:
    def __init__(self, master_repo=None, blacklist_repo=None, blacklist_mgr=None):
        self.master_repo = master_repo or MasterRepo()
        self.blacklist_repo = blacklist_repo or BlacklistRepo()
        self.blacklist_mgr = blacklist_mgr or BlacklistManager(repo=self.blacklist_repo)
        
        # 외부 수집 모듈 지연 초기화
        self.master = MasterSync()
        self.market_loader = MarketDataLoader()
        self.fin_parser = FinancialParser()
        self.metric_calc = MetricCalculator()
        self.val_calc = ValuationCalculator()
        
        # DB connection 참조 (Health Check 등 직접 쿼리용)
        self.db = self.master_repo

    def sync_trading_calendar(self, limit_date: date) -> None:
        """
        `usdms_db`의 `trading_calendar` 테이블을 자동 동기화합니다.
        - `trading_calendar`에서 MAX(dt)를 조회합니다.
        - MAX(dt) 다음 날부터 limit_date까지 루프를 돌며 `is_us_trading_day(curr_d)`로 opnd_yn ('Y'/'N')을 매칭하여 인서트합니다.
        """
        max_dt = None
        with self.db.get_cursor() as cur:
            cur.execute("SELECT MAX(dt) as max_dt FROM trading_calendar")
            row = cur.fetchone()
            if row:
                if isinstance(row, dict):
                    max_dt = row.get("max_dt") or row.get("max")
                else:
                    max_dt = row[0]
                    
        if not max_dt:
            start_date = limit_date - timedelta(days=365)
        else:
            if isinstance(max_dt, datetime):
                max_dt = max_dt.date()
            start_date = max_dt + timedelta(days=1)
            
        if start_date > limit_date:
            logger.info(f"Trading calendar is up to date. max_dt: {max_dt}, limit_date: {limit_date}")
            return
            
        logger.info(f"Syncing trading calendar from {start_date} to {limit_date}...")
        
        with self.db.get_cursor() as cur:
            current = start_date
            while current <= limit_date:
                opnd_yn = 'Y' if is_us_trading_day(current) else 'N'
                query = """
                    INSERT INTO trading_calendar (dt, opnd_yn, created_at, updated_at)
                    VALUES (%s, %s, NOW(), NOW())
                    ON CONFLICT (dt) DO UPDATE SET opnd_yn = EXCLUDED.opnd_yn, updated_at = NOW()
                """
                cur.execute(query, (current, opnd_yn))
                current += timedelta(days=1)

    async def run(self, test_limit: int = None, target_date: date = None, target_group: int = None) -> Dict[str, Any]:
        """
        Step 1~5 일일 자동화 파이프라인 전체를 오케스트레이션합니다.
        각 스텝은 예외 차단을 통해 부분 성공(Partial Success)을 보장합니다.
        """
        # 0. 동적 FileHandler 바인딩 (실시간 웹소켓 로그 스트리밍용)
        import sys
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        # 테스트 환경인 경우 테스트 로그 파일로 경로 격리하여 프로덕션 로그 오염 방지
        is_test = os.environ.get("TDMS_ENV") == "test" or "pytest" in sys.modules
        log_filename = "daily_routine_test.log" if is_test else "daily_routine.log"
        log_file_path = os.path.join(logs_dir, log_filename)
        
        file_handler = None
        root_logger = logging.getLogger()
        
        # 기존 동일한 파일에 연결된 FileHandler가 있는지 검사하여 재사용 또는 생성
        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename == os.path.abspath(log_file_path):
                file_handler = handler
                break
                
        if not file_handler:
            file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        try:
            if target_date is None:
                # KST 수집 당일 기준 전날을 수집 대상일로 삼음 (미국 기준 전날 영업일 마감)
                target_date = datetime.now(KST).date() - timedelta(days=1)
                
            # 0. trading_calendar 테이블 자동 갱신 동기화 실행
            try:
                await asyncio.to_thread(self.sync_trading_calendar, limit_date=target_date)
            except Exception as e:
                logger.error(f"Failed to sync trading calendar up to {target_date}: {e}", exc_info=True)
     
            # 1. target_date가 미국 영업일인지 여부와 상관없이 수/토 정기 수집 파이프라인 전체를 기동합니다.
            # (단, trading_calendar 동기화를 통해 휴장 여부는 DB에 계속 누적 갱신됩니다.)
     
            start_time = datetime.now(KST)
            report = {
                "routine": "daily_routine",
                "start_time": start_time.isoformat(),
                "status": "RUNNING",
                "steps": []
            }

            # ----------------------------------------------------
            # Step 1: MasterSync (SEC Tickers)
            # ----------------------------------------------------
            step_start = datetime.now(KST)
            logger.info("[Step 1] Executing SEC Master Sync...")
            try:
                # sync_daily는 비동기 함수임
                res = await self.master.sync_daily(limit=test_limit)
                report["steps"].append({
                    "step": "Master Sync",
                    "status": "SUCCESS",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "details": res
                })
            except Exception as e:
                logger.error(f"[Step 1] SEC Master Sync failed: {e}", exc_info=True)
                report["steps"].append({
                    "step": "Master Sync",
                    "status": "FAILED",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "error": str(e)
                })

            # 수집 대상 CIK 추출 및 블랙리스트 제외 (가격 수집용 전체 대상)
            all_targets = self.master_repo.get_collect_targets()
            all_ciks = [t['cik'] for t in all_targets if not self.blacklist_mgr.is_blacklisted(t['cik'])]
            if test_limit:
                all_ciks_for_price = all_ciks[:test_limit]
            else:
                all_ciks_for_price = all_ciks

            # 재무정보(SEC Filing) 및 가치평가 연산 대상에만 2분할 MOD 2 샤딩 적용
            if target_group is None:
                current_weekday = datetime.now(KST).weekday()
                if current_weekday in (2, 3, 4):
                    target_group = 0
                else:
                    target_group = 1

            import hashlib
            if target_group in (0, 1):
                sharded_targets = []
                for t in all_targets:
                    cik_str = t['cik']
                    h_val = int(hashlib.md5(cik_str.encode()).hexdigest(), 16) % 2
                    if h_val == target_group:
                        sharded_targets.append(t)
                logger.info(f"Target Group Filter (Financial & Calculators): Selected Group {target_group} ({len(sharded_targets)}/{len(all_targets)} targets).")
                sharded_ciks = [t['cik'] for t in sharded_targets if not self.blacklist_mgr.is_blacklisted(t['cik'])]
            else:
                logger.info(f"Target Group Filter (Financial & Calculators): Disabled (target_group={target_group}). Processing all {len(all_targets)} targets.")
                sharded_ciks = all_ciks.copy()

            if test_limit:
                sharded_ciks = sharded_ciks[:test_limit]

            # DB 내 최신 가격 적재일 기준 동적 lookback_days 계산
            db_max_date = None
            try:
                with self.db.get_cursor() as cur:
                    cur.execute("SELECT MAX(dt) as d FROM us_daily_price")
                    row = cur.fetchone()
                    db_max_date = row['d'] if row and row['d'] else None
            except Exception as e:
                logger.warning(f"Failed to query max price date: {e}")

            if db_max_date:
                if isinstance(db_max_date, datetime):
                    db_max_date = db_max_date.date()
                days_diff = (target_date - db_max_date).days
                lookback_days = max(10, days_diff + 2)
                logger.info(f"Dynamic lookback calculated: {lookback_days} days (db_max_date: {db_max_date})")
            else:
                lookback_days = 30
                logger.info(f"No max price date found. Using default lookback: {lookback_days} days")

            lookback_start_date = (target_date - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

            # ----------------------------------------------------
            # Step 2: Market Data Update (OHLCV & Factors)
            # ----------------------------------------------------
            # ----------------------------------------------------
            # Step 2: Market Data Update (OHLCV & Factors) - 가격 정보는 전체 수집
            # ----------------------------------------------------
            step_start = datetime.now(KST)
            logger.info(f"[Step 2] Fetching Market Prices and Factors for {len(all_ciks_for_price)} companies (Lookback: {lookback_days} days)...")
            try:
                await asyncio.to_thread(self.market_loader.collect_daily_updates, lookback_days=lookback_days, ciks=all_ciks_for_price)
                report["steps"].append({
                    "step": "Market Data Loader",
                    "status": "SUCCESS",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "details": {"processed_count": len(all_ciks_for_price), "lookback_days": lookback_days}
                })
            except Exception as e:
                logger.error(f"[Step 2] Market Data Loader failed: {e}", exc_info=True)
                report["steps"].append({
                    "step": "Market Data Loader",
                    "status": "FAILED",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "error": str(e)
                })

            # ----------------------------------------------------
            # Step 3: SEC Filing Index & Financial Parser - 재무정보는 분할 수집
            # ----------------------------------------------------
            step_start = datetime.now(KST)
            logger.info(f"[Step 3] SEC Filing Financial Parsing for {len(sharded_ciks)} companies...")
            try:
                # financial_parser.run은 동기 함수임
                await asyncio.to_thread(self.fin_parser.run, ciks=sharded_ciks)
                report["steps"].append({
                    "step": "Financial Parser",
                    "status": "SUCCESS",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "details": {"processed_count": len(sharded_ciks)}
                })
            except Exception as e:
                logger.error(f"[Step 3] Financial Parser failed: {e}", exc_info=True)
                report["steps"].append({
                    "step": "Financial Parser",
                    "status": "FAILED",
                    "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                    "error": str(e)
                })

            # ----------------------------------------------------
            # Step 3.5 & 4: Metric & Valuation Calculators - 가치평가는 분할 적용
            # ----------------------------------------------------
            step_start = datetime.now(KST)
            logger.info(f"[Step 3.5 & 4] Calculating Financial Metrics & Valuations for {len(sharded_ciks)} companies...")
            try:
                # CIK별 최신 가치평가 날짜 사전 벌크 적재 캐시 구축 (1회 쿼리)
                latest_val_dates_cache = {}
                if self.val_calc and hasattr(self.val_calc.repo, "get_all_latest_valuation_dates"):
                    try:
                        latest_val_dates_cache = self.val_calc.repo.get_all_latest_valuation_dates(sharded_ciks)
                        logger.info(f"Loaded {len(latest_val_dates_cache)} latest valuation dates into memory cache.")
                    except Exception as cache_err:
                        logger.warning(f"Failed to load latest valuation dates bulk cache: {cache_err}")

                # 일일 루틴 시에는 self_healing=False로 설정하여 매번 갭 탐색 SQL(3,000회) 방지
                calc_success, calc_fail = await asyncio.to_thread(
                    self._run_calculations, 
                    sharded_ciks, 
                    latest_val_dates_cache=latest_val_dates_cache, 
                    self_healing=False
                )
            except Exception as e:
                logger.error(f"[Step 3.5 & 4] Calculation loop failed: {e}", exc_info=True)
                calc_success, calc_fail = 0, len(sharded_ciks)

            report["steps"].append({
                "step": "Metric & Valuation Calculation",
                "status": "SUCCESS" if calc_fail == 0 else "PARTIAL_SUCCESS",
                "duration_seconds": (datetime.now(KST) - step_start).total_seconds(),
                "details": {
                    "total_target": len(sharded_ciks),
                    "success_count": calc_success,
                    "fail_count": calc_fail
                }
            })

            # ----------------------------------------------------
            # Step 5: Health Check & Isolation (Anomalies)
            # ----------------------------------------------------
            step_start = datetime.now(KST)
            logger.info("[Step 5] Performing Ingestion Health Checks & Data Isolation...")
            try:
                anomalies = await asyncio.to_thread(self._detect_anomalies_and_quarantine, target_date)
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

            # 최종 리포트 마감 및 영속화
            end_time = datetime.now(KST)
            report["end_time"] = end_time.isoformat()
            report["total_duration_seconds"] = (end_time - start_time).total_seconds()
            
            has_failed_step = any(s["status"] == "FAILED" for s in report["steps"])
            report["status"] = "FAILED" if has_failed_step else "SUCCESS"
            
            self._save_report(report)
            logger.info(f"Daily routine completed with status: {report['status']}")
            return report
        finally:
            if file_handler:
                file_handler.close()
                root_logger.removeHandler(file_handler)

    def _run_calculations(self, ciks: List[str], latest_val_dates_cache: Dict[str, Any] = None, self_healing: bool = False) -> tuple[int, int]:
        """CIK별 지표 및 밸류에이션 동기 연산 루프"""
        import time
        calc_success = 0
        calc_fail = 0
        total = len(ciks)
        loop_start_time = time.time()
        
        for idx, cik in enumerate(ciks):
            # 50개 종목 연산마다 또는 마지막 종목일 때 진행 정보 로깅
            if idx % 50 == 0 or idx == total - 1:
                elapsed = time.time() - loop_start_time
                if elapsed == 0:
                    elapsed = 1e-6
                items_per_sec = (idx + 1) / elapsed
                remaining = total - (idx + 1)
                eta_seconds = remaining / items_per_sec if items_per_sec > 0 else 0
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                progress_pct = (idx + 1) / total * 100.0
                
                logger.info(
                    f"[Metric & Valuation Calculation] Progress: {progress_pct:.1f}% ({idx+1}/{total}) | "
                    f"Speed: {items_per_sec:.1f} it/s | Elapsed: {elapsed:.0f}s | ETA: {eta_str} | "
                    f"Current CIK: {cik}"
                )

            try:
                self.metric_calc.calculate_and_save(cik, rebuild=False)
                self.val_calc.calculate_and_save(
                    cik, 
                    rebuild=False, 
                    latest_val_dates_cache=latest_val_dates_cache, 
                    self_healing=self_healing
                )
                calc_success += 1
            except Exception as e:
                logger.error(f"Calculator failed for CIK: {cik}. Error: {e}")
                calc_fail += 1
                self.blacklist_mgr.record_failure(
                    cik=cik,
                    reason_code="PARSE_ERROR_CRITICAL",
                    detail=f"Metric/Valuation calculation failed: {str(e)}"
                )
        return calc_success, calc_fail

    def run_weekly_backfill(self) -> Dict[str, Any]:
        """
        주간 정기 자동화 파이프라인.
        1. 쿨다운이 지난 블랙리스트 차단 대상 자동 해제
        2. 메타데이터 미보강 종목 대상 yfinance 보강 기동 (MasterEnricher)
        3. 신규 보강 메타데이터 및 가격 정보 기준 Dynamic Targeting (apply_targeting_rules) 실행
        """
        logger.info("Starting Weekly Backfill and Maintenance routine...")
        start_time = datetime.now()
        
        # 1. 쿨다운 7일 경과 블랙리스트 자동 해제
        released = self.blacklist_mgr.auto_release_expired_blocks(cool_off_days=7)
        
        # 2. 메타데이터 Enricher 기동 (최대 50개)
        # run_enrichment는 async이므로 동기 래퍼 내에서 루프 가동
        from p3_usdms.collectors.master_enricher import MasterEnricher
        enricher = MasterEnricher(master_repo=self.master_repo, blacklist_mgr=self.blacklist_mgr)
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(enricher.run_enrichment(limit=50))
            enriched = 0
            logger.info("Weekly Backfill: Scheduled MasterEnricher task in running loop.")
        except RuntimeError:
            enriched = asyncio.run(enricher.run_enrichment(limit=50))
            
        # 3. Dynamic Targeting 적용
        target_stats = self.master_repo.apply_targeting_rules()
        
        # 4. Valuation 갭 복구 (Self-healing=True)
        targets = self.master_repo.get_collect_targets()
        ciks = [t['cik'] for t in targets if not self.blacklist_mgr.is_blacklisted(t['cik'])]
        logger.info(f"Weekly Backfill: Running Valuation self-healing (gap scanning) for {len(ciks)} companies...")
        calc_success, calc_fail = self._run_calculations(ciks, self_healing=True)
        
        report = {
            "routine": "weekly_backfill",
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "status": "SUCCESS",
            "details": {
                "auto_released_blacklist_count": released,
                "enriched_metadata_count": enriched,
                "targeting_rules_applied": target_stats,
                "self_healing_valuation": {"success": calc_success, "fail": calc_fail}
            }
        }
        self._save_report(report)
        logger.info(f"Weekly Backfill routine completed successfully: {report['details']}")
        return report

    def _detect_anomalies_and_quarantine(self, target_date: date) -> List[Dict[str, Any]]:
        """
        수집 기준일(target_date)에 적재된 가격 및 가치평가 데이터를 분석하여 오염 데이터를 식별하고 격리(삭제/롤백)합니다.
        """
        anomalies = []

        # 1. 시세 데이터 오염 검사 (target_date vs target_date 전일 가격 merge 비교)
        # PRICE_SPIKE (50% 초과 변동)
        price_query = """
            SELECT t.cik, t.latest_ticker, p_today.cls_prc as today_prc, p_yesterday.cls_prc as yesterday_prc
            FROM us_ticker_master t
            JOIN us_daily_price p_today ON t.cik = p_today.cik AND p_today.dt = %s
            JOIN us_daily_price p_yesterday ON t.cik = p_yesterday.cik AND p_yesterday.dt = %s - INTERVAL '1 day'
        """
        
        # 2. Valuation 데이터 오염 검사 (target_date vs target_date 전일 PE 비교)
        # VALUATION_JUMP (2배 초과 혹은 0.5배 미만)
        val_query = """
            SELECT t.cik, t.latest_ticker, v_today.pe as today_pe, v_yesterday.pe as yesterday_pe
            FROM us_ticker_master t
            JOIN us_daily_valuation v_today ON t.cik = v_today.cik AND v_today.dt = %s
            JOIN us_daily_valuation v_yesterday ON t.cik = v_yesterday.cik AND v_yesterday.dt = %s - INTERVAL '1 day'
        """

        with self.db.get_cursor() as cur:
            # 1. 가격 검사
            cur.execute(price_query, (target_date, target_date))
            price_rows = cur.fetchall()
            for r in price_rows:
                if isinstance(r, dict):
                    cik = r['cik']
                    today_prc = r['today_prc']
                    yesterday_prc = r['yesterday_prc']
                else:
                    cik = r[0]
                    today_prc = r[2]
                    yesterday_prc = r[3]
                
                # 시세가 0원 이하인 비정상 오염
                if today_prc <= 0:
                    anomalies.append({
                        "cik": cik, "ticker": cik, "type": "ZERO_OR_NEGATIVE_PRICE",
                        "detail": f"Price is {today_prc} (<= 0)"
                    })
                    continue

                if yesterday_prc > 0:
                    ratio = today_prc / yesterday_prc
                    if ratio > 1.5 or ratio < 0.5:
                        anomalies.append({
                            "cik": cik, "ticker": cik, "type": "PRICE_SPIKE",
                            "detail": f"Price changed from {yesterday_prc} to {today_prc} ({((ratio-1)*100):.1f}%)"
                        })

            # 2. Valuation 검사
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

        # 오염 종목 격리(Quarantine) 수행 - 당일 레코드를 완전히 삭제하여 API 노출 차단
        if anomalies:
            logger.warning(f"Ingestion health check detected {len(anomalies)} anomalies! Isolating records...")
            with self.db.get_cursor() as cur:
                for anomaly in anomalies:
                    cik = anomaly["cik"]
                    logger.warning(f"Isolating data for CIK {cik} due to {anomaly['type']}")
                    
                    # 1. 시세 삭제
                    cur.execute("DELETE FROM us_daily_price WHERE cik = %s AND dt = %s", (cik, target_date))
                    # 2. 가치평가 삭제
                    cur.execute("DELETE FROM us_daily_valuation WHERE cik = %s AND dt = %s", (cik, target_date))
                    
                    # 데이터 이상 유발 사유로 실패 카운팅 및 지속 시 블랙리스트 자동 편입
                    self.blacklist_mgr.record_failure(
                        cik=cik,
                        reason_code="PARSE_ERROR_CRITICAL",
                        detail=f"HealthCheck isolated: {anomaly['type']} - {anomaly['detail']}"
                    )

        return anomalies

        return anomalies

    def _save_report(self, report: Dict[str, Any]) -> None:
        """실행 리포트를 logs 폴더에 JSON 파일로 저장합니다."""
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        
        filename = f"{report['routine']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(log_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=4, ensure_ascii=False)
            logger.info(f"Routine execution report saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write execution report file: {e}")
