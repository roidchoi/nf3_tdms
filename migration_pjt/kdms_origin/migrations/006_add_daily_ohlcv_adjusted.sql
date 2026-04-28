-- migrations/006_add_daily_ohlcv_adjusted.sql
--
-- [Phase 1] daily_ohlcv_adjusted 테이블 신규 추가
-- KIS 팩터 기반 수정주가 일봉을 물리화(Materialized)하여 사용단에서 직접 조회 가능하게 함.
--
-- 실행 방법 (개발 DB):
--   psql -h localhost -U <POSTGRES_USER> -d kdms_db -f migrations/006_add_daily_ohlcv_adjusted.sql
--
-- 운영 서버 실행 방법:
--   docker exec -it kdms_timescaledb psql -U <POSTGRES_USER> -d kdms_db \
--     -f /path/to/migrations/006_add_daily_ohlcv_adjusted.sql

SET TIMEZONE = 'Asia/Seoul';

-- =================================================================
-- 1. 수정주가 일봉 물리화 테이블
-- =================================================================
CREATE TABLE IF NOT EXISTS daily_ohlcv_adjusted (
    dt          DATE NOT NULL,
    stk_cd      VARCHAR(6) NOT NULL,
    open_prc    NUMERIC(14, 2),   -- 수정 시가
    high_prc    NUMERIC(14, 2),   -- 수정 고가
    low_prc     NUMERIC(14, 2),   -- 수정 저가
    cls_prc     NUMERIC(14, 2),   -- 수정 종가
    vol         BIGINT,            -- 수정 거래량
    adj_factor  NUMERIC(18, 8),   -- 적용된 누적 수정계수 (감사 추적용)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dt, stk_cd)
);

COMMENT ON TABLE daily_ohlcv_adjusted
    IS 'KIS 팩터 기반 수정주가 일봉 물리화 테이블 (사용단 직접 조회용). daily_task 실행 시 자동 갱신됨.';
COMMENT ON COLUMN daily_ohlcv_adjusted.adj_factor
    IS '해당 날짜에 적용된 누적 수정계수 (1.0 = 보정 없음). 감사 추적 및 검증용.';

SELECT create_hypertable('daily_ohlcv_adjusted', 'dt', if_not_exists => TRUE);

-- 성능 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_adj_stk_cd_dt
    ON daily_ohlcv_adjusted (stk_cd, dt DESC);

-- =================================================================
-- 2. 완료 메시지
-- =================================================================
DO $$
BEGIN
    RAISE NOTICE '✅ [Migration 006] daily_ohlcv_adjusted 테이블 생성 완료.';
END $$;
