# Daily Routine Process Documentation (V2.0)

본 문서는 `ops/run_daily_routine.py`에 의해 수행되는 일일 데이터 수집 및 처리 과정의 논리적 흐름, 코드 레벨의 상세 수행 내역, 그리고 데이터베이스 상호작용을 상세히 기술합니다. 이 문서는 시스템의 모순 및 누락을 판별하기 위한 기준 문서(Reference)로 활용됩니다.

---

## 0. 실행 환경 및 초기화 (Initialization)
*   **스크립트 진입점:** `ops/run_daily_routine.py` -> `DailyRoutine.run()`
*   **비동기 실행:** `asyncio` 기반의 이벤트 루프로 실행되나, 각 Step 내부에서 동기(blocking) 함수와 비동기 함수가 혼용됩니다.
*   **DB 연결:** 각 Step 완료 시마다 `db.close()` 및 `DatabaseManager()` 재생성을 통해 Connection Lock 및 Memory Leak을 방지합니다.

---

## Step 1: Master Sync (마스터 동기화)
**담당:** `backend.collectors.master_sync.MasterSync.sync_daily()`

SEC의 최신 티커 목록과 로컬 DB(`us_ticker_master`)를 대조하여 메타데이터를 동기화합니다.

### 1-1. SEC 데이터 수집 (Data Fetching)
1.  **SEC Exchanges:** `sec_client.get_tickers_exchange()` 호출. (실패 시 빈 dict 사용)
2.  **SEC Tickers:** `sec_client.get_company_tickers()` 호출. CIK 별로 그룹화(1:N 관계).

### 1-2. Diff Processing (상태 비교 및 갱신)

#### A. New Listings (신규 상장)
*   **조건:** SEC 목록에는 있으나 DB(`us_ticker_master`)에 없는 CIK.
*   **로직:**
    *   `_resolve_primary_ticker`: 1:N 티커 중 우선순위(알파벳 문자 우선, 특수문자 후순위)로 메인 티커 선정.
    *   **INSERT `us_ticker_master`:** `is_active=TRUE`, `is_collect_target=FALSE`.
    *   **INSERT `us_ticker_history`:** `start_dt=Today`, `end_dt=9999-12-31`.

#### B. Delistings (상장 폐지)
*   **조건:** DB에는 `is_active=TRUE`이나 SEC 목록에 없는 CIK.
*   **로직:**
    *   **UPDATE `us_ticker_master`:** `is_active=FALSE`, `is_collect_target=FALSE`.
    *   **UPDATE `us_ticker_history`:** `end_dt=Today` (현재 활성 레코드 마감).

#### C. Ticker Changes (티커 변경)
*   **조건:** CIK는 같으나 DB의 `latest_ticker`와 SEC의 `ticker`가 다름.
*   **로직 (SCD Type 2):**
    *   **Noise Filter (New):** 만약 `start_dt > Yesterday`인 레코드(당일 생성된 티커)를 닫아야 한다면, **DELETE** 처리 (노이즈 제거).
    *   **Close Old:** `us_ticker_history`의 기존 레코드(`end_dt=9999`)를 `end_dt=Yesterday`로 업데이트.
    *   **Open New:** `us_ticker_history`에 새 티커 레코드 INSERT (`start_dt=Today`).
    *   **Update Master:** `us_ticker_master`의 `latest_ticker`, `exchange`, `updated_at` 갱신.

### 1-3. Metadata Enrichment (메타데이터 보강)
*   **대상:** `is_collect_target=FALSE`이거나 필수 정보(Market Cap, Sector 등)가 누락된 활성 종목.
*   **로직:** `yfinance` API를 통해 메타데이터(Sector, Industry, MarketCap, QuoteType, Country) 수집.
*   **필터:** `BlacklistManager`를 통과한 CIK만 수행.
*   **UPDATE `us_ticker_master`:** 수집된 정보로 컬럼 일괄 갱신.

### 1-4. Target Status Update (수집 대상 선정)
*   **Retention(제외):** 시가총액 < 3,500만불 OR 주가 < $0.80 OR 비주류 거래소 OR 비미국기업 -> `is_collect_target=FALSE`.
*   **Entry(진입):** 시가총액 >= 5,000만불 AND 주가 >= $1.00 AND 주요 거래소(NYSE/ISDAQ/AMEX) AND 미국기업 -> `is_collect_target=TRUE`.

---

## Step 2: Market Data Update (시세 수집)
**담당:** `backend.collectors.market_data_loader.MarketDataLoader.collect_daily_updates()`

활성 타겟 종목의 최신 시세를 수집합니다.

### 2-1. 초기화 및 범위 설정
*   **대상:** `us_ticker_master` WHERE `is_collect_target=TRUE` (Test Mode 시 제한).
*   **기간:** `Lookback 10 days` ~ `Yesterday`. (과거 10일치 데이터를 재수집하여 수정된 가격 반영).

### 2-2. API 호출 및 저장
*   **API:** `kis_us_wrapper.get_ohlcv()` (일봉). `add_adjusted=True` 옵션 사용.
*   **저장 (`us_daily_price`):**
    *   데이터 존재 시 Upsert (TimescaleDB / Hypertable).
    *   주요 컬럼: `open_prc`, `high_prc`, `low_prc`, `cls_prc` (Raw), `amt`, `vol`.
*   **팩터 계산 (`us_price_adjustment_factors`):**
    *   `PriceEngine` 호출.
    *   `Adj Close`와 `Close`의 비율(`ratio`) 변동을 감지하여 액면분할/배당락 팩터 자동 계산 및 저장.

---

## Step 3: Financial Data Update (재무 수집)
**담당:** `FinancialParser.process_filings()` (Orchestrated in `run_daily_routine.py`)

SEC XBRL 데이터를 파싱하여 재무제표를 구축합니다.

### 3-1. Gap Scanning (공백 감지)
*   **기준:** `SELECT MAX(filed_dt) FROM us_financial_facts`.
*   **범위:** `Start = Global Max - 3 days` (안전 오버랩), `End = Yesterday`.
*   **SEC Index:** `sec_client.get_filings_by_date()`로 해당 기간의 전체 공시 목록 확보.

### 3-2. Filtering (필터링)
*   **Form Type:** `10-K`, `10-Q`, `8-K` (및 Amendment)만 허용.
*   **Membership:** 수집 대상(`target_ciks`)에 포함된 CIK만 허용.
*   **Blacklist:** 블랙리스트 등재 CIK 제외.
*   **DB Overlap:** `us_financial_facts`에 이미 해당 날짜 이후의 데이터가 있는지 확인(중복 제거).

### 3-3. Parsing & Saving (파싱 및 저장)
*   **Raw Data (`us_financial_facts`):**
    *   SEC `companyfacts` JSON 다운로드.
    *   `us-gaap` 태그 파싱 -> 저장 (`val`, `period_start`, `period_end`, `filed_dt`).
*   **Shares (`us_share_history`):**
    *   `dei` 태그의 `EntityCommonStockSharesOutstanding` 추출 -> 저장.
*   **Standard Financials (`us_standard_financials`):**
    *   **Logic (V2):** `(Fiscal Year, Fiscal Period)` 기준으로 그룹화.
    *   **Instant Rule:** Balance Sheet 항목(자산/부채 등)은 해당 기간 `End Date`의 최신 값 사용.
    *   **Duration Rule:** Income Statement 항목(매출/이익)은 `Start ~ End` 기간이 일치하는 값(분기/연간) 사용.
    *   **Validation:** 자산(Total Assets) 또는 매출(Revenue) 등 핵심 항목이 있어야 저장.
    *   **Mapping:** `XBRLMapper`를 통해 표준 계정과목으로 매핑 및 저장.

---

## Step 4: Metadata & Price Internal Calculation (내부 지표 갱신)
**담당:** `run_daily_routine.py` (Internal Logic)

수집된 최신 재무/시세 데이터를 Master 테이블에 반영합니다.

### 4-1. Optimization Strategy
*   **Robust Mode:** 전체 타겟을 Chunk(5개 단위)로 나누어 처리하며 잦은 Commit 수행 (Lock 방지).
*   **Lookback:** 최근 14일 이내의 데이터만 조회 (Partition Pruning 유도).

### 4-2. Calculation logic
1.  **Fetch:** `us_daily_price` 최신 종가(`cls_prc`), `us_daily_valuation` 최신 시총(`mkt_cap`) 조회.
    *   주의: `us_daily_valuation`은 Step 5에서 계산되므로, 여기서는 어제 자 시총일 수 있음.
    *   (코드 확인 결과: `SELECT mkt_cap`을 조회하여 Master에 반영함)
2.  **Update `us_ticker_master`:**
    *   `market_cap`, `current_price` 컬럼 갱신.
    *   `updated_at = NOW()`.

---

## Step 5: Valuation & Metrics (밸류에이션 산출)
**담당:** `backend.engines.valuation_calculator`

매일의 시가총액과 최신 재무데이터를 결합하여 투자 지표를 산출합니다.

### 5-1. Preparation
*   **대상:** `is_collect_target=TRUE` 종목.
*   **기간:** 최근 30일 (재계산 윈도우).

### 5-2. PIT Matching (Point-In-Time)
*   **Algorithm:** `pandas.merge_asof(direction='backward')`.
*   **Price:** 일별 시세 (`dt` 기준).
*   **Shares:** 과거 가장 최근의 `us_share_history` (`filed_dt` 기준).
    *   *Fallback:* Share History 없을 시 재무제표의 `shares_outstanding` 사용.
*   **Financials:** 과거 가장 최근의 `us_standard_financials` (`filed_dt` 기준).

### 5-3. Metric Calculation
*   **Market Cap:** `Price * Shares`.
*   **TTM Calculation:** 분기 데이터일 경우 `Value * 4` (간이 TTM).
*   **Ratios:**
    *   PER = `Mkt Cap / Net Income(TTM)`
    *   PBR = `Mkt Cap / Total Equity`
    *   PSR = `Mkt Cap / Revenue(TTM)`
    *   EV/EBITDA = `(Mkt Cap + Debt - Cash) / EBITDA(TTM)`
    *   PCR = `Mkt Cap / OCF(TTM)`

### 5-4. Saving (`us_daily_valuation`)
*   **Batch Insert:** 50행 단위로 저장.
*   **Result:** `dt`, `cik`, `pe`, `pb` 등의 지표가 매일 생성됨.

---

## Step 6: Health Check (건전성 진단)
**담당:** `DailyRoutine._detect_anomalies()`

*   **Price Spike:** 전일 대비 주가 변동폭 > 50%.
*   **Valuation Jump:** 전일 대비 PER/PBR 비율이 2배 이상 or 0.5배 이하.
*   **Actions:** 리포트(`json`)에 Anomaly 항목으로 기록 (경고).

---

## 결론 및 참고사항
*   이 프로세스는 **데이터의 존재 여부(Existence)**에 강하게 의존합니다. (Gap Scan은 `filed_dt` 의존, Valuation은 `filed_dt` 기준 Merge)
*   **Known Constraint:** 8-K와 같이 XBRL이 없는 공시만 발생하는 기간에는 `MAX(filed_dt)`가 갱신되지 않아 Gap Scan이 반복될 수 있는 구조적 한계가 존재합니다. (Phase 4.51에서 확인됨)
