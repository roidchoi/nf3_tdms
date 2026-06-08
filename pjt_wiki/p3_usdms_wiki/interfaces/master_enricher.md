# MasterEnricher (master_enricher.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-04  
> **물리 경로**: `tdms_core/p3_usdms/collectors/master_enricher.py`  
> **상태**: ✅ 완료

---

## 1. 개요
`us_ticker_master` 테이블에 보강 데이터가 누락된(Active 상태이면서 `country IS NULL` 인) 종목을 조회하여 yfinance API를 연동해 국가(country), 섹터(sector), 산업(industry) 메타데이터를 일괄 보강합니다. 비-미국계 ADR 종목을 감지해 수집 타겟에서 배제하고, API 호출 오류를 분류하여 블랙리스트 매니저와 연동하는 역할을 수행합니다.

---

## 2. 인터페이스 시그니처

```python
import asyncio
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.utils.blacklist_manager import BlacklistManager

class MasterEnricher:
    def __init__(self, master_repo: MasterRepo = None, blacklist_mgr: BlacklistManager = None):
        """
        MasterEnricher를 초기화합니다.
        
        Args:
            master_repo (MasterRepo, optional): DB 마스터 레포지토리
            blacklist_mgr (BlacklistManager, optional): 블랙리스트 매니저
        """

    async def run_enrichment(self, limit: int = 50) -> int:
        """
        메타데이터 보강이 필요한 종목을 최대 limit개 가져와 yfinance API를 조회하고 DB를 갱신합니다.
        
        [비즈니스 규칙]
        1. 이미 수집 블랙리스트에 차단된 CIK인 경우 조회를 건너뜁니다.
        2. yfinance Ticker info의 country가 "United States"가 아닌 경우(ADR 종목 등)는 `is_collect_target = FALSE` 로 설정하여 수집 대상에서 제외합니다.
        3. info 데이터의 일부 속성이 유실된 경우 무한 루프 재조회를 차단하기 위해 "Unknown" 값으로 DB를 채웁니다.
        4. yfinance API 연동 중 예외 발생 시 에러 메시지 분석을 통해 원인을 세분화합니다:
           - "429" 또는 "too many requests" -> RATE_LIMIT
           - "401" 또는 "unauthorized" -> HTTP_401
           - "timeout" -> TIMEOUT
           - "404" 또는 "not found" -> HTTP_404 (즉시 target = False 및 Unknown 처리 후 즉시 차단)
           - "delisted" -> DELISTED (즉시 target = False 및 Unknown 처리 후 즉시 차단)
           - 그 외 -> UNKNOWN_ERROR
           추출된 reason_code를 기반으로 `blacklist_mgr.record_failure`를 호출합니다.
        5. yfinance API 밴 방지를 위해 호출 루프 내에서 강제적으로 1.0초의 비동기 Cooldown Sleep을 실행합니다.
        
        Args:
            limit (int): 1회 배치 당 최대 보강 시도 종목 수 (기본값: 50)
        Returns:
            int: 보강에 성공하여 DB 갱신이 완료된 종목의 개수
        """
```

---

## 3. 의존 관계
* **`MasterRepo.get_missing_enrichment_targets(limit)`**: 보강이 안 된 활성 마스터 목록 로드.
* **`MasterRepo.update_metadata(cik, country, sector, industry, is_collect_target)`**: 보강 데이터 및 수집 여부 반영.
* **`BlacklistManager.is_blacklisted(cik)`**: 기 차단 여부 필터링.
* **`BlacklistManager.record_failure(cik, reason_code, detail, ticker)`**: 실패 누적 및 차단 유도.
