# 인터페이스: USDMS DB 스키마 (db_schema.md)

> **소스 파일**: `migration_pjt/usdms_origin/docs/spec_usdms_core_logic.md`, `docs/plan_usdms_roadmap.md`
> **현재 버전**: v5.0 (Production As-Built)
> **마지막 업데이트**: 2026-04-28

---

## 핵심 테이블 목록 (9개)

### A. 마스터 & 이력

#### 1. `us_ticker_master` — 종목 마스터 (CIK 중심)
```sql
PRIMARY KEY: cik VARCHAR(10)    -- Zero-padded 불변 식별자 (예: '0000320193')

Fields:
  latest_ticker   VARCHAR(10)          -- 최신 티커
  latest_name     VARCHAR(255)         -- 최신 법인명
  exchange        VARCHAR(20)          -- NYSE / NASDAQ / AMEX / OTC / OTHER
  sic_code        VARCHAR(10)          -- 산업 분류 코드
  sector          VARCHAR(100)         -- GICS/SIC Sector
  industry        VARCHAR(100)         -- GICS/SIC Industry
  country         VARCHAR(100)         -- 본사 소재지
  quote_type      VARCHAR(20)          -- EQUITY / ETF / MUTUALFUND
  market_cap      DOUBLE PRECISION     -- 최신 시가총액 (Daily Update)
  current_price   DOUBLE PRECISION     -- 최신 주가 (Daily Update)
  is_active       BOOLEAN DEFAULT TRUE        -- 상장 유지 여부
  is_collect_target BOOLEAN DEFAULT FALSE     -- [핵심] 수집/분석 대상 여부
  first_seen_dt   DATE
  last_seen_dt    DATE
  created_at      TIMESTAMP DEFAULT NOW()
  updated_at      TIMESTAMP DEFAULT NOW()
```

#### 2. `us_ticker_history` — 티커 변경 이력 (SCD Type 2)
```sql
PRIMARY KEY: id SERIAL
UNIQUE: (cik, ticker, start_dt)

Fields:
  cik         VARCHAR(10) REFERENCES us_ticker_master(cik)
  ticker      VARCHAR(10)
  start_dt    DATE                     -- 해당 티커 사용 시작일
  end_dt      DATE DEFAULT '9999-12-31' -- 해당 티커 사용 종료일
```
> ⚠️ **Noise Deletion**: `start_dt > Yesterday` 인 당일 생성/종료 레코드는 DELETE 처리 (장중 일시적 변경 노이즈 제거)

#### 3. `us_collection_blacklist` — 수집 차단 목록
```sql
PRIMARY KEY: cik VARCHAR(10)

Fields:
  ticker          VARCHAR(10)
  reason_code     VARCHAR(50)  -- SEC_403 / PARSE_ERROR / NO_DATA / EMPTY_FILING
  reason_detail   TEXT
  is_blocked      BOOLEAN DEFAULT TRUE    -- TRUE: 영구 차단, FALSE: 재시도 가능
  fail_count      INTEGER DEFAULT 0
  last_failed_at  TIMESTAMP
  last_verified_at TIMESTAMP
  admin_note      TEXT
```

### B. 재무 데이터 (2-Layer)

#### 4. `us_financial_facts` — Raw XBRL 저장소 (EAV 모델)
```sql
PRIMARY KEY: fact_id BIGSERIAL

Fields:
  cik           VARCHAR(10)
  tag           VARCHAR(255)   -- XBRL Tag (예: Assets, NetIncomeLoss)
  val           DOUBLE PRECISION
  period_start  DATE           -- 기간 시작일 (Duration 항목용)
  period_end    DATE NOT NULL   -- 기간 종료일 (Key)
  filed_dt      DATE NOT NULL   -- 공시일 (Point-in-Time Key)
  frame         VARCHAR(50)    -- XBRL Frame (예: CY2023Q4)
  fy            DOUBLE PRECISION
  fp            VARCHAR(10)    -- FY / Q1 / Q2 / Q3
  form          VARCHAR(10)    -- 10-K / 10-Q
```

#### 5. `us_standard_financials` — 표준화 재무 데이터 (Analysis Ready)
```sql
PRIMARY KEY: (cik, report_period DATE, filed_dt DATE)

Fields:
  fiscal_year    INTEGER
  fiscal_period  VARCHAR(10)

  -- [1] Balance Sheet (Instant)
  total_assets            DOUBLE PRECISION
  total_debt              DOUBLE PRECISION   -- EV 계산용 (단기+장기차입금)
  shares_outstanding      DOUBLE PRECISION

  -- [2] Income Statement (Duration)
  revenue         DOUBLE PRECISION
  gross_profit    DOUBLE PRECISION    -- GP/A 전략용
  op_income       DOUBLE PRECISION
  rnd_expense     DOUBLE PRECISION    -- 성장주 분석
  interest_expense DOUBLE PRECISION   -- 이자보상배율
  net_income      DOUBLE PRECISION
  ebitda          DOUBLE PRECISION    -- (파생) OpIncome + Dep/Amor

  -- [3] Cash Flow (Duration)
  ocf     DOUBLE PRECISION    -- 영업활동현금흐름
  capex   DOUBLE PRECISION    -- 자본지출
  fcf     DOUBLE PRECISION    -- 잉여현금흐름 (OCF - Capex)

  is_restated  BOOLEAN DEFAULT FALSE
```

#### 6. `us_share_history` — 주식 수 이력 (PIT)
```sql
PRIMARY KEY: (cik, filed_dt DATE)
Field: val DOUBLE PRECISION  -- EntityCommonStockSharesOutstanding
```

### C. 시세 & 팩터 (KDMS 역산 모델 동일)

#### 7. `us_daily_price` — 일봉 원본 시세 (Hypertable)
```sql
PRIMARY KEY: (dt DATE, cik VARCHAR(10))
Chunk Size: 1 day (1,000+ chunks 스케일링 최적화)

Fields:
  ticker    VARCHAR(10)        -- 데이터 추적 편의
  open_prc  DOUBLE PRECISION NOT NULL
  high_prc  DOUBLE PRECISION NOT NULL
  low_prc   DOUBLE PRECISION NOT NULL
  cls_prc   DOUBLE PRECISION NOT NULL   -- Raw (미수정)
  vol       BIGINT DEFAULT 0
  amt       DOUBLE PRECISION DEFAULT 0.0
```

#### 8. `us_price_adjustment_factors` — 가격 수정 팩터
```sql
PRIMARY KEY: (cik, event_dt DATE)

Fields:
  factor_val   DOUBLE PRECISION NOT NULL  -- 수정비율 (Adj / Close)
  event_type   VARCHAR(20)               -- DIVIDEND / SPLIT
  matched_info TEXT                       -- 디버그 정보
```

### D. 퀀트 지표 (Valuation Engine 산출물)

#### 9. `us_daily_valuation` — 가치평가 지표 (Daily - Hypertable)
```sql
PRIMARY KEY: (dt DATE, cik VARCHAR(10))
Chunk Size: 52 weeks (Lock Contention 최적화)

Fields:
  mkt_cap   DOUBLE PRECISION   -- 시가총액
  pe        DOUBLE PRECISION   -- PER
  pb        DOUBLE PRECISION   -- PBR
  ps        DOUBLE PRECISION   -- PSR
  pcr       DOUBLE PRECISION   -- PCR (Price / OCF)
  ev_ebitda DOUBLE PRECISION   -- EV / EBITDA
```

#### 10. `us_financial_metrics` — 재무 비율
```sql
PRIMARY KEY: (cik, report_period DATE, filed_dt DATE)

Fields:
  -- Profitability: roe, roa, roic, op_margin, net_margin
  -- Quality: gp_a_ratio (Novy-Marx), debt_ratio, current_ratio, interest_coverage
  -- Growth: rev_growth_yoy, op_growth_yoy, eps_growth_yoy
```
