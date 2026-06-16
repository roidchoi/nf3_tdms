# [P4ERR-006] 실시간 로그 스트리밍 웹소켓 프록시 연결 장애 (HTTP 404 및 403)

## 1. 에러 증상 (Symptoms)
- 통합 관리자 대시보드 하단의 실시간 로그 스트리밍(Realtime Output Stream) 영역에서 대한민국(KDMS) 및 미국(USDMS) 탭이 모두 `DISCONNECTED` 상태로 머물며 로그 스트리밍이 원활히 되지 않음.
- `p4_backend` 컨테이너 로그 분석 결과:
  ```text
  ERROR:p4_manager.proxy_ws:Failed to connect to upstream WebSocket ws://p2_kdms:8000/ws/logs: server rejected WebSocket connection: HTTP 404
  ERROR:p4_manager.proxy_ws:Failed to connect to upstream WebSocket ws://p3_usdms:8005/ws/logs: server rejected WebSocket connection: HTTP 403
  ```
- `p2_kdms` 컨테이너 로그 분석 결과:
  ```text
  WARNING:  Unsupported upgrade request.
  WARNING:  No supported WebSocket library detected. Please use "pip install 'uvicorn[standard]'", or install 'websockets' or 'wsproto' manually.
  ```

---

## 2. 발생 원인 (Root Cause)
1. **KDMS(HTTP 404) 원인**:
   - `p2_kdms` 의 `requirements.txt` 의존성에 `websockets` 모듈이 누락되어 uvicorn이 WebSocket upgrade 요청을 수락하지 못하고 일반 GET 요청의 404 Not Found로 처리함.
2. **USDMS(HTTP 403) 원인**:
   - `p3_usdms` 백엔드 내부의 `admin_router`가 `/api/admin` 접두사(prefix) 하위에 마운트되어 최종 웹소켓 진입점이 `ws://p3_usdms:8005/api/admin/ws/logs`가 됨.
   - 그러나 통합 매니저 `p4_backend` 의 웹소켓 프록시 라우터(`proxy_ws.py`)가 접두사가 생략된 `ws://p3_usdms:8005/ws/logs` 로 업스트림 접속을 찔러 FastAPI 라우터 및 CORS 정합성 불일치로 인해 403 Forbidden 거부가 발생함.

---

## 3. 해결 조치 (Resolution)
1. **의존성(websockets) 보강**:
   - [requirements.txt (KDMS)](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/requirements.txt) 및 [requirements.txt (USDMS)](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/requirements.txt)에 `websockets>=12.0`을 명시적으로 선언함.
2. **프록시 경로 정정**:
   - [proxy_ws.py (P4 Backend)](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/proxy_ws.py) 35라인 부근의 미국 타겟 웹소켓 엔드포인트를 다음과 같이 정정함:
     ```python
     # 수정 전
     target_url = "ws://p3_usdms:8005/ws/logs"
     # 수정 후
     target_url = "ws://p3_usdms:8005/api/admin/ws/logs"
     ```
3. **컨테이너 빌드 및 핫 리로드**:
   - `docker compose build p2_kdms p3_usdms p4_backend && docker compose up -d p2_kdms p3_usdms p4_backend`
   - 재기동 후 대시보드 브라우저에서 `Stream Status: CONNECTED`로 활성화되며 녹색 점 점등을 시각 검증함.

---

## 4. 예방 대책 (Prevention)
- 신규 백엔드 모듈 추가 및 프레임워크 릴리즈 시, WebSocket 업스트림 핸들링을 위한 `websockets` 의존성이 항상 도커 환경에 번들링되도록 `requirements.txt` 템플릿에 기본 포함시킬 것.
- 하위 백엔드 서비스의 라우터 prefix 규칙이 변경될 경우, `p4_backend`에 선언된 연동 주소 매핑 정보도 병행 업데이트하도록 아키텍처 의사결정 기록(decisions.md)에 유지관리 지침 추가.
