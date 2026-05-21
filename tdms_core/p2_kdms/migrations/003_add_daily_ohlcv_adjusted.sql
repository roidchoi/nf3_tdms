-- migrations/003_add_daily_ohlcv_adjusted.sql

-- 1. daily_ohlcv_adjusted 테이블 생성
CREATE TABLE IF NOT EXISTS daily_ohlcv_adjusted (
    dt DATE NOT NULL,
    stk_cd VARCHAR(6) NOT NULL,
    open_prc INTEGER,
    high_prc INTEGER,
    low_prc INTEGER,
    cls_prc INTEGER,
    vol BIGINT,
    adj_factor NUMERIC NOT NULL DEFAULT 1.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dt, stk_cd)
);
COMMENT ON TABLE daily_ohlcv_adjusted IS '종목별 일봉 수정주가 물리 테이블';

-- TimescaleDB 하이퍼테이블로 변환
SELECT create_hypertable('daily_ohlcv_adjusted', 'dt', if_not_exists => TRUE);

-- 2. daily_ohlcv_gap 테이블 생성
CREATE TABLE IF NOT EXISTS daily_ohlcv_gap (
    stk_cd VARCHAR(6) NOT NULL,
    dt DATE NOT NULL,
    reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stk_cd, dt)
);
COMMENT ON TABLE daily_ohlcv_gap IS 'OHLCV 수집 누락(휴장일 등) 또는 실패 이력';
