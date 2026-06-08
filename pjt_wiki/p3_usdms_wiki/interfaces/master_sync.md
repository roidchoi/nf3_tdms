# MasterSync

> 마지막 변경: Task-008
> 소스 위치: [master_sync.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/master_sync.py)

### 1. 개요 및 목적
- SEC EDGAR와 yfinance API로부터 미국 상장 종목의 마스터 정보를 동기화하고 변경 사항을 기록하는 메인 오케스트레이터 파이프라인입니다.
- 연관된 문서: [[p3_usdms_wiki/interfaces/sec_client]], [[p3_usdms_wiki/interfaces/master_repo]]

### 2. 상세 명세 (요약 금지)

#### 주요 핵심 컴포넌트

##### 1. `BufferedLogHandler(logging.Handler)`
- **목적**: `yfinance` 수집 프로세스는 백그라운드 ThreadPoolExecutor에서 수행되며, 이 때 대량의 로그 폭풍(Logging Storm)으로 인한 데드락을 방지하기 위해 락-프리(`SimpleQueue`) 방식으로 로그를 비동기 수집하고 메인 스레드에서 조회할 수 있도록 설계되었습니다.
- **제약**: `yfinance`가 뱉는 로그를 기반으로 401(Crumb 에러) 또는 429(Rate Limit) 등의 세부 상태를 격리 분석하는 데 사용됩니다.

##### 2. `normalize_exchange(raw: str) -> str`
- **동작**: 다양한 포맷의 거래소 문자열을 다음 5대 표준 거래소 명칭으로 정규화합니다:
  - `['NASDAQ', 'NYSE', 'AMEX', 'OTC', 'OTHER']`

##### 3. `_resolve_primary_ticker(self, candidates: List[Dict], current_db_ticker: Optional[str] = None) -> Dict`
- **동작**: SEC 상의 1개 CIK에 2개 이상의 Ticker가 얽혀 있는 다중 티커(1:N) 상황에서, 아래 5개 룰(Logic V2)을 순차적으로 적용하여 주 티커(Primary Ticker)를 선정합니다:
  - **Rule 0 (Hard Override)**: `EXCEPTION_MAP`에 정의된 CIK는 사전에 하드코딩된 특정 티커로 강제 매칭합니다. (예: `0001652044` -> `GOOGL`, `0001067983` -> `BRK-B`)
  - **Rule 1 (Exchange Rank)**: 거래소 선호 등급 순위가 높을수록 우선합니다. (`NYSE (1) > NASDAQ (2) > AMEX (3) > OTC (4) > OTHER (5)`)
  - **Rule 2 (Purity)**: 특수 문자(`.`, `-`, `$`)를 포함하지 않는 일반 순수 문자열 티커를 우선합니다.
  - **Rule 3 (Stickiness)**: 기존 DB에 이미 적재된 티커가 존재하고, 해당 티커의 Exchange Rank 및 Special Character 유무가 신규 후보의 최선의 것과 대등하다면 기존 티커를 고수하여 불필요한 SCD Type 2 이력 분할을 방지합니다.
  - **Rule 4 (Tie-Breaker)**: 위 조건에서 모두 동률인 경우, 티커 글자 수가 더 짧은 순(Length ASC) -> 사전 순(Alpha ASC)으로 최종 매칭합니다.

##### 4. `sync_daily(self, limit: int = None) -> Dict[str, int]`
- **동작**: 전체 데일리 동기화 메인 프로세스입니다:
  - **Step 1**: SEC API (`get_company_tickers`, `get_tickers_exchange`)를 조회하여 메모리에 로딩합니다.
  - **Step 2**: DB의 `us_ticker_master`를 전부 조회하여 기존 마스터 상태를 읽어옵니다.
  - **Step 3 (Diff Processing)**:
    - **신규 상장(New Listings)**: SEC에 새로 나타난 CIK를 마스터에 등록하고 첫 `us_ticker_history` 이력을 생성합니다.
    - **상장 폐지(Delistings)**: SEC 벌크 파일에서 사라진 CIK를 검지하면, Submissions API를 개별적으로 확인하는 **신뢰성 검증(Authority Verification)**을 수행하여 404/Error인 경우에만 `is_active = FALSE`로 격하시키고 이력(`end_dt = YESTERDAY`)을 마감합니다. (벌크의 일시적 누락 오탐 방지)
    - **티커 변경(Ticker Changes)**: 주 티커가 변경되었을 경우, 기존 이력을 마감(`end_dt = YESTERDAY`)하고 신규 티커로 새로운 이력을 오픈(`start_dt = TODAY`)하는 SCD Type 2 로직을 트랜잭션 안전하게 수행합니다.
  - **Step 4 (Enrichment)**: `yfinance`를 활용해 신규 또는 수집 대상의 기업 메타 정보(Sector, Industry, Market Cap, Quote Type, Country 등)를 다중 비동기 수집하고 업데이트합니다.
  - **Step 5 (Targeting Analysis)**: 수집 타겟 테이블을 갱신합니다.

##### 5. `_update_target_status(self)`
- **동작**: 수집 타겟 조건(Retention 및 Entry)을 만족하는 대상의 `is_collect_target` 플래그를 정기 조정합니다.
  - **이탈 기준 (Retention Out)**: `market_cap < TARGET_RETAIN_MARKET_CAP` 또는 `current_price < TARGET_RETAIN_PRICE` 또는 `exchange NOT IN ('NASDAQ', 'NYSE', 'AMEX')` 또는 `country != 'United States'` 또는 `quote_type != 'EQUITY'` 혹은 임계 필드가 `NULL`인 대상을 수집 타겟에서 배제합니다.
  - **유입 기준 (Entry In)**: `market_cap >= TARGET_MIN_MARKET_CAP` 이고 `current_price >= TARGET_MIN_PRICE` 이고 `exchange IN ('NASDAQ', 'NYSE', 'AMEX')` 이고 `country = 'United States'` 이고 `quote_type = 'EQUITY'` 인 활성화된 종목을 새로운 수집 타겟으로 대입합니다.
- **특징**:
  - 임계 시가총액 및 가격은 하드코딩되지 않고 `.env`에 정의된 `TARGET_*` 환경변수를 바인딩하여 쿼리 인자로 안전하게 전달됩니다.
  - 유입 기준 쿼리에 블랙리스트 CIK 제외 조건(`AND cik NOT IN (SELECT cik FROM us_collection_blacklist WHERE is_blocked = TRUE)`)이 추가되어 타겟 지정이 차단됩니다.

### 3. 주의사항 및 의존성
- **yfinance 비동기 처리**: `yfinance`는 동기 블로킹 라이브러리이므로 `loop.run_in_executor`를 통해 ThreadPool로 작업을 위임합니다.
- **SCD Type 2의 트랜잭션 무결성**: 티커 변경 감지 시 동일 트랜잭션 내에서 `us_ticker_history` 테이블의 이력을 닫고(끝 날짜 수정) 새로운 이력을 삽입하는 행위가 원자적으로 보장되어야 하므로 `BaseRepository.get_cursor()` 컨텍스트 관리자 하에서 일괄 처리가 실행됩니다.
