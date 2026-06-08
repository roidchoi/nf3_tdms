from typing import List, Dict, Any, Optional
from datetime import datetime
from p3_usdms.repositories.base import BaseRepository

class BlacklistRepo(BaseRepository):
    """
    us_collection_blacklist 테이블에 접근하여 수집 차단 목록을 관리하는 리포지토리 클래스
    """
    def add_blacklist(self, cik: str, reason_code: str, reason_detail: str = None, ticker: str = None) -> None:
        """
        CIK를 블랙리스트에 추가하거나 업데이트하여 수집을 영구/임시 차단합니다.
        is_blocked = TRUE로 강제 전환하며 fail_count를 1 누적합니다.
        """
        cik_padded = str(cik).zfill(10)
        query = """
            INSERT INTO us_collection_blacklist (
                cik, ticker, reason_code, reason_detail, is_blocked, fail_count, last_failed_at, updated_at
            )
            VALUES (%s, %s, %s, %s, TRUE, 1, NOW(), NOW())
            ON CONFLICT (cik) DO UPDATE SET
                ticker = COALESCE(EXCLUDED.ticker, us_collection_blacklist.ticker),
                reason_code = EXCLUDED.reason_code,
                reason_detail = EXCLUDED.reason_detail,
                is_blocked = TRUE,
                fail_count = us_collection_blacklist.fail_count + 1,
                last_failed_at = NOW(),
                updated_at = NOW()
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik_padded, ticker, reason_code, reason_detail))

    def is_blocked(self, cik: str) -> bool:
        """
        해당 CIK가 현재 수집 차단(is_blocked = TRUE) 상태인지 확인합니다.
        """
        cik_padded = str(cik).zfill(10)
        query = "SELECT is_blocked FROM us_collection_blacklist WHERE cik = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (cik_padded,))
            row = cur.fetchone()
            if row:
                return bool(row['is_blocked'])
            return False

    def release_blacklist(self, cik: str, admin_note: str = "System Released") -> None:
        """
        해당 CIK의 차단 상태를 해제(is_blocked = FALSE)하고 실패 횟수를 0으로 리셋합니다.
        """
        cik_padded = str(cik).zfill(10)
        query = """
            UPDATE us_collection_blacklist
            SET is_blocked = FALSE,
                fail_count = 0,
                admin_note = %s,
                last_verified_at = NOW(),
                updated_at = NOW()
            WHERE cik = %s
        """
        with self.get_cursor() as cur:
            cur.execute(query, (admin_note, cik_padded))

    def get_fail_count(self, cik: str) -> int:
        """
        해당 CIK의 누적 실패 횟수(fail_count)를 조회합니다. 존재하지 않으면 0을 반환합니다.
        """
        cik_padded = str(cik).zfill(10)
        query = "SELECT fail_count FROM us_collection_blacklist WHERE cik = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (cik_padded,))
            row = cur.fetchone()
            if row:
                return int(row['fail_count'])
            return 0

    def increment_fail_count(self, cik: str, reason_code: str, ticker: str = None) -> None:
        """
        블랙리스트에 차단 등록(is_blocked=TRUE)은 하지 않은 채로 fail_count만 단순히 증가시키고 기록을 남깁니다.
        (일시적인 에러 및 수집 재시도 유예 시 사용)
        """
        cik_padded = str(cik).zfill(10)
        query = """
            INSERT INTO us_collection_blacklist (
                cik, ticker, reason_code, is_blocked, fail_count, last_failed_at, updated_at
            )
            VALUES (%s, %s, %s, FALSE, 1, NOW(), NOW())
            ON CONFLICT (cik) DO UPDATE SET
                ticker = COALESCE(EXCLUDED.ticker, us_collection_blacklist.ticker),
                reason_code = EXCLUDED.reason_code,
                fail_count = us_collection_blacklist.fail_count + 1,
                last_failed_at = NOW(),
                updated_at = NOW()
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cik_padded, ticker, reason_code))

    def get_auto_release_candidates(self, cool_off_days: int = 7) -> List[Dict[str, Any]]:
        """
        마지막 실패 시각(last_failed_at)으로부터 cool_off_days가 지난 차단(is_blocked=TRUE) 상태인 CIK 목록을 반환합니다.
        """
        query = """
            SELECT cik, ticker, reason_code, fail_count, last_failed_at
            FROM us_collection_blacklist
            WHERE is_blocked = TRUE
              AND last_failed_at <= NOW() - (%s * INTERVAL '1 day')
        """
        with self.get_cursor() as cur:
            cur.execute(query, (cool_off_days,))
            return cur.fetchall()

    def get_blocked_stocks(self) -> List[Dict[str, Any]]:
        """현재 차단 상태(is_blocked = TRUE)인 종목 목록을 반환합니다."""
        query = """
            SELECT cik, ticker, reason_code as reason_cd, reason_detail as detail, is_blocked, fail_count, last_failed_at, updated_at
            FROM us_collection_blacklist
            WHERE is_blocked = TRUE
        """
        with self.get_cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
