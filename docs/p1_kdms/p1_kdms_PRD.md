# p1_kdms PRD — 한국 시장 데이터 백엔드

> **버전**: v1.0 | **작성일**: 2026-04-28
> **참조 원본**: `migration_pjt/kdms_origin/` (KDMS v7.0)
> **상위 PRD**: `docs/parent/tdms_PRD.md`
> **참조 위키**: `pjt_wiki/migration-pjt/ref_kdms_wiki/`

---

## 1. 목적 및 범위

p1_kdms는 KDMS 원본의 **백엔드 기능**을 정제·리팩토링하여 재구현한다.
프론트엔드(Vue3 SPA)는 `p3_manager`가 담당하므로 이 문서에서 제외한다.

### 핵심 목표
1. 기존 운영 중인 `kdms_db` 데이터를 **단절 없이 인계**받아 수집 재개
2. 원본의 검증된 비즈니스 로직 보존 + 가독성·유지보수성 중심 리팩토링
3. `p2_usdms`와 유사 기능의 구현 방향을 통일하여 상호 참조 유지보수 확보
4. `p3_manager`가 REST API로 제어·조회할 수 있는 완결된 백엔드 제공

---

## 2. 인계 전제 조건

| 항목 | 내용 |
|---|---|
| DB 볼륨 | 기존 `kdms_pgdata` Docker 볼륨 그대로 재사용 (`external: true`) |
| DB 이름 | `kdms_db` (변경 없음) |
| DB 포트 | `5432` (변경 없음) |
| 인계 전 백업 | `BackupManager --target kdms --tag pre_p1_migration` 실행 필수 |
| 스키마 호환 | 신규 init.sql과 기존 스키마 diff 확인 후 마이그레이션 스크립트 적용 |

---

## 3. 기능 요구사항

### 3.1 데이터 수집 기능

#### F-01: 일일 시세 수집 (OHLCV)
- **수집 대상**: 전체 KOSPI + KOSDAQ 상장 종목
- **데이터 소스**: Kiwoom REST API (1차), KIS REST API (보조)
- **저장 테이블**: `daily_ohlcv` (raw, 미수정 — 수정주가 저장 금지)
- **수집 주기**: 평일 장 마감 후 1회 (기본 17:10 KST)
- **원본 참조**: `kdms_origin/tasks/daily_task.py` → `sync_factors_and_prices()`
- **리팩토링 포인트**: 수집 실패 종목을 gap 목록으로 별도 기록하여 다음 실행 시 자동 재시도

#### F-02: 주가 수정계수 계산 및 관리
- **대상 이벤트**: 액면분할, 주식배당, 무상증자 등 주가 불연속 이벤트
- **저장 테이블**: `price_adjustment_factors` — `(stk_cd, event_dt, price_source)` UNIQUE
- **이원화 관리**: KIS 소스와 Kiwoom 소스를 `price_source` 컬럼으로 구분하여 병존
- **수정주가 역산**: `adjusted = raw × Π(factor_val | event_dt > price_date)` — 저장하지 않고 조회 시 계산
- **원본 참조**: `kdms_origin/collectors/factor_calculator.py`
- **주의**: KIS API의 `start_date`는 실제로 무시됨 → `end_date`를 과거로 이동하며 페이지네이션 필요

#### F-03: PIT 재무제표 수집
- **데이터 소스**: KIS REST API (`fetch_all_financial_data`)
- **저장 테이블**: `financial_statements`, `financial_ratios`
- **PIT Key**: `retrieved_at TIMESTAMPTZ` — 수집 시점을 기록하여 Look-ahead Bias 방지
- **조회 패턴**: 특정 날짜 기준 가장 최신 버전 → `ORDER BY retrieved_at DESC LIMIT 1`
- **수집 주기**: 주 1회 (토요일 09:00 KST)
- **원본 참조**: `kdms_origin/tasks/financial_task.py`

#### F-04: 시가총액 수집 (KRX)
- **데이터 소스**: `pykrx.stock.get_market_cap_by_ticker()`
- **저장 테이블**: `daily_market_cap` (Hypertable, Phase 8 신규)
- **수집 주기**: 평일 17:10 (일일 수집), 주간 갭 복구 (최근 30일)
- **주의**: pykrx는 비동기 미지원 → 별도 스레드(`run_in_executor`)에서 동기 호출
- **원본 참조**: `kdms_origin/collectors/krx_loader.py`

#### F-05: 분봉 데이터 수집
- **수집 대상**: `minute_target_history` 기준 선정된 고거래대금 상위 종목
- **저장 테이블**: `minute_ohlcv` (Hypertable, dt_tm 파티셔닝)
- **수집 주기**: 토요일 10:20 (주간 백필)
- **대상 선정 기준**: 직전 분기 평균 거래대금 상위 N개 종목 (`target_selector.py`)
- **원본 참조**: `kdms_origin/tasks/backfill_task.py`

#### F-06: 종목 마스터 관리
- **저장 테이블**: `stock_info`
- **수집 내용**: 종목명, 시장구분(KOSPI/KOSDAQ), 상장/폐지 상태, 상장일
- **수집 주기**: 일일 업데이트 시 함께 갱신
- **원본 참조**: `kdms_origin/tasks/daily_task.py` → `update_stock_info()`

---

### 3.2 API 엔드포인트

#### 데이터 조회 (`/api/data`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/data/stocks` | 전체 종목 목록 (필터 지원) |
| GET | `/api/data/ohlcv/daily` | 일봉 OHLCV (raw / adjusted 선택) |
| GET | `/api/data/ohlcv/daily/adjusted` | 수정주가 역산 일봉 (직접 계산) |
| GET | `/api/data/ohlcv/minute` | 분봉 OHLCV |
| GET | `/api/data/factors` | 수정계수 조회 |
| GET | `/api/data/financials` | 재무제표 (PIT 지원) |
| POST | `/api/data/screening` | 재무 스크리닝 |
| GET | `/api/data/market-cap` | 시가총액 |
| GET | `/api/data/preview/{table}` | 테이블 미리보기 (p3_manager용) |

#### 헬스 및 시스템 (`/api/health`, `/api/admin`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health/freshness` | 데이터 최신성 확인 |
| GET | `/api/health/gaps` | 데이터 갭 탐지 |
| GET | `/api/health/milestones` | 시스템 마일스톤 |
| POST | `/api/health/milestones` | 마일스톤 생성 |
| POST | `/api/admin/tasks/{task_id}/run` | 태스크 즉시 실행 |
| GET | `/api/admin/tasks/status` | 전체 태스크 상태 |
| GET | `/api/admin/schedules` | 스케줄 목록 조회 |
| PUT | `/api/admin/schedules/{id}` | 스케줄 수정 |
| WS | `/ws/logs` | 실시간 실행 로그 스트리밍 |

---

### 3.3 자동화 스케줄

| Job ID | 실행 시간 (KST) | 기능 | 원본 |
|---|---|---|---|
| `daily_update` | 월~금 17:10 | OHLCV + 팩터 + 시총 동기화 | `daily_task.py` |
| `financial_update` | 토 09:00 | PIT 재무 데이터 | `financial_task.py` |
| `backfill_minute` | 토 10:20 | 분봉 백필 + 시총 갭 복구 | `backfill_task.py` |

- **스케줄러**: `AsyncIOScheduler` (FastAPI lifespan 연동, BackgroundScheduler 사용 금지)
- **p3_manager 연동**: `/api/admin/tasks/{task_id}/run` 으로 수동 즉시 실행 가능

---

## 4. DB 스키마

원본 `kdms_db` 스키마를 그대로 인계한다. 신규 추가 테이블만 별도 마이그레이션 스크립트로 적용.

### 4.1 핵심 테이블 요약

| 테이블 | 타입 | 용도 |
|---|---|---|
| `stock_info` | 일반 | 종목 마스터 (PK: `stk_cd`) |
| `daily_ohlcv` | Hypertable (dt) | 일봉 Raw 시세 |
| `minute_ohlcv` | Hypertable (dt_tm) | 분봉 시세 |
| `price_adjustment_factors` | 일반 | 수정계수 (PIT) |
| `daily_market_cap` | Hypertable (dt) | 시가총액 |
| `financial_statements` | 일반 | 재무제표 PIT (`retrieved_at`) |
| `financial_ratios` | 일반 | 재무비율 PIT |
| `system_milestones` | 일반 | 데이터 신뢰도 이벤트 |
| `minute_target_history` | 일반 | 분봉 수집 대상 이력 |

> 상세 DDL: `pjt_wiki/migration-pjt/ref_kdms_wiki/interfaces/db_schema.md`

### 4.2 스키마 변경 시 원칙
- 기존 컬럼 삭제 금지 (하위 호환)
- 컬럼 추가는 `DEFAULT` 값이 있는 nullable 컬럼으로만 추가
- 변경 시 `ops/apply_schema_update.py` 방식의 마이그레이션 스크립트 필수 작성

---

## 5. 리팩토링 방향

### 5.1 원본에서 보존할 핵심 로직
| 모듈 | 보존 이유 |
|---|---|
| `factor_calculator.py` 수정계수 계산 알고리즘 | 검증 완료된 복잡한 이벤트 처리 로직 |
| `kis_rest.py` KIS API 페이지네이션 | `start_date` 무시 특이동작 대응 로직 |
| `db_manager.py` PIT 재무 조회 쿼리 | `retrieved_at DESC` 인덱스 기반 최신 버전 조회 |
| `daily_task.py` 수집 순서 및 의존성 | 팩터 → OHLCV 순서 보장 로직 |

### 5.2 주요 리팩토링 대상

| 대상 | 원본 문제점 | 개선 방향 |
|---|---|---|
| `db_manager.py` (940+ lines) | 단일 God Class — 모든 쿼리 혼재 | 도메인별 Repository 클래스 분리 (`OhlcvRepo`, `FinancialRepo` 등) |
| `main_collection.py` | 실행 모드가 if/else로 뒤섞임 | 명확한 진입점 분리 (`ops/` 디렉토리) |
| `daily_update.py` / `daily_task.py` 중복 | 레거시 스크립트와 태스크 로직 중복 | 레거시 제거, `tasks/daily_task.py` 단일 소스 |
| 예외 처리 | `except Exception` 광범위 catch | 구체적 예외 타입 명시, 재시도 로직 분리 |
| 하드코딩 설정값 | 코드 내 직접 작성된 시간, 임계값 | `.env` / `config.yaml` 외부화 |
| `kiwoom_rest.py` 토큰 관리 | 인스턴스별 독립 토큰 캐시 | `shared/KiwoomApiCore` 의 `TokenManager`로 통합 |

### 5.3 p2_usdms와 통일할 구현 패턴

| 기능 | KDMS 현재 | USDMS 현재 | 통일 방향 |
|---|---|---|---|
| DB 커서 | `ThreadedConnectionPool` + 수동 acquire/release | `get_cursor()` context manager | **USDMS 패턴 채택** (context manager) |
| 헬스체크 | `run_diagnostics.py` 분리 실행 | `DailyRoutine._detect_anomalies()` 루틴 내 통합 | **루틴 내 통합** (p2 패턴) |
| 블랙리스트 | 없음 (실패 시 그냥 skip) | `BlacklistManager` (사유 코드 체계) | **USDMS 패턴 도입** |
| 운영 진입점 | 최상위 루트에 py 파일 산재 | `ops/` 폴더로 집중 | **`ops/` 폴더 구조** 채택 |

---

## 6. 프로젝트 디렉토리 구조 (목표)

```
p1_kdms/
├── main.py                    # FastAPI 앱, lifespan, 라우터 등록
├── config.py                  # 환경변수 로딩 (pydantic-settings)
│
├── routers/
│   ├── data.py                # 시세/재무 데이터 조회
│   ├── health.py              # 신선도/갭/마일스톤
│   └── admin.py               # 태스크 실행/스케줄/WebSocket
│
├── models/
│   ├── data_models.py         # Pydantic 응답 모델
│   └── admin_models.py        # 태스크/스케줄 요청 모델
│
├── tasks/
│   ├── daily_task.py          # 일일 OHLCV + 팩터 + 시총
│   ├── financial_task.py      # PIT 재무 수집
│   └── backfill_task.py       # 분봉 백필 + 시총 갭 복구
│
├── collectors/                # 데이터 소스 연동
│   ├── kiwoom_client.py       # shared/KiwoomApiCore 래퍼
│   ├── kis_kr_client.py       # shared/KisApiCore → KR 전용 엔드포인트
│   ├── krx_loader.py          # pykrx 시총 수집 (스레드 실행)
│   ├── factor_calculator.py   # 수정계수 계산
│   └── target_selector.py     # 분봉 대상 종목 선정
│
├── repositories/              # DB 쿼리 레이어 (리팩토링 신규)
│   ├── base.py                # 커넥션 풀 + get_cursor() (shared 위임)
│   ├── ohlcv_repo.py          # OHLCV CRUD
│   ├── factor_repo.py         # 수정계수 CRUD
│   ├── financial_repo.py      # 재무 데이터 CRUD
│   ├── market_cap_repo.py     # 시총 CRUD
│   └── master_repo.py         # stock_info CRUD
│
├── ops/                       # 운영 진입점
│   ├── initial_build.py       # 초기 DB 구축 (최초 1회)
│   ├── rebuild_factors.py     # 수정계수 전체 재구축
│   ├── run_diagnostics.py     # 데이터 무결성 점검
│   └── backfill_market_cap.py # 시총 스마트 백필
│
├── init/
│   └── init.sql               # 스키마 DDL (Hypertable 포함)
│
├── docker-compose.yml
├── backend.Dockerfile
├── .env.example
└── requirements.txt
```

---

## 7. 기술 스택

| 항목 | 값 | 비고 |
|---|---|---|
| 언어 | Python 3.12 | |
| 프레임워크 | FastAPI 0.121+ | |
| ASGI 서버 | Uvicorn 0.38+ | |
| DB 드라이버 | psycopg2-binary 2.9+ | |
| 데이터 처리 | pandas 2.3+, pyarrow 22+ | Apache Arrow 응답 지원 |
| 스케줄러 | APScheduler 3.11+ | AsyncIOScheduler 필수 |
| 설정 관리 | pydantic-settings | `.env` 로딩 |
| HTTP 클라이언트 | requests 2.32+ | |
| KRX 수집 | pykrx | 동기 → run_in_executor |
| DB | TimescaleDB (PostgreSQL 16) | |
| 컨테이너 | Docker + Compose | 볼륨 `external: true` 필수 |

---

## 8. 환경 변수 (.env)

```bash
# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=kdms_db
POSTGRES_USER=kdms_user
POSTGRES_PASSWORD=your_password
DB_POOL_MIN=5
DB_POOL_MAX=20

# KIS API (shared 모듈과 토큰 캐시 공유)
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=xxx
KIS_MOCK=false

# Kiwoom API
KIWOOM_APP_KEY=xxx
KIWOOM_APP_SECRET=xxx

# Schedule (cron 표현식 또는 시:분)
SCHEDULE_DAILY_UPDATE=17:10
SCHEDULE_FINANCIAL_UPDATE=sat:09:00
SCHEDULE_BACKFILL_MINUTE=sat:10:20

# 운영 설정
LOG_LEVEL=INFO
MINUTE_TARGET_COUNT=100       # 분봉 수집 대상 종목 수
MARKET_CAP_GAP_LOOKBACK_DAYS=30
```

---

## 9. Docker 구성

```yaml
# docker-compose.yml (핵심)
services:
  db:
    image: timescale/timescaledb-ha:pg16
    volumes:
      - kdms_pgdata:/home/postgres/pgdata/data   # 외부 볼륨
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: kdms_db
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  backend:
    build:
      context: .
      dockerfile: backend.Dockerfile
    ports:
      - "8000:8000"
    depends_on:
      - db
    env_file: .env
    volumes:
      - ./logs:/app/logs          # 로그 파일 마운트
      - ./backups:/app/backups    # 백업 파일 마운트

volumes:
  kdms_pgdata:
    external: true               # ← DB 볼륨 보호 핵심
```

---

## 10. 구현 단계 (Phase)

### Phase 1 — DB 인계 및 기본 수집 재개 (최우선)
- [ ] Docker Compose에 `external: true` 볼륨 설정
- [ ] 기존 `kdms_db` 볼륨 연결 확인 및 백업
- [ ] FastAPI 앱 기본 구조 + `repositories/` 레이어 구성
- [ ] 일일 OHLCV 수집 (`F-01`) 재개 — 수집 연속성 확인
- [ ] 시가총액 수집 (`F-04`) 재개

### Phase 2 — 핵심 수집 기능 완성
- [ ] 수정계수 수집 및 역산 API (`F-02`)
- [ ] PIT 재무제표 수집 (`F-03`)
- [ ] 분봉 수집 (`F-05`)
- [ ] 종목 마스터 관리 (`F-06`)
- [ ] APScheduler 자동화 스케줄 연결

### Phase 3 — API 및 리팩토링
- [ ] 데이터 조회 엔드포인트 완성 (수정주가 역산 포함)
- [ ] `db_manager.py` → `repositories/` 분리 리팩토링
- [ ] `ops/` 진입점 정리 (레거시 스크립트 제거)
- [ ] Blacklist 패턴 도입 (수집 실패 종목 관리)

### Phase 4 — p3_manager 연동
- [ ] `/api/admin` 엔드포인트 완성 (태스크 실행/스케줄/WebSocket)
- [ ] `/api/health` 완성 (갭 탐지, 마일스톤)
- [ ] p3_manager 연동 테스트

---

## 11. 알려진 이슈 및 주의사항

| 이슈 | 내용 | 대응 |
|---|---|---|
| KIS `start_date` 무시 | 페이지네이션 시 `end_date` 역방향 이동 방식 필수 | `kis_kr_client.py`에 명시적 주석 + 테스트 |
| pykrx 비동기 미지원 | 동기 함수 → event loop 블로킹 발생 | `asyncio.run_in_executor(None, ...)` 래핑 |
| AsyncIOScheduler 필수 | `BackgroundScheduler` 사용 시 FastAPI event loop 충돌 | 코드 리뷰 체크리스트 항목 추가 |
| Docker 볼륨 유실 위험 | `docker-compose down -v` 실행 시 볼륨 삭제 가능 | `external: true` + 팀 운영 가이드 공유 |
| 수정계수 이원화 | KIS/Kiwoom 팩터가 미세하게 다를 수 있음 | `price_source` 컬럼으로 구분 관리, 불일치 시 로그 경고 |

---

*서브프로젝트 상세 구현은 이 문서를 기준으로 진행한다.*
*공통 모듈(`shared/`) 설계 상세는 `docs/shared/shared_PRD.md` 참조.*
