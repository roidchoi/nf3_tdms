import asyncio
import logging
import yfinance as yf
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.utils.blacklist_manager import BlacklistManager

logger = logging.getLogger(__name__)

class MasterEnricher:
    def __init__(self, master_repo: MasterRepo = None, blacklist_mgr: BlacklistManager = None):
        self.master_repo = master_repo or MasterRepo()
        self.blacklist_mgr = blacklist_mgr or BlacklistManager()

    async def run_enrichment(self, limit: int = 50) -> int:
        """
        메타데이터가 없는 활성 종목을 조회하여 yfinance를 통해 country, sector, industry 등을 보강합니다.
        국가가 United States가 아닌 경우 수집 대상(is_collect_target)에서 제외(ADR 필터링)합니다.
        """
        targets = self.master_repo.get_missing_enrichment_targets(limit)
        if not targets:
            logger.info("No master enrichment targets found.")
            return 0

        success_count = 0
        logger.info(f"Starting metadata enrichment for {len(targets)} targets.")

        for target in targets:
            cik = target['cik']
            ticker = target['latest_ticker']
            
            # 이미 블랙리스트 차단된 종목이면 스킵
            if self.blacklist_mgr.is_blacklisted(cik):
                logger.debug(f"[{ticker}] Already blacklisted. Skipping enrichment.")
                continue

            try:
                logger.debug(f"[{ticker}] Fetching yfinance info...")
                
                # yfinance API 호출 (블로킹 함수이므로 asyncio run_in_executor 등으로 감싸거나, 
                # 여기서는 E2E 루틴에서 간단하게 호출하고 sleep을 줌)
                # Ticker info 호출은 IO-bound이므로 스레드 실행이 좋으나, 기본적으로 yfinance 동기 연동을 그대로 따름
                ticker_obj = yf.Ticker(ticker)
                info = ticker_obj.info
                
                if not info or not isinstance(info, dict):
                    raise ValueError("Empty or invalid yfinance info object returned")

                country = info.get("country")
                sector = info.get("sector")
                industry = info.get("industry")
                quote_type = info.get("quoteType")

                # 데이터가 완전 비어있어 보완이 불가능한 경우 -> Unknown 강제 설정하여 무한 재검색 차단
                if not country:
                    country = "Unknown"
                if not sector:
                    sector = "Unknown"
                if not industry:
                    industry = "Unknown"

                # ADR 필터링 규칙: 국가가 United States가 아닌 경우 수집 대상에서 제외
                # (is_collect_target = FALSE)
                is_collect_target = (country.strip().lower() == "united states")

                # DB 업데이트
                self.master_repo.update_metadata(
                    cik,
                    country,
                    sector,
                    industry,
                    is_collect_target
                )
                
                logger.info(f"[{ticker}] Enriched country: {country}, collect_target: {is_collect_target}")
                success_count += 1

            except Exception as e:
                err_msg = str(e)
                logger.error(f"[{ticker}] Enrichment failed for CIK: {cik}. Error: {err_msg}")
                
                # 오류 원인 분류
                reason_code = "UNKNOWN_ERROR"
                if "429" in err_msg or "too many requests" in err_msg.lower():
                    reason_code = "RATE_LIMIT"
                elif "401" in err_msg or "unauthorized" in err_msg.lower():
                    reason_code = "HTTP_401"
                elif "timeout" in err_msg.lower():
                    reason_code = "TIMEOUT"
                elif "404" in err_msg or "not found" in err_msg.lower():
                    reason_code = "HTTP_404"
                elif "delisted" in err_msg.lower():
                    reason_code = "DELISTED"

                # 블랙리스트 매니저를 통한 예외 제어 및 백오프 누적
                self.blacklist_mgr.record_failure(
                    cik,
                    reason_code,
                    detail=err_msg,
                    ticker=ticker
                )

                # yfinance API 404 Not Found 등으로 정보 조회가 완전히 실패한 경우,
                # 매일 반복 조회를 시도하여 Rate Limit이 가중되는 현상을 막기 위해
                # DB 메타데이터를 'Unknown'으로 덮어씌워 수집 대상에서 일시 제외합니다.
                if reason_code in ["HTTP_404", "DELISTED"]:
                    try:
                        self.master_repo.update_metadata(
                            cik=cik,
                            country="Unknown",
                            sector="Unknown",
                            industry="Unknown",
                            is_collect_target=False
                        )
                    except Exception as db_err:
                        logger.error(f"[{ticker}] Failed to write Unknown fallback to DB: {db_err}")

            # API 밴 방지를 위한 Cooldown Sleep
            await asyncio.sleep(1.0)

        return success_count
