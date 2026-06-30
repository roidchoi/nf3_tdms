# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p4_manager (통합 관리 레이어)  
> **마지막 업데이트**: 2026-06-30 (물리 DB 동기화 UI 및 스토어 연동 반영 완료)  
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

tdms_core/p4_manager/
├── frontend/               # Vite + Vue3 + TS SPA 프론트엔드 [✅완성]
│   ├── src/
│   │   ├── api/
│   │   │   └── http.ts     # Axios API 인스턴스 [✅완성]
│   │   ├── components/dashboard/
│   │   │   ├── TaskStatusCard.vue   # 수동 태스크 제어 및 안전 경고 카드 [✅완성]
│   │   │   ├── LogTerminal.vue      # 실시간 로그 스트리밍 다크 터미널 [✅완성]
│   │   │   ├── ScheduleModal.vue    # 드롭다운 시간변경 및 이중 타임존/안전장치 모달 [✅완성]
│   │   │   ├── BlacklistPanel.vue   # 미국 CIK 수집 차단 리스트 및 차단 해제 모달 패널 [✅완성]
│   │   │   └── MilestoneTimeline.vue # 한국 수집/정제 마일스톤 이력 타임라인 패널 [✅완성]
│   │   ├── stores/
│   │   │   ├── statusStore.ts  # Pinia 상태관리 스토어 [✅완성]
│   │   │   ├── logStore.ts     # 실시간 로그 웹소켓 및 링버퍼(500줄) 관리 스토어 [✅완성]
│   │   │   ├── scheduleStore.ts # 한국/미국 스케줄러 관리 및 API 제어 스토어 [✅완성]
│   │   │   ├── healthStore.ts  # 신선도/갭/마일스톤/블랙리스트 통합 헬스 스토어 [✅완성]
│   │   │   ├── explorerStore.ts # 동적 테이블 미리보기 조회 관리 스토어 [✅완성]
│   │   │   ├── backupStore.ts   # 로컬 물리 백업 이력 및 실행 상태 관리 스토어 [✅완성]
│   │   │   └── syncStore.ts     # DB 물리 동기화 및 네트워크 제어 관리 스토어 [✅완성]
│   │   ├── views/
│   │   │   ├── DashboardView.vue   # 통합 모니터링 메인 뷰 (탭 컨트롤 및 접속 환경 배지 포함) [✅완성]
│   │   │   ├── ScheduleView.vue    # 한국/미국 스케줄러 관리 탭 뷰 [✅완성]
│   │   │   ├── HealthView.vue      # 데이터 헬스 모니터링 통합 탭 뷰 (신선도/갭/특화패널) [✅완성]
│   │   │   ├── ExplorerView.vue    # 데이터 익스플로러 동적 미리보기 탭 뷰 [✅완성]
│   │   │   ├── BackupView.vue      # 로컬 DB 백업 실행 및 이력 조회 탭 뷰 (서버 제한 포함) [✅완성]
│   │   │   └── SyncView.vue        # DB 물리 동기화 및 네트워크 탐색 제어 탭 뷰 [✅완성]
│   │   ├── tests/
│   │   │   ├── TaskStatusCard.spec.ts   # 컴포넌트 렌더링 및 이중 컨펌 동작 테스트 [✅완성]
│   │   │   ├── DashboardView.spec.ts    # 대시보드 뷰 스토어 연동 테스트 [✅완성]
│   │   │   ├── logStore.spec.ts         # 500줄 버퍼 제한 테스트 [✅완성]
│   │   │   ├── ScheduleModal.spec.ts    # EST 시차 환산 및 장중 변경 안전 확인 테스트 [✅완성]
│   │   │   ├── scheduleStore.spec.ts    # 스케줄 API 동작 스토어 테스트 [✅완성]
│   │   │   ├── healthStore.spec.ts      # health 스토어 fetch 및 차단해제 API 연동 테스트 [✅완성]
│   │   │   ├── explorerStore.spec.ts    # explorer 스토어 fetch 및 상태 보관 테스트 [✅완성]
│   │   │   ├── ExplorerView.spec.ts     # ExplorerView 렌더링, 스켈레톤 및 오프라인 배너 테스트 [✅완성]
│   │   │   ├── BackupView.spec.ts       # BackupView 서버 환경 비활성화 및 개발자 UI 렌더링 검증 테스트 [✅완성]
│   │   │   └── SyncView.spec.ts         # SyncView 피어/네트워크 스캔 및 이중 컨펌 작동 검증 테스트 [✅완성]
│   │   ├── App.vue         # 메인 프레임 [✅완성]
│   │   ├── shims-vue.d.ts  # TypeScript Vue shim [✅완성]
│   │   ├── main.ts         # Pinia 바인딩 및 앱 런타임 엔트리포인트 [✅완성]
│   │   └── style.css       # HSL 다크 테마 및 Glassmorphic 디자인 토큰 [✅완성]
│   ├── tsconfig.app.json   # TypeScript 6.0 설정 [✅완성]
│   └── vite.config.ts      # Vitest 설정 [✅완성]
├── nginx/
│   └── nginx.conf          # Nginx 리버스 프록시 및 WS 중계 설정 [✅완성]
├── services/
│   ├── status_service.py   # 비동기 상태 수집, 캐싱 및 수동 기동 중계 서비스 [✅완성]
│   ├── backup_service.py   # DB 물리 볼륨 압축 아카이빙 및 이력 조회 서비스 [✅완성]
│   └── sync_service.py     # DB 물리 동기화 및 네트워크 IP 자가 탐색 서비스 [✅완성]
├── routers/
│   ├── manager.py          # GET/PUT/POST 통합 관리 API 라우터 (헬스/스케줄 중계 및 물리 백업 추가) [✅완성]
│   └── proxy_ws.py         # /ws/logs/{market} 웹소켓 중계 프록시 라우터 [✅완성]
├── tests/
│   ├── conftest.py         # pytest 커스텀 런타임 옵션 정의 [✅완성]
│   ├── test_infra.py       # 인프라 3단계 TDD 검증 코드 [✅완성]
│   ├── test_status.py      # 비동기 상태 수집 검증 코드 [✅완성]
│   ├── test_proxy_ws.py    # 웹소켓 중계 검증 코드 [✅완성]
│   ├── test_scheduler_bridge.py # 스케줄러 중계 검증 코드 [✅완성]
│   ├── test_health_bridge.py # 헬스 중계 API 6종 및 장애 격리 검증 코드 [✅완성]
│   ├── test_explorer_bridge.py # 데이터 익스플로러 테이블 미리보기 중계 검증 코드 [✅완성]
│   ├── test_backup.py      # 백업 및 장비 환경감지 API 검증 코드 [✅완성]
│   └── test_sync_service.py # 물리 동기화 및 자가 탐색 API 6종 검증 코드 [✅완성]
├── backend.Dockerfile      # FastAPI 백엔드 이미지 빌드 명세 [✅완성]
├── frontend.Dockerfile     # Vue 컴파일 및 Nginx 프로덕션 Multi-stage 빌드 명세 [✅완성]
├── docker-compose.yml      # 멀티 컨테이너 환경 및 tdms-net 정의 [✅완성]
├── config.py               # Pydantic Settings 환경설정 로더 [✅완성]
├── main.py                 # FastAPI 백엔드 엔트리포인트 [✅완성]
├── pyproject.toml          # pytest 환경 [✅완성]
└── requirements.txt        # 의존 패키지 정의 [✅완성]

---

## 2. 핵심 데이터 흐름

```
[클라이언트 브라우저 (포트 80)]
       │ (HTTP Request / WS 연결)
       ▼
[p4_frontend (Nginx 리버스 프록시)]
       ├── /api/kr/*  ──> [p2_kdms (포트 8000)] (한국 시세 데이터 API)
       ├── /api/us/*  ──> [p3_usdms (포트 8005)] (미국 시세 데이터 API)
       ├── /api/mgr/* ──> [p4_backend (포트 8010)] (통합 관리 API)
       ├── /ws/logs/* ──> [p4_backend (포트 8010)] ──> [p2 / p3 웹소켓] (실시간 로그 중계)
       └── / (Index.html) ──> 정적 페이지 서빙 (Vue SPA 대시보드)
```

---

## 3. 모듈별 상태 및 역할

| frontend | ✅완성 | `DashboardView.vue`, `TaskStatusCard.vue`, `LogTerminal.vue` | 다크 테마 대시보드 화면 및 태스크 즉시 실행 조작 UI, 실시간 로그 터미널 제공 |
| nginx | ✅완성 | `nginx.conf` | 포트 80 수신 및 각 백엔드(p2, p3, p4) 프록시 및 WebSocket 중계 위임 |
| routers | ✅완성 | `manager.py`, `proxy_ws.py` | 통합 관리자 전용 API 라우터 및 실시간 웹소켓 중계 프록시 엔드포인트 제공 |
| services | ✅완성 | `status_service.py`, `backup_service.py`, `sync_service.py` | p2/p3 백엔드 상태/태스크 캐싱, 로컬 DB 백업/복구 제어 및 DB 물리 동기화/IP 네트워크 자가 탐색 제공 |
| tests | ✅완성 | `test_infra.py`, `test_status.py`, `test_proxy_ws.py`, `test_sync_service.py` | 헬스체크 및 프록시 검증, 비동기 상태 수집 및 에러 격리, 웹소켓 중계 및 동기화/네트워크 자가 탐색 기능 검증 |
| 루트 패키지 | ✅완성 | `main.py`, `config.py` | p4 통합 관리 백엔드 설정 로드 및 lifespan 이벤트 루프 처리 |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트 / 서비스 | 실행 방법 | 역할 |
|---|---|---|
| `p4_frontend` (Nginx) | `docker-compose up --build -d p4_frontend` | Multi-stage Vue 빌드 후 80 포트 리프록시 및 정적 SPA 서빙 기동 |
| `p4_backend` (FastAPI) | `docker-compose up --build -d p4_backend` | 통합 관리 레이어 API 서버 구동 (PYTHONPATH=/app) |
| `test_infra` (pytest) | `conda run -n tdms_p4_env env PYTHONPATH=/home/roid2/pjt/nf3/01_nf3_tdms pytest tests/ -v --run-integration` | 인프라 및 전체 기능 통합 검증 실행 |
| `frontend_tests` (vitest) | `npm run test` (Cwd: `frontend`) | 프론트엔드 컴포넌트 동작 및 안전 통제 검증 실행 |

---

## 5. 테스트 현황

| tests/test_infra.py | FastAPI 헬스 체크 엔드포인트 (`main.py`) | ✅통과 |
| tests/test_infra.py | `nginx.conf` 프록시 규칙 검증 | ✅통과 |
| tests/test_infra.py | Docker Compose & Nginx 통합 라우팅 | ✅통과 |
| tests/test_status.py | 비동기 상태 수집 및 캐싱 정규화 (`status_service.py`) | ✅통과 |
| tests/test_status.py | 백엔드 장애 격리 (Fault Isolation) | ✅통과 |
| tests/test_status.py | 태스크 즉시 실행 API (`POST /run`) 및 예외 처리 검증 | ✅통과 |
| tests/test_proxy_ws.py | WebSocket 이중 프록시 중계 및 커넥션 탈출 시 자원 해제 보장 | ✅통과 |
| tests/test_scheduler_bridge.py | 크론 시간 변경, 토글 제어 중계 API 및 예외 격리 검증 | ✅통과 |
| tests/test_health_bridge.py | 헬스 중계 API 6종 및 예외 격리 검증 | ✅통과 |
| frontend/src/tests/TaskStatusCard.spec.ts | 수동 기동 UI 렌더링, 스위치 토글, 거래시간 안전장치 및 스토어 연동 | ✅통과 |
| frontend/src/tests/DashboardView.spec.ts | 통합 헬스 요약 정보 스토어 연동 렌더링 | ✅통과 |
| frontend/src/tests/logStore.spec.ts | Pinia 스토어 웹소켓 수신 및 링 버퍼 500줄 용량 제어 검증 | ✅통과 |
| frontend/src/tests/ScheduleModal.spec.ts | 미국 EST 시간대 환산 및 한국/미국 장중 변경 통제 "변경승인" 이중 안전장치 검증 | ✅통과 |
| frontend/src/tests/scheduleStore.spec.ts | Pinia scheduleStore 스케줄 fetch/toggle/reschedule API 연동 검증 | ✅통과 |
| frontend/src/tests/healthStore.spec.ts | Pinia healthStore 헬스 데이터 fetch 및 차단 해제 연동 검증 | ✅통과 |
| frontend/src/tests/explorerStore.spec.ts | Pinia explorerStore 메타/데이터 API 연동 및 오프라인 검증 | ✅통과 |
| frontend/src/tests/ExplorerView.spec.ts | ExplorerView UI 렌더링, 스켈레톤, 오프라인 에러 배너 검증 | ✅통과 |
| tests/test_explorer_bridge.py | 백엔드 미리보기 중계 API 2종 및 하위 백엔드 장애 격리 검증 | ✅통과 |
| tests/test_backup.py | 백엔드 장비 환경 식별 API 및 개발 환경 물리 DB 백업/조회 API 검증 | ✅통과 |
| tests/test_sync_service.py | 이중 확인 텍스트 불일치 및 서버 환경 push 쓰기 동작 차단 검증 | ✅통과 |
| tests/test_sync_service.py | 로컬/원격 무인화 sudoers NOPASSWD 비밀번호 요구 검증 | ✅통과 |
| tests/test_sync_service.py | powershell.exe 우회 DNS 서버 IP 탐색 및 소켓 연결 테스트 검증 | ✅통과 |
| tests/test_sync_service.py | asyncio C클래스 포트 스캔 및 서버 감지 실패 예외 처리 검증 | ✅통과 |
| tests/test_sync_service.py | 정규식 기반 .env 내 DEV_IP/SERVER_IP 갱신 및 메모리 변수 적용 검증 | ✅통과 |
| frontend/src/tests/BackupView.spec.ts | BackupView UI 렌더링, 접속 환경 인식 및 서버 통제 작동 검증 | ✅통과 |
| frontend/src/tests/SyncView.spec.ts | SyncView 피어/네트워크 설정, 자동 탐색, 연결 검증, 이중 컨펌 동작 검증 | ✅통과 |
| tests/test_sync_service.py | 백엔드 동기화 오케스트레이션 및 IP 탐색/검증 API 연동 검증 | ✅통과 |

---

## 6. 가비지 현황

> Lint 시 사용자 승인 후 삭제. 이 섹션이 비어있는 것이 정상.

| 파일/폴더 | 생성 Task | 삭제 사유 |
|---|---|---|
| — | — | — |

---

## 7. 변경 이력 요약

| Task | 주요 변경 내용 |
|---|---|
| Task-초기화 | 초기 구조 생성 |
| T-001 | Conda 가상환경, Docker Compose, Nginx 프록시 인프라 구축 및 TDD 검증 완료 |
| T-002 | 백엔드 통합 상태 집계 서비스 개발 및 예외 격리(Fault Isolation) 적용 완료 |
| T-003 | 통합 대시보드 UI 개발, 태스크 수동 실행 POST API 중계 연동 및 Multi-stage Docker 빌드 적용 완료 |
| T-004 | WebSocket 로그 스트리밍 이중 중계 프록시 API, Pinia logStore 500줄 링 버퍼 및 다크 터미널 UI 구현 완료 |
| T-005 | 백엔드 한국/미국 스케줄 API 교차 보완, P4 스케줄 중계 및 통합 API 3종, 프론트엔드 ScheduleView/Modal 안전 통제 장치 구현 완료 |
| T-006 | 백엔드 미국 CIK 차단 해제 API 신설, P4 헬스 중계 및 장애 격리 API 6종, 프론트엔드 HealthView 및 한국 마일스톤 타임라인, 미국 블랙리스트 제어 패널 구현 완료 |
| T-007 | 백엔드 미리보기 중계 및 장애 격리 API 2종, 프론트엔드 ExplorerView 및 스토어 구현 완료 |
| T-008 | DB 백업 실행 및 이력 관리 기능 구현, 서버 환경 차단 물리 안전장치 적용 완료 |
| T-010 | 물리 동기화 백라운드 파이프라인, 로컬/원격 sudo NOPASSWD 사전 점검, powershell.exe DNS 우회 쿼리, asyncio 사설 대역 비동기 스캔 및 .env 실시간 갱신 구현 완료 |
| T-011 | 스케줄링 변수 중앙화에 따른 KDMS/USDMS 스케줄 중계 및 API 개정 대응, proxy_ws 웹소켓 로그 스트리밍 연결 장애 해결 가이드 반영 |
| T-105 (2026-06-16) | HTTPX ReadTimeout 예외 해결을 위한 timeout 상향(2.0s -> 10.0s) 및 상태 캐싱 중복 오버라이딩 방지 로직 적용 |