-- US-DMS Database Schema (v5.0) - Synchronized with Live DB
-- Last Updated: 2025-12-12
-- Status: Finalized for Phase 3 (Financial & Valuation)

-- [1] 종목 마스터 (CIK Centric)
CREATE TABLE IF NOT EXISTS us_ticker_master (
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

CREATE INDEX IF NOT EXISTS idx_us_ticker_master_ticker ON us_ticker_master(latest_ticker);
CREATE INDEX IF NOT EXISTS idx_us_ticker_master_target ON us_ticker_master(is_collect_target);

-- [2] 티커 변경 이력
CREATE TABLE IF NOT EXISTS us_ticker_history (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) REFERENCES us_ticker_master(cik),
    ticker VARCHAR(10) NOT NULL,
    start_dt DATE NOT NULL,
    end_dt DATE DEFAULT '9999-12-31',
    UNIQUE(cik, ticker, start_dt)
);

-- [3] 일봉 시세 (Hypertable)
CREATE TABLE IF NOT EXISTS us_daily_price (
    dt DATE NOT NULL,
    cik VARCHAR(10) NOT NULL,
    ticker VARCHAR(10),                -- 당시 Ticker (Historical Ticker)
    open_prc DOUBLE PRECISION NOT NULL,
    high_prc DOUBLE PRECISION NOT NULL,
    low_prc DOUBLE PRECISION NOT NULL,
    cls_prc DOUBLE PRECISION NOT NULL, -- Raw Close
    vol BIGINT DEFAULT 0,
    amt DOUBLE PRECISION DEFAULT 0.0,
    PRIMARY KEY (dt, cik)
);

-- TimescaleDB Hypertable 변환
SELECT create_hypertable('us_daily_price', 'dt', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_us_daily_price_cik_dt ON us_daily_price(cik, dt DESC);

-- [4] 가격 수정 팩터 (역산용)
CREATE TABLE IF NOT EXISTS us_price_adjustment_factors (
    cik VARCHAR(10) NOT NULL,
    event_dt DATE NOT NULL,            -- 이벤트 발생일
    factor_val DOUBLE PRECISION NOT NULL, -- 수정계수
    event_type VARCHAR(20),            -- DIVIDEND, SPLIT
    matched_info TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, event_dt)
);

-- [5] 재무 데이터 (Raw XBRL Tags)
CREATE TABLE IF NOT EXISTS us_financial_facts (
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

CREATE INDEX IF NOT EXISTS idx_us_financial_facts_lookup ON us_financial_facts(cik, tag, filed_dt DESC);

-- [6] 재무 표준화 중간 테이블 (Standardized Financials)
CREATE TABLE IF NOT EXISTS us_standard_financials (
    cik VARCHAR(10) NOT NULL,
    report_period DATE NOT NULL,       -- 분기 말일
    filed_dt DATE NOT NULL,            -- 공시일 (Point-in-Time)
    
    -- [1] Balance Sheet
    total_assets DOUBLE PRECISION,
    current_assets DOUBLE PRECISION,
    cash_and_equiv DOUBLE PRECISION,
    inventory DOUBLE PRECISION,
    account_receivable DOUBLE PRECISION,
    
    total_equity DOUBLE PRECISION,
    retained_earnings DOUBLE PRECISION,
    
    total_liabilities DOUBLE PRECISION,
    current_liabilities DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,
    
    shares_outstanding DOUBLE PRECISION,

    -- [2] Income Statement
    revenue DOUBLE PRECISION,
    cogs DOUBLE PRECISION,
    gross_profit DOUBLE PRECISION,
    
    sgna_expense DOUBLE PRECISION,
    rnd_expense DOUBLE PRECISION,
    
    op_income DOUBLE PRECISION,
    interest_expense DOUBLE PRECISION,
    tax_provision DOUBLE PRECISION,
    net_income DOUBLE PRECISION,
    
    ebitda DOUBLE PRECISION,
    
    -- [3] Cash Flow
    ocf DOUBLE PRECISION,
    capex DOUBLE PRECISION,
    fcf DOUBLE PRECISION,
    
    is_restated BOOLEAN DEFAULT FALSE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR(10),
    
    PRIMARY KEY (cik, report_period, filed_dt)
);

CREATE INDEX IF NOT EXISTS idx_us_standard_financials_pit ON us_standard_financials(cik, filed_dt DESC);
CREATE INDEX IF NOT EXISTS idx_std_fin_fy_fp ON us_standard_financials(cik, fiscal_year, fiscal_period);

-- [6.5] 주식 수 이력 (PIT)
CREATE TABLE IF NOT EXISTS us_share_history (
    cik VARCHAR(10) NOT NULL,
    filed_dt DATE NOT NULL,
    val DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, filed_dt)
);
CREATE INDEX IF NOT EXISTS idx_us_share_history_pit ON us_share_history(cik, filed_dt DESC);


-- [7] 가치평가 (Daily Updated - Hypertable)
CREATE TABLE IF NOT EXISTS us_daily_valuation (
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
-- [핵심 변경] 청크 단위를 1년(52주)으로 설정하여 대량 Insert 시 Lock 부하 방지
SELECT create_hypertable('us_daily_valuation', 'dt', chunk_time_interval => INTERVAL '52 weeks', if_not_exists => TRUE);

-- [8] 재무 비율 (Standard Table)
CREATE TABLE IF NOT EXISTS us_financial_metrics (
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
CREATE INDEX IF NOT EXISTS idx_us_financial_metrics_pit ON us_financial_metrics(cik, filed_dt DESC);

-- [9] 수집 차단 목록 (Blacklist Management)
CREATE TABLE IF NOT EXISTS us_collection_blacklist (
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
CREATE INDEX IF NOT EXISTS idx_blacklist_status ON us_collection_blacklist(is_blocked);


-- [Analyst Role Setup]
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly_analyst') THEN
        CREATE ROLE readonly_analyst WITH LOGIN PASSWORD 'analyst_pass';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE usdms_db TO readonly_analyst;
GRANT USAGE ON SCHEMA public TO readonly_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_analyst;