
# US-DMS Core Logic Specification (v5.0 - Production As-Built)

## 0. 문서 개요 및 목적
본 문서는 US-DMS(US Data Management System)의 **핵심 로직과 데이터베이스 구조**를 정의하는 최상위 명세서입니다.
**`init.sql`**과 실제 구현된 파이썬 코드(`MasterSync`, `FinancialParser` 등)를 기준으로 작성되었으며, 시스템의 **현재 상태(As-Built)**를 정확히 반영합니다.

---

## 1. 데이터베이스 스키마 설계 (PostgreSQL/TimescaleDB)

모든 테이블 명세는 실제 운영 DB의 DDL을 기준으로 합니다.

### 1.1 종목 마스터 및 이력 (Master Data)

```sql
-- 1. 종목 마스터 (CIK Centric)
CREATE TABLE us_ticker_master (
    cik VARCHAR(10) PRIMARY KEY,       -- 불변 식별자 (Zero-padded, 예: '0000320193')
    latest_ticker VARCHAR(10),         -- 최신 티커
    latest_name VARCHAR(255),          -- 최신 법인명
    exchange VARCHAR(20),              -- NYSE, NASDAQ, AMEX, OTC, OTHER
    sic_code VARCHAR(10),              -- 산업 분류 코드
    sector VARCHAR(100),               -- GICS/SIC Sector
    industry VARCHAR(100),             -- GICS/SIC Industry
    country VARCHAR(100),              -- 본사 소재지
    quote_type VARCHAR(20),            -- EQUITY, ETF, MUTUALFUND 등
    
    market_cap DOUBLE PRECISION,       -- 최신 시가총액 (Daily Update)
    current_price DOUBLE PRECISION,    -- 최신 주가 (Daily Update)
    
    is_active BOOLEAN DEFAULT TRUE,          -- 상장 유지 여부
    is_collect_target BOOLEAN DEFAULT FALSE, -- [핵심] 수집/분석 대상 여부 (Filtering)
    
    first_seen_dt DATE,
    last_seen_dt DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. 티커 변경 이력 (SCD Type 2)
CREATE TABLE us_ticker_history (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) REFERENCES us_ticker_master(cik),
    ticker VARCHAR(10) NOT NULL,
    start_dt DATE NOT NULL,            -- 해당 티커 사용 시작일
    end_dt DATE DEFAULT '9999-12-31',  -- 해당 티커 사용 종료일
    UNIQUE(cik, ticker, start_dt)
);

-- 9. 수집 차단 목록 (Blacklist)
CREATE TABLE us_collection_blacklist (
    cik VARCHAR(10) PRIMARY KEY,
    ticker VARCHAR(10),
    reason_code VARCHAR(50),           -- SEC_403, PARSE_ERROR, NO_DATA, EMPTY_FILING
    reason_detail TEXT,
    is_blocked BOOLEAN DEFAULT TRUE,   -- TRUE: 영구 차단, FALSE: 일시 차단(재시도 가능)
    fail_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 1.2 재무 데이터 (Fundamental Data)

```sql
-- 3. Raw XBRL 저장소 (EAV Model - Entity-Attribute-Value)
CREATE TABLE us_financial_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    cik VARCHAR(10) NOT NULL,
    tag VARCHAR(255) NOT NULL,         -- XBRL Tag (예: Assets, NetIncomeLoss)
    val DOUBLE PRECISION,              -- 수치 값
    period_start DATE,                 -- 기간 시작일 (Duration 항목용)
    period_end DATE NOT NULL,          -- 기간 종료일 (Key)
    filed_dt DATE NOT NULL,            -- 공시일 (Point-in-Time Key)
    frame VARCHAR(50),                 -- XBRL Frame (예: CY2023Q4)
    fy DOUBLE PRECISION,               -- Fiscal Year
    fp VARCHAR(10),                    -- Fiscal Period (FY, Q1, Q2, Q3)
    form VARCHAR(10)                   -- 10-K, 10-Q 등
);

-- 4. 표준화된 재무 데이터 (Analysis Ready)
CREATE TABLE us_standard_financials (
    cik VARCHAR(10) NOT NULL,
    report_period DATE NOT NULL,       -- 회계 기간 종료일
    filed_dt DATE NOT NULL,            -- 공시일 (PIT)
    fiscal_year INTEGER,
    fiscal_period VARCHAR(10),
    
    -- [1] Balance Sheet (대차대조표 - Instant)
    total_assets DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,       -- 총차입금 (Short + Long Term)
    shares_outstanding DOUBLE PRECISION, -- 발행주식수
    
    -- [2] Income Statement (손익계산서 - Duration)
    revenue DOUBLE PRECISION,
    gross_profit DOUBLE PRECISION,
    op_income DOUBLE PRECISION,        -- 영업이익
    rnd_expense DOUBLE PRECISION,      -- 연구개발비 (성장성 지표)
    interest_expense DOUBLE PRECISION, -- 이자비용 (안정성 지표)
    net_income DOUBLE PRECISION,
    ebitda DOUBLE PRECISION,           -- (파생) OpIncome + Dep/Amor
    
    -- [3] Cash Flow (현금흐름표 - Duration)
    ocf DOUBLE PRECISION,              -- 영업활동현금흐름
    capex DOUBLE PRECISION,            -- 자본지출
    fcf DOUBLE PRECISION,              -- 잉여현금흐름 (OCF - Capex)
    
    PRIMARY KEY (cik, report_period, filed_dt)
);

-- 6.5 주식 수 이력 (Shares History - DEI Based)
CREATE TABLE us_share_history (
    cik VARCHAR(10) NOT NULL,
    filed_dt DATE NOT NULL,            -- 공시일
    val DOUBLE PRECISION,              -- 발행주식수 (EntityCommonStockSharesOutstanding)
    PRIMARY KEY (cik, filed_dt)
);
```

### 1.3 시세 및 팩터 (Market Data)

```sql
-- 5. 일봉 시세 (Raw Data - Hypertable)
CREATE TABLE us_daily_price (
    dt DATE NOT NULL,
    cik VARCHAR(10) NOT NULL,
    ticker VARCHAR(10),                 -- [Added] 데이터 추적 편의성
    open_prc DOUBLE PRECISION NOT NULL, -- [Added] OHLC 지원
    high_prc DOUBLE PRECISION NOT NULL,
    low_prc DOUBLE PRECISION NOT NULL,
    cls_prc DOUBLE PRECISION NOT NULL,
    vol BIGINT DEFAULT 0,
    amt DOUBLE PRECISION DEFAULT 0.0,
    PRIMARY KEY (dt, cik)
);
-- Chunk Size: 1 day (Optimized for 1,000+ chunks scaling)

-- 6. 가격 수정 팩터 (Adjustment Factors)
CREATE TABLE us_price_adjustment_factors (
    cik VARCHAR(10) NOT NULL,
    event_dt DATE NOT NULL,            -- 이벤트 발생일 (Ex-Date)
    factor_val DOUBLE PRECISION NOT NULL, -- 수정비율 (Adj / Close)
    event_type VARCHAR(20),            -- DIVIDEND, SPLIT
    matched_info TEXT,                 -- 디버그 정보
    PRIMARY KEY (cik, event_dt)
);
```

### 1.4 퀀트 지표 (Metrics & Valuation)

```sql
-- 7. 가치평가 지표 (Daily Updated)
CREATE TABLE us_daily_valuation (
    dt DATE NOT NULL,
    cik VARCHAR(10) NOT NULL,
    mkt_cap DOUBLE PRECISION,
    pe DOUBLE PRECISION,               -- PER
    pb DOUBLE PRECISION,               -- PBR
    ps DOUBLE PRECISION,               -- PSR
    pcr DOUBLE PRECISION,              -- PCR (Price / OCF)
    ev_ebitda DOUBLE PRECISION,        -- EV / EBITDA
    PRIMARY KEY (dt, cik)
);
-- Chunk Size: 52 weeks (Optimized for Lock Contention)

-- 8. 재무 비율 (Financial Metrics)
CREATE TABLE us_financial_metrics (
    cik VARCHAR(10) NOT NULL,
    report_period DATE NOT NULL,
    filed_dt DATE NOT NULL,

    -- Profitability
    roe DOUBLE PRECISION,
    roa DOUBLE PRECISION,
    roic DOUBLE PRECISION,             -- 투하자본이익률
    op_margin DOUBLE PRECISION,
    net_margin DOUBLE PRECISION,

    -- Stability
    debt_ratio DOUBLE PRECISION,       -- 부채비율
    current_ratio DOUBLE PRECISION,    -- 유동비율
    interest_coverage DOUBLE PRECISION,-- 이자보상배율
    
    -- Quality
    gp_a_ratio DOUBLE PRECISION,       -- GP / Assets (Novy-Marx)

    -- Growth
    rev_growth_yoy DOUBLE PRECISION,
    op_growth_yoy DOUBLE PRECISION,
    eps_growth_yoy DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, report_period, filed_dt)
);
```

---

## 2. 모듈별 핵심 구현 로직 (Core Logic Implementation)

### 2.1 Master Sync: 대표 티커 선정 및 노이즈 제거

SEC CIK는 하나지만 Ticker는 여러 개일 수 있습니다(예: GOOG/GOOGL). 이를 단일 '대표 티커'로 확정하는 로직입니다.

1.  **Rule 0 (Exceptions):** `GOOGL`, `BRK-B` 등 관행적으로 사용되는 티커를 하드코딩 매핑하여 최우선 적용.
2.  **Rule 1 (Stickiness):** 기존 DB에 이미 선정된 티커가 있고, 그 티커가 여전히 SEC 목록에 존재한다면 **기존 티커 유지** (잦은 변경 방지).
3.  **Rule 2 (Priority Sort):**
    *   알파벳 우선 (특수문자 포함된 티커 후순위).
    *   짧은 길이 우선.
    *   사전순(Lexicographical) 우선.
4.  **Noise Deletion (글리치 방어):**
    *   티커 변경이 감지되었으나, 그 `Start Date`가 **오늘**이고 동시에 `End Date` 처리가 필요하다면(즉, 당일 생성 후 당일 변경), 해당 이력은 **DB에서 삭제(DELETE)**합니다. 이는 장중 일시적 변경이나 데이터 오류로 인한 불필요한 이력 증식을 막기 위함입니다.

### 2.2 Financial Parser: 재무 표준화 및 그룹화

단순 매핑을 넘어 올바른 재무제표를 재구성하기 위한 로직입니다.

1.  **Grouping (FY/FP):** `(Fiscal Year, Fiscal Period)`를 기준으로 데이터를 그룹화합니다. SEC 공시의 `filed_dt` 차이로 인해 흩어진 데이터를 하나의 결산 정보로 묶습니다.
2.  **Instant vs Duration:**
    *   `Instant` (BS): 그룹 내 가장 최신 `filed_dt`의 값을 채택 (재작성/수정 공시 반영).
    *   `Duration` (IS/CF):
        *   `FY` (연간): 누적 값이므로 그대로 사용.
        *   `Q1`: 그대로 사용.
        *   `Q2/Q3`: **YTD - Prev_YTD** 공식을 통해 해당 분기의 이산 값(Discrete Value)을 역산하여 추출합니다.
3.  **Gap Recovery Strategy:**
    *   `MAX(filed_dt)` 이후의 데이터만 스캔.
    *   **Known Constraint:** 8-K 등 XBRL 없는 공시만 있는 기간에는 Gap 포인터가 전진하지 못하는 문제가 있어, `Blacklist` 및 중복 검사 로직으로 무한 루프를 방지합니다.

### 2.3 Targeting Logic (수집 대상 선정)

모든 종목을 수집하되, `Valuation`과 `Price` 업데이트는 리소스 효율을 위해 선별된 타겟에 집중합니다.

*   **Entry Condition (진입):**
    *   Market Cap >= $5,000만 (약 700억원)
    *   Price >= $1.00
    *   Exchange: NYSE, NASDAQ, AMEX
    *   Country: United States
    *   Type: EQUITY
*   **Retention Condition (유지/퇴출):**
    *   Market Cap < $3,500만 (버퍼 적용)
    *   Price < $0.80
    *   Exchange 이탈 시
    *   -> `is_collect_target = FALSE` 전환.

### 2.4 Valuation Engine (PIT Fallback)

정확한 시가총액 및 지표 산출을 위한 데이터 병합 전략입니다.

1.  **Data Source:**
    *   Price: `dt` 기준 매칭.
    *   Shares: `us_share_history` (1순위), `us_standard_financials.shares_outstanding` (2순위).
    *   Financials: `us_standard_financials` (TTM 변환 포함).
2.  **Logic:** `merge_asof(direction='backward')`를 사용하여, 특정 시점(`dt`)에 투자자가 알 수 있었던 가장 최신의 재무/주식 수 정보(`filed_dt`)를 매칭합니다.