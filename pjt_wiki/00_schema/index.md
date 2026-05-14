# pjt_wiki Index (MoC)

> **프로젝트**: NF3 TDMS (Total Data Management System)
> **마지막 업데이트**: 2026-05-14 (T-001~T-008 전체 완료)
> **총 등록 파일**: 15개

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

## p1_wiki (p1_shared 공통 인프라)

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

## 빠른 참조 — 현재 가장 중요한 항목

### ⚠️ 필독 에러

- [P1-ERR-001] Docker 볼륨 UID 불일치 → `p1_wiki/errors/p1-err-001_volume_uid_mismatch.md`
- [P1-ERR-002] pg_restore 논리 복원 실패 → `p1_wiki/errors/p1-err-002_logical_restore_failure.md`

### 📐 최근 변경된 인터페이스

- `PhysicalSyncManager`: T-008에서 T-009 흡수, tar+SSH 파이프라인 확정 → `p1_wiki/interfaces/physical_sync_manager.md`
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