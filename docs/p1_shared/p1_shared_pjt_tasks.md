# P1 Task 계획서

> **Sub Project**: p1_shared (공통 모듈)
> **기준 문서**: PRD v1.1 (2026-04-29)
> **작성일**: 2026-04-30
> **총 Task**: 9개 (Phase 1: 3개 / Phase 2: 2개 / Phase 3: 2개 / Phase 4: 2개)

---

## § 1. 프로젝트 개요

`p1_shared/`는 p2_kdms·p3_usdms·p4_manager가 **공통으로 사용하는 모듈**을 제공하는 기반 패키지다.
서브프로젝트는 p1_shared에 의존하나 p1_shared는 서브프로젝트에 의존하지 않으며,
모든 모듈은 p2·p3 없이 단독으로 단위 테스트 실행 가능해야 한다.

**Phase 구분 기준:**
- Phase 1 (핵심 인프라): p2·p3 구현 착수 전 반드시 완료해야 하는 공통 기반
- Phase 2 (API 클라이언트 통합): KIS·Kiwoom 토큰 캐시 공유 코어
- Phase 3 (운영 도구): 백업·복구·기동 검증 (Docker 볼륨 안전망)
- Phase 4 (DB 동기화): 개발PC ↔ 서버PC 양방향 동기화 + 실제 인계 실행

---

## § 2. Task 의존성 흐름

```
T-001 (패키지 기반 + 공통 유틸 + 로거)
  ├── T-002 (env_detector)  ─────────────────────────────┐
  └── T-003 (DB 커넥션 풀) ──────────────────────────────┤
                                                          │
T-004 (TokenManager + KiwoomApiCore)                      │
  └── T-005 (KisApiCore)                                  │
                                                          ↓
                                               T-006 (BackupManager)
                                                    │
                                               T-007 (StartupValidator)
                                               T-008 (SyncManager + SafetyChecker)
                                               (의존: T-002, T-003, T-006)
                                                    │
                                               T-009 (DB 인계 실행)
```

**병렬 가능 구간:**
- T-002, T-003, T-004 는 T-001 완료 후 **동시 진행 가능**
- T-005는 T-004 완료 후 즉시 착수 가능
- T-006, T-007 은 T-003 완료 후 **동시 진행 가능**

---

## § 3. Task 목록

### Phase 1: 핵심 인프라

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-001 | 패키지 기반 + 공통 유틸 + 로거 | `pyproject.toml` 패키지 정의 및 editable install 검증, `db/exceptions.py` 공통 예외, `utils/retry.py` (sync/async 지수 백오프 재시도 데코레이터), `utils/date_utils.py` (KR/US 영업일 유틸), `ops/logger.py` (Rich 콘솔 + 파일 로테이션 + `WebSocketQueueHandler`), 각 모듈 단위 테스트 | 대기 | High | - | - | - |
| T-002 | 환경 감지 모듈 | `utils/env_detector.py` — `TDMS_ENV` 명시 → hostname → IP 순서 감지, `.env` 환경별 프로파일 로드(`load_env_profile()`), `get_peer_host()`, `.env` 템플릿 작성, 단위 테스트 | 대기 | High | T-001 | - | - |
| T-003 | DB 커넥션 풀 | `db/connection.py` — `DbConnectionPool(psycopg2.pool.ThreadedConnectionPool 래퍼)`, `get_cursor()` context manager (예외 시 rollback·커넥션 반환 보장), `close_all()`, 스레드 안전성 검증, 단위 테스트 | 대기 | High | T-001 | - | - |

### Phase 2: API 클라이언트 통합

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-004 | 토큰 매니저 + Kiwoom API 코어 | `api/token_manager.py` — 파일 기반 토큰 캐시, `get_valid_token()`, `is_valid()` (만료 5분 전 처리), `save_token()`. `api/kiwoom_api_core.py` — `kdms_origin/kiwoom_rest.py` 기반 리팩토링, `TokenManager` 연동, `get_headers()`, `request()`, 단위 테스트 | 대기 | Medium | T-001 | - | - |
| T-005 | KIS API 코어 | `api/kis_api_core.py` — 토큰 캐시 공유 코어(`token_cache_path` 동일 경로로 p2·p3 간 공유), `get_headers()`, `request()` (401 시 자동 갱신 + 1회 재시도), `base_url` 실전/모의 자동 선택, 서브클래스(`KisKrClient`, `KisUsClient`) 패턴 검증, 단위 테스트 | 대기 | Medium | T-004 | - | - |

### Phase 3: 운영 도구

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-006 | 백업 매니저 | `ops/backup_manager.py` — `pg_dump -Fc` 백업, `verify()` (pg_restore --list 헤더 파싱), `restore()` 강건 복원 (`pre-data → data → post-data` section_order 단계별 적용, `pre_backup=True` 기본값), `check_volume_exists()` Docker 볼륨 실물 파일 확인, `list_backups()`, `cleanup_old()` 보관 정책, CLI 진입점(`python -m p1_shared.ops.backup_manager`), 단위 테스트 | 대기 | High | T-002, T-003 | - | - |
| T-007 | DB 기동 검증기 | `ops/startup_validator.py` — DB 접속 테스트, 핵심 테이블 존재·행수 검증, `check_volume_exists()` 연동, Hypertable 청크 상태 확인, `print_report()` 실패 항목별 구체적 조치 안내 출력, FastAPI lifespan 연동 패턴 검증, 단위 테스트 | 대기 | High | T-003, T-006 | - | - |

### Phase 4: DB 동기화

| ID | Task명 | 구현 범위 요약 | 상태 | 우선순위 | 의존성 | 시작일 | 완료일 |
|----|--------|--------------|------|---------|--------|--------|--------|
| T-008 | DB 동기화 매니저 | `ops/sync_manager.py` — `FullSyncSafetyChecker` (DB 크기·커버리지 비교, 이상 조건 4종 감지, `CONFIRM-FULL-SYNC` 30초 타임아웃 재확인), `SyncManager.sync()` full/diff/table 3가지 모드 (rsync SSH 전송, `section_order` 복원), `dry_run` 계획 출력, CLI 진입점, 단위 테스트 | 대기 | Medium | T-002, T-003, T-006 | - | - |
| T-009 | DB 인계 실행 | 실제 환경에서 DB 인계 검증 실행: ① kdms — 개발PC → 서버PC full 동기화 (`sync --source dev --target server --db kdms --mode full`), ② usdms — 서버PC → 개발PC full 동기화 (`sync --source server --target dev --db usdms --mode full`). `FullSyncSafetyChecker` 통과 확인 및 `StartupValidator` 결과 검증까지 완료 | 대기 | Medium | T-008 | - | - |

**상태값:** `대기` / `진행 중` / `완료` / `보류`

---

## § 4. PRD 요구사항 커버리지

| PRD 요구사항 ID | 요구사항 | 구현 Task |
|----------------|---------|-----------|
| FR-01 | 패키지 구조 정의 및 editable install (`pyproject.toml`) | T-001 |
| FR-02 | 공통 예외 정의 (`db/exceptions.py`) | T-001 |
| FR-03 | 지수 백오프 재시도 데코레이터 sync/async (`utils/retry.py`) | T-001 |
| FR-04 | KR/US 영업일 유틸리티 (`utils/date_utils.py`) | T-001 |
| FR-05 | 공통 로거 팩토리 + WebSocketQueueHandler (`ops/logger.py`) | T-001 |
| FR-06 | hostname/IP 기반 환경 자동 감지 (`utils/env_detector.py`) | T-002 |
| FR-07 | 환경별 `.env` 프로파일 자동 로드 | T-002 |
| FR-08 | `get_peer_host()` — 동기화 상대방 PC IP 반환 | T-002 |
| FR-09 | `DbConnectionPool` + `get_cursor()` context manager | T-003 |
| FR-10 | 파일 기반 토큰 캐시 (`api/token_manager.py`) | T-004 |
| FR-11 | Kiwoom REST API 코어 (`api/kiwoom_api_core.py`) | T-004 |
| FR-12 | KIS API 토큰 공유 코어 (`api/kis_api_core.py`) | T-005 |
| FR-13 | 401 응답 시 자동 토큰 갱신 + 1회 재시도 | T-005 |
| FR-14 | `pg_dump -Fc` 백업 실행 및 검증 | T-006 |
| FR-15 | 강건 복원 (pre-data → data → post-data section_order) | T-006 |
| FR-16 | Docker 볼륨 실물 파일 존재 확인 (`check_volume_exists()`) | T-006 |
| FR-17 | 백업 보관 정책 + 이력 조회 (`list_backups`, `cleanup_old`) | T-006 |
| FR-18 | CLI 진입점 (`python -m p1_shared.ops.backup_manager`) | T-006 |
| FR-19 | Docker 재기동 DB 기동 검증 (`ops/startup_validator.py`) | T-007 |
| FR-20 | 검증 실패 시 구체적 조치 방법 안내 출력 | T-007 |
| FR-21 | FastAPI lifespan 연동 패턴 | T-007 |
| FR-22 | Full 동기화 안전 검증기 (`FullSyncSafetyChecker`) | T-008 |
| FR-23 | full/diff/table 3가지 동기화 모드 | T-008 |
| FR-24 | `CONFIRM-FULL-SYNC` 재확인 + 30초 타임아웃 | T-008 |
| FR-25 | dry-run 계획 출력 | T-008 |
| FR-26 | kdms 인계: 개발PC → 서버PC full 동기화 | T-009 |
| FR-27 | usdms 인계: 서버PC → 개발PC full 동기화 | T-009 |

**미커버 항목:** 없음

---

## § 5. 진행 현황

| 구분 | 수량 |
|------|------|
| 전체 | 9개 |
| 완료 | 0개 |
| 진행 중 | 0개 |
| 대기 | 9개 |

---

## § 6. 변경 이력

| 날짜 | 변경 내용 | 사유 |
|------|----------|------|
| 2026-04-30 | 초안 작성 (14개 → 9개 통합 조정) | 단순 기능 통합, 복잡·고위험 Task 분리 유지 |
