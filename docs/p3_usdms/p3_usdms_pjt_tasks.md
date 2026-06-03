# P3 Task 계획서

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)
> **기준 문서**: PRD v1.0 (2026-04-28)
> **참조 원본**: `migration_pjt/usdms_origin/` (USDMS v5.0)
> **작성일**: 2026-05-28
> **최종 수정**: 2026-06-01 (T-002 → T-002-A / T-002-B 분할)
> **총 Task**: 10개 (Phase 1: 3개 / Phase 2: 4개 / Phase 3: 2개 / Phase 4: 1개)

---

## § 1. 프로젝트 개요

p3_usdms는 USDMS 원본(v5.0)의 백엔드 기능을 정제·리팩토링하여 재구현한다. 기존 `usdms_db` 데이터를 단절 없이 인계받아 수집을 재개하며, p1_shared 공통 모듈(EnvDetector, DbConnectionPool, StartupValidator, KisApiCore)을 활용하여 환경 독립적인 백엔드를 구축한다. p4_manager가 REST API로 제어·조회할 수 있는 완결된 백엔드 제공이 최종 목표다.

> ⚠️ **원본 코드베이스 분석 결과 (v5.0 기준 실제 구현 현황)**
> - `DailyRoutine` (ops/run_daily_routine.py): Step 1 Master Sync → Step 2 Market Data → Step 3 Financial Update → Step 3.5 Metric Calc → Step 4 Valuation Calc → Step 5 Health Check
> - `MasterSync`: SEC EDGAR API 3종(company_tickers, tickers_exchange, submissions) + yfinance 비동기 enrichment + SCD Type 2 이력관리 + Targeting 분석 — 최대 복잡도
> - `FinancialParser`: XBRL Raw Facts → 이산화(Q2=Q2_YTD-Q1, Q3=Q3_YTD-Q2, FY 직접) → `us_share_history` DEI 태그 별도 추출
> - `ValuationCalculator`: `merge_asof(direction='backward')` PIT 매칭, PE/PB/PS/PCR/EV-EBITDA 산출, 주식수 Hybrid Fallback
> - `MetricCalculator`: ROE/ROA/ROIC/GP-A/Debt Ratio/Current Ratio/Interest Coverage + YoY 성장률(Rev/Op/EPS)
> - `PriceEngine`: KIS Adj Close / Raw Close 비율로 수정계수 이벤트 감지
> - **Auditors 3종**: `PriceReproducer`(누적계수 재현), `FinancialDiagnostic`(회계항등식/Leakage), `MetricVerifier`(ROE역산)
> - **원본 API 미완성**: `routers/data.py`에 3개 엔드포인트만 존재 — PRD 기준으로 전면 신규 구현 필요

**Phase 구분 기준:**
- Phase 1 (MVP): DB 인계 완료 + 티커 마스터 및 일봉 OHLCV 핵심 수집 가동
- Phase 2 (수집 완성): SEC 재무 파싱 + 가치평가/재무비율 산출 + Blacklist + 일일 루틴 자동화 통합
- Phase 3 (API 완성): 전체 REST API + 헬스/어드민 엔드포인트 + WebSocket + Auditors
- Phase 4 (연동): p4_manager E2E 연동 검증

---

## § 2. Task 의존성 흐름

```
T-001 (인프라 + DB 인계)
  │
  ▼
T-002-A (티커 마스터 수집 코어 — MasterSync + SECClient + MasterRepo)
  │
  ▼
T-002-B (일봉 OHLCV + 수정계수 + API / KIS)
  │
  ├──→ T-003 (SEC XBRL 재무 파싱 + 주식수 이력)
  │         │
  │         ▼
  │       T-004 (가치평가 + 재무비율 산출)
  │         │
  ├──→ T-005 (Blacklist + 일일 루틴 전체 자동화)
  │       ↑
  │    (T-003, T-004 완료 후)
  │
  ▼
T-006 (데이터 조회 REST API 완성)
  │
  ▼
T-007 (헬스·어드민 API + Auditors + WebSocket)
  │
  ▼
T-008 (리팩토링 최종 정리 + db_manager → repositories 분리)
  │
  ▼
T-009 (p4_manager 연동 테스트)
```

---

## § 3. Task 목록

### Phase 1: DB 인계 + 핵심 수집

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-001 | 프로젝트 기반 구조 및 DB 인계 | Docker Compose(`external: true` 볼륨), FastAPI 골격(`main.py`, `config.py`), `repositories/base.py`(EnvDetector DSN 자동 결정, DbConnectionPool), `StartupValidator` lifespan 연동, `BackupManager` 인계 전 백업 실행, 기존 `db_manager.py` 호환 shim 유지 | 완료 | High | - | 2026-05-29 | 2026-05-29 |
| T-002-A | 티커 마스터 수집 코어 (SEC EDGAR + SCD Type 2 + MasterRepo) | `collectors/sec_client.py`(SEC EDGAR 3종 API 래퍼 — company_tickers / tickers_exchange / submissions), `collectors/master_sync.py`(SCD Type 2 Diff, Authority Verification, normalize_exchange, _resolve_primary_ticker, Targeting 분석, yfinance asyncio Enrichment 통합), `repositories/master_repo.py`(`us_ticker_master` / `us_ticker_history` CRUD), `/api/data/tickers` 엔드포인트, `routers/data.py` 초기화 | 완료 | High | T-001 | 2026-06-01 | 2026-06-01 |
| T-002-B | 일봉 OHLCV + 수정계수 + 가격 API (KIS) | `collectors/kis_us_client.py`(KisApiCore US 래퍼, 토큰 캐시 공유), `collectors/market_data_loader.py`(KIS 미국 일봉 수집), `collectors/price_engine.py`(Adj/Close 비율 수정계수 이벤트 감지), `repositories/price_repo.py`(`us_daily_price` / `us_price_adjustment_factors` CRUD), `/api/data/price/daily`, `/api/data/price/factors` 엔드포인트 | 완료 | High | T-002-A | - | - |

### Phase 2: 수집 완성 + 자동화

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-003 | SEC XBRL 재무 파싱 + 주식수 이력 | `collectors/financial_parser.py`(Raw Facts EAV 저장, `_standardize_financials_v2` — FY/FP 그룹화·이산화·Q4역산, FCF/EBITDA 후처리), `collectors/xbrl_mapper.py`(US-GAAP 태그 매핑 보존), `collectors/sec_client.py`(company_facts, filings_by_date SEC Index 스캔), `repositories/financial_repo.py`(`us_financial_facts` bulk insert, `us_standard_financials` upsert, `us_share_history` upsert) | 완료 | High | T-002 | 2026-06-02 | 2026-06-02 |
| T-004 | 가치평가 + 재무비율 산출 | `engines/valuation_calculator.py`(`merge_asof(direction='backward')` PIT 매칭, PE/PB/PS/PCR/EV-EBITDA, TTM×4, 주식수 Hybrid Fallback, 50건 배치 저장), `engines/metric_calculator.py`(ROE/ROA/ROIC/GP-A/Debt Ratio/Current Ratio/Interest Coverage + YoY 성장률 Rev/Op/EPS), `repositories/valuation_repo.py`(`us_daily_valuation`, `us_financial_metrics` ON CONFLICT upsert) | 완료 | High | T-003 | 2026-06-02 | 2026-06-02 |
| T-005 | Blacklist + MasterEnricher + 일일 루틴 전체 자동화 | `utils/blacklist_manager.py`(DB 기반, `add_blacklist`/`is_blacklisted`/`remove_blacklist`, 사유코드 체계), `collectors/master_enricher.py`(yfinance sector/industry/country/quote_type 배치 보강), `tasks/daily_routine.py`(Step 1~5 오케스트레이터, Step별 독립 예외처리, 부분 성공 허용, 실행 Report JSON 저장), `AsyncIOScheduler` lifespan 연동(`daily_routine(화~토 07:00)`, `weekly_backfill(일 03:00)`), `/api/admin/tasks/{id}/run` 수동 실행 엔드포인트 | 대기 | High | T-003, T-004 | - | - |

### Phase 3: API 완성 + Auditors

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-006 | 데이터 조회 REST API 완성 | `routers/data.py` 전면 재구현: `/api/data/tickers`(exchange/is_collect_target 필터), `/api/data/price/daily`(raw/adjusted 분기), `/api/data/price/factors`, `/api/data/financials`(PIT 지원), `/api/data/valuation`, `/api/data/metrics`, `/api/data/preview/{table}` — 원본 3개 엔드포인트에서 7종으로 확장 | 대기 | Medium | T-005 | - | - |
| T-007 | 헬스·어드민 API + Auditors + WebSocket | `/api/health/freshness`, `/api/health/gaps`, `/api/health/blacklist`, `/api/admin/tasks/status`, `/api/admin/schedules`(GET/PUT), `WS /ws/logs` 실시간 로그 스트리밍, `auditors/financial_auditor.py`(회계항등식/Critical Nulls/Historical Leakage), `auditors/metric_auditor.py`(ROE역산 검증), `auditors/price_auditor.py`(PriceReproducer 누적계수 재현), `ops/run_diagnostics.py` REST API 엔드포인트 연동 | 대기 | Medium | T-006 | - | - |

### Phase 3.5: 리팩토링 정리

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-008 | `db_manager.py` → `repositories/` 분리 리팩토링 | 원본 `db_manager.py`(GOD NODE, 11KB, 전 쿼리 단일 클래스) → 도메인별 Repository 완전 분리(`price_repo`, `financial_repo`, `valuation_repo`, `master_repo`), `kis_api_core.py` → `p1_shared/KisApiCore` 교체, `ops/` 레거시 스크립트 정리(`run_diagnostics.py` 진입점만 유지), 하드코딩 수집 기준(`$50M`, `$1.00`) `.env` 외부화, 전체 단위 테스트 통과 확인 | 대기 | Medium | T-007 | - | - |

### Phase 4: p4_manager 연동

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-009 | p4_manager 연동 테스트 | p4_manager 연동 API E2E 시나리오 검증, `/api/mgr` 프록시 통신 확인, WebSocket 로그 프록시 검증, 엔드포인트별 계약(Contract) 검증, `tdms-net` 공유 네트워크 연결 확인 | 대기 | Low | T-008 | - | - |

**상태값:** `대기` / `진행 중` / `완료` / `보류`

---

## § 4. PRD 요구사항 커버리지

| PRD 요구사항 ID | 요구사항 | 구현 Task |
|----------------|---------|-----------| 
| F-01 | 티커 마스터 동기화 (MasterSync — SEC EDGAR, SCD Type 2, Noise Deletion, Targeting) | T-002 |
| F-02 | 메타데이터 보강 (MasterEnricher — yfinance Sector/Industry/Country) | T-005 |
| F-03 | 일봉 OHLCV 수집 (KIS US 래퍼, Raw 원본 저장) | T-002 |
| F-04 | 가격 수정계수 관리 (PriceEngine — Adj/Close 비율법) | T-002 |
| F-05 | SEC XBRL 재무 파싱 (FinancialParser — FY/FP 그룹화, 이산화, FCF/EBITDA 후처리) | T-003 |
| F-06 | 주식 수 이력 관리 (us_share_history — DEI 태그 추출) | T-003 |
| F-07 | 수집 차단 목록 관리 (BlacklistManager — DB 기반, 사유코드 체계) | T-005 |
| F-08 | PIT 가치평가 산출 (ValuationCalculator — merge_asof, PE/PB/PS/PCR/EV-EBITDA) | T-004 |
| F-09 | 재무비율 산출 (MetricCalculator — ROE/ROA/ROIC/GP-A/YoY 성장률) | T-004 |
| F-10 | 재무 감사 (FinancialAuditor — 회계항등식, Historical Leakage) | T-007 |
| F-11 | 지표 역산 검증 (MetricAuditor — ROE역산) | T-007 |
| F-12 | 수정주가 재현성 검증 (PriceAuditor — 누적계수 재현, AAPL/NVDA 기준) | T-007 |
| F-13 | 일일 루틴 (DailyRoutine Step 1~5, 단계별 독립 예외처리, Report 저장) | T-005 |
| API-데이터 | 데이터 조회 엔드포인트 7종 | T-002(`/tickers`, `/price/daily`, `/price/factors`), T-006(나머지 4종) |
| API-헬스 | 헬스·시스템 엔드포인트 5종 + WebSocket | T-005(`/tasks/{id}/run`), T-007(나머지) |
| SCHED | 2종 자동화 스케줄 (daily_routine 화~토 07:00, weekly_backfill 일 03:00) | T-005 |
| REFACTOR-1 | `db_manager.py`(GOD NODE) → `repositories/` 도메인별 분리 | T-001(base), T-002(price/master), T-003(financial), T-004(valuation), T-008(완전 분리) |
| REFACTOR-2 | `kis_api_core.py` 중복 → `p1_shared/KisApiCore` 통합 (토큰 캐시 공유) | T-002(래퍼), T-008(완전 교체) |
| REFACTOR-3 | `ops/` 레거시 스크립트 정리, 실행 진입점 단일화 | T-008 |
| REFACTOR-4 | 하드코딩 수집 기준 외부화 (`.env`/`config.yaml`) | T-008 |
| INFRA | Docker 인계 + StartupValidator + BackupManager | T-001 |

**미커버 항목:** 없음

---

## § 5. 진행 현황

| 구분 | 수량 |
|------|------|
| 전체 | 10개 |
| 완료 | 2개 |
| 진행 중 | 0개 |
| 대기 | 8개 |

---

## § 6. 설계 판단 사항

### Task 분해 주요 결정

1. **T-002에 수정계수 포함**: `MarketDataLoader`가 OHLCV 수집 후 즉시 `PriceEngine.calculate_factors_from_ratio()` 를 호출하는 구조(원본 `_save_data()` 내 연결)이므로 분리 불가. T-002에 통합.

2. **T-003에 xbrl_mapper 포함**: `FinancialParser`가 `XBRLMapper`를 직접 의존하므로 함께 구현. xbrl_mapper.py(16KB, 수백 개 태그 매핑)는 원본 그대로 보존이 원칙.

3. **T-005에 MasterEnricher + Blacklist 통합**: 두 기능이 `DailyRoutine` 자동화 조립의 마지막 퍼즐. 단독으로는 동작 검증 불가한 단편이므로 일일 루틴 완성 Task에 흡수.

4. **T-008 리팩토링 별도 Task화**: 원본 `db_manager.py`가 GOD NODE(11KB)인 점을 고려, 구현 완료 후 리팩토링을 별도 Task로 분리. 기능 구현 중 db_manager shim을 임시로 유지하고 T-008에서 완전 교체.

5. **Auditors를 T-007로 묶음**: `PriceAuditor`, `FinancialAuditor`, `MetricAuditor` 3종은 모두 "완성된 데이터를 검증"하는 역할로, 데이터 수집/계산 파이프라인 완성(T-005) 이후 구현 가능. 헬스 API와 함께 구현하면 API 엔드포인트로 노출 가능.

### p2_kdms와 통일할 패턴

| 기능 | p2 방식 | p3 반영 방향 |
|---|---|---|
| DB 커서 | `get_cursor()` context manager | p1_shared DbConnectionPool 사용 (동일) |
| PIT 재무 저장 | INSERT → DISTINCT ON 버전 선택 | `us_standard_financials`도 동일 패턴 적용 |
| 수정주가 전략 | On-the-fly + 물리 테이블 이중 | US는 On-the-fly만 (물리 갱신 없음 — PRD 기준) |
| Blacklist | `reason_code` 체계 | `SEC_403`, `PARSE_ERROR`, `NO_DATA`, `EMPTY_FILING` 동일 사용 |
| 헬스체크 | REST API 엔드포인트 | `run_diagnostics.py` → API 전환 |

---

## § 7. 변경 이력

| 날짜 | 변경 내용 | 사유 |
|------|----------|------|
| 2026-05-28 | 초안 작성 (9개 Task, Phase 1~4) | PRD v1.0 + usdms_origin v5.0 코드베이스 직접 분석 기반 |
