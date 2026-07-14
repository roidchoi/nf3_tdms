import logging
from p3_usdms.repositories.blacklist_repo import BlacklistRepo

logger = logging.getLogger(__name__)

class BlacklistManager:
    # 일시적인 오류로 재시도가 가능한 코드 목록 (바로 차단하지 않고 누적 카운트만 증가)
    TRANSIENT_ERRORS = {
        "RATE_LIMIT", "HTTP_401", "TIMEOUT", "HTTP_429", "HTTP_500",
        "HTTP_502", "HTTP_503", "HTTP_504", "CONNECTION_ERROR", "TEMPORARY_ERROR"
    }

    # 영구적인 오류로 판단되어 발견 즉시 차단(is_blocked = True)하는 코드 목록
    PERMANENT_ERRORS = {
        "DELISTED", "HTTP_404", "PARSE_ERROR_CRITICAL", "NO_EXCHANGE", "SEC_403", "NOT_FOUND"
    }

    def __init__(self, repo: BlacklistRepo = None):
        self.repo = repo or BlacklistRepo()

    def record_failure(self, cik: str, reason_code: str, detail: str = None, ticker: str = None, threshold: int = 5) -> None:
        """
        수집 실패 시 발생한 에러 코드에 맞춰 처리 방식을 분기합니다.
        - 일시적 오류: fail_count만 증가시키고, 누적 횟수가 threshold에 도달하면 영구 차단으로 승격시킵니다.
        - 영구적 오류: 즉시 add_blacklist를 호출하여 is_blocked = TRUE로 차단합니다.
        """
        reason_upper = reason_code.upper()

        if reason_upper in self.PERMANENT_ERRORS:
            logger.warning(f"[{cik}] Permanent collection failure detected: {reason_code}. Blocking immediately.")
            self.repo.add_blacklist(cik, reason_code, detail, ticker)
        else:
            # 기본값은 일시적 오류로 간주하여 점진적 카운팅
            self.repo.increment_fail_count(cik, reason_code, ticker)
            current_fails = self.repo.get_fail_count(cik)
            logger.info(f"[{cik}] Transient failure recorded: {reason_code}. Fail count: {current_fails}/{threshold}")
            
            if current_fails >= threshold:
                promote_detail = f"Promoted to block. Accumulated failures reached threshold ({threshold}). Last error: {detail}"
                logger.warning(f"[{cik}] Fail count threshold reached. Promoting to blocked blacklist.")
                self.repo.add_blacklist(cik, reason_code, promote_detail, ticker)

    def is_blacklisted(self, cik: str) -> bool:
        """해당 CIK가 현재 수집 차단 상태인지 여부를 판단합니다."""
        return self.repo.is_blocked(cik)

    def auto_release_expired_blocks(self, cool_off_days: int = 7) -> int:
        """
        차단 유예기간이 경과한 블랙리스트 종목들의 차단을 자동으로 해제하고,
        해제된 종목의 총 개수를 반환합니다. 누적 재차단 횟수를 해제 시 보존합니다.
        """
        candidates = self.repo.get_auto_release_candidates(cool_off_days)
        released_count = 0
        for cand in candidates:
            cik = cand['cik']
            ticker = cand.get('ticker')
            re_count = cand.get('re_blocked_count', 0)
            logger.info(f"Auto-releasing blacklisted CIK: {cik} (ticker: {ticker}) [re-block count: {re_count}] after cool-off.")
            self.repo.release_blacklist(
                cik, 
                admin_note=f"Auto-released by system (re-block count: {re_count})", 
                reset_counters=False
            )
            released_count += 1
        return released_count
