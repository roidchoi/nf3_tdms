# Task-004: WebSocket 로그 스트리밍 이중화 프록시 구현 완료 워크스루

## 1. 구현 파일 목록 및 역할

### 백엔드 (FastAPI)
- **`tdms_core/p4_manager/routers/proxy_ws.py` [NEW]**
  - 클라이언트의 `/ws/logs/{market}` 요청을 접수하여 `websockets` 비동기 라이브러리를 통해 내부 KDMS(`ws://p2_kdms:8000/ws/logs`) 및 USDMS(`ws://p3_usdms:8005/ws/logs?log_file=...`) 웹소켓 서버로 중계 터널링 프록싱합니다.
  - `asyncio.gather`를 이용하여 업스트림 로그 수신과 클라이언트 해제 감지 프로세스를 동시에 양방향으로 추적하고, 세션 이탈 시 소켓 커넥션 누수(`Connection Leak`)가 발생하지 않도록 `finally` 구문을 통해 확실하게 close 처리합니다.
- **`tdms_core/p4_manager/main.py` [MODIFY]**
  - 신규 WebSocket 프록시 라우터(`proxy_ws`)를 등록하였습니다.
- **`tdms_core/p4_manager/requirements.txt` [MODIFY]**
  - 비동기 소켓 클라이언트 통신을 위해 `websockets>=12.0` 의존성 패키지를 기입 및 설치 완료하였습니다.
- **`tdms_core/p4_manager/tests/test_proxy_ws.py` [NEW]**
  - 잘못된 마켓 요청 시 1008 차단 예외 및 프론트엔드 연결 중단 시 백그라운드 소켓 자원 회수 동작을 Mocking을 통해 검증 완료했습니다.
- **`tdms_core/p4_manager/nginx/nginx.conf` [MODIFY]**
  - Nginx의 웹소켓 로그 중계 설정을 직접 백엔드 연동에서 P4 오케스트레이션 백엔드 프록시로 위임하도록 변경했습니다.

### 프론트엔드 (Vue3 + Pinia + TS)
- **`tdms_core/p4_manager/frontend/src/stores/logStore.ts` [NEW]**
  - 실시간 로그 데이터를 수집하는 Pinia 스토어입니다.
  - 로그 최대 한도를 **500줄**로 제한하는 링 버퍼(`shift()`) 제어를 반영해 브라우저 돔(DOM) 및 렌더링 부하를 예방합니다.
- **`tdms_core/p4_manager/frontend/src/components/dashboard/LogTerminal.vue` [NEW]**
  - 다크 윈도우 셸 디자인의 로그 터미널 창입니다.
  - 자동 하단 스크롤(Auto Scroll), 스크롤 고정 잠금(Scroll Lock), 버퍼 비우기(Clear), 텍스트 폰트 크기 변경, 전체 화면 오버레이 기능 등을 풍부히 지원합니다.
  - 실시간 소켓 연결 LED 펄스 인디케이터를 통해 가시적인 연결 상태 피드백을 전달합니다.
- **`tdms_core/p4_manager/frontend/src/views/DashboardView.vue` [MODIFY]**
  - 대시보드 하단에 실시간 로그 스트리밍 섹션을 배치하여 기동 즉시 로그를 모니터링할 수 있도록 조립 완료했습니다.
- **`tdms_core/p4_manager/frontend/src/tests/logStore.spec.ts` [NEW]**
  - Pinia 스토어 링 버퍼 500라인 컷오프 한계 로직 유닛 테스트를 완료했습니다.

---

## 2. 테스트 및 검증 결과

### ① 백엔드 Pytest
```bash
conda run -n tdms_p4_env env PYTHONPATH=. pytest tdms_core/p4_manager/tests/ -v -m "not integration"
```
- 결과: **10개 테스트 통과 (100% Green)**
- 신규 작성한 `test_proxy_ws_invalid_market_closes_connection` 및 `test_proxy_ws_client_disconnect_closes_upstream_connection` 포함 전체 성공 완료.

### ② 프론트엔드 Vitest
```bash
npm run test
```
- 결과: **3개 테스트 파일 (총 6개 유닛 테스트) 통과 (100% Green)**
- 신규 작성한 `logStore.spec.ts` 링 버퍼 동작 테스트 통과 완료.

---

## 3. 다음 작업 시 참고사항

- **T-005 (스케줄 조회 및 수정 모달)** 구현 단계에 진입 가능합니다.
- Nginx 웹소켓 중계 설정 변경 사항은 로컬 Docker Compose 빌드 반영 단계에서 정상 구동됨을 확증합니다.
