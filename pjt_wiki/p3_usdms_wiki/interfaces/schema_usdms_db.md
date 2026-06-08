# usdms_timescaledb DB 스키마 (schema_usdms_db.md)

> **DB**: `usdms_db`
> **컨테이너**: `usdms_timescaledb`
> **포트**: `5433`
> **사용자**: `postgres` (or `readonly_analyst`)
> **볼륨**: `usdms_pgdata` (external: true)
> **마지막 업데이트**: 2026-06-08
> **관련**: `[[p3_usdms_wiki/interfaces/master_repo.md]]`, `[[p3_usdms_wiki/interfaces/financial_repo.md]]`, `[[p3_usdms_wiki/interfaces/valuation_repo.md]]`, `[[p3_usdms_wiki/interfaces/daily_routine.md]]`

---

## 개요

| 항목 | 내용 |
|---|---|
| 총 테이블 수 | 11개 |
| TimescaleDB 하이퍼테이블 | 2개 (`us_daily_price`, `us_daily_valuation`) |
| 일반 테이블 | 9개 |

---

## TimescaleDB 하이퍼테이블 목록

| 테이블명 | 파티션 기준 컬럼 | 청크 시간 간격 (Chunk Interval) |
|---|---|---|
| `us_daily_price` | `dt` | 7일 (기본값) |
| `us_daily_valuation` | `dt` | 52주 (1년) |

---

## 테이블 상세 스키마

---

### 1. `us_ticker_master` — 종목 마스터 (CIK Centric)

> SEC EDGAR의 CIK(Central Index Key)를 기본키로 사용하는 미국 주식 종목 마스터 테이블.

```sql
CREATE TABLE us_ticker_master (
    cik               VARCHAR(10) PRIMARY KEY,       -- CIK 식별자 (Zero-padded, 10자리)
    latest_ticker     VARCHAR(10),                   -- 최신 티커 심볼
    latest_name       VARCHAR(255),                  -- 최신 사명
    exchange          VARCHAR(20),                   -- 상장 거래소 (NYSE, NASDAQ, AMEX, OTC 등)
    sic_code          VARCHAR(10),                   -- 산업 표준 분류 코드
    sector            VARCHAR(100),                  -- GICS/SIC Sector 분류
    market_cap        DOUBLE PRECISION,              -- 시가총액 (USD)
    current_price     DOUBLE PRECISION,              -- 현재가 (USD)
    quote_type        VARCHAR(20),                   -- 자산 종류 (EQUITY, ETF 등)
    is_collect_target BOOLEAN DEFAULT FALSE,         -- 데이터 수집 대상 여부
    country           VARCHAR(100),                  -- 국가명
    industry          VARCHAR(100),                  -- 세부 산업군
    is_active         BOOLEAN DEFAULT TRUE NOT NULL, -- 활성 여부
    first_seen_dt     DATE,                          -- 시스템 최초 감지일
    last_seen_dt      DATE,                          -- 시스템 마지막 감지일
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_ticker_master_pkey` | `cik` | PRIMARY KEY (btree) | 고유 식별자 PK 조회 |
| `idx_us_ticker_master_ticker` | `latest_ticker` | btree | 티커명을 활용한 종목 고속 조회 |
| `idx_us_ticker_master_target` | `is_collect_target` | btree | 일일 수집 타겟 필터링 최적화 |

---

### 2. `us_ticker_history` — 티커 변경 이력

> CIK 주체에 매핑되는 티커의 유효 기간(SCD Type 2)을 관리하는 테이블.

```sql
CREATE TABLE us_ticker_history (
    id        SERIAL PRIMARY KEY,
    cik       VARCHAR(10) REFERENCES us_ticker_master(cik),
    ticker    VARCHAR(10) NOT NULL,
    start_dt  DATE NOT NULL,
    end_dt    DATE DEFAULT '9999-12-31',
    UNIQUE(cik, ticker, start_dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_ticker_history_pkey` | `id` | PRIMARY KEY (btree) | 대리키 PK 조회 |
| `us_ticker_history_cik_ticker_start_dt_key` | `(cik, ticker, start_dt)` | UNIQUE (btree) | 특정 시점 CIK의 티커 유일성 제약 및 룩업 |

---

### 3. `us_daily_price` — 일봉 시세 (하이퍼테이블)

> 미국 종목별 원본 일봉 시세 데이터.

```sql
CREATE TABLE us_daily_price (
    dt        DATE NOT NULL,
    cik       VARCHAR(10) NOT NULL,
    ticker    VARCHAR(10),                -- 거래 당시의 티커명
    open_prc  DOUBLE PRECISION NOT NULL,  -- 시가
    high_prc  DOUBLE PRECISION NOT NULL,  -- 고가
    low_prc   DOUBLE PRECISION NOT NULL,  -- 저가
    cls_prc   DOUBLE PRECISION NOT NULL,  -- 종가 (Raw Close)
    vol       BIGINT DEFAULT 0,           -- 거래량
    amt       DOUBLE PRECISION DEFAULT 0.0, -- 거래대금
    PRIMARY KEY (dt, cik)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_daily_price_pkey` | `(dt, cik)` | PRIMARY KEY (btree) | 기본 키 및 Timescale 파티션 키 |
| `us_daily_price_dt_idx1` | `dt DESC` | btree | 시계열 범위 검색 및 정렬 최적화 |
| `idx_us_daily_price_cik_dt` | `(cik, dt DESC)` | btree | 종목별 최근 주가 조회 최적화 |

---

### 4. `us_price_adjustment_factors` — 가격 수정 팩터

> 주식 분할(Split) 및 배당(Dividend)에 따른 가격 역산용 수정 비율 정보.

```sql
CREATE TABLE us_price_adjustment_factors (
    cik          VARCHAR(10) NOT NULL,
    event_dt     DATE NOT NULL,            -- 이벤트 권리락 발생일
    factor_val   DOUBLE PRECISION NOT NULL, -- 수정계수 곱세인자
    event_type   VARCHAR(20),              -- SPLIT, DIVIDEND
    matched_info TEXT,
    created_at   TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, event_dt, event_type)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_price_adjustment_factors_pkey` | `(cik, event_dt, event_type)` | PRIMARY KEY (btree) | 이벤트 유일성 보장 및 룩업 |

---

### 5. `us_financial_facts` — 재무 원시 XBRL 태그 데이터

> SEC EDGAR XBRL facts 데이터의 원본을 고속으로 백필 및 파싱하기 위한 중계 저장 테이블.

```sql
CREATE TABLE us_financial_facts (
    fact_id      BIGSERIAL PRIMARY KEY,
    cik          VARCHAR(10) NOT NULL,
    tag          VARCHAR(255) NOT NULL,    -- US-GAAP / SEC 태그명
    val          DOUBLE PRECISION,         -- 금액 수치
    period_start DATE,                     -- 해당 재무 기간 시작일 (IS/CF인 경우)
    period_end   DATE NOT NULL,            -- 해당 재무 기간 마감일
    filed_dt     DATE NOT NULL,            -- 공시 일자 (PIT 버전관리 키)
    frame        VARCHAR(50),
    fy           DOUBLE PRECISION,         -- 결산 회계연도 (Fiscal Year)
    fp           VARCHAR(10),              -- 결산 분기 (Q1, Q2, Q3, FY 등)
    form         VARCHAR(10)               -- 공시 서식 (10-K, 10-Q 등)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_financial_facts_pkey` | `fact_id` | PRIMARY KEY (btree) | 대리키 조회 |
| `idx_us_financial_facts_lookup` | `(cik, tag, filed_dt DESC)` | btree | 특정 공시일(filed_dt) 기준 최신 팩트 룩업 |

---

### 6. `us_standard_financials` — 표준화 재무제표 (PIT)

> `us_financial_facts` 테이블로부터 표준 재무 필드를 매핑 및 정규화하여 도출한 PIT 기반 재무제표.

```sql
CREATE TABLE us_standard_financials (
    cik                VARCHAR(10) NOT NULL,
    report_period      DATE NOT NULL,       -- 보고서 대상 분기 마감일
    filed_dt           DATE NOT NULL,       -- 실제 공시일 (Point-in-Time Key)
    
    -- [1] Balance Sheet (대차대조표)
    total_assets       DOUBLE PRECISION,    -- 자산총계
    current_assets     DOUBLE PRECISION,    -- 유동자산
    cash_and_equiv     DOUBLE PRECISION,    -- 현금및현금성자산
    inventory          DOUBLE PRECISION,    -- 재고자산
    account_receivable DOUBLE PRECISION,    -- 매출채권
    total_equity       DOUBLE PRECISION,    -- 자본총계
    retained_earnings  DOUBLE PRECISION,    -- 이익잉여금
    total_liabilities  DOUBLE PRECISION,    -- 부채총계
    current_liabilities DOUBLE PRECISION,   -- 유동부채
    total_debt         DOUBLE PRECISION,    -- 총차입부채
    shares_outstanding DOUBLE PRECISION,    -- 발행주식수 (재무 기준)

    -- [2] Income Statement (손익계산서)
    revenue            DOUBLE PRECISION,    -- 매출액
    cogs               DOUBLE PRECISION,    -- 매출원가
    gross_profit       DOUBLE PRECISION,    -- 매출총이익
    sgna_expense       DOUBLE PRECISION,    -- 판관비
    rnd_expense        DOUBLE PRECISION,    -- 연구개발비
    op_income          DOUBLE PRECISION,    -- 영업이익
    interest_expense   DOUBLE PRECISION,    -- 이자비용
    tax_provision      DOUBLE PRECISION,    -- 법인세비용
    net_income         DOUBLE PRECISION,    -- 당기순이익
    ebitda             DOUBLE PRECISION,    -- EBITDA
    
    -- [3] Cash Flow Statement (현금흐름표)
    ocf                DOUBLE PRECISION,    -- 영업활동현금흐름
    capex              DOUBLE PRECISION,    -- 자본지출
    fcf                DOUBLE PRECISION,    -- 잉여현금흐름 (FCF)
    
    is_restated        BOOLEAN DEFAULT FALSE, -- 정정공시 여부
    fiscal_year        INTEGER,             -- 회계연도
    fiscal_period      VARCHAR(10),         -- 회계분기
    
    PRIMARY KEY (cik, report_period, filed_dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_standard_financials_pkey` | `(cik, report_period, filed_dt)` | PRIMARY KEY (btree) | 복합 고유 PK |
| `idx_us_standard_financials_pit` | `(cik, filed_dt DESC)` | btree | as-of 시점 기준 유효한 최신 표준재무 조회 |
| `idx_std_fin_fy_fp` | `(cik, fiscal_year, fiscal_period)` | btree | 연도/분기별 재무 추이 비교 분석 최적화 |

---

### 7. `us_share_history` — 주식 수 이력 (PIT)

> 공시일(filed_dt)을 키로 관리하는 발행주식수 원천 변경 이력.

```sql
CREATE TABLE us_share_history (
    cik        VARCHAR(10) NOT NULL,
    filed_dt   DATE NOT NULL,              -- 공시 및 효력 일자
    val        DOUBLE PRECISION,           -- 발행주식수
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, filed_dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_share_history_pkey` | `(cik, filed_dt)` | PRIMARY KEY (btree) | 복합 고유 PK |
| `idx_us_share_history_cik_dt` | `(cik, filed_dt DESC)` | btree | 최근 일자 기준 유효 주식수 조회 |

---

### 8. `us_daily_valuation` — 일별 가치평가 지표 (하이퍼테이블)

> 당일 종가와 시계열상 최신 유효 PIT 재무 값을 매핑해 매일 산출하는 5대 가치 평가 배수.

```sql
CREATE TABLE us_daily_valuation (
    dt        DATE NOT NULL,
    cik       VARCHAR(10) NOT NULL,
    mkt_cap   DOUBLE PRECISION,            -- 시가총액 (USD)
    pe        DOUBLE PRECISION,            -- PER (Price-to-Earnings)
    pb        DOUBLE PRECISION,            -- PBR (Price-to-Book)
    ps        DOUBLE PRECISION,            -- PSR (Price-to-Sales)
    pcr       DOUBLE PRECISION,            -- PCR (Price-to-CashFlow)
    ev_ebitda DOUBLE PRECISION,            -- EV/EBITDA
    PRIMARY KEY (dt, cik)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_daily_valuation_pkey` | `(dt, cik)` | PRIMARY KEY (btree) | 기본 키 및 Timescale 파티션 키 |
| `us_daily_valuation_dt_idx` | `dt DESC` | btree | 시계열 조건 스크리닝 가속화 |

---

### 9. `us_financial_metrics` — 표준화 재무 비율 및 성장성 지표 (PIT)

> PIT 시점별 수익성, 안전성 지표 및 YoY 성장률 연산 결과.

```sql
CREATE TABLE us_financial_metrics (
    cik               VARCHAR(10) NOT NULL,
    report_period     DATE NOT NULL,
    filed_dt          DATE NOT NULL,       -- Point-in-Time Key
    -- Profitability (수익성)
    roe               DOUBLE PRECISION,    -- ROE (%)
    roa               DOUBLE PRECISION,    -- ROA (%)
    roic              DOUBLE PRECISION,    -- ROIC (%)
    op_margin         DOUBLE PRECISION,    -- 영업이익률 (%)
    net_margin        DOUBLE PRECISION,    -- 순이익률 (%)
    -- Quality & Stability (안전성)
    gp_a_ratio        DOUBLE PRECISION,    -- GP/A (매출총이익/자산총계)
    debt_ratio        DOUBLE PRECISION,    -- 부채비율 (%)
    current_ratio     DOUBLE PRECISION,    -- 유동비율 (%)
    interest_coverage DOUBLE PRECISION,    -- 이자보상배율
    -- Growth (성장성 YoY)
    rev_growth_yoy    DOUBLE PRECISION,    -- 매출액 YoY 성장률 (%)
    op_growth_yoy     DOUBLE PRECISION,    -- 영업이익 YoY 성장률 (%)
    eps_growth_yoy    DOUBLE PRECISION,    -- EPS YoY 성장률 (%)
    created_at        TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cik, report_period, filed_dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_financial_metrics_pkey` | `(cik, report_period, filed_dt)` | PRIMARY KEY (btree) | 복합 고유 PK |
| `idx_us_financial_metrics_pit` | `(cik, filed_dt DESC)` | btree | 분석 시점 기준 최신 재무 비율 스크리닝 |

---

### 10. `us_collection_blacklist` — 수집 차단 목록

> KIS API 수집 실패, 403 인증 거절 등의 장애나 노이즈 종목의 루프백 방지를 위한 블랙리스트.

```sql
CREATE TABLE us_collection_blacklist (
    cik              VARCHAR(10) PRIMARY KEY,
    ticker           VARCHAR(10),
    reason_code      VARCHAR(50),           -- SEC_403, PARSE_ERROR, NO_DATA 등
    reason_detail    TEXT,
    is_blocked       BOOLEAN DEFAULT TRUE,  -- True인 경우 수집 대상에서 완전히 제외
    fail_count       INTEGER DEFAULT 0,
    last_failed_at   TIMESTAMP,
    last_verified_at TIMESTAMP,
    admin_note       TEXT,                  -- 관리자 특이사항 기재란
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `us_collection_blacklist_pkey` | `cik` | PRIMARY KEY (btree) | 단일 PK 조회 |
| `idx_blacklist_status` | `is_blocked` | btree | 수집 대상 여부 고속 판단 |

---

### 11. `trading_calendar` — 미국 주식 시장 거래일 캘린더

> 미국 주식 시장(NYSE/NASDAQ)의 휴장 및 개장 정보를 일별 관리. 수집 배치 시 동작 판별 기준.

```sql
CREATE TABLE trading_calendar (
    dt         DATE NOT NULL,               -- 기준 날짜
    opnd_yn    CHAR(1) NOT NULL,            -- 개장 여부 ('Y': 개장, 'N': 휴장)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 레코드 생성 시각
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 마지막 상태 업데이트 시각
    PRIMARY KEY (dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `trading_calendar_pkey` | `dt` | PRIMARY KEY (btree) | 특정 일자 캘린더 개장 여부 고속 룩업 |

---

## 테이블 간 관계 요약 (Relationship Map)

```
       us_ticker_master (cik)
          ├── us_ticker_history          (cik, start_dt, ticker)  [SCD Type 2]
          ├── us_collection_blacklist    (cik)                    [수집 필터링]
          ├── us_daily_price             (cik, dt)                [일봉 수집]
          │     └── (JOIN)
          │          │
          ├── us_daily_valuation         (cik, dt)                [배수 연산]
          │          │
          ├── us_price_adjustment_factors (cik, event_dt)         [수정 비율]
          ├── us_share_history           (cik, filed_dt)          [PIT 주식수]
          │          │
          ├── us_financial_facts         (cik, filed_dt, tag)     [원시 XBRL]
          │     └── (Standardize)
          │          │
          └── us_standard_financials     (cik, report_period, filed_dt)
                └── (Derive metrics)
                     │
                └── us_financial_metrics (cik, report_period, filed_dt)

       trading_calendar (dt)  <-- DailyRoutine 일일 기동 여부 판정 기준
```

---

## DB 운영 치트시트 (Operations Cheat Sheet)

### 1. 컨테이너 접속 및 psql 실행
```bash
docker exec -it usdms_timescaledb psql -U postgres -d usdms_db
```

### 2. 하이퍼테이블 청크 및 통계 상태 조회
```sql
-- 하이퍼테이블 청크 수 조회
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;

-- 대략적인 총 레코드 수 확인
SELECT hypertable_name, approximate_row_count(hypertable_name::regclass)
FROM timescaledb_information.hypertables;
```

### 3. 특정 일자(as_of) 기준 유효한 Point-in-Time 재무 데이터 조회 예시 (예: 애플 AAPL, CIK '0000320193')
```sql
-- 2026-06-01 시점에 조회가 가능한 가장 최신의 재무제표 획득
SELECT DISTINCT ON (report_period)
    report_period,
    filed_dt,
    total_assets,
    revenue,
    net_income
FROM us_standard_financials
WHERE cik = '0000320193'
  AND filed_dt <= '2026-06-01'
ORDER BY report_period DESC, filed_dt DESC;
```

### 4. 수집 차단 상태인 티커 목록 조회
```sql
SELECT cik, ticker, reason_code, last_failed_at 
FROM us_collection_blacklist 
WHERE is_blocked = TRUE 
ORDER BY last_failed_at DESC;
```

### 5. 거래일 캘린더 동기화 상태 조회
```sql
SELECT MIN(dt) as start_cal, MAX(dt) as end_cal, COUNT(*) as total_days 
FROM trading_calendar;
```
