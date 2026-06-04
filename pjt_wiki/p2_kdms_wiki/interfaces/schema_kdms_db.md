# kdms_timescaledb DB 스키마 (schema_kdms_db.md)

> **DB**: `kdms_db`
> **컨테이너**: `kdms_timescaledb`
> **포트**: `5432`
> **사용자**: `roid`
> **볼륨**: `kdms_pgdata` (external: true)
> **마지막 업데이트**: 2026-05-27
> **관련**: `[[p2_kdms_wiki/interfaces/ohlcv_repo.md]]`, `[[p2_kdms_wiki/interfaces/financial_repo.md]]`, `[[p2_kdms_wiki/operations/runbook.md]]`

---

## 개요

| 항목 | 내용 |
|---|---|
| 총 테이블 수 | 12개 |
| TimescaleDB 하이퍼테이블 | 3개 (daily_ohlcv, daily_ohlcv_adjusted, minute_ohlcv) |
| 일반 테이블 | 9개 |

---

## TimescaleDB 하이퍼테이블 목록

| 테이블명 | 파티션 기준 컬럼 | 현재 청크(chunk) 수 |
|---|---|---|
| `daily_ohlcv` | `dt` | 2,159 |
| `daily_ohlcv_adjusted` | `dt` | 2,159 |
| `minute_ohlcv` | `dt_tm` | 320 |

---

## 테이블 상세 스키마

---

### 1. `daily_ohlcv` — 일봉 OHLCV (하이퍼테이블)

> 종목별 일별 원본 시세. 약 1,000만 행 이상 (min_row_counts 기준).

```sql
CREATE TABLE daily_ohlcv (
    dt        DATE                  NOT NULL,  -- 거래일
    stk_cd    VARCHAR(6)            NOT NULL,  -- 종목코드 (6자리)
    open_prc  INTEGER,                         -- 시가
    high_prc  INTEGER,                         -- 고가
    low_prc   INTEGER,                         -- 저가
    cls_prc   INTEGER,                         -- 종가
    vol       BIGINT,                          -- 거래량
    amt       BIGINT,                          -- 거래대금
    turn_rt   NUMERIC(10,2),                   -- 회전율 (%)
    PRIMARY KEY (dt, stk_cd)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `daily_ohlcv_pkey` | `(dt, stk_cd)` | PRIMARY KEY, btree |
| `daily_ohlcv_dt_idx` | `dt DESC` | btree |
| `idx_daily_ohlcv_stk_cd_dt` | `(stk_cd, dt DESC)` | btree |

**Triggers:** `ts_insert_blocker` (TimescaleDB 청크 라우팅)

---

### 2. `daily_ohlcv_adjusted` — 수정주가 물리 테이블 (하이퍼테이블)

> 수정계수 누적곱이 적용된 수정주가 물리 테이블. `OhlcvRepo.refresh_adjusted_ohlcv_batch()`로 갱신.

```sql
CREATE TABLE daily_ohlcv_adjusted (
    dt         DATE                      NOT NULL,  -- 거래일
    stk_cd     VARCHAR(6)                NOT NULL,  -- 종목코드
    open_prc   NUMERIC(14,2),                       -- 수정 시가
    high_prc   NUMERIC(14,2),                       -- 수정 고가
    low_prc    NUMERIC(14,2),                       -- 수정 저가
    cls_prc    NUMERIC(14,2),                       -- 수정 종가
    vol        BIGINT,                              -- 수정 거래량
    adj_factor NUMERIC(18,8),                       -- 누적 수정계수 (기록용)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- 마지막 갱신 시각
    PRIMARY KEY (dt, stk_cd)
);
COMMENT ON TABLE daily_ohlcv_adjusted IS '종목별 일봉 수정주가 물리 테이블';
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `daily_ohlcv_adjusted_pkey` | `(dt, stk_cd)` | PRIMARY KEY, btree |
| `daily_ohlcv_adjusted_dt_idx` | `dt DESC` | btree |
| `idx_daily_ohlcv_adj_stk_cd_dt` | `(stk_cd, dt DESC)` | btree |

**Triggers:** `ts_insert_blocker` (TimescaleDB 청크 라우팅)

> ⚠️ **주의**: `NUMERIC(14,2)` 타입으로 소수점을 허용함. 정수 기반 원본 테이블(`daily_ohlcv`)과 타입 다름.

---

### 3. `daily_ohlcv_gap` — OHLCV 수집 누락/실패 이력

> 수집 실패 또는 휴장일 등 데이터가 없는 날짜를 기록.

```sql
CREATE TABLE daily_ohlcv_gap (
    stk_cd     VARCHAR(6)  NOT NULL,              -- 종목코드
    dt         DATE        NOT NULL,              -- 대상 날짜
    reason     TEXT,                              -- 실패/누락 사유
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 마지막 기록 시각
    PRIMARY KEY (stk_cd, dt)
);
COMMENT ON TABLE daily_ohlcv_gap IS 'OHLCV 수집 누락(휴장일 등) 또는 실패 이력';
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `daily_ohlcv_gap_pkey` | `(stk_cd, dt)` | PRIMARY KEY, btree |

> 💡 PK 순서 주의: `daily_ohlcv`는 `(dt, stk_cd)`, `daily_ohlcv_gap`은 `(stk_cd, dt)` — 역순.

---

### 4. `daily_market_cap` — 일별 시가총액

> pykrx(KRX 공공 API) 기반 일별 전 종목 시가총액.

```sql
CREATE TABLE daily_market_cap (
    dt             DATE        NOT NULL,  -- 거래일
    stk_cd         VARCHAR(6)  NOT NULL,  -- 종목코드
    cls_prc        INTEGER,               -- 종가
    mkt_cap        BIGINT,                -- 시가총액 (원)
    vol            BIGINT,                -- 거래량
    amt            BIGINT,                -- 거래대금
    listed_shares  BIGINT,                -- 상장주식수
    PRIMARY KEY (dt, stk_cd)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `daily_market_cap_pkey` | `(dt, stk_cd)` | PRIMARY KEY, btree |

---

### 5. `stock_info` — 종목 마스터

> KIS 마스터 파일 ZIP 기반 종목 정보. 활성 종목 조회의 기준 테이블.

```sql
CREATE TABLE stock_info (
    stk_cd      VARCHAR(6)   NOT NULL,                      -- 종목코드 (6자리. 2024년 이후 KRX 알파벳 혼용 규격 포함)
    stk_nm      VARCHAR(100) NOT NULL,                      -- 종목명
    market_type VARCHAR(10),                                 -- 시장 구분 ('KOSPI', 'KOSDAQ', ...)
    status      VARCHAR(20)  NOT NULL DEFAULT 'listed',     -- 상태 ('listed', 'delisted')
    delist_dt   DATE,                                        -- 상장폐지일 (NULL=현재 상장중)
    list_dt     DATE,                                        -- 최초 상장일
    m_vol       BIGINT,                                      -- 상장주식수 (issued shares)
    cap         BIGINT,                                      -- 자본금
    update_dt   DATE,                                        -- 마스터 마지막 갱신일
    PRIMARY KEY (stk_cd)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `stock_info_pkey` | `stk_cd` | PRIMARY KEY, btree |
| `idx_stock_info_market_status` | `(market_type, status, stk_cd)` | btree (복합 필터용) |

**활성 종목 조회 조건:**
```sql
WHERE status = 'listed' AND (delist_dt IS NULL OR delist_dt > CURRENT_DATE)
```

---

### 6. `price_adjustment_factors` — 수정계수 이력

> 액면분할, 배당 등 코퍼레이트 액션 이벤트에 의한 수정계수 기록.

```sql
CREATE TABLE price_adjustment_factors (
    id           BIGINT      NOT NULL DEFAULT nextval('price_adjustment_factors_id_seq'),
    stk_cd       VARCHAR(6)  NOT NULL,     -- 종목코드
    event_dt     DATE        NOT NULL,     -- 수정계수 이벤트 발생일
    price_ratio  NUMERIC     NOT NULL,     -- 가격 수정계수 (곱셈형, e.g. 0.5 = 50:1 분할)
    volume_ratio NUMERIC     NOT NULL,     -- 거래량 수정계수 (역수, e.g. 2.0 = 50:1 분할)
    price_source VARCHAR(20) NOT NULL,     -- 출처 ('KIS', 'KIWOOM', ...)
    details      JSONB,                    -- 원인 상세 (선택)
    effective_dt TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 이 계수가 DB에 기록된 시각
    PRIMARY KEY (id)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `price_adjustment_factors_pkey` | `id` | PRIMARY KEY, btree |
| `uq_paf_stock_event_source` ⭐ | `(stk_cd, event_dt, price_source)` | UNIQUE CONSTRAINT, btree |
| `idx_paf_stock_event_dt` | `(stk_cd, event_dt DESC)` | btree (수정계수 이력 조회) |
| `idx_paf_effective_dt` | `effective_dt DESC` | btree |

> 💡 실제 유일성 제약은 `(stk_cd, event_dt, price_source)` UNIQUE 조합. `id`는 surrogate key.

---

### 7. `financial_statements` — 재무제표 (PIT 버전관리)

> KIS OpenAPI 7종 재무 API 중 대차대조표(BS) + 손익계산서(IS) 데이터. 동일 결산년월 데이터가 retrieved_at 별로 다수 행 공존 (PIT 원칙).

```sql
CREATE TABLE financial_statements (
    id              BIGINT     NOT NULL DEFAULT nextval('financial_statements_id_seq'),
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 수집 시각 (PIT 버전 키)
    stk_cd          VARCHAR(6) NOT NULL,   -- 종목코드
    stac_yymm       VARCHAR(6) NOT NULL,   -- 결산년월 (YYYYMM)
    div_cls_code    VARCHAR(1) NOT NULL,   -- 결산 구분 ('1'=분기, '0'=연간)
    -- 대차대조표
    cras            NUMERIC,               -- 유동자산 (Current Assets)
    fxas            NUMERIC,               -- 비유동자산 (Fixed Assets)
    total_aset      NUMERIC,               -- 자산총계
    flow_lblt       NUMERIC,               -- 유동부채
    fix_lblt        NUMERIC,               -- 비유동부채
    total_lblt      NUMERIC,               -- 부채총계
    cpfn            NUMERIC,               -- 자본금
    total_cptl      NUMERIC,               -- 자본총계
    -- 손익계산서
    sale_account    NUMERIC,               -- 매출액
    sale_cost       NUMERIC,               -- 매출원가
    sale_totl_prfi  NUMERIC,               -- 매출총이익
    bsop_prti       NUMERIC,               -- 영업이익 (영업이익률 분자)
    op_prfi         NUMERIC,               -- 영업외이익
    thtr_ntin       NUMERIC,               -- 당기순이익
    PRIMARY KEY (id)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `financial_statements_pkey` | `id` | PRIMARY KEY, btree | surrogate key |
| `idx_fs_lookup` | `(stk_cd, stac_yymm, div_cls_code, retrieved_at DESC)` | btree | 단건 최신 버전 조회 |
| `idx_fs_pit_screening` | `(stac_yymm, div_cls_code, retrieved_at DESC, stk_cd)` | btree | as_of 기준 PIT 스크리닝 |

> ⚠️ **PIT 설계 특이사항**: `ON CONFLICT` 없이 항상 INSERT → 동일 `(stk_cd, stac_yymm, div_cls_code)`에 다수 버전 행 존재 가능.  
> 조회 시 `DISTINCT ON (stac_yymm)` + `retrieved_at <= as_of_date` 패턴 사용. → `[[p2_kdms_wiki/decisions/dec-001_pit_financial_pattern.md]]` 참조.

---

### 8. `financial_ratios` — 재무비율 (PIT 버전관리)

> KIS OpenAPI 7종 재무 API 중 재무비율/성장성/안정성/수익성 지표. `financial_statements`와 동일한 PIT 설계 원칙 적용.

```sql
CREATE TABLE financial_ratios (
    id                  BIGINT     NOT NULL DEFAULT nextval('financial_ratios_id_seq'),
    retrieved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stk_cd              VARCHAR(6) NOT NULL,
    stac_yymm           VARCHAR(6) NOT NULL,
    div_cls_code        VARCHAR(1) NOT NULL,
    -- 성장성
    grs                 NUMERIC,   -- 매출액증가율 (%)
    bsop_prfi_inrt      NUMERIC,   -- 영업이익증가율 (%)
    ntin_inrt           NUMERIC,   -- 순이익증가율 (%)
    -- 수익성
    roe_val             NUMERIC,   -- ROE (%)
    eps                 NUMERIC,   -- 주당순이익 (EPS)
    sps                 NUMERIC,   -- 주당매출액 (SPS)
    bps                 NUMERIC,   -- 주당순자산 (BPS)
    -- 안정성
    rsrv_rate           NUMERIC,   -- 유보율 (%)
    lblt_rate           NUMERIC,   -- 부채비율 (%)
    cptl_ntin_rate      NUMERIC,   -- 자본이익률 (%)
    self_cptl_ntin_inrt NUMERIC,   -- 자기자본순이익률 (%)
    -- 수익성 (추가)
    sale_ntin_rate      NUMERIC,   -- 매출순이익률 (%)
    sale_totl_rate      NUMERIC,   -- 매출총이익률 (%)
    -- 가치평가
    eva                 NUMERIC,   -- EVA (경제적부가가치)
    ebitda              NUMERIC,   -- EBITDA
    ev_ebitda           NUMERIC,   -- EV/EBITDA
    bram_depn           NUMERIC,   -- 감가상각비
    -- 유동성
    crnt_rate           NUMERIC,   -- 유동비율 (%)
    quck_rate           NUMERIC,   -- 당좌비율 (%)
    -- 성장성 (추가)
    equt_inrt           NUMERIC,   -- 자기자본증가율 (%)
    totl_aset_inrt      NUMERIC,   -- 총자산증가율 (%)
    PRIMARY KEY (id)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 | 용도 |
|---|---|---|---|
| `financial_ratios_pkey` | `id` | PRIMARY KEY, btree | surrogate key |
| `idx_fr_lookup` | `(stk_cd, stac_yymm, div_cls_code, retrieved_at DESC)` | btree | 단건 최신 버전 조회 |
| `idx_fr_pit_screening` | `(stac_yymm, div_cls_code, retrieved_at DESC, stk_cd)` | btree | as_of 기준 PIT 스크리닝 |

---

### 9. `minute_ohlcv` — 분봉 데이터 (하이퍼테이블)

> Kiwoom REST API 기반 1분봉 데이터. KOSPI Top-200, KOSDAQ Top-400 대상.

```sql
CREATE TABLE minute_ohlcv (
    dt_tm    TIMESTAMPTZ NOT NULL,  -- 체결 시각 (분봉 기준, timezone aware)
    stk_cd   VARCHAR(6)  NOT NULL,  -- 종목코드
    open_prc INTEGER,               -- 시가
    high_prc INTEGER,               -- 고가
    low_prc  INTEGER,               -- 저가
    cls_prc  INTEGER,               -- 종가 (체결가)
    vol      BIGINT,                -- 거래량
    PRIMARY KEY (dt_tm, stk_cd)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `minute_ohlcv_pkey` | `(dt_tm, stk_cd)` | PRIMARY KEY, btree |
| `idx_minute_ohlcv_stk_cd_dt_tm` | `(stk_cd, dt_tm DESC)` | btree (종목별 분봉 조회) |
| `minute_ohlcv_dt_tm_idx` | `dt_tm DESC` | btree (TimescaleDB 파티션) |

**Triggers:** `ts_insert_blocker` (TimescaleDB 청크 라우팅)

---

### 10. `minute_target_history` — 분봉 수집 대상 종목 이력

> 분기별 분봉 수집 대상 종목을 거래대금 기준으로 선정한 이력.

```sql
CREATE TABLE minute_target_history (
    quarter         VARCHAR(6)  NOT NULL,  -- 분기 (e.g. '2025Q1')
    market          VARCHAR(10) NOT NULL,  -- 시장 ('KOSPI', 'KOSDAQ')
    symbol          VARCHAR(20) NOT NULL,  -- 종목코드
    avg_trade_value BIGINT,                -- 평균 거래대금 (거래일 평균)
    rank            INTEGER,               -- 거래대금 순위
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 선정 기록 시각
    PRIMARY KEY (quarter, market, symbol)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `minute_target_history_pkey` | `(quarter, market, symbol)` | PRIMARY KEY, btree |
| `idx_target_quarter` | `(quarter, market, rank)` | btree (분기/시장별 순위 조회) |

---

### 11. `trading_calendar` — 거래일 캘린더

> 한국 증시 개장/휴장일 정보. `backfill_task.py`의 누락일 탐지 기준.

```sql
CREATE TABLE trading_calendar (
    dt         DATE        NOT NULL,               -- 날짜
    opnd_yn    CHAR(1)     NOT NULL,               -- 개장 여부 ('Y'=개장, 'N'=휴장)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 마지막 업데이트 시각
    PRIMARY KEY (dt)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `trading_calendar_pkey` | `dt` | PRIMARY KEY, btree |

**데이터 소스**: `daily_ohlcv`의 `DISTINCT dt` → `backfill_task._sync_trading_calendar_history()`로 동기화.

---

### 12. `system_milestones` — 시스템 마일스톤

> 마이그레이션 시점, 주요 이벤트 등 시스템 레벨 기록.

```sql
CREATE TABLE system_milestones (
    milestone_name  VARCHAR(100) NOT NULL,             -- 마일스톤 식별자
    milestone_date  DATE         NOT NULL,             -- 발생 날짜
    description     TEXT,                              -- 상세 설명
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(), -- 마지막 업데이트
    PRIMARY KEY (milestone_name)
);
```

**인덱스:**

| 인덱스명 | 컬럼 | 종류 |
|---|---|---|
| `system_milestones_pkey` | `milestone_name` | PRIMARY KEY, btree |

---

## 테이블 간 관계 요약

```
stock_info (stk_cd)
    ├── daily_ohlcv          (stk_cd, dt)       [UPSERT]
    ├── daily_ohlcv_adjusted (stk_cd, dt)       [UPSERT via CTE]
    ├── daily_ohlcv_gap      (stk_cd, dt)       [수집 실패 기록]
    ├── daily_market_cap     (stk_cd, dt)       [UPSERT]
    ├── price_adjustment_factors (stk_cd, event_dt, price_source) [UPSERT]
    ├── financial_statements (stk_cd, stac_yymm, div_cls_code) [INSERT, 버전 누적]
    ├── financial_ratios     (stk_cd, stac_yymm, div_cls_code) [INSERT, 버전 누적]
    └── minute_ohlcv         (stk_cd, dt_tm)    [UPSERT]

minute_target_history (quarter, market, symbol)  ← TargetSelector
trading_calendar (dt)                            ← daily_ohlcv에서 동기화
system_milestones (milestone_name)               ← 수동 기록
```

---

## DB 운영 치트시트

```bash
# 컨테이너 접속
docker exec -it kdms_timescaledb psql -U roid -d kdms_db

# 전체 테이블 크기 확인
SELECT relname AS table, pg_size_pretty(pg_total_relation_size(oid)) AS size
FROM pg_class WHERE relkind='r' AND relnamespace=(SELECT oid FROM pg_namespace WHERE nspname='public')
ORDER BY pg_total_relation_size(oid) DESC;

# 하이퍼테이블 청크 현황
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;

# 특정 테이블 행 수 빠른 확인 (TimescaleDB 통계 기반)
SELECT hypertable_name, approximate_row_count(hypertable_name::regclass)
FROM timescaledb_information.hypertables;

# 수집 누락 종목 최근 10건 조회
SELECT * FROM daily_ohlcv_gap ORDER BY updated_at DESC LIMIT 10;

# 특정 종목의 수정계수 이력 조회
SELECT * FROM price_adjustment_factors WHERE stk_cd = '005930' ORDER BY event_dt DESC;

# PIT 재무제표 버전 확인 (삼성전자, 분기)
SELECT stac_yymm, retrieved_at, thtr_ntin
FROM financial_statements
WHERE stk_cd = '005930' AND div_cls_code = '1'
ORDER BY stac_yymm DESC, retrieved_at DESC;
```
