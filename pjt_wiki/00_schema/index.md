# pjt_wiki Index (MoC)

> **프로젝트**: NF3 TDMS (Total Data Management System)
> **마지막 업데이트**: 2026-06-10
> **총 등록 파일**: 40개


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
| `date_utils.md` | — | — | 한국 거래일 및 미국 주식시장 영업일 판별 공통 유틸리티 |
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
> **상태**: ✅ T-008 완료 (DatabaseManager 레거시 제거, 수집 기준/스케줄 설정 외부화, 미국 휴장 판단 및 trading_calendar 동기화 완료)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 미국 시장 코드베이스 물리 구조 및 모듈 상태 | 2026-06-05 |
| `environment.md` | p3_usdms Conda 환경 및 의존성 패키지 | 2026-06-05 |
| `interfaces/schema_usdms_db.md` | usdms_db TimescaleDB 스키마 구성, 인덱스 및 관계 명세 | 2026-06-08 |

### interfaces/ (미국 시장 마스터 수집 핵심 인터페이스)

| 파일 | 핵심 클래스/모듈 | 내용 요약 |
|---|---|---|
| `sec_client.md` | SECClient | SEC EDGAR API 래퍼 (Rate Limit 및 User-Agent 준수) |
| `master_sync.md` | MasterSync | 마스터 티커 동기화 파이프라인 (Logic V2, SCD Type 2, yfinance Enrichment) |
| `master_enricher.md` | MasterEnricher | yfinance 기반 메타데이터 보강, ADR 수집 제외 및 에러 백오프 통제 |
| `master_repo.md` | MasterRepo | 마스터, 이력 DB CRUD 및 Dynamic Targeting Rules SQL 적용 |
| `blacklist_repo.md` | BlacklistRepo | us_collection_blacklist 테이블 연동 CRUD 처리 |
| `blacklist_manager.md` | BlacklistManager | 실패 에러 분석 및 일시적/영구적 에러 분기, 쿨다운 관리 매니저 |
| `daily_routine.md` | DailyRoutine | 5단계 일일 루틴 자동화, 동적 lookback 계산 및 이상치 롤백/격리 |
| `financial_parser.md` | FinancialParser | SEC XBRL facts 수집/정제 및 discrete 분기 재무 데이터 도출 파이프라인 |
| `financial_repo.md` | FinancialRepo | us_financial_facts, us_standard_financials, us_share_history 테이블 CRUD/Upsert |
| `xbrl_mapper.md` | XBRLMapper | US-GAAP 원시 태그의 분석용 표준 회계 필드 우선순위 매핑 및 정규화 |
| `valuation_repo.md` | ValuationRepo | 일별 가격, 주식수 이력, 표준재무 조회 및 daily_valuation/financial_metrics 일괄 Upsert |
| `valuation_engine.md` | ValuationCalculator / MetricCalculator | PIT 가치평가(5대 가치지표), 9대 재무비율 및 3대 YoY 성장률 산출 |
| `data_api_endpoints.md` | routers/data.py | REST API 7종 엔드포인트 명세 및 Throttling 범위, Arrow 바이너리 직렬화 규격 |
| `health_admin_api.md` | routers/health.py, routers/admin.py | Freshness/Gaps/Blacklist 헬스 체크, 동적 크론 제어, 및 WebSocket 실시간 로그 전송 엔드포인트 명세 |
| `auditors.md` | FinancialDiagnostic, MetricVerifier, PriceReproducer | 재무(항등식/Null), 지표(ROE/Outlier), 수정주가(KIS API 대조) 감사 엔진 3종의 시그니처 및 사양 |

### decisions/

| 파일 | 결정 요약 | Task |
|---|---|---|
| `decisions.md#USDMS_DEC-001` | SEC XBRL 재무 데이터 이산화 계산 및 Overwrite 벌크 갱신 전략 | T-003 |
| `decisions.md#USDMS_DEC-002` | 자가 치유형(Self-Healing) 가치평가 및 지표 복구 엔진 최적화 | T-005 |
| `decisions.md#USDMS_DEC-003` | 일시적/영구적 에러의 이원화 예외 처리 및 자동 쿨다운 릴리즈 루프 | T-005 |
| `decisions.md#USDMS_DEC-004` | 수집 마감 분기점 및 거래정지/차단 배제 기반 실질 갭 진단 정책 | T-007 |

### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `usdms-err-001_wsl2_bind_mount_sync_error.md` | WSL2 마운트 동기화 유실로 인한 빈 DB 기동 현상 | High |
| `usdms-err-002_valuation_rebuild_timeout.md` | Valuation 자가치유 갭 탐색 쿼리 실행 지연 및 타임아웃 | High |

---

## p4_manager_wiki (p4_manager 통합 관리 레이어)

> **역할**: 한국/미국 백엔드 통합 모니터링 UI 및 오케스트레이션
> **상태**: ✅ T-006 공통 헬스 모니터링 및 시장별 특화 패널 완료 (2026-06-09)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 17개 파일의 물리구조, 새로 구성된 Vue SPA 프론트엔드 폴더 구조 및 테스트 현황 | T-007 |
| `environment.md` | tdms_p4_env Conda/Node.js 런타임 환경, 주요 패키지(fastapi, vue3, vitest, websockets) 버전, Nginx 프록시 해결책 및 TS5101/TS6133 빌드 오류 대안 기록 | T-007 |
| `decisions.md` | Nginx 동적 리졸브(P4DEC-001) 및 백그라운드 캐싱 폴링/장애 격리(P4DEC-002), 데이터 갭 정규화 및 API 동적 예외 격리(P4DEC-003) 적용 결정 | T-006 |

### interfaces/ (인터페이스 명세)

| 파일 | 핵심 클래스/모듈 | 내용 요약 | 마지막 업데이트 |
|---|---|---|---|
| `api_routing_map.md` | — | `/api/mgr/health`, `/api/mgr/run`, 스케줄 3종 및 헬스 6종 API 명세, Nginx 80포트 리버스 프록시 / WebSocket 5종 라우팅 맵 | T-007 |
| `get_integrated_status.md` | status_service | `/api/mgr/status` 통합 상태 집계 API 명세 및 KR/US 예외 격리(Fault Isolation) 리턴 스키마 | T-002 |
| `post_run_task.md` | status_service / routers/manager.py | `/api/mgr/run` 수동 태스크 기동 API 및 KR/US 동적 중계 규격 | T-003 |
| `ws_proxy_logs.md` | proxy_ws.py | `/api/mgr/ws/logs/{market}` WebSocket 중계 프록시 API 명세 및 리소스 누수 방지 설계 결정 | T-004 |
| `get_health_freshness.md` | routers/manager.py | `/api/mgr/health/freshness/{market}` 데이터 수집 신선도 중계 API 명세 | T-006 |
| `get_health_gaps.md` | routers/manager.py | `/api/mgr/health/gaps/{market}` 데이터 누락 갭 정규화 및 중계 API 명세 | T-006 |
| `post_blacklist_release.md` | routers/manager.py | `/api/mgr/health/us/blacklist/{cik}/release` 미국 CIK 수집 차단 해제 중계 API 명세 | T-006 |
| `kr_milestones.md` | routers/manager.py | `/api/mgr/health/kr/milestones` 한국 마일스톤 생성/조회 중계 API 명세 | T-006 |
| `get_preview_meta.md` | routers/manager.py | `/api/mgr/preview/meta` 데이터 탐색기 지원 테이블 메타조회 API 명세 | T-007 |
| `get_preview_table.md` | routers/manager.py | `/api/mgr/preview/{market}/{table}` 데이터 100건 동적 조회 및 장애 격리 API 명세 | T-007 |


### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `p4err-001_module_not_found_tdms_core.md` | 도커 백엔드 기동 시 `tdms_core` 임포트 불가 (PYTHONPATH 부재) -> Dockerfile 내 `ENV PYTHONPATH="/app"` 추가 주입 | High |

---

## 빠른 참조 — 현재 가장 중요한 항목

### ⚠️ 필독 에러

- [P1-ERR-001] Docker 볼륨 UID 불일치 → `p1_shared_wiki/errors/p1-err-001_volume_uid_mismatch.md`
- [P1-ERR-002] pg_restore 논리 복원 실패 → `p1_shared_wiki/errors/p1-err-002_logical_restore_failure.md`
- [P2-ERR-001] KIS API 403 Forbidden 차단 → `p2_kdms_wiki/errors/err-001_kis_api_403_forbidden.md`
- [P2-ERR-002] 시총 bigint 오버플로우 롤백 → `p2_kdms_wiki/errors/err-002_bigint_out_of_range_in_market_cap.md`
- [USDMS-ERR-001] WSL2 바인드 마운트 동기화 유실 → `p3_usdms_wiki/errors/usdms-err-001_wsl2_bind_mount_sync_error.md`
- [USDMS-ERR-002] Valuation 자가치유 갭 탐색 타임아웃 → `p3_usdms_wiki/errors/usdms-err-002_valuation_rebuild_timeout.md`

### 📐 최근 변경된 인터페이스

- `post_run_task`: `/api/mgr/run` 수동 태스크 기동 API 및 KR/US 동적 중계 규격 → `p4_manager_wiki/interfaces/post_run_task.md`
- `get_integrated_status`: `/api/mgr/status` 통합 상태 집계 API 명세 및 KR/US 예외 격리(Fault Isolation) 리턴 스키마 → `p4_manager_wiki/interfaces/get_integrated_status.md`
- `ws_proxy_logs`: `/api/mgr/ws/logs/{market}` WebSocket 로그 중계 프록시 API 스펙 및 자원 방출 설계 결정 → `p4_manager_wiki/interfaces/ws_proxy_logs.md`
- `api_routing_map`: `/api/mgr/health` 및 `/api/mgr/run`, 스케줄 3종 및 헬스 6종 API 명세, Nginx 리버스 프록시/WS 중계 경로 맵 → `p4_manager_wiki/interfaces/api_routing_map.md`
- `get_health_freshness`: `/api/mgr/health/freshness/{market}` 데이터 수집 신선도 중계 API 명세 → `p4_manager_wiki/interfaces/get_health_freshness.md`
- `get_health_gaps`: `/api/mgr/health/gaps/{market}` 데이터 누락 갭 정규화 및 중계 API 명세 → `p4_manager_wiki/interfaces/get_health_gaps.md`
- `post_blacklist_release`: `/api/mgr/health/us/blacklist/{cik}/release` 미국 CIK 수집 차단 해제 중계 API 명세 → `p4_manager_wiki/interfaces/post_blacklist_release.md`
- `kr_milestones`: `/api/mgr/health/kr/milestones` 한국 마일스톤 생성/조회 중계 API 명세 → `p4_manager_wiki/interfaces/kr_milestones.md`
- `get_preview_meta`: `/api/mgr/preview/meta` 데이터 탐색기 지원 테이블 메타조회 API 명세 → `p4_manager_wiki/interfaces/get_preview_meta.md`
- `get_preview_table`: `/api/mgr/preview/{market}/{table}` 데이터 100건 동적 조회 및 장애 격리 API 명세 → `p4_manager_wiki/interfaces/get_preview_table.md`
- `DailyRoutine`: target_date 파라미터화, 미국 휴장일 자동 스킵 및 trading_calendar 테이블 자동 동기화 → `p3_usdms_wiki/interfaces/daily_routine.md`
- `date_utils`: 미국 주식시장 영업일/공휴일 판정 및 마지막 영업일 산출 공통 유틸리티 → `p1_shared_wiki/interfaces/date_utils.md`
- `Health/Admin API Endpoints`: Freshness/Gaps 판정, 차단 해제 API 신설, 동적 스케줄링 및 WebSocket 실시간 로그 중계 → `p3_usdms_wiki/interfaces/health_admin_api.md`
- `Auditors 3종`: 재무(항등식/Null), 지표(ROE/Outlier), 수정주가(KIS API 대조) 감사 엔진 → `p3_usdms_wiki/interfaces/auditors.md`
- `BlacklistManager`: 일시적/영구적 에러 분기 및 쿨다운 자동 해제 관리 → `p3_usdms_wiki/interfaces/blacklist_manager.md`
- `PhysicalSyncManager`: T-008에서 T-009 흡수, tar+SSH 파이프라인 확정 → `p1_shared_wiki/interfaces/physical_sync_manager.md`
- `Data API Endpoints`: REST API 7종 및 Arrow IPC 스트리밍 지원 완료 → `p3_usdms_wiki/interfaces/data_api_endpoints.md`
- `SyncManager`: **폐기 예정** — 실운영 사용 금지, PhysicalSyncManager 사용

### 🔄 진행중인 작업

- p1_shared: ✅ 완료 (T-001~T-008, 미국 영업일 판별 추가 완료)
- p2_kdms: 🔄 진행 중
- p3_usdms: ✅ 완료 (T-001~T-008)
- p4_manager: 🔄 진행 중 (T-007 완료)



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