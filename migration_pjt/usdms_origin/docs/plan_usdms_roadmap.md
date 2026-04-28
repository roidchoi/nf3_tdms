
# US-DMS (US Data Management System) Roadmap (v4.5 - Synchronized)

## 1. 프로젝트 개요 및 전략

본 프로젝트는 미국 주식 시장의 전 종목(상장 폐지 종목 포함)에 대해 **SEC EDGAR 기반의 딥 펀더멘털 데이터**와 **가격 역산(Reverse Calculation) 기반의 무결점 시세 DB**를 구축하는 것을 목표로 합니다.

### 1.1 핵심 전략 (Key Pillars)

1. **SEC Direct Core & Deep Dive**: 벤더 없이 SEC EDGAR에서 데이터를 100% 직접 수집하며, 기존의 단순 재무(BS/IS)를 넘어 **현금흐름(CF), 연구개발비(R&D), 이자비용** 등 기관급 팩터 산출을 위한 심층 데이터를 확보합니다.
    
2. **Robust Price Architecture**: API가 제공하는 수정주가를 맹신하지 않고, **Raw 데이터와 수정계수(Factor)를 분리 저장**하고 직접 역산하는 KDMS 방식을 도입하여 데이터 정합성을 보장합니다.
    
3. **CIK Centric & PIT**: 변경 잦은 Ticker 대신 불변 식별자인 **CIK**를 기준으로 히스토리를 관리하며, 모든 데이터는 공시일(Filed Date) 기준의 **Point-in-Time** 구조를 준수하여 미래 참조 편향을 원천 차단합니다.
    

### 1.2 커버리지 목표

- **대상**: NYSE, NASDAQ, AMEX, OTC 포함 전 종목 + **기간 내 상장 폐지된 모든 종목**
    
- **기간**: 2010년 1월 ~ 현재 (XBRL 데이터 완비 기간)
    
- **데이터 깊이**:
    
    - 기존: PER, PBR, PSR 위주
        
    - **확장**: **EV/EBITDA, P/FCF, GP/A, ROIC** 등 고도화된 퀀트 지표 산출 가능
        

## 2. 시스템 아키텍처 및 데이터 흐름

```mermaid
graph TD
    %% Sources
    SEC_ARC[SEC Archives\n(master.idx)] -->|1. CIK List| MASTER[Master Sync]
    SEC_API[SEC CompanyFacts API\n(JSON)] -->|2. XBRL Tags| FIN_PARSER[Financial Parser]
    MKT_API[Market Data API\n(KIS/Yahoo)] -->|3. OHLCV Raw| MKT_LOADER[Market Loader]

    %% Processing Layer
    FIN_PARSER -->|Normalize| FIN_STD[Standardizer\n(BS/IS/CF/R&D)]
    MKT_LOADER -->|Reverse Calc| PRC_CALC[Price Factor Calc\n(Raw vs Adj)]

    %% Database Layer (PostgreSQL/TimescaleDB)
    subgraph "US-DMS Database"
        MASTER --> TB_MST[us_ticker_master]
        MASTER --> TB_HIST[us_ticker_history]
        
        FIN_PARSER --> TB_RAW_FIN[us_financial_facts\n(Raw XBRL)]
        FIN_STD --> TB_STD_FIN[us_standard_financials\n(Clean Data)]
        
        MKT_LOADER --> TB_PRC[us_daily_price\n(Raw OHLCV)]
        PRC_CALC --> TB_ADJ[us_price_adjustment_factors]
        
        TB_MST -.-> TB_BLK[us_collection_blacklist]
    end

    %% Engine Layer
    TB_STD_FIN & TB_PRC & TB_ADJ --> VAL_ENG[Valuation Engine]
    VAL_ENG --> TB_VAL[us_daily_valuation\n(EV/EBITDA, FCF, GP/A)]
```

## 3. 데이터베이스 스키마 설계 (v5.0 Current)

실제 운영 중인 `init.sql`과 동기화된 완벽한 스키마 명세입니다.

### 3.1 마스터 및 히스토리

```sql
-- 1. 종목 마스터 (Extended)
CREATE TABLE us_ticker_master (
    cik VARCHAR(10) PRIMARY KEY,       -- 불변 식별자 (Zero-padded)
    latest_ticker VARCHAR(10),
    latest_name VARCHAR(255),
    exchange VARCHAR(20),              -- NYSE, NASDAQ, AMEX, OTC
    sic_code VARCHAR(10),              -- 산업 분류
    sector VARCHAR(100),               -- GICS/SIC Sector
    
    -- [Phase 1.5 Enrichment]
    market_cap DOUBLE PRECISION,
    current_price DOUBLE PRECISION,
    quote_type VARCHAR(20),
    is_collect_target BOOLEAN DEFAULT FALSE,
    
    -- [Phase 3.5 Enrichment]
    country VARCHAR(100),
    industry VARCHAR(100),
    
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    first_seen_dt DATE,
    last_seen_dt DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. 티커 변경 이력
CREATE TABLE us_ticker_history (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) REFERENCES us_ticker_master(cik),
    ticker VARCHAR(10) NOT NULL,
    start_dt DATE NOT NULL,
    end_dt DATE DEFAULT '9999-12-31',
    UNIQUE(cik, ticker, start_dt)
);

-- [9] 수집 차단 목록 (Blacklist Management)
CREATE TABLE us_collection_blacklist (
    cik VARCHAR(10) PRIMARY KEY,       -- Zero-padded CIK
    ticker VARCHAR(10),
    reason_code VARCHAR(50),           -- SEC_403, PARSE_ERROR, NO_DATA
    reason_detail TEXT,
    is_blocked BOOLEAN DEFAULT TRUE,   -- TRUE: 수집 제외, FALSE: 해제(재시도)
    fail_count INTEGER DEFAULT 0,
    last_failed_at TIMESTAMP,
    last_verified_at TIMESTAMP,        -- 관리자 검증 시각
    admin_note TEXT,                   -- 대시보드 관리자 메모
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 3.2 재무 데이터 (2-Layer 구조)

```sql
-- 3. Raw XBRL 저장소 (EAV 모델)
CREATE TABLE us_financial_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    cik VARCHAR(10) NOT NULL,
    tag VARCHAR(255) NOT NULL,
    val DOUBLE PRECISION,
    period_start DATE,
    period_end DATE NOT NULL,
    filed_dt DATE NOT NULL,            -- PIT Key
    frame VARCHAR(50),
    fy DOUBLE PRECISION,
    fp VARCHAR(10),
    form VARCHAR(10)
);

-- 4. 표준화된 재무 데이터 (핵심 분석용 - Standardized Financials)
CREATE TABLE us_standard_financials (
    cik VARCHAR(10) NOT NULL,
    report_period DATE NOT NULL,       -- 분기 말일
    filed_dt DATE NOT NULL,            -- 공시일 (Point-in-Time)
    
    -- [1] Balance Sheet
    total_assets DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,       -- EV 계산용 (단기+장기차입금)
    shares_outstanding DOUBLE PRECISION,
    
    -- [2] Income Statement (R&D, 이자비용 추가)
    revenue DOUBLE PRECISION,
    gross_profit DOUBLE PRECISION,     -- GP/A 전략용
    op_income DOUBLE PRECISION,
    rnd_expense DOUBLE PRECISION,      -- 성장주 분석 핵심
    interest_expense DOUBLE PRECISION, -- 이자보상배율용
    net_income DOUBLE PRECISION,
    ebitda DOUBLE PRECISION,           -- (파생) EBITDA
    
    -- [3] Cash Flow
    ocf DOUBLE PRECISION,              -- 영업활동현금흐름
    capex DOUBLE PRECISION,            -- 자본지출 (FCF 계산용)
    fcf DOUBLE PRECISION,              -- 잉여현금흐름
    
    is_restated BOOLEAN DEFAULT FALSE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR(10),
    
    PRIMARY KEY (cik, report_period, filed_dt)
);

-- [6.5] 주식 수 이력 (PIT)
CREATE TABLE us_share_history (
    cik VARCHAR(10) NOT NULL,
    filed_dt DATE NOT NULL,
    val DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, filed_dt)
);
```

### 3.3 시세 및 팩터 (KDMS 역산 모델)

```sql
-- 5. 일봉 시세 (Raw Data Only - Hypertable)
CREATE TABLE us_daily_price (
    dt DATE NOT NULL,
    cik VARCHAR(10) NOT NULL,
    cls_prc DOUBLE PRECISION,          -- 수정되지 않은 Raw Close
    vol BIGINT DEFAULT 0,
    amt DOUBLE PRECISION DEFAULT 0.0,
    PRIMARY KEY (dt, cik)
);

-- 6. 가격 수정 팩터 (Split/Dividend 역산용)
CREATE TABLE us_price_adjustment_factors (
    cik VARCHAR(10) NOT NULL,
    event_dt DATE NOT NULL,            -- 이벤트 발생일
    factor_val DOUBLE PRECISION NOT NULL, -- 수정계수
    event_type VARCHAR(20),            -- DIVIDEND, SPLIT
    matched_info TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, event_dt)
);
```

### 3.4 퀀트 지표 (Valuation Engine 산출물)

```sql
-- 7. 가치평가 및 퀄리티 지표 (Daily Updated - Hypertable)
CREATE TABLE us_daily_valuation (
    dt DATE NOT NULL,
    cik VARCHAR(10) NOT NULL,
    mkt_cap DOUBLE PRECISION,
    pe DOUBLE PRECISION,      -- PER
    pb DOUBLE PRECISION,      -- PBR
    ps DOUBLE PRECISION,      -- PSR
    pcr DOUBLE PRECISION,     -- PCR
    ev_ebitda DOUBLE PRECISION,
    PRIMARY KEY (dt, cik)
);
-- Chunk time interval Optimized to 52 weeks

-- 8. 재무 비율 (Standard Table - us_financial_metrics)
CREATE TABLE us_financial_metrics (
    cik VARCHAR(10) NOT NULL,
    report_period DATE NOT NULL,
    filed_dt DATE NOT NULL,   -- PIT Key

    -- Profitability
    roe DOUBLE PRECISION,
    roa DOUBLE PRECISION,
    roic DOUBLE PRECISION,
    op_margin DOUBLE PRECISION,
    net_margin DOUBLE PRECISION,

    -- Quality & Stability
    gp_a_ratio DOUBLE PRECISION,        -- Gross Profit / Total Assets
    debt_ratio DOUBLE PRECISION,
    current_ratio DOUBLE PRECISION,
    interest_coverage DOUBLE PRECISION, -- Op Income / Interest Expense

    -- Growth
    rev_growth_yoy DOUBLE PRECISION,
    op_growth_yoy DOUBLE PRECISION,
    eps_growth_yoy DOUBLE PRECISION,

    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, report_period, filed_dt)
);
```

## 4. 모듈별 상세 구현 명세 (Planned)

### Module 1: Master Sync
- **Source**: SEC Archives (master.idx)
- **Logic**: Index Parsing -> Ticker Mapping -> DB Sync.

### Module 2: Financial Parser
- **Step 1**: Raw Collection (SEC API).
- **Step 2**: Standardization (Mapping tags to standard fields).

### Module 3: Market Loader
- **Logic**: KIS API (Adj Close) / Raw Comparison -> Factor Generation.

### Module 4: Valuation Engine
- **Logic**: PIT Matching (Price + Financials) -> Ratio Calculation.

## 5. 단계별 실행 로드맵 (8주 완성)

(기준: 명세서 v4.1 계획)
|**단계**|**기간**|**주요 과제**|
|---|---|---|
|**Phase 1**|1주|인프라 & 마스터 구축|
|**Phase 2**|3주|재무 파서 & 표준화|
|**Phase 3**|2주|시세 수집 & 역산|
|**Phase 4**|2주|Valuation 엔진|

## 6. 결론
본 플랫폼은 기관 수준의 딥 데이터(R&D, FCF)와 무결점 시세 DB를 제공합니다.

---

## 7. 구현 현황 및 계획과의 차이 (Implementation Reality & Deviations)

**[중요]** 현재(v4.5) 구현된 시스템은 운영 효율성과 데이터 품질을 위해 다음과 같이 구체화/변경되었습니다.

### 7.1 Schema Changes (누락된 테이블 반영)
*   **`us_collection_blacklist` (추가):** SEC 403 에러, 파싱 불가, 데이터 없음 등 예외 상황을 영구/일시적으로 관리하기 위한 테이블이 추가되었습니다.
*   **`us_share_history` (추가):** 정확한 시가총액 산출을 위해 재무제표의 `DEI` 태그에서 주식 수(Shares Outstanding)만을 별도로 추출하여 PIT로 관리합니다.
*   **`us_financial_metrics` (추가):** Valuation 외에 ROE, ROA, 부채비율 등 재무 건전성 지표를 별도 보관하는 테이블이 구현되었습니다.

### 7.2 Ticker Policy (노이즈 관리)
*   **Plan:** 무조건적인 이력 보존 (SCD Type 2).
*   **Actual:** **Intraday Noise Deletion**. 장중 일시적 티커 변경(`Start > Yesterday`)은 보존 가치가 없으므로 즉시 삭제하여 DB 오염을 방지합니다.

### 7.3 Financial Standardization (복잡도 증가)
*   **Plan:** 단순 태그 매핑.
*   **Actual:** **Fiscal Year/Period Grouping**.
    *   BS(대차대조표)와 IS(손익계산서)의 보고 시점 차이(`Instant` vs `Duration`)를 해결하기 위해, `(FY, FP)` 기준으로 데이터를 그룹화하고 YTD 값을 분기별 이산 값(Discrete)으로 변환하는 로직이 추가되었습니다.
    *   **Known Issue (8-K Gap):** XBRL 데이터가 없는 8-K 공시만 존재하는 기간에는 `MAX(filed_dt)`가 갱신되지 않아 Gap Scan이 반복되는 구조적 한계가 있으며, Blacklist로 방어 중입니다.

### 7.4 Price Adjustment (역산 로직 단순화)
*   **Plan:** 외부 캘린더 데이터(배당/분할일)와 대조하여 검증.
*   **Actual:** **Ratio-Based Only**.
    *   무료 외부 캘린더 데이터의 신뢰도 문제로 인해, 1차적으로 `Adj Close / Close` 비율 변동만을 감지하여 팩터를 생성합니다. 이는 외부 의존성을 줄이기 위함입니다.

### 7.5 Database Optimization (TimescaleDB)
*   **Plan:** 일반적인 Insert.
*   **Actual:** **Chunk & Batch Management**.
    *   `us_daily_valuation` 등의 Hypertable은 Lock Contention 방지를 위해 Chunk 단위를 수정(1년)하고, Application Level에서 Batch Commit 및 Connection Reset을 강제합니다.