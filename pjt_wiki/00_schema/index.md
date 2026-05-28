# pjt_wiki Index (MoC)

> **프로젝트**: NF3 TDMS (Total Data Management System)
> **마지막 업데이트**: 2026-05-27
> **총 등록 파일**: 21개

---

## 사용 지침

이 파일은 Claude가 새 세션에서 가장 먼저 읽는 파일이다. 전체 wiki를 읽지 않아도 "어디에 무엇이 있는지" 파악하는 용도.

---

## parent_wiki (전체 공통)

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `overview.md` | 전체 Sub Project 구성 및 진행도 (템플릿) | — |
| `architecture.md` | 시스템 아키텍처 (템플릿) | — |
| `decisions.md` | 공통 의사결정 (템플릿) | — |
| `environment.md` | 공통 환경 (템플릿) | — |

---

## p1_shared_wiki (p1_shared 공통 인프라)

> **역할**: p2_kdms, p3_usdms, p4_manager가 공통으로 의존하는 핵심 라이브러리
> **상태**: ✅ T-001~T-008 모두 완료 | 전체 테스트 통과

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 21개 소스 파일 구조, 모듈 상태, 테스트 현황 | T-008 |
| `environment.md` | tdms_p1_env Conda, 패키지 버전, .env 변수, Docker 구성 | T-008 |
| `operations/runbook.md` | DB 동기화/감사/백업/검증/테스트 실행 명령 모음 | T-008 |

### interfaces/ (God Node 우선 — 연결도 순)

| 파일 | 핵심 클래스 | edges | 내용 요약 |
|---|---|---|---|
| `env_detector.md` | EnvDetector | **97** | 개발PC/서버PC 자동 감지, .env 프로파일 로드 |
| `db_connection_pool.md` | DbConnectionPool | **80** | psycopg2 커넥션 풀, get_cursor() context manager |
| `backup_manager.md` | BackupManager | **58** | pg_dump 백업, pre-data→data→post-data 강건 복원 |
| `startup_validator.md` | StartupValidator | **48** | Docker 재기동 후 5종 검증, FastAPI lifespan 패턴 |
| `physical_sync_manager.md` | PhysicalSyncManager | **20** | tar+SSH 물리 동기화, 5단계 파이프라인 |
| `kis_api_core.md` | KisApiCore | — | KIS REST API 연동, OAuth2 토큰 자동 관리, 지수 백오프 재시도 및 스로틀 지연 적용 |
| `kiwoom_api_core.md` | KiwoomApiCore | — | Kiwoom REST API 연동, OAuth2 토큰 자동 관리, 초당 5회 제한 스로틀 0.25초 지연 적용 |

### decisions/ (핵심 기술 의사결정)

| 파일 | 결정 요약 | 발생 Task |
|---|---|---|
| `dec-001_physical_sync.md` | 논리 복원 실패 → 물리 Stop-and-Copy 채택 | T-008 |
| `dec-002_pg_restore_section_order.md` | FK 순서 문제 → pre-data→data→post-data 복원 | T-006 |

### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `p1-err-001_volume_uid_mismatch.md` | 물리 복제 후 UID 불일치 → chown 1000:1000 | High |
| `p1-err-002_logical_restore_failure.md` | pg_restore 하이퍼테이블 충돌 → 물리 복제로 전환 | High |

---

## p2_kdms_wiki (p2_kdms 한국 시장 백엔드)

> **역할**: 한국 시장 주가/재무/시총/분봉 데이터 수집 및 조회 API 백엔드
> **상태**: 🔄 구현 완료 — 지식화 완료 (2026-05-26, Graphify 기반)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 전체 폴더 구조, 모듈 상태, 데이터 흐름, 테스트 현황 | 2026-05-26 |
| `environment.md` | tdms_p2_env Conda, 패키지 버전, .env Layer A/B 변수 | 2026-05-26 |
| `operations/runbook.md` | API 서버 구동, 배치 태스크(daily_update, financial, backfill) 수동 트리거 및 ops 스크립트 실행 가이드 | 2026-05-26 |

### interfaces/ (God Node 우선 — 연결도 순)

| 파일 | 핵심 클래스/모듈 | degree | 내용 요약 |
|---|---|---|---|
| `ohlcv_repo.md` | OhlcvRepo | **39** | 일봉/수정주가(On-the-fly+물리)/분봉 CRUD, 팩터역산용 DF |
| `financial_repo.md` | FinancialRepo | **38** | PIT 재무제표/비율 INSERT + DISTINCT ON 버전 선택 |
| `schema_kdms_db.md` | kdms_db | — | kdms_timescaledb 내 12개 테이블 컬럼 타입, PK, 인덱스, hypertable 3종 상세 스키마 |
| `data_api_endpoints.md` | routers/data.py | — | /api/data/* 전체 엔드포인트 명세 |
| `fastapi_lifespan.md` | main.py lifespan | — | DB풀, StartupValidator, APScheduler 크론 등록 순서 |
| `settings_config.md` | Settings | — | pydantic-settings Layer A/B 이중 구조, .env 변수 |

### decisions/

| 파일 | 결정 요약 | Task |
|---|---|---|
| `dec-001_pit_financial_pattern.md` | PIT 재무: ON CONFLICT 없이 INSERT → DISTINCT ON 버전 선택 | T-004 |
| `dec-002_price_adjustment_dual_strategy.md` | 수정주가: On-the-fly + 물리 테이블 이중 제공 | T-003 |
| `dec-003_support_alphanumeric_stock_codes.md` | 종목코드: 한국거래소(KRX) 알파벳 혼용 종목코드 지원을 위한 수집기 필터 완화 | — |
| `dec-004_kis_api_throttling_strategy.md` | 속도 정책: 안전 마진 기반 KIS API 스로틀링(Throttling) 및 방어적 시가총액 bigint 연산 | Task-010 |

### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `err-001_kis_api_403_forbidden.md` | API 과호출로 인한 KIS IP 차단 (403 Forbidden) -> Throttling 딜레이 도입 | High |
| `err-002_bigint_out_of_range_in_market_cap.md` | 기형적 주식수 데이터 연산으로 인한 시총 bigint 오버플로우 -> 1000억 주 초과 컷오프 | Critical |

---

## p3_usdms_wiki (p3_usdms 미국 시장 백엔드)

> **역할**: 미국 시장 티커/주가/재무/가치지표 데이터 수집 및 조회 API 백엔드
> **상태**: ⬜ 미착수 (템플릿 상태)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 미국 시장 코드베이스 물리 구조 및 모듈 상태 | — |
| `environment.md` | p3_usdms Conda 환경 및 의존성 패키지 | — |

---

## p4_manager_wiki (p4_manager 통합 관리 레이어)

> **역할**: 한국/미국 백엔드 통합 모니터링 UI 및 오케스트레이션
> **상태**: ⬜ 미착수 (템플릿 상태)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 통합 관리자 코드베이스 물리 구조 및 모듈 상태 | — |
| `environment.md` | p4_manager 개발 환경 및 의존성 패키지 | — |

---

## 빠른 참조 — 현재 가장 중요한 항목

### ⚠️ 필독 에러

- [P1-ERR-001] Docker 볼륨 UID 불일치 → `p1_shared_wiki/errors/p1-err-001_volume_uid_mismatch.md`
- [P1-ERR-002] pg_restore 논리 복원 실패 → `p1_shared_wiki/errors/p1-err-002_logical_restore_failure.md`
- [P2-ERR-001] KIS API 403 Forbidden 차단 → `p2_kdms_wiki/errors/err-001_kis_api_403_forbidden.md`
- [P2-ERR-002] 시총 bigint 오버플로우 롤백 → `p2_kdms_wiki/errors/err-002_bigint_out_of_range_in_market_cap.md`

### 📐 최근 변경된 인터페이스

- `PhysicalSyncManager`: T-008에서 T-009 흡수, tar+SSH 파이프라인 확정 → `p1_shared_wiki/interfaces/physical_sync_manager.md`
- `SyncManager`: **폐기 예정** — 실운영 사용 금지, PhysicalSyncManager 사용

### 🔄 진행중인 작업

- p1_shared: ✅ 완료 (T-001~T-008)
- 다음: p2_kdms, p3_usdms, p4_manager 구현 예정

---

## Graphify 지식 그래프 연동

> `graphify-out/GRAPH_REPORT.md` 참조 (464 nodes, 1183 edges, 17 communities)

| Community | 핵심 노드 | 설명 |
|---|---|---|
| DB Connection & Startup Validation | DbConnectionPool, StartupValidator | 74 nodes |
| Environment Detection & Auditing | EnvDetector, audit_* | 64 nodes |
| Backup Manager Operations | BackupManager | 53 nodes |
| Physical DB Sync Pipeline | PhysicalSyncManager | 25 nodes |
| Sync Manager (Legacy Logical) | SyncManager (**폐기 예정**) | 38 nodes |