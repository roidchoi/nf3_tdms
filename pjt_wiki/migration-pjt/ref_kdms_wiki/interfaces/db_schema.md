# 인터페이스: KDMS DB 스키마 (db_schema.md)

> **소스 파일**: `migration_pjt/kdms_origin/init/init.sql`
> **연관 모듈**: `collectors/db_manager.py`
> **마지막 업데이트**: 2026-04-28

---

## 핵심 테이블 목록

### 1. `stock_info` — 종목 마스터
```sql
PRIMARY KEY: stk_cd (VARCHAR(6))
Fields:
  stk_nm        VARCHAR     -- 종목명
  market_type   VARCHAR     -- KOSPI / KOSDAQ
  status        VARCHAR     -- listed / delisted
  delist_dt     DATE        -- 상장폐지일
  list_dt       DATE        -- 상장일
  m_vol         BIGINT      -- 시장거래량
  cap           BIGINT      -- 시가총액
  update_dt     TIMESTAMP   -- 마지막 갱신일시
```

### 2. `daily_ohlcv` — 일봉 원본 시세 (Hypertable)
```sql
PRIMARY KEY: (dt DATE, stk_cd VARCHAR(6))
Partitioned By: dt (TimescaleDB hypertable)
Fields:
  open_prc    NUMERIC   -- 시가 (raw, 미수정)
  high_prc    NUMERIC   -- 고가
  low_prc     NUMERIC   -- 저가
  cls_prc     NUMERIC   -- 종가
  vol         BIGINT    -- 거래량
  amt         BIGINT    -- 거래대금
  turn_rt     NUMERIC   -- 회전율
```
> ⚠️ **수정주가는 저장하지 않음**. `price_adjustment_factors`를 이용해 역산.

### 3. `minute_ohlcv` — 분봉 시세 (Hypertable)
```sql
PRIMARY KEY: (dt_tm TIMESTAMPTZ, stk_cd VARCHAR(6))
Partitioned By: dt_tm (TimescaleDB hypertable)
Fields:
  open_prc, high_prc, low_prc, cls_prc  NUMERIC
  vol  BIGINT
```

### 4. `price_adjustment_factors` — 수정 계수 (PIT)
```sql
PRIMARY KEY: id BIGSERIAL
UNIQUE: (stk_cd, event_dt, price_source)
Fields:
  stk_cd        VARCHAR(6)
  event_dt      DATE           -- 이벤트 발생일 (분할/배당)
  price_ratio   NUMERIC        -- 주가 수정 승수
  volume_ratio  NUMERIC        -- 거래량 수정 승수
  price_source  VARCHAR        -- KIWOOM / KIS
  effective_dt  DATE           -- 이 팩터가 기록된 시점 (PIT 추적)
```

### 5. `financial_statements` — 재무제표 (PIT)
```sql
PRIMARY KEY: id BIGSERIAL
INDEX: (stk_cd, stac_yymm, div_cls_code, retrieved_at DESC)
Fields:
  retrieved_at   TIMESTAMPTZ  -- 수집 시점 (PIT Key)
  stac_yymm      VARCHAR(6)   -- 회계기간 (YYYYMM)
  div_cls_code   CHAR(1)      -- '0'=연간, '1'=분기
  -- Balance Sheet
  cras, fxas, total_aset, flow_lblt, fix_lblt, total_lblt, cpfn, total_cptl
  -- Income Statement
  sale_account, sale_cost, sale_totl_prfi, bsop_prti, op_prfi, thtr_ntin
```

### 6. `financial_ratios` — 재무비율 (PIT)
```sql
PRIMARY KEY: id BIGSERIAL
Fields:
  -- Profitability: roe_val, cptl_ntin_rate, sale_ntin_rate
  -- Growth: grs, bsop_prfi_inrt, ntin_inrt, equt_inrt, totl_aset_inrt
  -- Stability: lblt_rate, crnt_rate, quck_rate, bram_depn
  -- Valuation: eps, bps, sps, rsrv_rate
  -- Other: eva, ebitda, ev_ebitda
```

### 7. `system_milestones` — 데이터 신뢰도 이벤트
```sql
PRIMARY KEY: milestone_name VARCHAR
Fields:
  milestone_date  DATE
  description     TEXT
  updated_at      TIMESTAMP
-- 예: 'SYSTEM:SCHEMA:CREATED', 'DATA:DAILY:COMPLETE:2024-01-01'
```

### 8. `daily_market_cap` — 시가총액 (Hypertable, Phase 8 신규)
```sql
PRIMARY KEY: (dt DATE, stk_cd VARCHAR(6))
Partitioned By: dt (TimescaleDB hypertable)
Fields:
  cls_prc        NUMERIC   -- 종가
  mkt_cap        BIGINT    -- 시가총액
  vol            BIGINT    -- 거래량
  amt            BIGINT    -- 거래대금
  listed_shares  BIGINT    -- 상장주식수
INDEX: idx_daily_market_cap_stk_cd_dt (stk_cd, dt DESC)
-- 데이터 소스: pykrx.stock.get_market_cap_by_ticker()
-- 수집: 매일 17:10 (Phase 5/5), 주간 갭 복구 (최근 30일)
```

### 9. `minute_target_history` — 분봉 수집 대상 이력
```sql
PRIMARY KEY: (quarter VARCHAR, market VARCHAR, symbol VARCHAR(6))
Fields:
  avg_trade_value  NUMERIC   -- 평균 거래대금
  rank             INT       -- 순위
```
