# Wiki Log

> **규칙**: append-only. 항목을 삭제하거나 수정하지 않는다. **형식**: `## [{날짜}] {유형} | {내용}` **유형**: Task완료 / 의사결정 / 에러등록 / 환경변경 / Lint / 실험완료 / 배포

---

## 사용 지침

이 파일은 프로젝트 전체의 타임라인이다. `grep "^## \[" log.md | tail -10` 으로 최근 10개 항목 확인 가능. index.md의 "빠른 참조" 섹션은 이 log를 기반으로 갱신된다.

---

<!-- 아래부터 실제 로그 항목 추가. 최신 항목이 위에 오도록. -->
## [2026-07-15] Task완료+의사결정 | KDMS 백필 수집 시 캘린더 개장일 기반으로 gap_days를 계산하여 max_requests 호출 횟수를 동적 확보하는 루프 조기 탈출 버그 수정 및 일봉/분봉 총거래량 오차율 5% 비교 하이브리드 누락 검출 필터링을 적용했습니다. 아울러 매니저 대시보드의 주간 백필 카드에서 테스트 토글을 제거하고 분봉/일봉/시총 개별 수동 기동 가로 버튼 배치 및 가장 최근 실행된 태스크 단 1개만 요약 출력하는 콤팩트 상태 바인딩 개선을 완료했습니다.

## [2026-07-14] Task완료+의사결정 | 개발 PC와 서버 PC 간 1:1 Dual Run 데이터 수집 정합성(개수, 누락, 수치 오차 등)을 교차 검증하는 `verify_dual_run.py` 실행 방법과 세부 내용을 `p1_shared_wiki/operations/runbook.md` 에 기록하여 차후 세션에서도 바로 비교 검증 작업을 수행 가능하도록 지식화 완료했습니다.

## [2026-07-14] Task완료+의사결정 | USDMS 수집 차단 사유 구분을 배제하고, 단순 누적 재차단 횟수(re_blocked_count) 기반으로 유예 기간(1일->7일->30일->60일)을 점진적으로 상향하고 5회차 차단 시 자동 해제를 영구 배제하는 쿨다운 시스템을 구현 완료했습니다. 관련하여 로컬 DB DDL 마이그레이션 적용 및 SQL 단일 쿼리 튜닝을 마쳤으며, pytest 실 DB 통합 테스트를 통해 시나리오 검증을 무사히 통과했습니다.

## [2026-07-12] Task완료+의사결정 | 개발 PC 및 WSL 가상환경이 절전(sleep) 상태에 들어갔다 복귀할 때 스케줄러 기동이 지연되어 작업이 누락되는 현상(misfired)을 방지하고자, KDMS 및 USDMS의 `misfire_grace_time` 설정을 기존 15분(900초)에서 **1시간(3,600초)**으로 조정하는 동시에, 여러 스케줄이 밀렸을 때 중복 동시 실행으로 인한 DB 락 경합 및 데이터 정합성 훼손을 차단하기 위해 **`coalesce=True`** 및 **`max_instances=1`**의 엄격한 동시성 보호 정책을 스케줄러에 추가 적용했습니다.

## [2026-07-10] Task완료+의사결정 | KDMS 모니터링 보드에 과거 작업 로그가 표시되지 않는 구조적 문제를 해결하기 위해, 로컬 파일 로깅(`logs/daily_update.log`) 및 웹소켓 최초 연결 시의 100라인 선제 스트리밍 백필 로직을 추가했습니다. 또한, USDMS 테스트 구동(pytest) 시 Mock 오류가 프로덕션 로그 파일(`logs/daily_routine.log`)에 누적 기입되는 현상을 방지하도록 pytest 구동 환경 여부에 따른 로그 파일 경로 격리 장치(`daily_routine_test.log` / `daily_update_test.log` 분기)를 구현 완료하여 로그 데이터 격리 무결성을 완성했습니다. 추가적으로 USDMS 웹소켓 라우터에서 최신 로그 파일 스캔 시 `_test.log` 형식의 임시 테스트 로그를 잘못 긁어가던 탐색 스캔 버그를 수정하여 완전히 제외시켰고, 기존에 오염되어 누적되었던 프로덕션 로그 파일의 내용을 청소하여 조치를 마무리했습니다.

## [2026-07-10] Task완료+의사결정+에러등록 | 일별 가치평가 지표 조회 시 6개월 날짜 필터를 기본값으로 주입하여 풀스캔 스펙 부하를 방지하는 성능 최적화를 적용했습니다. 또한, 종목 코드 검색기(코드 헬퍼)의 화면 레이아웃을 좌우 7:3 비율로 분할하여 사용성을 크게 개편하고, 부분 일치/정확히 일치(match_type) 및 검색 범위(search_field) 옵션을 백엔드와 연동하여 짧은 티커(T, F 등)도 정밀 탐색이 가능하도록 구현 완료했습니다. 특히 검색기 수직 공간을 극대화하여 절약하기 위해 옵션 라벨을 컴팩트하게 단축('부분', '정확', '전체', '코드', '명칭')한 뒤 가로 2:3 비율로 좌우 정렬하였으며, 검색 실행 버튼을 검색어 입력 행 내부로 인라인 이동 배치하여 레이아웃을 고도로 효율화했습니다. 미국 종목 회사명 공란 버그도 latest_name 매핑으로 해결했습니다. 아울러 pytest 구동 시 실제 DB의 블랙리스트 테이블이 오염되어 AAPL 수집이 영구 중단되었던 심각한 격리 실패 현상(USDMS-ERR-006)을 DailyRoutine 의존성 주입 리팩토링 및 DbConnectionPool 내 테스트 환경 감지 실 DB 차단 세이프가드 구축을 통해 근본적으로 해결하고 AAPL 누락 데이터를 완벽히 백필 복구했습니다.

## [2026-07-09] Task완료+의사결정 | KDMS 일일 시세/재무 수집 루프 및 USDMS CIK 밸류에이션 계산 루프에 tqdm 스타일 진행상황 실시간 모니터링 로그(진행률%, 속도, 경과시간, ETA)를 구현했습니다. 또한, USDMS 가치평가 재연산 시 CIK MOD 2 결정론적 샤딩을 적용하여 주 2회 수요일/토요일 스케줄에 맞춰 수집 분량의 50%를 분할 계산하도록 최적화하였으며(USDMS_DEC-006), 대용량 데이터 적재 시 Bus error 방지를 위한 docker 공유 메모리 확장(512MB)을 완수했습니다. 나아가 크론 일정 조율 시 요일(`day_of_week`) 변경 기능을 스케줄 모달 UI에 추가하고, `.env` 스케줄 설정을 웹 콘솔에서 도커 재빌드/재시작 없이 메모리에 무중단 핫플러깅하는 `.env` 재로드 API 및 대시보드 연동을 완수했습니다.

## [2026-07-07] Task완료+의사결정 | KDMS 재무 업데이트 대상 종목 선정을 결정론적 해시(MD5 MOD 5) 기반 요일별 5분할 순환 방식으로 전면 고도화 적용하여 실패 종목의 타겟 독점(Stuck) 현상을 근본적으로 차단하고, 수동 기동 시에는 전체 활성 종목을 일괄 수집할 수 있도록 -1 옵션을 구현(dec-007 보강) 및 관련 전체 pytest 101개 통과 완료했습니다.

## [2026-07-07] Task완료+의사결정+에러등록 | KDMS 재무 업데이트 성능 개선을 위해 일일 600개 쿼터 샤딩 및 N+1 쿼리 방지를 위한 인메모리 벌크 캐싱 기법(dec-007)을 적용하고, KIS API 주말 점검으로 인한 수집 Stuck 시 컨테이너 강제 재시작 조치 내역(err-006)을 추가했습니다. 아울러 USDMS에서 수/토 시분할 배치 안정화를 위해 미국 휴장일 기준 전체 수집 조기 스킵 로직을 전면 제거(USDMS_DEC-005)하고 관련 daily_routine 인터페이스 및 테스트 코드를 개편 적용 완료했습니다.

## [2026-07-03] Task완료+에러등록 | 미국 USDMS 스케줄 크론 작업 중 찰나의 지터(1.32초)로 인해 스케줄 작동이 누락되는 현상(usdms-err-005)의 원인을 APScheduler misfire_grace_time 미지정으로 규명하고, 10시간 유예 설정을 적용 및 원격 서버 PC 배포 완료.

## [2026-07-03] Task완료+에러등록+환경변경 | 도커 컨테이너 환경 내 데이터 물리 동기화 및 정밀 감사 기동 시 발생하는 sudo/ssh 유틸리티 부재, 볼륨 경로 차이, docker-compose 누락(P4ERR-008, P4ERR-009) 및 정밀 감사 시 conda 부재(P4ERR-010) 오류 분석 및 조치 완료. 아울러 도커 컴포즈 기본값 설정 오류로 서버 PC 환경이 개발 PC 환경으로 오표시되는 문제(P4ERR-011) 해결을 위해 서버 PC의 로컬 .env 및 컴포즈 설정을 전면 교정 완료.

## [2026-06-24] 환경변경+의사결정 | 도커 가상 스위치 DNS 오류 방지를 위한 정적 서브넷(172.20.0.0/16) 및 컨테이너 고정 IP 할당(kdms_db: 172.20.0.3, usdms_db: 172.20.0.4 등) 적용 완료. OCI 런타임 마운트 지연 해소를 위한 restart 정책 상향 및 env_detector.py 내 DNS gaierror 시 고정 IP 자동 폴백 연동으로 기동 안정성 극대화.

## [2026-06-18] Task완료+에러등록 | 미국 USDMS 2026년 이후 재무 팩트 자본총계 대량 누락 및 지표(ROE/ROIC) 계산 불가 오류(usdms-err-004) 원인 규명 및 패치 완료. financial_repo.py 벌크 적재 쿼리 컬럼 추가 및 financial_parser.py 30일 완화 규칙 적용. 3,640개 CIK 대상 2026년 고속 백필 E2E 재처리(100% 성공) 완수로 ROE 누락율 50.37% -> 1.20% 정상화 성공.

## [2026-06-18] Task완료+의사결정+에러등록 | KIS 마스터 제공 오류로 상장주식수 0 유입 시 DB 최근 10영업일의 정상 주식수로 대체하는 Fallback 방어 로직(dec-006, err-004) 반영 완료. 아울러 2020~2025년 과거 캘린더 영업일 1,583일 및 시가총액 데이터 428만 건 백필 적재 완수로 데이터 안정성 확보, p2_kdms의 누락되었던 운영 스크립트 8종 및 테스트 파일 6종 반영으로 codebase_map.md 현행화 및 MoC(index.md) 갱신 완료.

## [2026-06-16] 에러등록 | 한국 KDMS 재무 업데이트 및 분봉 백필 태스크 기동 시 naive datetime 사용으로 인한 KST 시간대 처리 불일치 장애 해결 가이드(err-003_task_kst_timezone_mismatch.md) 등록 및 MoC(index.md) 현행화 완료.

## [2026-06-16] 에러등록 | 미국 USDMS 주식 백엔드 기동 시 logging.basicConfig 설정 누락에 따른 로깅 누락 및 백그라운드 실행 상태 유실 장애 해결 가이드(usdms-err-003_logging_missing_and_running_status_loss.md) 등록 및 MoC(index.md) 현행화 완료.

## [2026-06-16] 에러등록 | 통합 관리자 P4 Manager 내 httpx 타임아웃 협소화로 인한 미국 시장 오프라인 오인 및 상태 캐싱 중복 덮어쓰기 장애 해결 가이드(p4err-007_httpx_timeout_and_caching_loss.md) 등록 및 MoC(index.md) 현행화 완료.

## [2026-06-12] 의사결정 | KIS 마스터 데이터 파싱 시 수익증권(BC), 뮤추얼펀드(MF), ELW(EW) 등의 비주식성 특수 상품을 수집 대상에서 선제 필터링하여 데이터 청정도를 높이는 의사결정(dec-005_filter_non_equity_instruments.md)을 등록하고 MoC(index.md) 현행화 완료.

## [2026-06-12] 에러등록 | 통합 관리자 대시보드 하단 실시간 로그 스트리밍 영역에서 의존성(websockets) 누락 및 라우팅 prefix 불일치로 발생했던 404/403 연결 장애 분석 및 해결 가이드(p4err-006_websocket_upstream_failed.md) 등록 및 MoC(index.md) 현행화 완료.

## [2026-06-12] Task완료 | T-011 스케줄링 변수 중앙화 및 API 개정 작업 완료에 따라 p1_shared 내 schedule_utils.md 신규 인터페이스 지식화, p2_kdms 및 p3_usdms, p4_manager의 관련 환경 정보(environment.md) 및 MoC(index.md) 현행화 완료.

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