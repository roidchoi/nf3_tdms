# Wiki Log

> **규칙**: append-only. 항목을 삭제하거나 수정하지 않는다. **형식**: `## [{날짜}] {유형} | {내용}` **유형**: Task완료 / 의사결정 / 에러등록 / 환경변경 / Lint / 실험완료 / 배포

---

## 사용 지침

이 파일은 프로젝트 전체의 타임라인이다. `grep "^## \[" log.md | tail -10` 으로 최근 10개 항목 확인 가능. index.md의 "빠른 참조" 섹션은 이 log를 기반으로 갱신된다.

---

<!-- 아래부터 실제 로그 항목 추가. 최신 항목이 위에 오도록. -->

## [2026-06-12] 에러등록 | 통합 관리자 대시보드 내 대한민국(KDMS) 스케줄 탭 조회 시 누락된 접두사(/tasks) 매핑 불일치로 발생했던 404 Not Found 에러 극복 가이드(p4err-005_scheduler_api_404_not_found.md) 등록 및 codebase_map.md, environment.md, MoC(index.md) 일제 갱신 완료.

## [2026-06-12] 에러등록 | WSL2 가상망 내에서 AI 에이전트 브라우저 실행 차단 장애를 극복하기 위해 Windows Chrome 원격 디버깅(--remote-debugging-port=9222) 포트 프록시 매핑(netsh) 및 WSL2 socat 백그라운드 터널 중계 연동 가이드(p4err-004_wsl2_agent_browser_forwarding.md) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-11] Task완료+의사결정 | p4_manager 통합 관리 레이어 T-010(물리 동기화 및 감사 리포팅 연동) 완료에 따른 codebase_map.md, environment.md, decisions.md(P4DEC-007 Windows PowerShell 우회 DNS 쿼리 및 Async C클래스 포트 스캔을 통한 서버 IP 자가 갱신), interfaces/physical_sync.md(물리 동기화 API), interfaces/network_api.md(네트워크 자가 감지 및 연결 검증 API) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-11] 환경변경 | 서버 PC 리소스 부족 해소를 위한 미사용 Docker 볼륨(68.79GB) 및 과거 백업본(15.4GB) 정리 완료, 윈도우 호스트 C드라이브 용량 환수(WSL2 vhdx Shrink) 및 SSH/sudoers 무인화 가이드 수립에 따른 environment.md 갱신 완료.

## [2026-06-11] Task완료+의사결정 | p4_manager 통합 관리 레이어 T-009 고도화(시장 격리형 물리 백업 및 개별 복구 오케스트레이션) 완료에 따른 decisions.md(P4DEC-006 시장 격리 및 동적 권한 보정 래퍼 추가), interfaces/backup_api.md(시장 격리 API 스펙 갱신) 지식화 완료.

## [2026-06-10] Task완료+의사결정 | p4_manager 통합 관리 레이어 T-009(안전 복구 및 무결성 진단 연동) 완료에 따른 codebase_map.md, environment.md, decisions.md(P4DEC-005 볼륨 바인딩 및 docker.sock 연동 의사결정 추가), interfaces/backup_api.md(물리 복구 API 명세 추가) 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-10] Task완료 | p4_manager 통합 관리 레이어 T-008(DB 백업 실행 및 이력 관리) 완료에 따른 codebase_map.md, environment.md, decisions.md(P4DEC-004 서버 백업 차단 아키텍처 의사결정), interfaces/backup_api.md(환경 프로파일 및 백업 API 명세) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-10] Task완료 | p4_manager 통합 관리 레이어 T-007(데이터 익스플로러 테이블 동적 미리보기) 완료에 따른 codebase_map.md, environment.md, interfaces/api_routing_map.md(동적 미리보기/메타 API 추가), interfaces/get_preview_meta.md(테이블 목록 메타 API 명세), interfaces/get_preview_table.md(테이블 미리보기 및 예외격리 API 명세) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-09] Task완료+의사결정 | p4_manager 통합 관리 레이어 T-006(공통 헬스 모니터링 및 시장별 특화 패널) 완료에 따른 codebase_map.md, decisions.md(P4DEC-003 정규화 및 API 동적 예외 격리), interfaces/get_health_freshness.md(신선도 중계), interfaces/get_health_gaps.md(누락 갭 정규화 중계), interfaces/post_blacklist_release.md(미국 차단 해제 중계), interfaces/kr_milestones.md(한국 마일스톤 중계) 신규 지식화 및 MoC(index.md) 현행화 완료. 아울러 p3_usdms 내 차단 해제 API 신설에 따라 health_admin_api.md 인터페이스 내용 갱신 완료.

## [2026-06-09] Task완료 | p4_manager 통합 관리 레이어 T-004(WebSocket 로그 스트리밍 이중화 프록시) 완료에 따른 codebase_map.md, environment.md(websockets 패키지 버전 추가), interfaces/api_routing_map.md(WebSocket 프록시 엔드포인트 추가), interfaces/ws_proxy_logs.md(WebSocket 중계 프록시 API 상세 명세) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-09] Task완료 | p4_manager 통합 관리 레이어 T-003(통합 대시보드 UI 및 태스크 수동 제어) 완료에 따른 codebase_map.md, environment.md(Node/Vite/Vue3/Vitest 환경 추가, TS5101/TS6133 환경 해결법 수록), interfaces/api_routing_map.md(POST /api/mgr/run 추가), interfaces/post_run_task.md(수동 태스크 기동 API 명세) 신규 지식화 및 MoC(index.md) 현행화 완료.


## [2026-06-09] Task완료+의사결정+에러등록 | p4_manager 통합 관리 레이어 T-002(백엔드 통합 상태 집계 서비스 개발) 완료에 따른 codebase_map.md, environment.md, decisions.md(P4DEC-002 백그라운드 캐싱 폴링 기법 및 실시간 API 장애 격리 레이어 적용), interfaces/get_integrated_status.md(통합 상태 집계 API 명세) 신규 지식화 및 errors/p4err-001_module_not_found_tdms_core.md(Docker 임포트 경로 환경 변수 해결) 추가 등록. MoC(index.md) 현행화 완료.


## [2026-06-09] Task완료+의사결정 | p4_manager 통합 관리 레이어 T-001(개발 환경 및 Nginx 프록시 인프라 구축) 완료에 따른 codebase_map.md, environment.md, decisions.md(P4DEC-001 Nginx 동적 리졸브 및 변수 기반 프록시 패스 적용), interfaces/api_routing_map.md(헬스체크 및 5종 라우팅 프록시/WS 중계 맵) 신규 지식화 및 MoC(index.md) 현행화 완료.

## [2026-06-08] Task완료 | usdms_db TimescaleDB 11개 테이블의 컬럼, 고유키, 인덱스 및 관계 명세를 상세 수록한 schema_usdms_db.md 신규 지식화 완료. 테스트/임시 테이블 잔해 자동 탐색 및 정리 스크립트 cleanup_database.py 구축 완료. MoC(index.md) 현행화 완료.

## [2026-06-05] Task완료 | p3_usdms 미국 시장 백엔드 T-008 완료에 따른 의존성/임계치/스케줄 설정 외부화 정보 environment.md 갱신, daily_routine.md 및 master_sync.md, master_repo.md 인터페이스 갱신 완료. 아울러 p1_shared 내 미국 주식시장 영업일 판별 기능 date_utils.md 신규 인터페이스 등록 및 codebase_map, MoC(index.md) 현행화 완료.

## [2026-06-04] Task완료+의사결정 | p3_usdms 미국 시장 백엔드 T-007(헬스체크 및 어드민 API, Auditors 3종 마이그레이션, 실시간 WebSocket 로그 전송) 완료에 따른 신규 인터페이스 문서(health_admin_api.md, auditors.md) 등록 및 기존 레포지토리 인터페이스(price_repo.md, blacklist_repo.md), codebase_map, decisions(USDMS_DEC-004) 및 MoC(index.md) 현행화 완료.

## [2026-06-04] Task완료 | p3_usdms 미국 시장 백엔드 T-006(데이터 조회 REST API 완성) 완료에 따른 REST API 7종 엔드포인트 명세(data_api_endpoints.md) 신규 등록, pyarrow 패키지 추가에 따른 환경 문서(environment.md) 및 MoC(index.md) 현행화 완료.


## [2026-06-04] Task완료+의사결정+에러등록 | p3_usdms 미국 시장 백엔드 T-005(Blacklist + MasterEnricher + 일일 자동화) 완료에 따른 핵심 인터페이스(blacklist_repo, blacklist_manager, master_enricher, daily_routine) 추가, 60일 룩백 자가 치유 및 쿼리 병목 최적화(USDMS_DEC-002, USDMS-ERR-002), 이원화 에러 분기 및 자동 릴리즈(USDMS_DEC-003) 위키 지식화 완료.

## [2026-06-02] Task완료 | p3_usdms 미국 시장 백엔드 T-004(가치평가 및 재무비율 대량 실 계산) 완료에 따른 핵심 인터페이스(valuation_repo, valuation_engine) 추가 및 550종목 DB 캐싱 최적화(Bulk Cache Caching) 위키 지식화 완료.

## [2026-06-02] Task완료 | p3_usdms 미국 시장 백엔드 T-003(SEC XBRL 재무 파싱 + 주식수 이력) 완료에 따른 핵심 인터페이스(financial_parser, financial_repo, xbrl_mapper) 및 의사결정(USDMS_DEC-001) 위키 지식화 완료.

## [2026-06-01] Task완료 | p3_usdms 미국 시장 백엔드 T-002-A 완료에 따른 핵심 인터페이스(sec_client, master_sync, master_repo) 문서화 완료 및 SECClient get_company_facts 누락 기능 복구 및 검증 완료.

## [2026-05-29] 에러등록 | WSL2 도커 데스크탑 바인드 마운트 동기화 유실로 인한 빈 DB 기동 및 IP 변경 에러(USDMS-ERR-001) 등록 완료.

## [2026-05-28] 환경변경+의사결정 | Kiwoom REST API의 초당 5회 한도 초과 차단 방지를 위한 0.25초 스로틀링 딜레이(P2DEC-004) 도입 완료. 관련 pytest 6종 통과 검증 완료.

## [2026-05-28] 의사결정+에러등록+Task완료 | KIS API Rate Limit 차단 회피를 위한 안전 마진 스로틀링 지연 도입(P2DEC-004, p2ERR-001) 및 시가총액 bigint 정수 오버플로우 방어막 패치(p2ERR-002) 적용 완료. 전 종목 E2E 청정 데이터 수집 백필 완수.

## [2026-05-27] 의사결정+Task완료 | 한국거래소(KRX) 2024년 알파벳 혼용 종목코드 전면 지원을 위한 수집기 필터 완화 결정(P2DEC-003) 등록 및 관련 DB 스키마 주석(schema_kdms_db.md) 보강 완료.

## [2026-05-26] Task완료 | kdms_timescaledb 내 12개 테이블 컬럼/PK/인덱스 상세 스키마(schema_kdms_db.md) 및 배치 태스크 실행/수동 트리거 운영 런북(runbook.md) 지식화 완료. MoC(index.md) 갱신.

## [2026-05-26] Task완료+지식화 | p2_kdms_wiki 전체 구축 — Graphify(425 nodes, 841 edges, 19 communities) 기반. codebase_map 전면 작성, interfaces 5개(ohlcv_repo, financial_repo, data_api_endpoints, fastapi_lifespan, settings_config), decisions 2개(PIT 재무 패턴, 수정주가 이중 전략), environment 전면 갱신. MoC(index.md) p2_kdms 섹션 현행화.

## [2026-05-14] Task완료+초기화 | p1_shared_wiki 전체 구축 — T-001~T-008 완료 기반. interfaces 5개, decisions 2개, errors 2개, runbook, codebase_map, environment 신규 생성. MoC를 Graphify God Node 기준으로 재구성.

## [{YYYY-MM-DD}] 초기화 | pjt_wiki 초기 구조 생성