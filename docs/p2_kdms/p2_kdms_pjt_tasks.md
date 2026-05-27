# P2 Task 계획서

> **Sub Project**: p2_kdms (한국 시장 데이터 백엔드)
> **기준 문서**: PRD v1.1 (2026-05-14)
> **작성일**: 2026-05-14
> **총 Task**: 9개 (Phase 1: 2개 / Phase 2: 4개 / Phase 3: 2개 / Phase 4: 1개)

---

## § 1. 프로젝트 개요

p2_kdms는 KDMS 원본(v7.0)의 백엔드 기능을 정제·리팩토링하여 재구현한다. 기존 `kdms_db` 데이터를 단절 없이 인계받아 수집을 재개하며, p1_shared 공통 모듈(EnvDetector, DbConnectionPool, StartupValidator, BackupManager, KisApiCore)을 활용하여 환경 독립적인 백엔드를 구축한다. p4_manager가 REST API로 제어·조회할 수 있는 완결된 백엔드 제공이 최종 목표다.

> ⚠️ **설계 변경 이력**: OHLCV 수집 소스를 Kiwoom에서 KIS로 전환함. Kiwoom 수정주가 오류 검증 후 수정계수 계산에 KIS를 채택한 이력이 있으며, 원시 OHLCV도 동일하게 KIS 단일 소스로 통일함. Kiwoom API는 분봉 수집 전용으로 역할 축소.

**Phase 구분 기준:**
- Phase 1 (MVP): DB 인계 완료 + 일일 OHLCV·종목 마스터 핵심 수집 가동
- Phase 2 (수집 및 스케줄 완성): 수정계수·재무제표·분봉 수집 기능 개별 구현 및 시가총액 수집 + 전체 스케줄 자동화 통합 완성
- Phase 3 (API 완성): 전체 REST API + Blacklist + WebSocket
- Phase 4 (연동): p4_manager E2E 연동 검증

---

## § 2. Task 의존성 흐름

```
T-001 (인프라)
  │
  ▼
T-002 (OHLCV + 종목마스터 / KIS)
  │
  ├──→ T-003 (수정계수 + 역산 API / KIS)
  │         │
  │         ▼
  │       T-004 (재무제표 수집)
  │         │
  ├──→ T-005 (분봉 수집 / Kiwoom)
  │         │
  ▼         ▼
T-006 (시총 + 전체 스케줄 자동화 완성)
  │
  ▼
T-007 (조회 API + Blacklist)
  │
  ▼
T-008 (헬스·어드민 API + WebSocket)
  │
  ▼
T-009 (p4_manager 연동)
```

---

## § 3. Task 목록

### Phase 1: DB 인계 + 핵심 수집

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-001 | 프로젝트 기반 구조 및 DB 인계 | Docker Compose(`container_name: kdms_timescaledb`, `external:true`), FastAPI 골격(`main.py`, `config.py`), `repositories/base.py`(EnvDetector DSN 자동 결정), `StartupValidator` lifespan 연동, BackupManager 인계 전 백업 실행 | 완료 | High | - | 2026-05-14 | 2026-05-14 |
| T-002 | 일일 OHLCV + 종목 마스터 수집 (KIS) | `collectors/kis_kr_client.py`(KisApiCore 래퍼, `start_date` 무시 페이지네이션 처리), `repositories/ohlcv_repo.py`, `repositories/master_repo.py`, `tasks/daily_task.py` 1차 구현(OHLCV + 종목마스터), `/api/data/stocks` | 완료 | High | T-001 | 2026-05-15 | 2026-05-15 |

### Phase 2: 개별 수집 및 스케줄 자동화 완성

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-003 | 수정계수 수집 + 역산 API 및 물리 테이블 반영 (KIS) | `collectors/factor_calculator.py`(누적곱 알고리즘), `repositories/factor_repo.py`, `price_adjustment_factors` CRUD, `/api/data/factors`, `/api/data/ohlcv/daily/adjusted`, `daily_ohlcv_adjusted` 물리 갱신 및 조회 API 완성 | 완료 | High | T-002 | 2026-05-21 | 2026-05-21 |
| T-004 | PIT 재무제표 수집 | `tasks/financial_task.py`(KIS `fetch_all_financial_data`), `repositories/financial_repo.py`, `financial_statements` / `financial_ratios` CRUD (PIT Key: `retrieved_at`) | 완료 | Medium | T-003 | 2026-05-21 | 2026-05-21 |
| T-005 | 분봉 수집 (Kiwoom) | `collectors/kiwoom_client.py`(KiwoomApiCore 래퍼 — 분봉 전용), `collectors/target_selector.py`(직전 분기 평균 거래대금 상위N), `tasks/backfill_task.py`(분봉 백필) | 완료 | Medium | T-002 | 2026-05-21 | 2026-05-21 |
| T-006 | 시가총액 수집 + 전체 스케줄 자동화 완성 | `collectors/krx_loader.py`(pykrx → run_in_executor), `repositories/market_cap_repo.py`, `daily_task.py`에 F-04 통합, 시가총액 갭 복구(2025년 11월 이전부터 현재까지), `AsyncIOScheduler` lifespan 연동 + 전체 자동화 스케줄(`daily_update(17:10)`, `financial_update(토 09:00)`, `backfill_minute(토 10:20)`) 등록 및 완성, `/api/admin/tasks/{id}/run` 수동 실행 엔드포인트 | 완료 | High | T-004, T-005 | - | - |

### Phase 3: API 완성

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-007 | 조회 API 완성 + Blacklist 패턴 | `/api/data/ohlcv/daily`, `/api/data/ohlcv/minute`, `/api/data/financials`, `/api/data/screening`, `/api/data/market-cap`, `/api/data/preview/{table}`, Blacklist 패턴(수집 실패 종목 사유 코드 관리, `daily_task.py` skip 로직 교체) | 완료 | Medium | T-006 | - | - |
| T-008 | 헬스·어드민 API + WebSocket | `/api/health/freshness`, `/api/health/gaps`, `/api/health/milestones` CRUD, `/api/admin/schedules` 조회·수정, `WS /ws/logs` 실시간 실행 로그 스트리밍 | 완료 | Medium | T-007 | - | - |

### Phase 4: p4_manager 연동

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-009 | p4_manager 연동 테스트 | p4_manager 연동 API E2E 시나리오 검증, 인증/권한 확인, 엔드포인트별 계약 검증 | 대기 | Low | T-008 | - | - |

**상태값:** `대기` / `진행 중` / `완료` / `보류`

---

## § 4. PRD 요구사항 커버리지

| PRD 요구사항 ID | 요구사항 | 구현 Task |
|----------------|---------|-----------|
| F-01 | 일일 시세 수집 OHLCV (KIS 단일 소스) | T-002 |
| F-02 | 주가 수정계수 계산 및 관리 (KIS) | T-003 |
| F-03 | PIT 재무제표 수집 | T-004 |
| F-04 | 시가총액 수집 (pykrx) | T-006 |
| F-05 | 분봉 데이터 수집 (Kiwoom) | T-005 |
| F-06 | 종목 마스터 관리 | T-002 |
| API-데이터 | 데이터 조회 엔드포인트 9종 | T-002(`/stocks`), T-003(`/factors`, `/adjusted`), T-007(나머지 6종) |
| API-헬스 | 헬스·시스템 엔드포인트 9종 + WebSocket | T-006(`/tasks/{id}/run`), T-008(나머지) |
| SCHED | 3종 자동화 스케줄 | T-006 |
| REFACTOR-1 | `db_manager.py` → `repositories/` 분리 | T-001(base), T-002(ohlcv, master), T-003(factor), T-004(financial), T-006(market_cap) |
| REFACTOR-2 | `kiwoom_rest.py` → `p1_shared/KiwoomApiCore` 통합 | T-005 |
| REFACTOR-3 | `ops/` 진입점 정리 (레거시 제거) | T-007 |
| REFACTOR-4 | Blacklist 패턴 도입 | T-007 |
| INFRA | Docker 인계 + StartupValidator + BackupManager | T-001 |
| INFRA-KIS | OHLCV 소스 Kiwoom → KIS 전환 | T-002 |

**미커버 항목:** 없음

---

## § 5. 진행 현황

| 구분 | 수량 |
|------|------|
| 전체 | 9개 |
| 완료 | 8개 |
| 진행 중 | 0개 |
| 대기 | 1개 |


---

## § 6. 변경 이력

| 날짜 | 변경 내용 | 사유 |
|------|----------|------|
| 2026-05-21 | T-003 수정계수 인프라 및 API, 물리 갱신 구현 완료 | KIS 마스터 바이트 슬라이싱 적용, API 4종 추가, DailyTask 통합, 전체 단위 테스트 통과 |
| 2026-05-20 | 구현 순서에 맞게 T- 번호 재정렬 (T-003~T-006) | Task 선후 관계 변경에 맞추어 태스크 번호 재부여 (수정계수: T-003, 재무제표: T-004, 분봉: T-005, 시총/스케줄: T-006) |
| 2026-05-20 | T-003 의존성 및 순서 조정 (Phase 1 -> Phase 2 이동) | 일일 스케줄 자동화 완성 시점에 수정계수, 재무제표, 분봉 수집이 선행되도록 선후관계 재설정 |
| 2026-05-14 | 초안 작성 (9개 Task, Phase 1~4) | PRD v1.1 기반 최초 작성 |
| 2026-05-14 | OHLCV 수집 소스 Kiwoom → KIS 변경 반영 | Kiwoom 수정주가 오류 이력, KIS 단일화 결정 |
| 2026-05-14 | 13개 → 9개 Task 통합 (T-002+T-003, T-004+T-005, T-006+T-007, T-010+T-011) | Task 세분화 과다, 세션 단위 완결성 기준 재조정 |
