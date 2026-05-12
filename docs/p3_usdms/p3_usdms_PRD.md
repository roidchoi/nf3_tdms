# p3_usdms PRD — 미국 시장 데이터 백엔드

> **버전**: v1.0 | **작성일**: 2026-04-28
> **참조 원본**: `migration_pjt/usdms_origin/` (USDMS v5.0)
> **상위 PRD**: `docs/parent/tdms_PRD.md`
> **참조 위키**: `pjt_wiki/migration-pjt/ref_usdms_wiki/`

---

## 1. 목적 및 범위

p3_usdms는 USDMS 원본의 **백엔드 기능**을 정제·리팩토링하여 재구현한다.
UI는 `p4_manager`가 담당하며, p3은 데이터 수집·저장·API 제공에만 집중한다.

### 핵심 목표
1. 기존 운영 중인 `usdms_db` 데이터를 **단절 없이 인계**받아 수집 재개
2. SEC EDGAR 기반 CIK 중심 티커 관리 체계 유지
3. XBRL 재무 파싱 → PIT 표준화 파이프라인 보존
4. `p2_kdms`와 유사 기능의 구현 방향을 통일 (DB 패턴, 운영 구조 등)
5. `p4_manager`가 REST API로 제어·조회할 수 있는 완결된 백엔드 제공

---

## 2. 인계 전제 조건

| 항목 | 내용 |
|---|---|
| DB 볼륨 | 기존 `usdms_pgdata` Docker 볼륨 그대로 재사용 (`external: true`) |
| DB 이름 | `usdms_db` (변경 없음) |
| DB 포트 | `5435` (변경 없음, KDMS와 충돌 없음) |
| 인계 전 백업 | `BackupManager --target usdms --tag pre_p3_migration` 실행 필수 |
| 스키마 호환 | 신규 init.sql과 기존 스키마 diff 확인 후 마이그레이션 스크립트 적용 |

---

## 3. 기능 요구사항

### 3.1 마스터 관리

#### F-01: 티커 마스터 동기화 (MasterSync)
- **데이터 소스**: SEC EDGAR `company_tickers_exchange.json`
- **식별자**: CIK (불변 식별자, zero-padded VARCHAR(10)) — Ticker 변경과 무관
- **저장 테이블**: `us_ticker_master`, `us_ticker_history` (SCD Type 2)
- **Noise Deletion**: `start_dt > Yesterday`인 당일 생성/종료 레코드는 DELETE (장중 노이즈 제거)
- **수집 대상 선정**: 시총 ≥ $5천만, 주가 ≥ $1.00, NYSE/NASDAQ/AMEX, 미국 법인, EQUITY
- **원본 참조**: `usdms_origin/backend/collectors/master_sync.py` → `MasterSync.sync_daily()`

#### F-02: 메타데이터 보강 (MasterEnricher)
- **데이터 소스**: yfinance (Sector, Industry, Country, QuoteType)
- **저장 테이블**: `us_ticker_master` (sector, industry, country, quote_type 컬럼)
- **실행 방식**: 신규 CIK 추가 시 배치 보강, 주기적 전수 갱신
- **원본 참조**: `usdms_origin/backend/collectors/master_enricher.py`

---

### 3.2 시세 수집

#### F-03: 일봉 OHLCV 수집
- **데이터 소스**: KIS 미국 주식 래퍼 (`shared/KisUsWrapper`)
- **저장 테이블**: `us_daily_price` (Hypertable, dt 파티셔닝, chunk 1 day)
- **저장 원칙**: **Raw 원본 가격만 저장** (수정주가 저장 금지)
- **수집 대상**: `is_collect_target = TRUE` 종목
- **수집 주기**: 미국 시장 마감 후 1회 (기본 07:00 KST 화~토)
- **원본 참조**: `usdms_origin/backend/collectors/market_data_loader.py`

#### F-04: 가격 수정계수 관리 (PriceEngine)
- **데이터 소스**: KIS US 일봉 API의 수정주가 vs 원본주가 비율
- **저장 테이블**: `us_price_adjustment_factors` — `(cik, event_dt)` PK
- **수정주가 역산**: `adjusted = raw × Π(factor_val | event_dt > price_date)`
- **원본 참조**: `usdms_origin/backend/collectors/price_engine.py`

---

### 3.3 재무 데이터 수집 및 표준화

#### F-05: SEC XBRL 재무 파싱 (FinancialParser)
- **데이터 소스**: SEC EDGAR `company_facts` API
- **저장 테이블**: `us_financial_facts` (Raw EAV), `us_standard_financials` (표준화)
- **파싱 전략**:
  - XBRL Tag → `xbrl_mapper.py`로 표준 필드 매핑 (US-GAAP 우선)
  - `(FY, FP)` 기준 그룹화, 분기 이산값 역산 (Q2 = Q2_YTD - Q1_YTD)
  - Q4 = FY - Q3_YTD
- **PIT Key**: `filed_dt` (SEC 공시일) — Look-ahead Bias 방지
- **수집 주기**: 일일 루틴 Step 3 (시세 수집 후 순차 실행)
- **원본 참조**: `usdms_origin/backend/collectors/financial_parser.py`

#### F-06: 주식 수 이력 관리
- **데이터 소스**: SEC EDGAR DEI 태그 (`EntityCommonStockSharesOutstanding`)
- **저장 테이블**: `us_share_history` (cik, filed_dt, val)
- **용도**: PIT 가치평가 시 발행주식수 시점 매칭 (1순위 소스)

#### F-07: 수집 차단 목록 관리 (BlacklistManager)
- **저장 테이블**: `us_collection_blacklist`
- **차단 사유 코드**: `SEC_403`, `PARSE_ERROR`, `NO_DATA`, `EMPTY_FILING`
- **동작**: `is_blocked=TRUE` → 수집 루프 완전 제외 / `is_blocked=FALSE` → 재시도 가능
- **원본 참조**: `usdms_origin/backend/utils/blacklist_manager.py`

---

### 3.4 가치평가 및 재무비율 산출

#### F-08: PIT 가치평가 산출 (ValuationCalculator)
- **저장 테이블**: `us_daily_valuation` (Hypertable, chunk 52 weeks)
- **산출 지표**: PER, PBR, PSR, PCR, EV/EBITDA
- **PIT 매칭**: `pandas.merge_asof(direction='backward')` — 가격 날짜 기준 최신 재무 자동 매칭
- **주식 수 소스**: `us_share_history` (1순위) → `us_standard_financials.shares_outstanding` (fallback)
- **TTM 처리**: 분기 데이터 × 4 (간이 TTM, 추후 Rolling Sum 개선 가능)
- **원본 참조**: `usdms_origin/backend/engines/valuation_calculator.py`

#### F-09: 재무비율 산출 (MetricCalculator)
- **저장 테이블**: `us_financial_metrics`
- **산출 지표**: ROE, ROA, ROIC, GP/A (Novy-Marx), 부채비율, 이자보상배율, 매출성장률 등
- **원본 참조**: `usdms_origin/backend/engines/metric_calculator.py`

---

### 3.5 데이터 무결성 검증 (Auditors)

#### F-10: 재무 감사
- 회계 항등식 검증: `Assets = Liabilities + Equity`
- 이력 누수(Historical Leakage) 탐지
- **원본 참조**: `usdms_origin/backend/auditors/financial_auditor.py`

#### F-11: 지표 역산 검증
- ROE 등 산출 지표를 원본 재무 데이터로 역산하여 검증
- **원본 참조**: `usdms_origin/backend/auditors/metric_auditor.py`

#### F-12: 수정주가 재현성 검증
- Raw 가격 × 수정계수 = yfinance Adj Close 값 비교
- **원본 참조**: `usdms_origin/backend/auditors/price_auditor.py`

---

### 3.6 일일 루틴 오케스트레이터

#### F-13: 일일 루틴 (DailyRoutine, Step 1~6)

```
Step 1: Master Sync         → MasterSync.sync_daily()
Step 2: Market Data         → MarketDataLoader.collect_daily_updates()
Step 3: Financial Parse     → FinancialParser.process_filings()
Step 4: Metadata Update     → us_ticker_master.market_cap, current_price 갱신
Step 5: Valuation & Metrics → ValuationCalculator + MetricCalculator
Step 6: Health Check        → DailyRoutine._detect_anomalies()
```

- 각 Step 실행 결과를 `DailyRoutine.record_step()`으로 기록
- 이상징후 감지 시 로그 ERROR 레벨 기록
- **원본 참조**: `usdms_origin/ops/run_daily_routine.py`

---

### 3.7 API 엔드포인트

#### 데이터 조회 (`/api/data`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/data/tickers` | 티커 마스터 목록 (필터: exchange, is_collect_target) |
| GET | `/api/data/price/daily` | 일봉 시세 (raw / adjusted) |
| GET | `/api/data/price/factors` | 수정계수 조회 |
| GET | `/api/data/financials` | 표준화 재무 데이터 (PIT 지원) |
| GET | `/api/data/valuation` | 가치평가 지표 (일별) |
| GET | `/api/data/metrics` | 재무비율 |
| GET | `/api/data/preview/{table}` | 테이블 미리보기 (p4_manager용) |

#### 헬스 및 시스템 (`/api/health`, `/api/admin`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health/freshness` | 데이터 최신성 확인 |
| GET | `/api/health/gaps` | 수집 갭 탐지 |
| GET | `/api/health/blacklist` | 차단 목록 조회 |
| POST | `/api/admin/tasks/{task_id}/run` | 태스크 즉시 실행 |
| GET | `/api/admin/tasks/status` | 전체 태스크 상태 |
| WS | `/ws/logs` | 실시간 실행 로그 스트리밍 |

---

### 3.8 자동화 스케줄

| Job ID | 실행 시간 (KST) | 기능 |
|---|---|---|
| `daily_routine` | 화~토 07:00 | Step 1~6 전체 일일 루틴 |
| `weekly_backfill` | 일 03:00 | 과거 이력 갭 복구 |

- **스케줄러**: `APScheduler AsyncIOScheduler`
- **p4_manager 연동**: `/api/admin/tasks/{task_id}/run`으로 수동 즉시 실행

---

## 4. DB 스키마

원본 `usdms_db` 스키마를 그대로 인계. 신규 컬럼 추가 시 `DEFAULT + nullable` 원칙.

### 4.1 핵심 테이블 요약

| 테이블 | 타입 | PIT Key | 용도 |
|---|---|---|---|
| `us_ticker_master` | 일반 | — | 종목 마스터 (PK: cik) |
| `us_ticker_history` | 일반 | `start_dt` | 티커 변경 이력 (SCD Type 2) |
| `us_collection_blacklist` | 일반 | — | 수집 차단 목록 |
| `us_financial_facts` | 일반 | `filed_dt` | Raw XBRL (EAV) |
| `us_standard_financials` | 일반 | `filed_dt` | 표준화 재무 (Analysis Ready) |
| `us_share_history` | 일반 | `filed_dt` | 주식 수 이력 |
| `us_daily_price` | Hypertable (dt) | — | 일봉 Raw 시세 |
| `us_price_adjustment_factors` | 일반 | `event_dt` | 수정계수 |
| `us_daily_valuation` | Hypertable (dt) | — | 가치평가 지표 |
| `us_financial_metrics` | 일반 | `filed_dt` | 재무비율 |

> 상세 DDL: `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/db_schema.md`

---

## 5. 리팩토링 방향

### 5.1 원본에서 보존할 핵심 로직

| 모듈 | 보존 이유 |
|---|---|
| `master_sync.py` Noise Deletion 로직 | 장중 티커 변경 노이즈 제거 — 검증된 비즈니스 규칙 |
| `financial_parser.py` XBRL 그룹화·이산화 | `(FY, FP)` 기준 Q2_discrete = Q2_YTD - Q1_YTD 로직 |
| `valuation_calculator.py` merge_asof 패턴 | `pandas.merge_asof(direction='backward')` PIT 매칭 |
| `blacklist_manager.py` 사유 코드 체계 | `SEC_403` 등 코드 체계 — p1에도 동일 패턴 도입 |
| `xbrl_mapper.py` US-GAAP 태그 매핑 | 수백 개 태그 매핑 테이블 — 재작성 비용 높음 |

### 5.2 주요 리팩토링 대상

| 대상 | 원본 문제점 | 개선 방향 |
|---|---|---|
| `db_manager.py` (GOD NODE, 243 edges) | 모든 쿼리 단일 클래스 혼재 | 도메인별 Repository 분리 (`PriceRepo`, `FinancialRepo` 등) |
| `run_daily_routine.py` 오류 처리 | Step 실패 시 전체 중단 | Step별 독립 예외 처리 + 부분 성공 허용 |
| 하드코딩 수집 대상 기준 | 코드 내 `$50M`, `$1.00` 등 직접 작성 | `.env` / `config.yaml` 외부화 |
| `kis_api_core.py` 중복 | kdms와 동일 코드 별도 존재 | `p1_shared/KisApiCore`로 통합 (토큰 캐시 공유) |
| 운영 스크립트 산재 | `ops/`, `db_init/` 역할 혼재 | `ops/` = 일상 운영, `db_init/` = 초기화 전용으로 명확히 분리 |

### 5.3 p2_kdms와 통일할 구현 패턴

| 기능 | p2 방식 | p3 현재 | 통일 결과 |
|---|---|---|---|
| DB 커서 | `get_cursor()` context manager 도입 | 이미 `get_cursor()` 사용 | **p3 패턴 유지** (p2가 채택) |
| 운영 진입점 | `ops/` 폴더 집중 | `ops/` + `db_init/` 혼재 | **`ops/` 집중** (db_init은 초기화 전용) |
| 블랙리스트 | p3 패턴 도입 예정 | `BlacklistManager` 완비 | **p3 패턴이 기준** |
| 실시간 로그 | WebSocket (`/ws/logs`) | 미구현 | **p1 방식 도입** (p4_manager 연동) |
| 헬스체크 API | `/api/health/*` | `run_diagnostics.py` 독립 실행 | **REST API 엔드포인트**로 전환 |

---

## 6. 프로젝트 디렉토리 구조 (목표)

```
p3_usdms/
├── main.py                    # FastAPI 앱, lifespan, 라우터 등록
├── config.py                  # 환경변수 로딩 (pydantic-settings)
│
├── routers/
│   ├── data.py                # 시세/재무/가치평가 조회
│   ├── health.py              # 갭 탐지, 블랙리스트, 신선도
│   └── admin.py               # 태스크 실행/스케줄/WebSocket
│
├── models/
│   ├── data_models.py         # Pydantic 응답 모델
│   └── admin_models.py        # 태스크/스케줄 요청 모델
│
├── tasks/
│   └── daily_routine.py       # Step 1~6 오케스트레이터
│
├── collectors/                # 데이터 소스 연동
│   ├── master_sync.py         # SEC 티커 동기화
│   ├── master_enricher.py     # yfinance 메타데이터 보강
│   ├── sec_client.py          # SEC EDGAR API 래퍼
│   ├── financial_parser.py    # XBRL 파싱·표준화
│   ├── xbrl_mapper.py         # US-GAAP → 표준 필드 매핑
│   ├── market_data_loader.py  # 일봉 OHLCV 수집
│   ├── price_engine.py        # 수정계수 계산
│   └── kis_us_client.py       # p1_shared/KisApiCore → US 전용 래퍼
│
├── engines/                   # 계산 레이어
│   ├── valuation_calculator.py
│   └── metric_calculator.py
│
├── auditors/                  # 데이터 무결성 검증
│   ├── financial_auditor.py
│   ├── metric_auditor.py
│   └── price_auditor.py
│
├── utils/
│   └── blacklist_manager.py   # 수집 차단 목록 관리
│
├── repositories/              # DB 쿼리 레이어 (리팩토링 신규)
│   ├── base.py                # get_cursor() (p1_shared 위임)
│   ├── price_repo.py
│   ├── financial_repo.py
│   ├── valuation_repo.py
│   └── master_repo.py
│
├── ops/                       # 운영 진입점
│   ├── run_daily_routine.py   # 일일 루틴 메인 진입점
│   ├── run_diagnostics.py     # 온디맨드 헬스체크
│   ├── kill_db_locks.py       # DB 락 긴급 해제
│   └── run_master_sync_only.py
│
├── db_init/                   # 초기화 전용 (1회성)
│   ├── init.sql
│   ├── run_historical_backfill.py
│   ├── rebuild_ticker_master.py
│   └── run_valuation_rebuild.py
│
├── tests/
│   ├── test_master_logic.py
│   ├── test_master_sync.py
│   └── test_daily_routine_subset.py
│
├── docker-compose.yml
├── backend.Dockerfile
├── .env.example
└── requirements.txt
```

---

## 7. 기술 스택

| 항목 | 값 |
|---|---|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| ASGI 서버 | Uvicorn |
| DB 드라이버 | psycopg2-binary |
| 데이터 처리 | pandas, numpy |
| 스케줄러 | APScheduler AsyncIOScheduler |
| 설정 관리 | pydantic-settings |
| HTTP 클라이언트 | requests, aiohttp |
| HTML 파싱 | beautifulsoup4, lxml |
| 메타데이터 보강 | yfinance |
| DB | TimescaleDB (PostgreSQL 16) |
| 컨테이너 | Docker + Compose (`external: true` 볼륨 필수) |

---

## 8. 환경 변수 (.env)

```bash
# Database
POSTGRES_HOST=db
POSTGRES_PORT=5435
POSTGRES_DB=usdms_db
POSTGRES_USER=usdms_user
POSTGRES_PASSWORD=your_password
DB_POOL_MIN=5
DB_POOL_MAX=20

# SEC EDGAR (필수 — 미설정 시 403 차단)
SEC_USER_AGENT=YourName your@email.com

# KIS API (p1_shared 모듈과 토큰 캐시 공유)
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=xxx
KIS_MOCK=false

# 수집 대상 선정 기준
TARGET_MIN_MARKET_CAP=50000000      # $5천만
TARGET_MIN_PRICE=1.00
TARGET_RETAIN_MARKET_CAP=35000000   # $3.5천만 (유지 기준)
TARGET_RETAIN_PRICE=0.80

# 스케줄
SCHEDULE_DAILY_ROUTINE=07:00        # KST, 화~토

# 운영 설정
LOG_LEVEL=INFO
```

---

## 9. Docker 구성

```yaml
services:
  db:
    image: timescale/timescaledb-ha:pg16
    volumes:
      - usdms_pgdata:/home/postgres/pgdata/data
    ports:
      - "5435:5432"            # 호스트 5435 → 컨테이너 5432
    environment:
      POSTGRES_DB: usdms_db
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  backend:
    build:
      context: .
      dockerfile: backend.Dockerfile
    ports:
      - "8005:8005"
    depends_on:
      - db
    env_file: .env
    volumes:
      - ./logs:/app/logs
      - ./backups:/app/backups

volumes:
  usdms_pgdata:
    external: true             # DB 볼륨 보호 핵심
```

---

## 10. 구현 단계 (Phase)

### Phase 1 — DB 인계 및 기본 수집 재개 (최우선)
- [ ] `external: true` 볼륨 연결 + 인계 전 백업
- [ ] FastAPI 앱 기본 구조 + `repositories/` 레이어
- [ ] Master Sync (F-01) 재개 — CIK 연속성 확인
- [ ] 일봉 시세 수집 (F-03) 재개

### Phase 2 — 핵심 수집 기능 완성
- [ ] XBRL 재무 파싱 (F-05, F-06)
- [ ] 수정계수 관리 (F-04)
- [ ] BlacklistManager (F-07) 완비
- [ ] 가치평가 산출 (F-08)
- [ ] 재무비율 산출 (F-09)
- [ ] 일일 루틴 Step 1~6 연결 + APScheduler

### Phase 3 — API 및 리팩토링
- [ ] 데이터 조회 엔드포인트 완성
- [ ] `db_manager.py` → `repositories/` 분리 리팩토링
- [ ] `kis_api_core.py` → `p1_shared/KisApiCore` 교체
- [ ] Auditors 연동 (F-10~F-12)

### Phase 4 — p4_manager 연동
- [ ] `/api/admin` 엔드포인트 (태스크 실행/WebSocket)
- [ ] `/api/health` 엔드포인트 (갭/블랙리스트/신선도)
- [ ] p4_manager 연동 테스트

---

## 11. 알려진 이슈 및 주의사항

| 이슈 | 내용 | 대응 |
|---|---|---|
| SEC 403 차단 | `SEC_USER_AGENT` 헤더 미설정 시 즉시 차단 | `.env`에 실제 이름+이메일 필수 |
| 8-K 공시 Gap | 10-K/10-Q 없이 8-K만 있는 기간 → Gap Scanner 무한 루프 위험 | Blacklist `EMPTY_FILING` 코드로 차단 |
| DB Lock Contention | Hypertable 동시 업서트 시 Lock 경합 | chunk 단위 커밋, `kill_db_locks.py` 긴급 해제 |
| TimescaleDB pg_restore role 에러 | `role "readonly_analyst" does not exist` | 데이터 복원과 무관 — 무시 가능 |
| CIK 변경 불가 | SEC CIK는 불변 식별자 — Ticker 변경과 무관 | `us_ticker_history`로 티커 변경 이력 별도 관리 |
| yfinance Rate Limit | 대량 메타데이터 보강 시 차단 가능 | 배치 단위 sleep + 재시도 로직 |

---

*공통 모듈(`p1_shared/`) 설계 상세는 `docs/p1_shared/p1_shared_PRD.md` 참조.*
*p4_manager 연동 인터페이스 상세는 `docs/p4_manager/p4_manager_PRD.md` 참조.*
