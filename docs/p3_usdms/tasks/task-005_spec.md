# Task-005: Blacklist + MasterEnricher + 일일 루틴 전체 자동화

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)
> **PRD 근거**: F-02(메타데이터 보강), F-07(수집 차단 목록 관리), F-13(일일 루틴 전체 자동화), SCHED(자동화 스케줄), API-헬스(`/tasks/{id}/run`)
> **작성일**: 2026-06-03
> **의존 Task**: T-003(SEC XBRL 재무 파싱), T-004(가치평가 및 재무비율)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `tdms_core/p3_usdms/config.py` | ✅ 직접 확인 |
| DbConnectionPool & BaseRepository 시그니처 | `tdms_core/p3_usdms/repositories/base.py` | ✅ 직접 확인 |
| us_ticker_master & us_ticker_history 스키마 | `tdms_core/p1_shared/p1_shared/db/usdms_origin/init.sql` | ✅ 직접 확인 |
| us_collection_blacklist 스키마 | `tdms_core/p1_shared/p1_shared/db/usdms_origin/init.sql` | ✅ 직접 확인 |
| Blacklist & MasterEnricher 기존 로직 | `migration_pjt/usdms_origin/backend/utils/blacklist_manager.py` <br> `migration_pjt/usdms_origin/backend/collectors/master_enricher.py` | ⚠️ 직접 확인 |
| run_daily_routine 기존 파이프라인 | `migration_pjt/usdms_origin/ops/run_daily_routine.py` | ⚠️ 직접 확인 |
| MasterRepo 시그니처 | `tdms_core/p3_usdms/repositories/master_repo.py` | ✅ 직접 확인 |
| AsyncIOScheduler lifespan 연동 | 이 Task에서 최초 설계 | 🆕 신규 |
| BlacklistRepo 설계 | 이 Task에서 최초 설계 | 🆕 신규 |
| /api/admin/tasks/{id}/run 엔드포인트 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

T-005는 미국 시장 데이터 수집 파이프라인의 최종 통합 단계입니다. 
본 Task 완료 후, 시스템은 외부 환경 요인(네트워크 끊김, Rate Limit)에 강건하고, 이상치/오염 데이터를 스스로 걸러내며, 수집 차단 및 스케줄에 맞춰 완전 자동화된 일일 파이프라인으로 동작해야 합니다.

**구현 범위:**
- **IN**:
  - `repositories/blacklist_repo.py` (신규: 블랙리스트 CRUD 구현)
  - `utils/blacklist_manager.py` (비즈니스 로직 래퍼 구현 - 일시적 오류와 영구적 오류 분리)
  - `collectors/master_enricher.py` (yfinance 기반 메타데이터 보완, ADR 차단, 실패 백오프 전략 적용)
  - `tasks/daily_routine.py` (Step 1~5 통합 오케스트레이터, 예외 격리, Step 5 이상치 검출 시 데이터 롤백 격리 기능 탑재)
  - `routers/admin.py` (신규: 태스크 수동 실행 API 및 실행 Lock 메커니즘 제공)
  - `main.py` (APScheduler `AsyncIOScheduler` lifespan 연동)
- **OUT**:
  - Phase 3에서 정의된 REST API 완성(T-006) 및 Auditors 비즈니스 로직 전체 구현(T-007)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/repositories/blacklist_repo.py` — `us_collection_blacklist` 테이블 연동 CRUD
- `tdms_core/p3_usdms/utils/blacklist_manager.py` — 실패 임계치 및 오류 분리 로직 처리 매니저
- `tdms_core/p3_usdms/collectors/master_enricher.py` — yfinance country, sector, industry 배치 업데이트
- `tdms_core/p3_usdms/tasks/daily_routine.py` — 5단계 일일 루틴 및 주간 백필(블랙리스트 재검증) 실행 엔진
- `tdms_core/p3_usdms/routers/admin.py` — `/api/admin/tasks/{id}/run` 수동 실행 엔드포인트
- `tdms_core/p3_usdms/tests/test_blacklist.py` — 블랙리스트 및 자동 릴리즈 테스트
- `tdms_core/p3_usdms/tests/test_master_enricher.py` — Enricher 필터링 및 백오프 테스트
- `tdms_core/p3_usdms/tests/test_daily_routine.py` — 격리/롤백 및 동시성 락 E2E/단위 테스트

### 수정 대상 파일
- `tdms_core/p3_usdms/main.py` — FastAPI lifespan 내 스케줄러 연동 및 `admin_router` 포함
- `tdms_core/p3_usdms/repositories/master_repo.py` — 메타데이터 보강 및 Targeting 조건 업데이트 쿼리 함수 추가

---

## § 3. 핵심 인터페이스

구현 Agent는 아래 인터페이스 규격을 철저히 준수하여 코드를 작성해야 합니다.

### 3.1 `BlacklistRepo` (신규 정의)
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
# 파일 경로: tdms_core/p3_usdms/repositories/blacklist_repo.py
from typing import List, Dict, Any, Optional
from p3_usdms.repositories.base import BaseRepository

class BlacklistRepo(BaseRepository):
    def add_blacklist(self, cik: str, reason_code: str, reason_detail: str = None, ticker: str = None) -> None:
        """
        CIK를 블랙리스트에 추가하거나 업데이트합니다.
        ON CONFLICT (cik) DO UPDATE를 수행하며 is_blocked = TRUE로 설정하고, 
        fail_count를 1 증가시키며 타임스탬프를 갱신합니다.
        """
        ...

    def is_blocked(self, cik: str) -> bool:
        """us_collection_blacklist에서 해당 CIK가 is_blocked = TRUE 상태인지 확인합니다."""
        ...

    def release_blacklist(self, cik: str, admin_note: str = "System Released") -> None:
        """해당 CIK의 차단 상태를 해제(is_blocked = FALSE)합니다."""
        ...

    def increment_fail_count(self, cik: str, reason_code: str, ticker: str = None) -> None:
        """블랙리스트 테이블에서 임계치를 도달하기 전 fail_count만 단순히 증가시키고 기록을 남깁니다."""
        ...

    def get_auto_release_candidates(self, cool_off_days: int = 7) -> List[Dict[str, Any]]:
        """마지막 실패 시간(last_failed_at)으로부터 cool_off_days가 지난 차단(is_blocked=TRUE) 상태인 CIK 목록을 조회합니다."""
        ...
```

### 3.2 `BlacklistManager` (신규 설계)
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
# 파일 경로: tdms_core/p3_usdms/utils/blacklist_manager.py
from p3_usdms.repositories.blacklist_repo import BlacklistRepo

class BlacklistManager:
    def __init__(self, repo: BlacklistRepo = None):
        self.repo = repo or BlacklistRepo()

    def record_failure(self, cik: str, reason_code: str, detail: str = None, ticker: str = None, threshold: int = 5) -> None:
        """
        실패 기록 시 일시적 오류와 영구적 오류를 구분합니다.
        - 일시적 오류(RATE_LIMIT, HTTP_401, TIMEOUT 등): 블랙리스트에 올리지 않고 increment_fail_count만 호출.
        - 영구적 오류(DELISTED, HTTP_404, PARSE_ERROR_CRITICAL 등): add_blacklist를 호출하여 즉시 차단하거나
          fail_count가 threshold에 도달하면 차단(is_blocked = True)으로 전환시킵니다.
        """
        ...

    def is_blacklisted(self, cik: str) -> bool:
        """해당 CIK가 차단 대상인지 판단합니다."""
        ...

    def auto_release_expired_blocks(self, cool_off_days: int = 7) -> int:
        """임계 시간을 경과한 블랙리스트 종목들의 차단을 자동으로 해제하고 해제된 종목 개수를 반환합니다."""
        ...
```

### 3.3 `MasterRepo` 확장 (수정 대상)
```python
# [출처: tdms_core/p3_usdms/repositories/master_repo.py — 이 Task에서 아래 메서드 추가 수정]
from typing import List, Dict, Any

class MasterRepo(BaseRepository):
    # 기존 메서드들 유지 (get_active_tickers 등)

    def get_missing_enrichment_targets(self, limit: int = 50) -> List[Dict[str, Any]]:
        """is_active = TRUE이고 country IS NULL인 보강 대상 종목을 최대 limit개 조회합니다."""
        ...

    def update_metadata(self, cik: str, country: str, sector: str, industry: str, is_collect_target: bool) -> None:
        """단일 종목의 메타데이터 및 수집 대상 지정을 반영합니다."""
        ...

    def bulk_update_metadata(self, updates: List[Dict[str, Any]]) -> None:
        """yfinance 수집된 여러 종목의 메타데이터를 배치 업데이트합니다."""
        ...

    def apply_targeting_rules(
        self, 
        min_market_cap_entry: float = 50000000.0, 
        min_price_entry: float = 1.00,
        min_market_cap_exit: float = 35000000.0,
        min_price_exit: float = 0.80
    ) -> Dict[str, int]:
        """
        Dynamic Targeting Rules를 SQL로 반영합니다.
        - Entry Criteria: 시가총액 >= entry, 가격 >= entry 이면 is_collect_target = TRUE
        - Retention Criteria: 시가총액 < exit, 가격 < exit 이면 is_collect_target = FALSE
        반환값: {"dropped_count": N, "added_count": M}
        """
        ...
```

### 3.4 `MasterEnricher` (신규 설계)
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
# 파일 경로: tdms_core/p3_usdms/collectors/master_enricher.py
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.utils.blacklist_manager import BlacklistManager

class MasterEnricher:
    def __init__(self, master_repo: MasterRepo = None, blacklist_mgr: BlacklistManager = None):
        self.master_repo = master_repo or MasterRepo()
        self.blacklist_mgr = blacklist_mgr or BlacklistManager()

    async def run_enrichment(self, limit: int = 50) -> int:
        """
        Enrichment 실행 루틴.
        1. get_missing_enrichment_targets(limit) 호출.
        2. yfinance를 이용하여 country, sector, industry, quoteType 등을 보강.
        3. country가 'United States'가 아닐 경우 is_collect_target = FALSE로 강제 제외.
        4. yfinance 실패 시 BlacklistManager를 통해 일시적/영구적 에러를 나누어 백오프 및 실패 기록.
           (만약 yfinance가 데이터를 던지지 못하면 country에 'Unknown'을 채워 매일 중복 재시도하는 현상 차단)
        """
        ...
```

### 3.5 `DailyRoutine` (신규 설계)
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
# 파일 경로: tdms_core/p3_usdms/tasks/daily_routine.py
import asyncio
from typing import Dict, Any, List

class DailyRoutine:
    def __init__(self):
        # 도메인 리포지토리 및 콜렉터들을 지연 초기화하여 주입
        ...

    async def run(self, test_limit: int = None) -> Dict[str, Any]:
        """
        Step 1~5 통합 실행 루틴.
        - 각 스텝은 try-except로 완전히 감싸져 독립 구동 (부분 성공 지원)
        - Step 1: MasterSync
        - Step 2: Market Data Update (OHLCV 수집 및 수정계수)
        - Step 3: SEC Filing Index 스캔 및 Financial Parser (Blacklist CIK 스킵)
        - Step 3.5: Metric Calculator (지표 비율 계산)
        - Step 4: Valuation Calculator (가치평가 계산)
        - Step 5: Health Check & Isolation (이상치 탐지 및 격리 롤백)
        - 실행 결과 report JSON 저장 (p1_shared.EnvDetector 또는 config.py에 정의된 logs 폴더에 보관)
        """
        ...

    def run_weekly_backfill(self) -> Dict[str, Any]:
        """주간 백필 및 블랙리스트 유효기간(cool-off 7일)이 경과한 종목 재검증 자동 릴리즈 실행"""
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_blacklist.py
def test_blacklist_manager_records_failure_and_blocks_on_threshold(mocker):
    """
    [목적] BlacklistManager가 실패 횟수를 누적시키고, 임계치에 도달하면 CIK를 차단 상태로 변경하는지 검증.
    [유도] threshold가 3으로 주어졌을 때, 3번째 record_failure가 호출되면 is_blocked=True 상태가 되어야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.is_blocked.return_value = False
    
    # fail_count 상태를 모방하기 위한 state
    fail_counts = {}
    def inc_fail(cik, reason_code, ticker=None):
        fail_counts[cik] = fail_counts.get(cik, 0) + 1
    def add_bl(cik, reason_code, reason_detail=None, ticker=None):
        pass
        
    mock_repo.increment_fail_count.side_effect = inc_fail
    mock_repo.add_blacklist.side_effect = add_bl
    
    from p3_usdms.utils.blacklist_manager import BlacklistManager
    mgr = BlacklistManager(repo=mock_repo)
    
    # 2번의 일시적 오류 발생 기록 (임계치 3)
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    
    mock_repo.increment_fail_count.assert_called()
    assert fail_counts["0000320193"] == 2
    mock_repo.add_blacklist.assert_not_called()
    
    # 3번째 실패 기록 -> add_blacklist가 호출되어 영구 차단으로 전환되어야 함
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    mock_repo.add_blacklist.assert_called_once_with("0000320193", "RATE_LIMIT", mocker.ANY, None)
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_master_enricher.py
import pytest

@pytest.mark.asyncio
async def test_master_enricher_filters_adr_and_excludes_from_collect(mocker):
    """
    [목적] yfinance 조회 결과 국가가 'United States'가 아니면 수집 대상(is_collect_target)에서 제외됨을 검증.
    [유도] yfinance Ticker info.country = 'United Kingdom'인 경우 is_collect_target=False를 update_metadata에 전달해야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_missing_enrichment_targets.return_value = [
        {"cik": "0001000000", "latest_ticker": "BP"}
    ]
    
    # yfinance Mock
    mock_ticker = mocker.Mock()
    mock_ticker.info = {"country": "United Kingdom", "sector": "Energy", "industry": "Oil & Gas", "quoteType": "EQUITY"}
    mocker.patch("yfinance.Ticker", return_value=mock_ticker)
    
    from p3_usdms.collectors.master_enricher import MasterEnricher
    enricher = MasterEnricher(master_repo=mock_repo)
    await enricher.run_enrichment(limit=1)
    
    mock_repo.update_metadata.assert_called_once_with(
        "0001000000", "United Kingdom", "Energy", "Oil & Gas", False
    )
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_daily_routine.py
def test_daily_routine_health_check_isolates_and_rolls_back_anomalies(mocker):
    """
    [목적] Step 5 Health Check 실행 시 가격 이상치가 검증되면 당일 오염 데이터를 격리(삭제 롤백)하는지 검증.
    [유도] PRICE_SPIKE(50% 초과) 감지 시, 해당 CIK의 당일 가격과 가치평가 레코드를 테이블에서 DELETE 처리하는 로직 유도.
    """
    # 헬스체크 메서드 내부에서 가격 이상 종목을 찾기 위해 모킹 데이터 제공
    # 당일 시세 vs 전일 시세 비교
    mock_db = mocker.Mock()
    
    # 50%를 초과하는 변동이 있는 시세 데이터셋 모사
    # CIK 0000320193: 전일 종가 $100 -> 당일 종가 $200 (100% 상승)
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.side_effect = [
        [{"cik": "0000320193", "cls_prc": 200.0}], # 당일 종가
        [{"cik": "0000320193", "cls_prc": 100.0}], # 전일 종가
        [], # Valuation 당일
        []  # Valuation 전일
    ]
    mock_db.get_cursor.return_value.__enter__.return_value = mock_cursor

    from p3_usdms.tasks.daily_routine import DailyRoutine
    routine = DailyRoutine()
    routine.db = mock_db
    
    # Anomaly Detection 및 롤백 실행
    anomalies = routine._detect_anomalies_and_quarantine()
    
    assert len(anomalies) == 1
    assert anomalies[0]["type"] == "PRICE_SPIKE"
    assert anomalies[0]["ticker"] == "0000320193"
    
    # 롤백 SQL 호출 여부 검증 (격리를 위해 당일 데이터 삭제 쿼리가 수행되어야 함)
    # DELETE FROM us_daily_price WHERE cik = '0000320193' AND dt = CURRENT_DATE 등
    delete_called = False
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        if "DELETE FROM US_DAILY_PRICE" in query_str and "0000320193" in str(call[0][1]):
            delete_called = True
            break
    assert delete_called is True
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
# 파일 경로: tdms_core/p3_usdms/tests/test_blacklist.py
def test_blacklist_manager_auto_release_with_zero_expired_records(mocker):
    """
    [목적] 자동 차단 해제 기한이 지난 레코드가 없을 때, 에러 없이 0을 반환하는가 검증.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_auto_release_candidates.return_value = []
    
    from p3_usdms.utils.blacklist_manager import BlacklistManager
    mgr = BlacklistManager(repo=mock_repo)
    released_count = mgr.auto_release_expired_blocks(cool_off_days=7)
    
    assert released_count == 0
    mock_repo.release_blacklist.assert_not_called()
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_master_enricher.py
import pytest

@pytest.mark.asyncio
async def test_master_enricher_handles_rate_limit_without_blacklisting(mocker):
    """
    [목적] yfinance가 HTTP 429(Rate Limit) 등의 일시적인 오류 로그를 기록할 때 블랙리스트 등록을 스킵하고 스킵 상태를 유지하는지 검증.
    [유도] yfinance 로깅 또는 리턴 결과에 'Rate limit' 단어가 들어 있을 때 record_failure에서 CIK를 차단 처리하지 말아야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_missing_enrichment_targets.return_value = [
        {"cik": "0000320193", "latest_ticker": "AAPL"}
    ]
    
    mock_bl = mocker.Mock()
    
    # yfinance 호출 시 Exception (429 Too Many Requests) 발생 모사
    mocker.patch("yfinance.Ticker", side_effect=Exception("HTTP Error 429: Too Many Requests"))
    
    from p3_usdms.collectors.master_enricher import MasterEnricher
    enricher = MasterEnricher(master_repo=mock_repo, blacklist_mgr=mock_bl)
    await enricher.run_enrichment(limit=1)
    
    # blacklisted 처리가 되지 않아야 함 (즉, 영구 차단 add_blacklist가 아닌 일시적 기록만)
    mock_bl.record_failure.assert_called_once_with(
        "0000320193", "RATE_LIMIT", detail=mocker.ANY, ticker="AAPL"
    )
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_daily_routine.py
import pytest

@pytest.mark.asyncio
async def test_daily_routine_continues_on_step_failure(mocker):
    """
    [목적] 특정 Step이 FAILED 되더라도, 예외가 차단되어 다음 수집 Step이 정상 수행되는지 검증.
    [유도] Step 1 실행 시 강제 Exception을 발생시켰을 때, Step 2의 실행 메서드가 여전히 호출되는지 검증.
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    routine = DailyRoutine()
    
    # Step 1 (MasterSync) 강제 실패 설정
    mock_master = mocker.Mock()
    mock_master.sync_daily.side_effect = Exception("SEC Connection Failed")
    routine.master = mock_master
    
    # Step 2 (MarketDataLoader) 호출 확인용
    mock_loader = mocker.Mock()
    routine.market_loader = mock_loader
    
    # 기타 Step 모킹 처리하여 통과
    routine.fin_parser = mocker.Mock()
    routine.verifier = mocker.Mock()
    routine.db = mocker.Mock()
    routine._detect_anomalies_and_quarantine = mocker.Mock(return_value=[])
    routine._save_report = mocker.Mock()
    
    # 실행
    report = await routine.run()
    
    # Step 1은 실패
    step1 = next(s for s in report["steps"] if s["step"] == "Master Sync")
    assert step1["status"] == "FAILED"
    
    # Step 2는 정상적으로 호출 시도되어야 함
    mock_loader.collect_daily_updates.assert_called_once()
```

```python
# [Tier 2 — 격리 통합]
# 파일 경로: tdms_core/p3_usdms/tests/test_daily_routine.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

def test_daily_routine_manual_run_prevents_concurrency_conflict(mocker):
    """
    [목적] 이미 daily_routine이 구동 중일 때, 수동 실행 엔드포인트 `/api/admin/tasks/daily_routine/run`을 추가 요청하면 409 Conflict를 반환하는지 검증.
    [유도] 실행 잠금 장치(Lock) 상태일 때 API 동작 유도.
    """
    from p3_usdms.routers.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router)
    
    # 일일 루틴의 실행 상태를 나타내는 Lock 모킹
    mocker.patch("p3_usdms.routers.admin.is_routine_running", return_value=True)
    
    client = TestClient(app)
    response = client.post("/api/admin/tasks/daily_routine/run")
    
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
# 파일 경로: tdms_core/p3_usdms/tests/test_daily_routine.py
import pytest

@pytest.mark.integration
def test_blacklist_repository_with_real_db(real_pool):
    """
    [목적] 실제 데이터베이스(real_pool)를 기동한 상태에서 BlacklistRepo의 CRUD 연동이 정상적으로 트랜잭션을 통해 영속화되는지 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    from p3_usdms.repositories.blacklist_repo import BlacklistRepo
    repo = BlacklistRepo()
    
    test_cik = "9999912345"
    
    # 1. 초기 상태 해제
    repo.release_blacklist(test_cik, admin_note="Test Init")
    assert repo.is_blocked(test_cik) is False
    
    # 2. 블랙리스트 등록
    repo.add_blacklist(test_cik, "TEST_403", reason_detail="Integration Test Block", ticker="TEST")
    assert repo.is_blocked(test_cik) is True
    
    # 3. 릴리즈 및 확인
    repo.release_blacklist(test_cik, admin_note="Test Release")
    assert repo.is_blocked(test_cik) is False
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_blacklist_manager_add_and_check_blocked` | Tier 2 | 정상 | 실패 횟수 임계치 도달 시 자동 CIK 차단 전환 검증 |
| 2 | `test_master_enricher_filters_adr_and_excludes_from_collect` | Tier 2 | 정상 | yfinance 국가가 US가 아닐 경우 collect_target 강제 제외 |
| 3 | `test_daily_routine_health_check_isolates_and_rolls_back_anomalies` | Tier 2 | 격리 | 이상치(PRICE_SPIKE) 검출 시 당일 오염 데이터 강제 삭제 격리 처리 |
| 4 | `test_blacklist_manager_auto_release_with_zero_expired_records` | Tier 1 | 경계값 | 차단 해제 만료 대상이 없을 때 예외 없이 0 반환하는가 확인 |
| 5 | `test_master_enricher_handles_rate_limit_without_blacklisting` | Tier 2 | 예외 | Rate Limit(429) 등 일시적 에러는 차단하지 않고 유예하는가 확인 |
| 6 | `test_daily_routine_continues_on_step_failure` | Tier 2 | 예외 | 특정 수집 스텝 에러 시에도 파이프라인 전체가 깨지지 않고 지속 동작함 |
| 7 | `test_daily_routine_manual_run_prevents_concurrency_conflict` | Tier 2 | 예외 | 중복 루틴 강제 실행 호출 시 Lock 감지하여 409 리턴 제어 |
| 8 | `test_blacklist_repository_with_real_db` | Tier 3 | 실제 통합 | 실 DB 컨테이너 연동 상태에서 Blacklist CRUD 트랜잭션 검증 |

**총 8개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.

- **기술 스택**: Python 3.12, fastapi, APScheduler, yfinance, pandas, psycopg2-binary
- **환경 변수**:
  - `DEV_USDMS_DB_HOST`, `DEV_USDMS_DB_PORT`, `DEV_USDMS_DB_NAME`, `DEV_USDMS_DB_USER`, `DEV_USDMS_DB_PASSWORD`
  - `SEC_USER_AGENT` (SEC EDGAR 호출 시 필수 제공되어야 함)
- **DB 테이블 및 구조**:
  - `us_ticker_master` (Enrichment 대상: country, sector, industry, is_collect_target 필드 갱신)
  - `us_collection_blacklist` (블랙리스트 보관: is_blocked, fail_count, last_failed_at 등)
- **데이터 오염 및 격리 로직 팁**:
  - `daily_routine.py`에 이상치 감지 및 자동 격리를 수행하기 위해, `us_daily_price` 및 `us_daily_valuation` 레코드를 당일 날짜(`CURRENT_DATE` 또는 시스템 로컬 타임 기준 Date)에 맞춰 조회하고 롤백 삭제를 처리하는 안전한 트랜잭션을 적용합니다.
  - yfinance 호출 후 API 밴을 예방하기 위해 `MasterEnricher` 내에서 임의의 Sleep(예: 1.0~2.0초)을 기본 적용하되, 테스트 모드에서는 mocking 처리되거나 타임아웃을 짧게 지정해야 합니다.

---

## § 6. 완료 기준

- [ ] § 4의 단위 및 격리 통합 테스트 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 실제 통합 테스트 통과
- [ ] 기존 T-001 ~ T-004 관련 기존 소스 및 단위 테스트 전체 통과 (회귀 없음)
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 Task-005 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-005_walkthrough.md` 작성 및 변경 내용 요약 기록
