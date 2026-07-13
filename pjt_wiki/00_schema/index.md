# pjt_wiki Index (MoC)

> **프로젝트**: NF3 TDMS (Total Data Management System)
> **마지막 업데이트**: 2026-07-09
> **총 등록 파일**: 60개


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
| `environment.md` | tdms_p1_env Conda, 패키지 버전, .env 변수, Docker 고정 IP 구성 | 2026-06-24 |
| `operations/runbook.md` | DB 동기화/감사/백업/검증/테스트 실행 명령 모음 | T-008 |

### interfaces/ (God Node 우선 — 연결도 순)

| 파일 | 핵심 클래스 | edges | 내용 요약 |
|---|---|---|---|
| `env_detector.md` | EnvDetector | **97** | 개발PC/서버PC 자동 감지, .env 프로파일 로드, 도커 DNS 장애 시 고정 IP 자동 폴백 |
| `db_connection_pool.md` | DbConnectionPool | **80** | psycopg2 커넥션 풀, get_cursor() context manager |
| `backup_manager.md` | BackupManager | **58** | pg_dump 백업, pre-data→data→post-data 강건 복원 |
| `startup_validator.md` | StartupValidator | **48** | Docker 재기동 후 5종 검증, FastAPI lifespan 패턴 |
| `physical_sync_manager.md` | PhysicalSyncManager | **20** | tar+SSH 물리 동기화, 5단계 파이프라인 |
| `schedule_utils.md` | — | — | 공통 스케줄링 문자열 파싱, .env 변수 덮어쓰기 및 요일 접두사 보존 병합 유틸리티 |
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
> **상태**: ✅ 완료 (2026-06-12, T-011 스케줄링 및 KIS 특수 상품 필터링 반영 완료)

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
| `dec-005_filter_non_equity_instruments.md` | 특수 상품: 비주식성 특수 상품(BC, MF, EW) 수집 제외 필터링 적용 | T-011 |
| `dec-006_fallback_listed_shares_mechanism.md` | 상장주식수 누락: API 0 유입 시 DB 최근 데이터 Fallback 대체 | — |
| `dec-007_financial_update_optimization.md` | KDMS 재무 업데이트 성능 최적화 전략 | — |
| `dec-008_scheduler_reload_and_logging.md` | 스케줄러 동적 리로드 및 진행률 로깅 개선 [NEW] | — |

### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `err-001_kis_api_403_forbidden.md` | API 과호출로 인한 KIS IP 차단 (403 Forbidden) -> Throttling 딜레이 도입 | High |
| `err-002_bigint_out_of_range_in_market_cap.md` | 기형적 주식수 데이터 연산으로 인한 시총 bigint 오버플로우 -> 1000억 주 초과 컷오프 | Critical |
| `err-003_task_kst_timezone_mismatch.md` | 태스크 실행 상태 기록 시 KST 시간대 처리 불일치 -> datetime.now(KST) 및 isoformat() 직렬화 | Medium |
| `err-004_listed_shares_zero_accumulation.md` | KIS 마스터 수집 장애로 인한 상장주식수/시가총액 0 누적 적재 -> 최근 10일 DB 데이터 Fallback 대체 | Critical |
| `err-005_daily_ohlcv_amt_turn_rt_zero_accumulation.md` | 거래대금/회전율 0 누적 적재 에러 조치 | High |
| `err-006_kis_api_weekend_maintenance_stuck.md` | KIS 주말 점검에 따른 접속 실패 대기시간 누적으로 수집기 Stuck 장애 및 컨테이너 재시작 [NEW] | High |

---

## p3_usdms_wiki (p3_usdms 미국 시장 백엔드)

> **역할**: 미국 시장 티커/주가/재무/가치지표 데이터 수집 및 조회 API 백엔드
> **상태**: ✅ T-011 완료 (스케줄 변수명 일원화 및 주간 유지보수 외부화, API 개정에 따른 보존 처리 적용 완료)

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
| `decisions.md#USDMS_DEC-005` | 수/토요일 시분할 일정에 따른 미국 휴장일 전체 스킵 로직 제거 및 캘린더 싱크 보존 | — |
| `decisions.md#USDMS_DEC-006` | 2분할 MOD 2 해시 샤딩 기반 가치평가 연산 최적화 [NEW] | — |
| `decisions.md#USDMS_DEC-007` | USDMS 스케줄러 동적 리로드 및 진행률 로깅 개선 [NEW] | — |

### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `usdms-err-001_wsl2_bind_mount_sync_error.md` | WSL2 마운트 동기화 유실로 인한 빈 DB 기동 현상 | High |
| `usdms-err-002_valuation_rebuild_timeout.md` | Valuation 자가치유 갭 탐색 쿼리 실행 지연 및 타임아웃 | High |
| `usdms-err-003_logging_missing_and_running_status_loss.md` | 로깅 기본값 누락 및 백그라운드 실행 상태 유실 -> logging.basicConfig 및 _running_task 동적 상태 오버라이드 | High |
| `usdms-err-004_financial_tag_and_date_filtering_null_metrics.md` | 재무 팩트 수집 필터링 및 날짜 어긋남에 의한 지표(ROE/ROIC) 누락 오류 (해결 및 백필 완료) | High |
| `usdms-err-005_apscheduler_misfire_grace_time_skipped.md` | APScheduler misfire_grace_time 미지정으로 인한 스케줄러 트리거 누락 | High |
| `usdms-err-006_test_isolation_failure_blacklist_aapl.md` | 테스트 기동 시 실 DB 블랙리스트 오염으로 인한 AAPL 수집 중단 장애 | Critical |

---

## p4_manager_wiki (p4_manager 통합 관리 레이어)

> **역할**: 한국/미국 백엔드 통합 모니터링 UI 및 오케스트레이션
> **상태**: ✅ T-011 스케줄링 변수 중앙화 및 API 개정 연동 완료 (2026-06-12)

### 코어 문서

| 파일 | 내용 요약 | 마지막 업데이트 |
|---|---|---|
| `codebase_map.md` | 17개 파일의 물리구조, 새로 구성된 Vue SPA 프론트엔드 폴더 구조 및 테스트 현황 | T-009 |
| `environment.md` | tdms_p4_env Conda/Node.js 런타임 환경, 주요 패키지(fastapi, vue3, vitest, websockets) 버전, Nginx 프록시 해결책 및 TS5101/TS6133 빌드 오류 대안 기록 | T-009 |
| `decisions.md` | Nginx 동적 리졸브(P4DEC-001), 백그라운드 캐싱 폴링/장애 격리(P4DEC-002), 데이터 갭 정규화 및 API 동적 예외 격리(P4DEC-003), 서버 백업 물리 차단 안전장치(P4DEC-004) 적용, 볼륨 바인딩(P4DEC-005), 시장 격리 백업/복구(P4DEC-006), IP 자가탐색(P4DEC-007), 크론 요일 편집/재로드 대우(P4DEC-008) 결정 추가, 가치평가 날짜 기본값 및 검색 조건 옵션 개편(P4DEC-009) 추가 | T-009 |

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
| `backup_api.md` | routers/manager.py | `/api/mgr/env`, `/api/mgr/backup`, `/api/mgr/backup/list`, `/api/mgr/restore` 물리 백업/복구 및 환경 프로파일 API 명세 | T-009 |
| `physical_sync.md` | routers/manager.py / sync_service | `/api/mgr/sync`, `/api/mgr/sync/status`, `/api/mgr/sync/audit` 물리 동기화 및 감사 리포팅 API 명세 | T-010 |
| `network_api.md` | routers/manager.py / sync_service | `/api/mgr/network/detect-server`, `/api/mgr/network/sync-ip`, `/api/mgr/network/test-connection` IP 자가 탐색 및 네트워크 연결 검증 API 명세 | T-010 |


### errors/ (해결된 에러 기록)

| 파일 | 에러 요약 | Severity |
|---|---|---|
| `p4err-001_module_not_found_tdms_core.md` | 도커 백엔드 기동 시 `tdms_core` 임포트 불가 (PYTHONPATH 부재) -> Dockerfile 내 `ENV PYTHONPATH="/app"` 추가 주입 | High |
| `p4err-002_real_db_volume_tar_permission.md` | 대용량 Docker 볼륨(66GB) 백업 시 I/O 병목 및 권한 미획득 -> 테스트용 격리 디렉토리 주입 우회 구현 | High |
| `p4err-003_host_cli_backup_execution_trouble.md` | 로컬 CLI 기동 시 data_path 누락 및 싱글톤 인스턴스 미활용, 비동기(await) 혼선에 따른 3종 에러 -> DATA_PATH 명시 및 인스턴스 동기 호출 | Medium |
| `p4err-004_wsl2_agent_browser_forwarding.md` | WSL2 가상망 내 에이전트 브라우저 실행 차단 -> Windows Chrome 원격 디버깅 및 포트 프록시 터널링(socat) 연동 | High |
| `p4err-005_scheduler_api_404_not_found.md` | 통합 관리자 KDMS 스케줄러 조회 시 누락된 접두사(/tasks) 매핑 불일치로 인한 404 에러 | Medium |
| `p4err-006_websocket_upstream_failed.md` | 실시간 로그 스트리밍 웹소켓 프록시 연결 장애 (HTTP 404 및 403) | Medium |
| `p4err-007_httpx_timeout_and_caching_loss.md` | HTTPX 타임아웃 및 캐싱 덮어쓰기 장애 -> timeout 10.0초 상향 및 중복 캐싱 오버라이딩 방지 | High |
| `p4err-008_container_sync_sudo_ssh_missing.md` | 컨테이너 내부 물리 동기화 시 sudo 미존재 및 ssh/scp 바이너리, 개인키 공유 누락 에러 | High |
| `p4err-009_container_sync_path_command_mismatch.md` | 컨테이너-호스트 간 data_path 불일치로 인한 압축해제 오류 및 docker-compose 유실 제어 차단 에러 | High |
| `p4err-010_conda_missing_in_audit_report.md` | 정밀 감사 프로세스 기동 시 컨테이너 내 conda 부재 및 DB 패스워드 로드 실패 에러 | High |
| `p4err-011_env_detector_docker_default_dev.md` | 도커 컴포즈 기본값 설정(dev)으로 인해 서버 PC가 개발 PC 환경으로 오표시되는 에러 | Medium |

---

## 빠른 참조 — 현재 가장 중요한 항목

### ⚠️ 필독 에러

- [P1-ERR-001] Docker 볼륨 UID 불일치 → `p1_shared_wiki/errors/p1-err-001_volume_uid_mismatch.md`
- [P1-ERR-002] pg_restore 논리 복원 실패 → `p1_shared_wiki/errors/p1-err-002_logical_restore_failure.md`
- [P2-ERR-001] KIS API 403 Forbidden 차단 → `p2_kdms_wiki/errors/err-001_kis_api_403_forbidden.md`
- [P2-ERR-002] 시총 bigint 오버플로우 롤백 → `p2_kdms_wiki/errors/err-002_bigint_out_of_range_in_market_cap.md`
- [P2-ERR-003] KST 시간대 처리 불일치 → `p2_kdms_wiki/errors/err-003_task_kst_timezone_mismatch.md`
- [P2-ERR-006] KIS API 주말 점검으로 인한 수집 정체 stuck 장애 → `p2_kdms_wiki/errors/err-006_kis_api_weekend_maintenance_stuck.md` [NEW]
- [USDMS-ERR-001] WSL2 바인드 마운트 동기화 유실 → `p3_usdms_wiki/errors/usdms-err-001_wsl2_bind_mount_sync_error.md`
- [USDMS-ERR-002] Valuation 자가치유 갭 탐색 타임아웃 → `p3_usdms_wiki/errors/usdms-err-002_valuation_rebuild_timeout.md`
- [USDMS-ERR-003] 로깅 기본값 누락 및 실행 상태 유실 → `p3_usdms_wiki/errors/usdms-err-003_logging_missing_and_running_status_loss.md`
- [USDMS-ERR-004] 재무 팩트 수집 필터링 및 날짜 어긋남에 의한 지표(ROE/ROIC) 누락 오류 → `p3_usdms_wiki/errors/usdms-err-004_financial_tag_and_date_filtering_null_metrics.md`
- [USDMS-ERR-005] APScheduler misfire_grace_time 미지정으로 인한 스케줄러 트리거 누락 → `p3_usdms_wiki/errors/usdms-err-005_apscheduler_misfire_grace_time_skipped.md`
- [USDMS-ERR-006] 테스트 기동 시 실 DB 오염으로 인한 AAPL 수집 중단 장애 → `p3_usdms_wiki/errors/usdms-err-006_test_isolation_failure_blacklist_aapl.md` [NEW]
- [P4-ERR-002] 대용량 DB 볼륨 tar 백업 권한 장애 → `p4_manager_wiki/errors/p4err-002_real_db_volume_tar_permission.md`
- [P4-ERR-003] 로컬 CLI 백업 기동 장애 → `p4_manager_wiki/errors/p4err-003_host_cli_backup_execution_trouble.md`
- [P4-ERR-004] WSL2 에이전트 브라우저 실행 및 포워딩 장애 → `p4_manager_wiki/errors/p4err-004_wsl2_agent_browser_forwarding.md`
- [P4-ERR-005] 통합 관리자 KDMS 스케줄러 조회 404 장애 → `p4_manager_wiki/errors/p4err-005_scheduler_api_404_not_found.md`
- [P4-ERR-006] 실시간 로그 스트리밍 웹소켓 프록시 404/403 장애 → `p4_manager_wiki/errors/p4err-006_websocket_upstream_failed.md`
- [P4-ERR-007] HTTPX 타임아웃 및 캐싱 덮어쓰기 장애 → `p4_manager_wiki/errors/p4err-007_httpx_timeout_and_caching_loss.md`
- [P4-ERR-008] 컨테이너 기반 물리 동기화 sudo/ssh 부재 → `p4_manager_wiki/errors/p4err-008_container_sync_sudo_ssh_missing.md`
- [P4-ERR-009] 컨테이너 기반 물리 동기화 경로/docker-compose 부재 → `p4_manager_wiki/errors/p4err-009_container_sync_path_command_mismatch.md`
- [P4-ERR-010] 정밀 감사 리포트 Conda 누락/DB 비밀번호 오류 → `p4_manager_wiki/errors/p4err-010_conda_missing_in_audit_report.md`
- [P4-ERR-011] 도커 컴포즈 기본값 설정 서버 환경 오인식 → `p4_manager_wiki/errors/p4err-011_env_detector_docker_default_dev.md`

### 📐 최근 변경된 인터페이스

- `physical_sync`: `/api/mgr/sync` 및 `/api/mgr/sync/status`, `/api/mgr/sync/audit` 물리 동기화 백그라운드 파이프라인 및 감사 연동 명세 → `p4_manager_wiki/interfaces/physical_sync.md`
- `network_api`: `/api/mgr/network/detect-server` 등 IP 자가 탐색 및 .env 파일 갱신/연결 테스트 API 명세 → `p4_manager_wiki/interfaces/network_api.md`
- `backup_api`: `/api/mgr/env`, `/api/mgr/backup`, `/api/mgr/backup/list`, `/api/mgr/restore` 물리 백업/복구 및 서버 환경 차단 API 명세 → `p4_manager_wiki/interfaces/backup_api.md`

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
- `DailyRoutine`: target_date 파라미터화, 미국 휴장일 자동 스킵 제거(수/토 배치 안정화) 및 trading_calendar 테이블 자동 동기화 → `p3_usdms_wiki/interfaces/daily_routine.md`
- `date_utils`: 미국 주식시장 영업일/공휴일 판정 및 마지막 영업일 산출 공통 유틸리티 → `p1_shared_wiki/interfaces/date_utils.md`
- `Health/Admin API Endpoints`: Freshness/Gaps 판정, 차단 해제 API 신설, 동적 스케줄링 및 WebSocket 실시간 로그 중계 → `p3_usdms_wiki/interfaces/health_admin_api.md`
- `Auditors 3종`: 재무(항등식/Null), 지표(ROE/Outlier), 수정주가(KIS API 대조) 감사 엔진 → `p3_usdms_wiki/interfaces/auditors.md`
- `BlacklistManager`: 일시적/영구적 에러 분기 및 쿨다운 자동 해제 관리 → `p3_usdms_wiki/interfaces/blacklist_manager.md`
- `PhysicalSyncManager`: T-008에서 T-009 흡수, tar+SSH 파이프라인 확정 → `p1_shared_wiki/interfaces/physical_sync_manager.md`
- `Data API Endpoints`: REST API 7종 및 Arrow IPC 스트리밍 지원 완료 → `p3_usdms_wiki/interfaces/data_api_endpoints.md`
- `SyncManager`: **폐기 예정** — 실운영 사용 금지, PhysicalSyncManager 사용

### ✅ 완료된 작업

- p1_shared: ✅ 완료 (T-001~T-008, 미국 영업일 판별 추가 완료)
- p2_kdms: ✅ 완료 (KST 시간대 처리 및 KIS 특수 상품 필터링 반영 완료)
- p3_usdms: ✅ 완료 (T-008 완료)
- p4_manager: ✅ 완료 (T-010 완료)



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