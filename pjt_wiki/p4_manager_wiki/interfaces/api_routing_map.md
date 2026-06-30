# P4 API 및 Nginx 프록시 라우팅 맵 (api_routing_map.md)

> 마지막 변경: T-007  
> 소스 위치: `tdms_core/p4_manager/main.py:17`, `tdms_core/p4_manager/routers/manager.py:15`, `tdms_core/p4_manager/routers/proxy_ws.py:11`, `tdms_core/p4_manager/nginx/nginx.conf:59`

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

#### 2.3. P4 백엔드 WebSocket 로그 중계 API
*   **엔드포인트**: `WebSocket /api/mgr/ws/logs/{market}`
*   **소스 위치**: `tdms_core/p4_manager/routers/proxy_ws.py:11`
*   **입력 파라미터**: `market` (Path), `log_file` (Query)
*   **출력 형식**:
*   반환 타입: 실시간 스트리밍 텍스트 (줄 단위)
*   상세 명세: [[p4_manager_wiki/interfaces/ws_proxy_logs]]


#### 2.4. P4 통합 스케줄 제어 API
*   **스케줄 목록 조회**: `GET /api/mgr/schedules/{market}`
    *   **설명**: 한국(kr) 또는 미국(us) 백엔드의 스케줄 정보를 단일 정규화 스키마(`job_id`, `name`, `next_run_time`, `trigger`, `is_paused`)로 정렬하여 반환합니다.
*   **스케줄 일정 변경**: `PUT /api/mgr/schedules/{market}/{job_id}`
    *   **설명**: 시장별 스케줄러 내 특정 작업(job_id)의 크론 매일 기동 일정(hour, minute)을 동적으로 재조정합니다.
*   **스케줄 활성 토글**: `POST /api/mgr/schedules/{market}/{job_id}/toggle`
    *   **설명**: 시장별 스케줄러 내 특정 작업(job_id)을 일시정지(pause) 또는 재개(resume) 처리합니다.
*   **소스 위치**: `tdms_core/p4_manager/routers/manager.py:45`


#### 2.5. P4 통합 데이터 헬스 모니터링 API
*   **데이터 신선도 조회 중계**: `GET /api/mgr/health/freshness/{market}`
    *   **설명**: 한국/미국 주식 데이터 수집 신선도(최종 영업일 대비 당일 일봉 수집 비율) 정보를 중계 조회합니다.
*   **데이터 갭 검출 및 정규화 중계**: `GET /api/mgr/health/gaps/{market}`
    *   **설명**: 한국의 분봉 누락 리스트와 미국의 수집 실패 갭 정보를 단일화된 공통 스키마(`gaps: [GapItem]`)로 정규화 매핑하여 반환합니다.
*   **한국 마일스톤 이력 조회**: `GET /api/mgr/health/kr/milestones`
    *   **설명**: 한국 백엔드(KDMS)에 기록된 데이터 수집/정제 마일스톤 랜드마크 이력을 중계 조회합니다.
*   **한국 마일스톤 등록/수정**: `POST /api/mgr/health/kr/milestones`
    *   **설명**: 새로운 한국 마일스톤 이력을 추가하거나 수정합니다.
*   **미국 수집 차단 블랙리스트 조회**: `GET /api/mgr/health/us/blacklist`
    *   **설명**: 미국 백엔드(USDMS)에 기록된 CIK 수집 실패 임계치 초과 차단 목록을 조회합니다.
*   **미국 블랙리스트 차단 해제**: `POST /api/mgr/health/us/blacklist/{cik}/release`
    *   **설명**: 특정 미국 수집 CIK의 차단 상태를 강제로 해제하고 재수집을 승인합니다.
*   **소스 위치**: `tdms_core/p4_manager/routers/manager.py:143`


#### 2.6. P4 통합 데이터 미리보기 중계 API
*   **테이블 메타데이터 조회**: `GET /api/mgr/preview/meta`
    *   **설명**: 한국(kr) 및 미국(us) 시장별 미리보기가 지원되는 테이블 화이트리스트 10종의 영문 식별자와 한글 표시명을 반환합니다.
    *   **상세 명세**: [[p4_manager_wiki/interfaces/get_preview_meta]]
*   **테이블 데이터 미리보기 중계**: `GET /api/mgr/preview/{market}/{table}`
    *   **설명**: 시장별 미리보기 데이터를 한글 종목코드 필터, 날짜 및 페이징 파라미터와 함께 비동기 중계하며, 통신 장애 시 200 OK와 `offline: true` 객체로 격리 처리합니다.
    *   **상세 명세**: [[p4_manager_wiki/interfaces/get_preview_table]]
*   **소스 위치**: `tdms_core/p4_manager/routers/manager.py:314`


#### 2.7. Nginx 리버스 프록시 라우팅 규칙
*   **수신 포트**: 호스트 포트 `80` (컨테이너 포트 `80` 바인딩)
*   **설정 위치**: `tdms_core/p4_manager/nginx/nginx.conf:59`

| 요청 경로 (Location) | 프록시 목적지 (Proxy Pass) | 비고 |
|---|---|---|
| `/api/kr/` | `http://$upstream_kdms:8000/api/` | KDMS (한국 주식 백엔드) 연동 |
| `/api/us/` | `http://$upstream_usdms:8005/api/` | USDMS (미국 주식 백엔드) 연동 |
| `/api/mgr/` | `http://$upstream_p4:8010/api/mgr/` | P4 Manager 백엔드 연동 |
| `/ws/logs/kr` | `http://$upstream_p4:8010/api/mgr/ws/logs/kr` | KDMS 로그 WebSocket 중계 터널 |
| `/ws/logs/us` | `http://$upstream_p4:8010/api/mgr/ws/logs/us` | USDMS 로그 WebSocket 중계 터널 |
| `/` (Fallback) | `/usr/share/nginx/html/index.html` | Vue.js SPA 정적 자원 서빙 |

### 3. 주의사항 및 의존성
*   **동적 리졸브**: Nginx 기동 순서 및 백엔드 의존성 해결을 위해 `resolver 127.0.0.11 valid=10s;` 선언 하에 업스트림 대상을 변수명으로 참조하고 있습니다.
*   **WS 중계 헤더**: WebSocket 중계 라우트에는 HTTP 1.1 사용선언(`proxy_http_version 1.1;`) 및 핸드셰이크 활성화를 위한 헤더 구성(`Upgrade $http_upgrade`, `Connection "Upgrade"`)이 필수적으로 요구됩니다.

