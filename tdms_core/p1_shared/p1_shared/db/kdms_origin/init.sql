-- init/init.sql (Final Version with Milestone Management)

-- TimescaleDB 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 타임존을 한국 시간으로 설정
SET TIMEZONE = 'Asia/Seoul';

-- =================================================================
-- 1. 시스템 신뢰도 마일스톤 테이블
-- =================================================================
CREATE TABLE IF NOT EXISTS system_milestones (
    milestone_name VARCHAR(100) PRIMARY KEY,
    milestone_date DATE NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE system_milestones IS '데이터셋의 신뢰도와 관련된 주요 역사적 시점을 기록';

-- 데이터베이스 스키마가 최초로 생성된 시점을 자동으로 기록
INSERT INTO system_milestones (milestone_name, milestone_date, description) VALUES
    ('SYSTEM:SCHEMA:CREATED', CURRENT_DATE, '데이터베이스 스키마가 최초로 생성된 날짜.')
ON CONFLICT (milestone_name) DO NOTHING;

-- =================================================================
-- 2. 종목 정보 테이블
-- =================================================================
CREATE TABLE IF NOT EXISTS stock_info (
    stk_cd VARCHAR(6) PRIMARY KEY,
    stk_nm VARCHAR(100) NOT NULL,
    market_type VARCHAR(10),
    status VARCHAR(20) DEFAULT 'listed' NOT NULL, -- 'listed', 'delisted' 등
    delist_dt DATE,                                -- 상장 폐지일
    list_dt DATE,
    m_vol BIGINT,
    cap BIGINT,
    update_dt DATE
);
COMMENT ON TABLE stock_info IS 'KOSPI/KOSDAQ 종목 기본 정보 (상폐 포함)';

-- =================================================================
-- 3. 시세 데이터 테이블 (순수 데이터)
-- =================================================================
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    dt DATE NOT NULL,
    stk_cd VARCHAR(6) NOT NULL,
    open_prc INTEGER, high_prc INTEGER, low_prc INTEGER, cls_prc INTEGER,
    vol BIGINT, amt BIGINT,
    turn_rt NUMERIC(10, 2), -- [추가] 거래회전율
    PRIMARY KEY (dt, stk_cd)
);
COMMENT ON TABLE daily_ohlcv IS '종목별 일봉 OHLCV 원본 데이터';
SELECT create_hypertable('daily_ohlcv', 'dt', if_not_exists => TRUE);

-- 초기 구축 시에만 사용하는 참고용 수정주가 테이블
CREATE TABLE IF NOT EXISTS daily_ohlcv_adjusted_legacy (
    dt DATE NOT NULL, stk_cd VARCHAR(6) NOT NULL,
    open_prc INTEGER, high_prc INTEGER, low_prc INTEGER, cls_prc INTEGER,
    vol BIGINT, amt BIGINT,
    turn_rt NUMERIC(10, 2), -- [추가] 거래회전율
    PRIMARY KEY (dt, stk_cd)
);
COMMENT ON TABLE daily_ohlcv_adjusted_legacy IS '초기 구축 시 수집한 참고용 수정주가 일봉 데이터';
SELECT create_hypertable('daily_ohlcv_adjusted_legacy', 'dt', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS minute_ohlcv (
    dt_tm TIMESTAMPTZ NOT NULL,
    stk_cd VARCHAR(6) NOT NULL,
    open_prc INTEGER, high_prc INTEGER, low_prc INTEGER, cls_prc INTEGER,
    vol BIGINT,
    PRIMARY KEY (dt_tm, stk_cd)
);
COMMENT ON TABLE minute_ohlcv IS '선별 종목 1분봉 OHLCV 원본 데이터';
SELECT create_hypertable('minute_ohlcv', 'dt_tm', if_not_exists => TRUE);

-- =================================================================
-- 4. 수정주가 계산용 종목 이력 및 factors 테이블
-- =================================================================
CREATE TABLE price_adjustment_factors (
    -- 1. 기본 식별자
    id BIGSERIAL PRIMARY KEY,
    stk_cd VARCHAR(6) NOT NULL,
    
    -- 2. 팩터 기준일 (이벤트가 발생한 날짜)
    event_dt DATE NOT NULL,
    
    -- 3. 팩터 값 (핵심 데이터)
    price_ratio NUMERIC NOT NULL,
    volume_ratio NUMERIC NOT NULL,
    
    -- 4. 데이터 근거 (신뢰성 및 추적성)
    price_source VARCHAR(20) NOT NULL,  -- 예: 'KIWOOM', 'KIS'
    details JSONB,                      -- 계산에 사용된 실제 값 (예: {'raw_close': 50000, ...})
    
    -- 5. PIT(Point-in-Time) 구현의 핵심
    effective_dt TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 이 팩터가 시스템에 반영된 시점

    -- 데이터 무결성을 위한 복합 UNIQUE 제약 조건
    CONSTRAINT uq_paf_stock_event_source UNIQUE (stk_cd, event_dt, price_source)
);

-- 3. 주석 및 인덱스 추가
COMMENT ON TABLE price_adjustment_factors IS '시세 역산을 통해 계산된 수정계수(Adjustment Factors) 마스터 테이블';
COMMENT ON COLUMN price_adjustment_factors.event_dt IS '수정계수 변경이 실제로 발생한 날짜 (Price Ratio가 1이 아닌 날짜)';
COMMENT ON COLUMN price_adjustment_factors.price_source IS '이 팩터를 계산하는 데 사용된 시세 데이터의 출처 (예: KIWOOM)';
COMMENT ON COLUMN price_adjustment_factors.effective_dt IS '이 팩터 정보가 시스템에 반영된 시점 (PIT 조회 기준)';
COMMENT ON COLUMN price_adjustment_factors.details IS '계산 근거가 된 원본/수정 종가 등 상세 정보';

CREATE INDEX IF NOT EXISTS idx_paf_stock_event_dt ON price_adjustment_factors (stk_cd, event_dt DESC);
CREATE INDEX IF NOT EXISTS idx_paf_effective_dt ON price_adjustment_factors (effective_dt DESC);

-- =================================================================
-- 5. 분봉 수집 대상 이력 테이블
-- =================================================================
CREATE TABLE IF NOT EXISTS minute_target_history (
    quarter VARCHAR(6) NOT NULL, -- (YYYYQN, 예: 2024Q1)
    market VARCHAR(10) NOT NULL, -- (KOSPI/KOSDAQ)
    symbol VARCHAR(20) NOT NULL, -- 종목코드
    avg_trade_value BIGINT,      -- 해당 분기 일평균 거래대금
    rank INTEGER,                -- 시장 내 순위
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (quarter, market, symbol)
);
COMMENT ON TABLE minute_target_history IS '분기별 분봉 데이터 수집 대상 종목 선정 이력';
CREATE INDEX idx_target_quarter ON minute_target_history (quarter, market, rank);

-- =================================================================
-- 6. 거래일 캘린더 (KIS API 캐시)
-- =================================================================
CREATE TABLE IF NOT EXISTS trading_calendar (
    dt DATE NOT NULL PRIMARY KEY,
    opnd_yn CHAR(1) NOT NULL, -- 'Y' or 'N'
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE trading_calendar IS 'KIS API(CTCA0903R)에서 수집한 휴장일 정보 캐시';
COMMENT ON COLUMN trading_calendar.opnd_yn IS '개장일여부 (Y/N)';

-- =================================================================
-- 7. KIS 재무제표 (BS: 대차대조표, IS: 손익계산서) (v5.5 - NUMERIC 타입 적용)
-- =================================================================
CREATE TABLE IF NOT EXISTS financial_statements (
    -- 1. 버전 식별자 (PK)
    id BIGSERIAL PRIMARY KEY,
    -- 2. PIT (Point-in-Time) 기준 시점
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 3. 비즈니스 키
    stk_cd VARCHAR(6) NOT NULL,
    stac_yymm VARCHAR(6) NOT NULL,    -- 결산년월
    div_cls_code VARCHAR(1) NOT NULL, -- '0': 연간, '1': 분기

    -- 4. BS (대차대조표)
    cras NUMERIC,         -- 유동자산 (BIGINT -> NUMERIC)
    fxas NUMERIC,         -- 고정자산 (BIGINT -> NUMERIC)
    total_aset NUMERIC,   -- 자산총계 (BIGINT -> NUMERIC)
    flow_lblt NUMERIC,    -- 유동부채 (BIGINT -> NUMERIC)
    fix_lblt NUMERIC,     -- 고정부채 (BIGINT -> NUMERIC)
    total_lblt NUMERIC,   -- 부채총계 (BIGINT -> NUMERIC)
    cpfn NUMERIC,         -- 자본금 (BIGINT -> NUMERIC)
    total_cptl NUMERIC,   -- 자본총계 (BIGINT -> NUMERIC)

    -- 5. IS (손익계산서)
    sale_account NUMERIC,   -- 매출액 (BIGINT -> NUMERIC)
    sale_cost NUMERIC,      -- 매출원가 (BIGINT -> NUMERIC)
    sale_totl_prfi NUMERIC, -- 매출총이익 (BIGINT -> NUMERIC)
    bsop_prti NUMERIC,      -- 영업이익 (BIGINT -> NUMERIC)
    op_prfi NUMERIC,        -- 경상이익 (BIGINT -> NUMERIC)
    thtr_ntin NUMERIC       -- 당기순이익 (BIGINT -> NUMERIC)
    -- spec_prfi, spec_loss 는 더미 값이므로 제외
);
COMMENT ON TABLE financial_statements IS 'KIS 재무제표 (대차대조표, 손익계산서) 통합 테이블 (PIT, v5.5)';
-- (필수) 최신 버전 조회를 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_fs_lookup ON financial_statements (stk_cd, stac_yymm, div_cls_code, retrieved_at DESC);

-- =================================================================
-- 8. KIS 재무비율 (통합) (PIT 버전 관리 적용)
-- =================================================================
CREATE TABLE IF NOT EXISTS financial_ratios (
    -- 1. 버전 식별자 (PK)
    id BIGSERIAL PRIMARY KEY,
    -- 2. PIT (Point-in-Time) 기준 시점
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 3. 비즈니스 키
    stk_cd VARCHAR(6) NOT NULL,
    stac_yymm VARCHAR(6) NOT NULL,    -- 결산년월
    div_cls_code VARCHAR(1) NOT NULL, -- '0': 연간, '1': 분기

    -- 4. 재무비율 (FHKST66430300)
    grs NUMERIC,             -- 매출액증가율
    bsop_prfi_inrt NUMERIC,  -- 영업이익증가율
    ntin_inrt NUMERIC,       -- 순이익증가율
    roe_val NUMERIC,         -- ROE
    eps NUMERIC,
    sps NUMERIC,             -- 주당매출액
    bps NUMERIC,
    rsrv_rate NUMERIC,       -- 유보비율
    lblt_rate NUMERIC,       -- 부채비율

    -- 5. 수익성비율 (FHKST66430400)
    cptl_ntin_rate NUMERIC,      -- 총자본순이익율
    self_cptl_ntin_inrt NUMERIC, -- 자기자본순이익율
    sale_ntin_rate NUMERIC,      -- 매출액순이익율
    sale_totl_rate NUMERIC,      -- 매출액총이익율

    -- 6. 기타주요비율 (FHKST66430500)
    eva NUMERIC,
    ebitda NUMERIC,
    ev_ebitda NUMERIC,
    -- payout_rate는 '비정상'으로 명시되어 제외

    -- 7. 안정성비율 (FHKST66430600)
    -- lblt_rate (중복)
    bram_depn NUMERIC,       -- 차입금의존도
    crnt_rate NUMERIC,       -- 유동비율
    quck_rate NUMERIC,       -- 당좌비율

    -- 8. 성장성비율 (FHKST66430800)
    -- grs (중복)
    -- bsop_prfi_inrt (중복)
    equt_inrt NUMERIC,       -- 자기자본증가율
    totl_aset_inrt NUMERIC   -- 총자산증가율
);
COMMENT ON TABLE financial_ratios IS 'KIS 재무비율 (재무, 수익성, 안정성, 성장성, 기타) 통합 테이블 (PIT 버전 관리)';
COMMENT ON COLUMN financial_ratios.retrieved_at IS '이 재무 데이터 버전을 수집(조회)한 시점';
-- (필수) 최신 버전 조회를 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_fr_lookup ON financial_ratios (stk_cd, stac_yymm, div_cls_code, retrieved_at DESC);

-- =================================================================
-- 9. API 성능 최적화 인덱스 (PRD 8.2.1)
-- =================================================================

-- [성능 개선 1] 분봉 조회 API (GET /ohlcv/minute/{stk_cd})
CREATE INDEX IF NOT EXISTS idx_minute_ohlcv_stk_cd_dt_tm
    ON minute_ohlcv (stk_cd, dt_tm DESC);

-- [성능 개선 2] 일봉 조회 API (GET /ohlcv/daily/{stk_cd})
CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_stk_cd_dt
    ON daily_ohlcv (stk_cd, dt DESC);

-- [성능 개선 3] 재무 스크리닝 API (GET /financials/screening)
CREATE INDEX IF NOT EXISTS idx_fs_pit_screening
    ON financial_statements (stac_yymm, div_cls_code, retrieved_at DESC, stk_cd);

-- [성능 개선 4] 재무비율 스크리닝 API (GET /financials/screening)
CREATE INDEX IF NOT EXISTS idx_fr_pit_screening
    ON financial_ratios (stac_yymm, div_cls_code, retrieved_at DESC, stk_cd);

-- [성능 개선 5] 종목 조회 API (GET /data/stocks)
CREATE INDEX IF NOT EXISTS idx_stock_info_market_status
    ON stock_info (market_type, status, stk_cd);

-- 사용자 및 권한
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'collector') THEN
        CREATE USER collector WITH PASSWORD 'collector_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analyst') THEN
        CREATE USER analyst WITH PASSWORD 'analyst_password';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE kdms_db TO collector;
GRANT USAGE ON SCHEMA public TO collector;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO collector;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collector;

GRANT CONNECT ON DATABASE kdms_db TO analyst;
GRANT USAGE ON SCHEMA public TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst;

-- =================================================================
-- 10. KRX 시가총액 데이터 (pykrx)
-- =================================================================
CREATE TABLE IF NOT EXISTS daily_market_cap (
    dt DATE NOT NULL,
    stk_cd VARCHAR(6) NOT NULL,
    cls_prc BIGINT,           -- 종가
    mkt_cap BIGINT,           -- 시가총액 (백만원)
    vol BIGINT,               -- 거래량
    amt BIGINT,               -- 거래대금 (백만원)
    listed_shares BIGINT,     -- 상장주식수
    PRIMARY KEY (dt, stk_cd)
);
COMMENT ON TABLE daily_market_cap IS 'pykrx로 수집한 일별 시가총액 및 상장주식수 데이터';
SELECT create_hypertable('daily_market_cap', 'dt', if_not_exists => TRUE);

-- 성능 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_daily_market_cap_stk_cd_dt
    ON daily_market_cap (stk_cd, dt DESC);

-- 완료 메시지
DO $$
BEGIN
    RAISE NOTICE '✅ [PIT Milestone Final] 데이터베이스 초기화가 성공적으로 완료되었습니다!';
END $$;