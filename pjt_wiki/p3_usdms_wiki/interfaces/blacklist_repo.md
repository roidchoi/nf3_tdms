# BlacklistRepo (blacklist_repo.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-04  
> **물리 경로**: `tdms_core/p3_usdms/repositories/blacklist_repo.py`  
> **상태**: ✅ 완료

---

## 1. 개요
`us_collection_blacklist` 테이블에 대한 데이터 접근(CRUD) 트랜잭션을 처리합니다. 수집 실패 횟수(fail_count) 기록, 특정 CIK의 차단 여부 판별, 차단 해제 및 쿨다운 기한 만료 후보 조회를 담당합니다.

---

## 2. 인터페이스 시그니처

```python
from typing import List, Dict, Any, Optional
from p3_usdms.repositories.base import BaseRepository

class BlacklistRepo(BaseRepository):
    def add_blacklist(self, cik: str, reason_code: str, reason_detail: str = None, ticker: str = None) -> None:
        """
        CIK를 블랙리스트에 추가하거나 강제로 차단 상태(is_blocked = TRUE)로 업데이트합니다.
        ON CONFLICT (cik) DO UPDATE를 수행하며, fail_count를 1 증가시키고 타임스탬프를 갱신합니다.
        
        Args:
            cik (str): 대상 기업 CIK (10자리 패딩 처리됨)
            reason_code (str): 차단 사유 에러 코드 (예: DELISTED, HTTP_404)
            reason_detail (str, optional): 상세 설명 메세지
            ticker (str, optional): 대상 기업 티커
        """

    def is_blocked(self, cik: str) -> bool:
        """
        us_collection_blacklist에서 해당 CIK가 존재하고 is_blocked = TRUE 인지 확인합니다.
        
        Args:
            cik (str): 대상 기업 CIK
        Returns:
            bool: 차단 여부 (True: 차단됨, False: 미차단 또는 기록 없음)
        """

    def release_blacklist(self, cik: str, admin_note: str = "System Released") -> None:
        """
        해당 CIK의 차단 상태를 해제(is_blocked = FALSE)하고, fail_count를 0으로 리셋하며
        차단 해제 사유(release_reason) 및 타임스탬프를 갱신합니다.
        
        Args:
            cik (str): 대상 기업 CIK
            admin_note (str): 차단 해제 비고 기록
        """

    def get_fail_count(self, cik: str) -> int:
        """
        해당 CIK의 누적 실패 횟수(fail_count)를 조회합니다. 존재하지 않으면 0을 반환합니다.
        
        Args:
            cik (str): 대상 기업 CIK
        Returns:
            int: 누적 실패 횟수
        """

    def increment_fail_count(self, cik: str, reason_code: str, ticker: str = None) -> None:
        """
        블랙리스트 차단 등록(is_blocked = TRUE)은 하지 않은 채로 fail_count만 단순히 1 증가시키고 기록을 남깁니다.
        (일시적인 에러 및 수집 재시도 유예 시 사용)
        
        Args:
            cik (str): 대상 기업 CIK
            reason_code (str): 일시적 실패 에러 코드 (예: RATE_LIMIT, TIMEOUT)
            ticker (str, optional): 대상 기업 티커
        """

    def get_auto_release_candidates(self, cool_off_days: int = 7) -> List[Dict[str, Any]]:
        """
        마지막 실패 시각(last_failed_at)으로부터 cool_off_days가 경과하고,
        현재 차단 상태(is_blocked = TRUE)인 CIK 목록을 조회합니다.
        
        Args:
            cool_off_days (int): 차단 유예 일수 (기본값: 7)
        Returns:
            List[Dict[str, Any]]: 쿨다운이 만료된 차단 대상 CIK 리스트 (cik, ticker, reason_code, fail_count, last_failed_at 포함)
        """
```

---

## 3. 관련 테이블 스키마 (`us_collection_blacklist`)
```sql
CREATE TABLE IF NOT EXISTS us_collection_blacklist (
    cik VARCHAR(10) PRIMARY KEY,
    ticker VARCHAR(12),
    reason_code VARCHAR(50) NOT NULL,
    reason_detail TEXT,
    is_blocked BOOLEAN DEFAULT FALSE,
    fail_count INT DEFAULT 0,
    last_failed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    released_at TIMESTAMP WITH TIME ZONE,
    release_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_blacklist_blocked ON us_collection_blacklist(is_blocked) WHERE is_blocked = TRUE;
```
