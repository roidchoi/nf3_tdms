# Task-003 Walkthrough: 통합 대시보드 UI 및 태스크 수동 제어

본 문서는 **T-003(통합 대시보드 UI 및 태스크 수동 제어)** 구현 작업에 대한 결과 보고 및 검증 내용을 기록한 문서입니다.

---

## 1. 구현 목표 및 범위
- **백엔드 중계 API**: `POST /api/mgr/run` 엔드포인트를 제공하여 한국(KDMS) 및 미국(USDMS) 백엔드 태스크 즉시 실행 명령을 비동기로 수동 호출하도록 연동.
- **장애 격리(Fault Isolation)**: 한쪽 시장 백엔드가 다운(OFFLINE)되어 `httpx.RequestError` 발생 시 대시보드 작동이 정지되지 않고 다른 시장 조작이 유지되도록 HTTP 503 에러 리턴 및 차단 로직 구성.
- **Vite + Vue3 + TS 프로젝트 구축**: `tdms_core/p4_manager/frontend` 디렉터리에 Vitest 기반 TDD 및 Glassmorphism 테마의 대시보드 구축.
- **수동 실행 제어 UI**: `TaskStatusCard.vue` 및 `DashboardView.vue` 컴포넌트 개발. 한국 시장은 정규 장 운영 시간대(09:00 ~ 15:30)에 운영 모드로 기동 시 경고 컨펌 모달을 통해 안전장치 제공.
- **Multi-stage 빌드 파이프라인**: `frontend.Dockerfile`을 Node 20 환경에서 Vue 빌드를 돌린 다음 Nginx로 서빙하는 Multi-stage Dockerfile로 리팩토링.

---

## 2. 세부 구현 내역

### 2.1 Backend (Python / FastAPI)
- **라우터 및 엔드포인트** ([routers/manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py))
  - `POST /api/mgr/run?market={market}&task_id={task_id}&is_test={is_test}` 노출.
  - `ValueError` 발생 시 `400 Bad Request` 처리.
  - `httpx.RequestError` 발생 시 `503 Service Unavailable`로 안전하게 예외 격리.
- **비동기 요청 중계 서비스** ([services/status_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/status_service.py))
  - `StatusService.run_task` 구현.
  - `market="kr"`일 때 `POST {settings.P2_KDMS_URL}/api/v1/admin/tasks/{task_id}/run`로 `{"test_mode": is_test}` 전송.
  - `market="us"`일 때 `POST {settings.P3_USDMS_URL}/api/admin/tasks/{task_id}/run`로 전송.

### 2.2 Frontend (Vite + Vue3 + TS)
- **의존성 설정** ([package.json](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/package.json))
  - `axios`, `pinia`, `vue-router` 프로덕션 의존성 주입.
  - `vitest`, `@vue/test-utils`, `jsdom` 등 유닛 테스트 도구 구축.
- **경로 별칭 및 컴파일러 대응** ([tsconfig.app.json](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/tsconfig.app.json) 및 [vite.config.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/vite.config.ts))
  - TypeScript 6.0 현대화 에일리어스 규격을 준수하여 `@/*` 에일리어스를 컴파일러 및 Vitest 환경에 매핑.
  - Vue 컴포넌트 타입 오류 해결을 위한 shims 선언 추가 ([shims-vue.d.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/shims-vue.d.ts)).
- **디자인 테마 및 Glassmorphism** ([style.css](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/style.css))
  - 다크 슬레이트 & 인디고 계열의 Premium Dark Theme 및 radial-gradient 효과 지정.
- **컴포넌트 설계**
  - `TaskStatusCard.vue`: 태스크별 마지막 상태, 최종 실행 시간, 기동 중 가로 스크롤링 슬라이드 바, 한국 시장 전용 테스트 모드 스위치 UI 구현 및 장중 기동 경고창 구현.
  - `DashboardView.vue`: 한국(KDMS) / 미국(USDMS) 백엔드의 게이트웨이 온라인 여부 및 갭/신선도 수집율 카드 배치, 2초 주기의 상태 자동 폴링 구현.

### 2.3 Docker 빌드 파이프라인
- **빌드 격리** ([frontend.Dockerfile](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend.Dockerfile))
  - Stage 1: `node:20-alpine`을 `builder`로 지정하여 `npm ci` 수행 및 `npm run build` 컴파일.
  - Stage 2: `nginx:1.25-alpine`에 Nginx Proxy 설정을 이식하고 builder의 `/app/dist` 폴더를 `/usr/share/nginx/html`로 복사.

---

## 3. 검증 결과

### 3.1 Backend Pytest (6 Passed)
```bash
PYTHONPATH=. conda run -n tdms_p4_env pytest tdms_core/p4_manager/tests/test_status.py -v -m "not integration"
```
수동 실행 테스트 및 장애 격리(Fault Isolation) 케이스 4종 추가 후 백엔드 전원 정상 통과(Green) 완료.
- `test_run_kr_task_success`: 한국 백엔드 수동 기동 중계 및 `is_test` 바인딩 성공 검증.
- `test_run_us_task_success`: 미국 백엔드 수동 기동 중계 성공 검증.
- `test_run_task_invalid_params`: 올바르지 않은 마켓 구분 호출 시 `400 Bad Request` 에러 검증.
- `test_run_task_backend_offline_fault_isolation`: 대상 백엔드 오프라인 시 `503 Service Unavailable` 반환 검증.

### 3.2 Frontend Vitest (5 Passed)
```bash
npm run test
```
- `TaskStatusCard.spec.ts`: 컴포넌트 기본 정보 렌더링, 테스트 모드 토글 Switch UI 작동, 장중 운영 기동 시 `window.confirm` 팝업 차단 경고, `statusStore.runTask` 연동 검증 등 4개 테스트 케이스 통과.
- `DashboardView.spec.ts`: 게이트웨이 헬스 보드 연동 모니터링 렌더링 검증 통과.

### 3.3 Docker Build
```bash
docker compose build p4_frontend
```
- Multi-stage 컴파일 파이프라인 정상 빌드 완료.
- `vue-tsc -b` 검사 완료 및 `dist/` 프로덕션 아티팩트 Nginx 이식 확인.

---

## 4. 향후 고려사항 및 관리 방침
1. **장 거래 시간 감지**: 현재 `TaskStatusCard`에서는 정규 장중 거래 시간(09:00 ~ 15:30)을 클라이언트 시스템 로컬 시간을 기준으로 판정하고 있습니다. 향후 서버-클라이언트 시간 편차를 최소화하기 위해 백엔드 API 단에서 시장 개장 정보를 반환하도록 고도화할 수 있습니다.
2. **WebSocket 로그**: 후속 T-004 작업 진행 시 백엔드 `proxy_ws.py`와의 실시간 이중화 스트리밍 데이터 구조가 프론트엔드 대시보드 로그 영역에 연동될 예정입니다.
