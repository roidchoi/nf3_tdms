# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p1_shared (공통 인프라 라이브러리)
> **마지막 업데이트**: 2026-05-28 (KIS/Kiwoom API 스로틀링 반영 완료)
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

```
tdms_core/p1_shared/
├── p1_shared/                   # 패키지 루트 (editable install로 배포)
│   ├── __init__.py              ✅
│   ├── api/                     # API 클라이언트 레이어  ✅
│   │   ├── __init__.py
│   │   ├── kis_api_core.py      # KIS REST API 클라이언트 (T-005)
│   │   ├── kiwoom_api_core.py   # Kiwoom REST API 클라이언트 (T-004)
│   │   └── token_manager.py     # 파일 기반 토큰 캐시 (T-004)
│   ├── db/                      # DB 접근 레이어  ✅
│   │   ├── __init__.py
│   │   ├── connection.py        # DbConnectionPool (T-003)
│   │   └── exceptions.py        # DbConnectionError, DbOperationError
│   ├── ops/                     # 운영 도구 레이어  ✅
│   │   ├── __init__.py
│   │   ├── auditors/            ✅
│   │   │   ├── audit_deep.py    # 정밀 무결성 감사 (양측 DB 대조)
│   │   │   ├── audit_fast.py    # 빠른 테이블 통계 비교
│   │   │   └── audit_usdms.py   # USDMS 전용 감사
│   │   ├── backup_manager.py    # pg_dump 백업·복구·검증 (T-006)
│   │   ├── db_sync.py           # 물리적 DB 동기화 파이프라인 (T-008)
│   │   ├── logger.py            # 공통 로거 get_logger() (T-001)
│   │   ├── startup_validator.py # DB 기동 검증기 (T-007)
│   │   └── sync_manager.py      # 논리적 동기화 (폐기 예정, T-008에 흡수)
│   └── utils/                   # 유틸리티 레이어  ✅
│       ├── __init__.py
│       ├── date_utils.py        # 한국 거래일 유틸 (T-001)
│       ├── env_detector.py      # 환경 자동 감지 (T-002)
│       └── retry.py             # 지수 백오프 재시도 데코레이터 (T-001)
├── tests/                       ✅
│   ├── test_connection.py
│   ├── test_connection_integration.py
│   ├── test_startup_validator.py
│   ├── test_startup_validator_integration.py
│   ├── test_sync_manager.py
│   ├── test_logger.py
│   ├── test_retry.py
│   ├── test_kis_api_core.py
│   ├── test_kiwoom_api_core.py
│   └── test_db_sync.py
├── requirements.txt             # psycopg2-binary, requests, python-dotenv, pytest, pytest-mock
├── pyproject.toml               # 패키지 메타데이터
└── p1_shared구현폴더.md         # 구현 폴더 규약 확인용

docs/p1_shared/
├── p1_shared_PRD.md             # 전체 PRD (871줄)
├── p1_shared_pjt_tasks.md       # Task 목록 (T-001~T-009)
├── shared_PRD보완지침.md         # 핵심 아키텍처 결정 보완
├── 의존성관리지침.md              # Conda/uv 환경 정책
├── tasks/                       # 각 Task별 Spec + Walkthrough
│   ├── task-001_spec.md / task-001_walkthrough.md
│   ├── task-002_spec.md / task-002_walkthrough.md
│   ├── task-003_spec.md / task-003_walkthrough.md
│   ├── task-004_spec.md / task-004_walkthrough.md
│   ├── task-005_spec.md / task-005_walkthrough.md
│   ├── task-006_spec.md / task-006_walkthrough.md
│   ├── task-007_spec.md / task-007_walkthrough.md
│   ├── task-008_spec.md / task-008_walkthrough.md
│   └── task-009_spec.md        (폐기됨, T-008에 흡수)
└── ops/                         # 운영 가이드 문서
    ├── db_sync_guide.md         # db_sync.py 사용법
    ├── timescaledb_sync_guide.md # 실패 분석 + 정립 프로토콜
    └── kdms_migration_history_20260507.md # KDMS 마이그레이션 실전 로그
```

---

## 2. 핵심 데이터 흐름

```
[외부 API: KIS / Kiwoom]
    │ KisApiCore / KiwoomApiCore (토큰 자동 관리)
    ▼
[p2_kdms / p3_usdms 수집 레이어]
    │ DbConnectionPool.get_cursor()
    ▼
[TimescaleDB (Docker)]
    │ BackupManager.backup()        ← 정기 스냅샷
    │ PhysicalSyncManager.execute() ← 개발PC ↔ 서버PC 동기화
    ▼
[감사: audit_fast / audit_deep / audit_usdms]
```

---

## 3. 모듈별 상태 및 역할

| 모듈/폴더 | 상태 | 핵심 파일 | 역할 요약 |
|---|---|---|---|
| `db/connection.py` | ✅ | DbConnectionPool | psycopg2 커넥션 풀, context manager 패턴 |
| `db/exceptions.py` | ✅ | DbConnectionError, DbOperationError | DB 예외 계층 |
| `utils/env_detector.py` | ✅ | EnvDetector | 개발PC/서버PC 자동 감지, .env 프로파일 로드 |
| `utils/retry.py` | ✅ | retry(), async_retry() | 지수 백오프 데코레이터 |
| `utils/date_utils.py` | ✅ | get_kr_trading_days() | 한국 주식 거래일 계산 |
| `ops/logger.py` | ✅ | get_logger() | 공통 구조화 로거 |
| `ops/backup_manager.py` | ✅ | BackupManager | pg_dump Fc 백업, pre-data→data→post-data 강건 복원 |
| `ops/startup_validator.py` | ✅ | StartupValidator | Docker 재기동 후 DB 5종 검증 |
| `ops/db_sync.py` | ✅ | PhysicalSyncManager | tar+SSH 파이프라인 물리 동기화 |
| `ops/sync_manager.py` | ⚠️ | SyncManager | **폐기 예정** — T-008의 PhysicalSyncManager로 대체 |
| `ops/auditors/` | ✅ | audit_fast/deep/usdms | 동기화 후 무결성 감사 |
| `api/token_manager.py` | ✅ | TokenManager | 파일 기반 API 토큰 캐시 |
| `api/kis_api_core.py` | ✅ | KisApiCore | KIS REST API, 401 자동 토큰 갱신, 스로틀링 딜레이(실전 0.08s, 모의 0.4s) |
| `api/kiwoom_api_core.py` | ✅ | KiwoomApiCore | Kiwoom REST API, TokenManager 연동, 스로틀링 딜레이(0.25s) |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트 | 실행 방법 | 역할 |
|---|---|---|
| `ops/db_sync.py` | `conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction pull` | 물리 DB 동기화 실행 |
| `ops/auditors/audit_fast.py` | `conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_fast` | 빠른 양측 DB 통계 비교 |
| `ops/auditors/audit_deep.py` | `conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_deep` | 정밀 무결성 검증 |
| `ops/auditors/audit_usdms.py` | `conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_usdms` | USDMS 전용 데이터 건수 검증 |

---

## 5. 테스트 현황

| 테스트 파일 | 커버 대상 | 단위 | 통합 | 상태 |
|---|---|---|---|---|
| `test_connection.py` | DbConnectionPool | ✅ | — | ✅통과 |
| `test_connection_integration.py` | DbConnectionPool 실 DB | — | ✅ | ✅통과 |
| `test_startup_validator.py` | StartupValidator | 14개 | — | ✅통과 |
| `test_startup_validator_integration.py` | StartupValidator 실 DB | — | 6개 | ✅통과 |
| `test_logger.py` | get_logger() | ✅ | — | ✅통과 |
| `test_retry.py` | retry/async_retry | ✅ | — | ✅통과 |
| `test_kis_api_core.py` | KisApiCore | ✅ | — | ✅통과 |
| `test_kiwoom_api_core.py` | KiwoomApiCore | ✅ | — | ✅통과 |
| `test_sync_manager.py` | SyncManager(폐기예정) | ✅ | — | ✅통과 |
| `test_db_sync.py` | PhysicalSyncManager | ✅ | — | ✅통과 |

---

## 6. 변경 이력 요약

| Task | 주요 변경 내용 |
|---|---|
| T-001 | 패키지 기반 구조 수립, logger/retry/date_utils 구현 |
| T-002 | EnvDetector 구현, WSL2 네트워크 IP 감지 로직 |
| T-003 | DbConnectionPool 구현, context manager 패턴 |
| T-004 | TokenManager + KiwoomApiCore 구현 |
| T-005 | KisApiCore 구현, 401 자동 토큰 갱신 |
| T-006 | BackupManager 구현, pre-data→data→post-data 강건 복원 |
| T-007 | StartupValidator 구현, 5종 검증 + FastAPI lifespan 패턴 |
| T-008 | PhysicalSyncManager 구현 (T-009 흡수), tar+SSH 파이프라인 |
| 2026-05-28 | KIS/Kiwoom OpenAPI 속도 제어(Throttling Delay) 도입 |
