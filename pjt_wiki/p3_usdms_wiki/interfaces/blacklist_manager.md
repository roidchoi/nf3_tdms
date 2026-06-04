# BlacklistManager (blacklist_manager.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-04  
> **물리 경로**: `tdms_core/p3_usdms/utils/blacklist_manager.py`  
> **상태**: ✅ 완료

---

## 1. 개요
`BlacklistRepo`를 래핑하여 수집 실패 에러에 대한 비즈니스 정책을 조율합니다. 에러 메시지를 기준으로 일시적 오류와 영구적 오류를 분리하고, 실패 누적 임계치 도달 시의 차단 승격(Promotion) 및 기한 만료된 차단 종목의 자동 해제(Auto-Release) 정책을 통제합니다.

---

## 2. 인터페이스 시그니처

```python
from p3_usdms.repositories.blacklist_repo import BlacklistRepo

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
        """
        BlacklistManager를 초기화합니다.
        
        Args:
            repo (BlacklistRepo, optional): 사용할 레포지토리 인스턴스. 미지정 시 신규 생성.
        """

    def record_failure(self, cik: str, reason_code: str, detail: str = None, ticker: str = None, threshold: int = 5) -> None:
        """
        수집 실패 시 에러 코드에 맞춰 처리 방식을 분기하여 기록합니다.
        
        - 영구적 오류 (PERMANENT_ERRORS 내에 존재하는 에러 코드):
          즉시 `repo.add_blacklist`를 호출하여 CIK를 차단 상태(is_blocked=TRUE)로 전환합니다.
          
        - 일시적 오류 (기타 또는 TRANSIENT_ERRORS 내에 존재하는 에러 코드):
          `repo.increment_fail_count`를 호출하여 누적 실패 횟수만 1 증가시킵니다.
          증가된 실패 횟수가 `threshold` (기본값: 5회) 이상이 되는 순간, `repo.add_blacklist`를 실행해 영구 차단으로 승격시킵니다.
        
        Args:
            cik (str): 대상 CIK
            reason_code (str): 에러 코드 문자열
            detail (str, optional): 예외 상세 메시지
            ticker (str, optional): 대상 티커
            threshold (int): 차단 승격 실패 임계치 (기본값: 5)
        """

    def is_blacklisted(self, cik: str) -> bool:
        """
        해당 CIK가 현재 수집 차단(is_blocked = TRUE) 상태인지 여부를 판별합니다.
        
        Args:
            cik (str): 대상 CIK
        Returns:
            bool: 차단 여부
        """

    def auto_release_expired_blocks(self, cool_off_days: int = 7) -> int:
        """
        마지막 실패 시각으로부터 쿨다운(cool_off_days, 기본 7일)이 만료된
        차단 상태(is_blocked=TRUE)의 CIK 종목들을 일괄 차단 해제(is_blocked=FALSE, fail_count=0)하고
        해제된 총 종목 개수를 반환합니다.
        
        Args:
            cool_off_days (int): 쿨다운 유예 일수 (기본값: 7)
        Returns:
            int: 자동 해제된 CIK의 수
        """
```
