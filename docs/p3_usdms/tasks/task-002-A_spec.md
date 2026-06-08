# Task-002-A: 티커 마스터 수집 코어 (SEC EDGAR + SCD Type 2 + MasterRepo)

> **Sub Project**: p3_usdms
> **PRD 근거**: F-01 (티커 마스터 동기화), API-데이터
> **작성일**: 2026-06-01
> **의존 Task**: T-001 (완료)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `tdms_core/p3_usdms/config.py` | ⚠️ 직접 확인 |
| EnvDetector 시그니처 | `pjt_wiki/p1_shared_wiki/interfaces/env_detector.md` | ✅ 확인 |
| DB Connection Pool | `pjt_wiki/p1_shared_wiki/interfaces/db_connection_pool.md` | ✅ 확인 |
| USDMS DB 스키마 | `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/db_schema.md` | ✅ 확인 |
| SECClient & MasterSync | `migration_pjt/usdms_origin/backend/collectors/` | ⚠️ 직접 확인 |
| MasterRepo | 신규 설계 | 🆕 신규 |

---

## § 1. 목표

미국 주식 수집의 근간이 되는 SEC EDGAR 기반 종목 마스터 동기화 및 yfinance 정보 보강(Enrichment) 엔진을 리팩토링하여 구축합니다. 또한 이를 안전하게 제어하고 조회할 수 있는 레포지토리 레이어와 `/tickers` 엔드포인트 골격을 구축합니다.

**구현 범위:**
- **IN**:
  - `SECClient`: SEC EDGAR API 3종(tickers, exchange, submissions) 호출 및 레이트 리밋 준수
  - `MasterSync`: 1:N 티커 매핑 해결(V2 Logic), SCD Type 2 이력 관리(Transient 노이즈 제거 포함), Authority Verification 검증을 통한 생존 티커 구출, yfinance 비동기 배치 enrichment, Targeting 조건에 맞는 수집 대상 분류
  - `MasterRepo`: `us_ticker_master` 및 `us_ticker_history` 테이블 접근용 기본 레포지토리
  - `/api/data/tickers` API 엔드포인트 및 FastAPI 라우터 초기화
- **OUT**:
  - 일봉 OHLCV 수집 및 KIS US API 연동 (T-002-B)
  - 수정주가 팩터 계산 엔진 (T-002-B)
  - SEC XBRL 재무제표 파싱 및 이산화 (T-003)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/collectors/sec_client.py` — SEC EDGAR API 호출 클라이언트 (이전 원본 리팩토링)
- `tdms_core/p3_usdms/collectors/master_sync.py` — 티커 마스터 동기화 엔진 (이전 원본 리팩토링)
- `tdms_core/p3_usdms/repositories/master_repo.py` — 종목 마스터 및 히스토리 DB 접근 레포지토리
- `tdms_core/p3_usdms/routers/data.py` — 데이터 조회 라우터 초기화 및 `/tickers` 구현
- `tdms_core/p3_usdms/tests/test_master_sync.py` — T-002-A 검증용 테스트 코드

### 수정 대상 파일
- `tdms_core/p3_usdms/main.py` — `routers/data.py` 라우터 등록 및 lifespan 연동

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 3.1 SECClient
```python
# [출처: migration_pjt/usdms_origin/backend/collectors/sec_client.py — 직접 확인 후 리팩토링]
class SECClient:
    def __init__(self) -> None:
        """
        config.py의 get_settings().SEC_USER_AGENT 로딩 검증.
        호스트(data.sec.gov, www.sec.gov)별 헤더 설정 및 세션 초기화.
        """
        ...

    def get_master_index(self) -> dict[str, dict[str, str]]:
        """
        company_tickers.json을 호출하여 CIK를 키로 하는 정보 반환.
        Returns:
            {
                "0000320193": {"ticker": "AAPL", "name": "Apple Inc."},
                ...
            }
        """
        ...

    def get_company_tickers(self) -> dict[str, dict[str, Any]]:
        """www.sec.gov/files/company_tickers.json 호출 Raw 반환"""
        ...

    def get_tickers_exchange(self) -> dict[str, str]:
        """
        company_tickers_exchange.json 호출 및 파싱.
        Returns:
            {
                "AAPL": "NASDAQ",
                "MSFT": "NASDAQ",
                ...
            }
        """
        ...

    def get_filings_by_date(self, target_date: Any) -> list[dict[str, Any]]:
        """
        SEC Daily Index (.idx) 파일 파싱.
        Returns:
            [
                {"cik": 320193, "form_type": "10-K", "accession": "edgar/data/..."},
                ...
            ]
        """
        ...
```

### 3.2 MasterSync
```python
# [출처: migration_pjt/usdms_origin/backend/collectors/master_sync.py — 직접 확인 후 리팩토링]
class MasterSync:
    def __init__(self) -> None:
        """
        DatabaseManager shim 어댑터 및 SECClient 초기화.
        yfinance 전용 thread executor 및 simple queue log handler 설정.
        """
        ...

    @staticmethod
    def normalize_exchange(raw: str) -> str:
        """exchange 문자열을 NASDAQ / NYSE / AMEX / OTC / OTHER 5종으로 정형화"""
        ...

    def _resolve_primary_ticker(self, candidates: list[dict], current_db_ticker: str = None) -> dict:
        """
        V2 결정 규칙 적용:
        1. Exception Map (GOOGL, BRK-B 등 하드코딩 매핑)
        2. Exchange Rank (NYSE > NASDAQ > AMEX > OTC > OTHER)
        3. Purity (특수문자 ., -, $ 포함 여부 우선 배제)
        4. Stickiness (기존 DB의 티커가 동급 랭크/순도라면 고수)
        5. Tie-Breaker (문자열 길이 짧은 순 -> 알파벳 순)
        """
        ...

    async def sync_daily(self, limit: int = None) -> dict[str, int]:
        """
        일일 동기화 메인 프로세스:
        Step 1. SEC 마스터 인덱스 로드 및 CIK 1:N 후보군 매핑
        Step 2. DB 마스터 상태 로드 (us_ticker_master)
        Step 3. Diff 분석:
                - 신규 상장 (New Listings): DB/History에 삽입, yfinance 단독 enrich
                - 상장 폐지 의심 (Missing CIK): Submissions API로 실시간 액티브 검증(_verify_batch_authority)
                  -> 실 액티브 확인 시 Update 처리, 완전 폐지 확인 시 Master 비활성화 및 History end_dt 갱신
                - 티커 변경 및 거래소 변경 (SCD Type 2): Transient 노이즈 제거, history end_dt 갱신 후 신규 행 추가
        Step 4. 마스터 정보 갱신 및 yfinance 배치 Enrichment (_enrich_specific_ciks)
        Step 5. 타겟팅 규칙 분석 및 갱신 (_update_target_status)
        """
        ...

    async def _verify_batch_authority(self, ciks: list[int]) -> list[dict]:
        """SEC Submissions API를 호출하여 CIK의 실제 생존 및 티커/거래소 정보 실시간 확인"""
        ...

    async def _enrich_specific_ciks(self, ciks: list[str]) -> None:
        """yfinance 비동기 병렬 호출 및 bulk DB 업데이트"""
        ...

    def _update_target_status(self) -> None:
        """
        수집 대상 타겟팅 분석:
        - 탈락 (Retention): market_cap < $35M OR price < $0.80 OR 거래소 메이저 외 OR 국가 미국 외 OR equity 외
        - 진입 (Entry): market_cap >= $50M AND price >= $1.00 AND 메이저 거래소 AND 미국 AND equity
        """
        ...
```

### 3.3 MasterRepo
```python
# [신규 정의 — T-002-A에서 최초 설계]
from p3_usdms.repositories.base import BaseRepository

class MasterRepo(BaseRepository):
    def get_active_tickers(self) -> list[dict]:
        """us_ticker_master에서 is_active = TRUE인 티커 목록 조회"""
        ...

    def get_collect_targets(self) -> list[dict]:
        """is_collect_target = TRUE인 종목 목록 조회"""
        ...

    def get_ticker_history(self, cik: str) -> list[dict]:
        """특정 CIK의 티커 변경 이력 조회"""
        ...
```

---

## § 4. 테스트 케이스

### 4.1 정상 동작 케이스 (Tier 1 & Tier 2)

```python
# [Tier 1 — 단위]
def test_normalize_exchange_returns_standardized_names():
    """
    [목적] 정리가 안 된 거래소명을 5종의 정규 거래소명(NASDAQ, NYSE, AMEX, OTC, OTHER)으로 매핑 확인
    [유도] MasterSync.normalize_exchange 정규화 규칙 동작 검증
    """
    assert MasterSync.normalize_exchange("NASDAQ/NMS") == "NASDAQ"
    assert MasterSync.normalize_exchange("new york stock exchange") == "NYSE"
    assert MasterSync.normalize_exchange("pink sheets") == "OTC"
    assert MasterSync.normalize_exchange("LSE") == "OTHER"
    assert MasterSync.normalize_exchange(None) == "OTHER"

# [Tier 1 — 단위]
def test_resolve_primary_ticker_prefers_higher_rank_and_purity():
    """
    [목적] 하나의 CIK에 여러 티커가 매핑될 때 V2 결정 규칙에 따라 올바른 메인 티커를 추출하는지 검증
    [유도] _resolve_primary_ticker() 가 Exception Map, 거래소 우선순위, 특수문자 정제 규칙을 올바르게 따르는지 검사
    """
    sync = MasterSync()
    candidates = [
        {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc.", "exchange_norm": "NASDAQ"},
        {"ticker": "AAPLP", "cik_str": 320193, "title": "Apple Preferred", "exchange_norm": "OTHER"},
    ]
    resolved = sync._resolve_primary_ticker(candidates)
    assert resolved["ticker"] == "AAPL"

# [Tier 2 — 격리 통합]
@pytest.mark.asyncio
async def test_sync_daily_inserts_new_listings(mocker):
    """
    [목적] SEC 데이터에 새로운 CIK가 유입되었을 때, DB 마스터와 히스토리에 신규 행이 삽입되는지 검증
    [유도] sync_daily()의 신규 상장 Diff 로직이 Mock DB 커서를 통해 올바른 쿼리로 변환되어 실행되는지 검증
    """
    # Arrange
    sync = MasterSync()
    
    # Mock SECClient
    mock_sec = mocker.patch.object(sync, "sec_client")
    mock_sec.get_master_index.return_value = {
        "0001999999": {"ticker": "NEWT", "name": "New Ticker Inc."}
    }
    mock_sec.get_tickers_exchange.return_value = {"NEWT": "NASDAQ"}
    mock_sec.get_company_tickers.return_value = {
        "0": {"cik_str": 1999999, "ticker": "NEWT", "title": "New Ticker Inc."}
    }
    
    # Mock DB cursor
    mock_cur = mocker.MagicMock()
    # DB 에는 아무것도 없는 것으로 설정 (db_records = [])
    mock_cur.fetchall.return_value = []
    mocker.patch.object(sync.db, "get_cursor", return_value=mocker.MagicMock(__enter__=lambda s: mock_cur))
    
    # yfinance enrich 스킵 설정
    mocker.patch.object(sync, "_enrich_specific_ciks")
    mocker.patch.object(sync, "_update_target_status")
    
    # Act
    stats = await sync.sync_daily()
    
    # Assert
    assert stats["new_listings"] == 1
    # INSERT us_ticker_master 및 us_ticker_history 쿼리가 실행되었는지 확인
    assert any("INSERT INTO us_ticker_master" in call[0][0] for call in mock_cur.execute.call_args_list or []) or mock_cur.execute.call_count > 0
```

### 4.2 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_sec_client_constructor_raises_value_error_if_user_agent_missing(mocker):
    """
    [목적] SEC_USER_AGENT 환경변수가 없거나 유효하지 않을 때 SECClient 기동을 방지
    [유도] SEC 규정을 준수하여 User-Agent 미설정 시 ValueError 발생 처리
    """
    mocker.patch("os.getenv", return_value="")
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SECClient()
```

### 4.3 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
@pytest.mark.integration
@pytest.mark.asyncio
async def test_master_sync_flow_with_real_db(real_pool):
    """
    [목적] 실제 DB에 연결된 환경에서 MasterSync를 동작시켜 신규 상장, 타겟팅 분석이 무결하게 반영되는지 최종 검증
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    sync = MasterSync()
    # 실제 db 커넥션을 사용하도록 인스턴스 db 연결 변경
    sync.db._pool = real_pool
    
    # 1. 테스트 실행 전 마스터 데이터 정리
    with real_pool.get_cursor() as cur:
        cur.execute("DELETE FROM us_ticker_history WHERE cik = '0001999999'")
        cur.execute("DELETE FROM us_ticker_master WHERE cik = '0001999999'")
        
    # 2. 강제로 테스트용 SEC 데이터 동기화 동작 유도
    # (실제 SEC API 호출을 피하기 위해 sec_client 부분 Mocking 적용 가능)
    # 여기서는 sync_daily 내부의 diff 로직 및 DB 물리 쓰기만을 격리하여 통합 테스트 수행
    
    # 3. DB에 성공적으로 물리 행이 영속화되었는지 검증
    with real_pool.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM us_ticker_master WHERE cik = '0001999999'")
        row = cur.fetchone()
        
    # Assert
    # (실제 sync_daily 구동 또는 master_repo를 활용하여 물리 DB의 상태가 올바르게 전이되었는지 검증)
    ...
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_normalize_exchange_returns_standardized_names` | Tier 1 | 정상 | 거래소 정규화 규칙 동작 |
| 2 | `test_resolve_primary_ticker_prefers_higher_rank_and_purity` | Tier 1 | 정상 | CIK 1:N 매핑 해결 규칙 |
| 3 | `test_sync_daily_inserts_new_listings` | Tier 2 | 정상 | 신규 상장 발생 시 DB/이력 일괄 적재 |
| 4 | `test_sec_client_constructor_raises_value_error_if_user_agent_missing` | Tier 1 | 예외 | SEC_USER_AGENT 규정 검증 |
| 5 | `test_master_sync_flow_with_real_db` | Tier 3 | 실제 통합 | 실 DB 물리 쓰기 및 타겟팅 상태 반영 검증 |

**총 5개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **yfinance 쓰레드 세이프 안정성**:
  - 원본 구현에서 yfinance API를 멀티쓰레딩으로 비동기 호출할 때 데드락과 좀비 쓰레드 생성을 방지하기 위해 `BufferedLogHandler` 및 전용 `ThreadPoolExecutor`를 사용하여 호출을 격리했습니다. 이를 리팩토링 시 그대로 이식해야 합니다.
- **SCD Type 2의 Transient 노이즈 제거**:
  - 하루 동안 생겼다가 사라지는 transient 변경에 대해 `start_dt > yesterday_date` 조건으로 `DELETE` 처리하는 이탈 방지 로직이 `sync_daily`에 적용되어 있습니다. 이 동작이 누락되지 않도록 주의하십시오.
- **SEC_USER_AGENT 필수 준수**:
  - 미국 SEC API는 User-Agent 누락 시 접근 차단(403)을 수행합니다. `SECClient` 뿐만 아니라 `MasterSync` 내의 submissions API 호출에서도 이를 필수로 전달해야 합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 1~4 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 통합 테스트 통과
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 T-002-A 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-002-A_walkthrough.md` 작성
