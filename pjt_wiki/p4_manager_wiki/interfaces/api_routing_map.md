# P4 API 및 Nginx 프록시 라우팅 맵 (api_routing_map.md)

> 마지막 변경: T-003  
> 소스 위치: `tdms_core/p4_manager/main.py:17`, `tdms_core/p4_manager/routers/manager.py:15`, `tdms_core/p4_manager/nginx/nginx.conf:27`

### 1. 개요 및 목적
*   P4 Manager 오케스트레이션 레이어 내부 백엔드 API와 외부 Nginx 리버스 프록시 및 WebSocket 중계를 매핑하는 핵심 인터페이스 규격입니다.
*   연관된 문서: [[p4_manager_wiki/environment.md]], [[p4_manager_wiki/decisions.md]]

### 2. 상세 명세 (요약 금지)

#### 2.1. P4 백엔드 헬스 체크 API
*   **엔드포인트**: `GET /api/mgr/health`
*   **소스 위치**: `tdms_core/p4_manager/main.py:17`
*   **입력 파라미터**: 없음
*   **출력 형식**:
    *   반환 타입: `dict` (JSON)
    *   예시 응답:
    ```json
    {
      "status": "ok",
      "service": "p4_backend"
    }
    ```

#### 2.2. P4 백엔드 수동 태스크 기동 API
*   **엔드포인트**: `POST /api/mgr/run`
*   **소스 위치**: `tdms_core/p4_manager/routers/manager.py:15`
*   **입력 파라미터**: `market` (query), `task_id` (query), `is_test` (query)
*   **출력 형식**:
    *   반환 타입: `dict` (JSON)
    *   상세 명세: [[p4_manager_wiki/interfaces/post_run_task]]


#### 2.3. Nginx 리버스 프록시 라우팅 규칙
*   **수신 포트**: 호스트 포트 `80` (컨테이너 포트 `80` 바인딩)
*   **설정 위치**: `tdms_core/p4_manager/nginx/nginx.conf:27`

| 요청 경로 (Location) | 프록시 목적지 (Proxy Pass) | 비고 |
|---|---|---|
| `/api/kr/` | `http://$upstream_kdms:8000/api/` | KDMS (한국 주식 백엔드) 연동 |
| `/api/us/` | `http://$upstream_usdms:8005/api/` | USDMS (미국 주식 백엔드) 연동 |
| `/api/mgr/` | `http://$upstream_p4:8010/api/mgr/` | P4 Manager 백엔드 연동 |
| `/ws/logs/kr` | `http://$upstream_kdms:8000/ws/logs` | KDMS 로그 WebSocket 중계 터널 |
| `/ws/logs/us` | `http://$upstream_usdms:8005/ws/logs` | USDMS 로그 WebSocket 중계 터널 |
| `/` (Fallback) | `/usr/share/nginx/html/index.html` | Vue.js SPA 정적 자원 서빙 |

### 3. 주의사항 및 의존성
*   **동적 리졸브**: Nginx 기동 순서 및 백엔드 의존성 해결을 위해 `resolver 127.0.0.11 valid=10s;` 선언 하에 업스트림 대상을 변수명으로 참조하고 있습니다.
*   **WS 중계 헤더**: WebSocket 중계 라우트에는 HTTP 1.1 사용선언(`proxy_http_version 1.1;`) 및 핸드셰이크 활성화를 위한 헤더 구성(`Upgrade $http_upgrade`, `Connection "Upgrade"`)이 필수적으로 요구됩니다.
