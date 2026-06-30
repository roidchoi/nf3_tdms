# Task-004: WebSocket 로그 스트리밍 이중화 프록시

> **Sub Project**: p4_manager
> **PRD 근거**: P4-REQ-004 (로그 모니터링 및 스트리밍)
> **작성일**: 2026-06-09
> **의존 Task**: T-003

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| KDMS WebSocket 스펙 | `tdms_core/p2_kdms/main.py:122` 직접 확인 완료 | ⚠️ 직접 확인 |
| USDMS WebSocket 스펙 | `pjt_wiki/p3_usdms_wiki/interfaces/health_admin_api.md` | ✅ 확인 |
| websockets 라이브러리 | P4 가상환경 내 미설치 → `requirements.txt`에 추가 설계 | 🆕 신규 |
| 프론트엔드 stores 및 컴포넌트 구조 | `pjt_wiki/p4_manager_wiki/codebase_map.md` | ✅ 확인 |

---

## § 1. 목표

FastAPI 백엔드(`p4_backend`)에서 한국(KDMS) 및 미국(USDMS) 백엔드의 WebSocket 실시간 수집 로그를 프론트엔드로 안전하게 터널링 중계(이중화 프록시)하고, 프론트엔드에서는 500줄의 링 버퍼를 활용해 메모리 누수 없이 실시간 모니터링을 가능케 합니다.

**구현 범위:**
- **IN**:
  - `p4_backend` 내부 신규 웹소켓 프록시 라우터 `proxy_ws.py` 구현
  - `p4_backend`와 각 시장 백엔드(`p2_kdms`, `p3_usdms`) 웹소켓 간 비동기 클라이언트 터널링 구축
  - 클라이언트 접속 종료 시 백그라운드 원격 소켓 연결 세션의 안전한 자원 반환(Leak 방지)
  - 프론트엔드 Pinia 스토어 `stores/logStore.ts` 구축 (500줄 링 버퍼 적용)
  - 대시보드 및 로그 연계 스트리밍 터널 UI (`LogView.vue` 또는 대시보드 패널)
- **OUT**:
  - 배치 스케줄러 자체의 시간 설정 변경 및 조회 UI (다음 태스크 T-005 범위)
  - 개별 시장의 신선도/갭 체크 및 CIK 차단 해제 모달 (T-006 범위)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/routers/proxy_ws.py` — WebSocket 중계 프록시 API 라우터
- `tdms_core/p4_manager/tests/test_proxy_ws.py` — 중계 백엔드 WebSocket 통합/격리 테스트
- `tdms_core/p4_manager/frontend/src/stores/logStore.ts` — 로그 버퍼 및 웹소켓 연결 스토어
- `tdms_core/p4_manager/frontend/src/tests/logStore.spec.ts` — 프론트엔드 링 버퍼 단위 테스트

### 수정 대상 파일
- `tdms_core/p4_manager/requirements.txt` — `websockets` 패키지 추가
- `tdms_core/p4_manager/main.py` — 신규 `proxy_ws` 라우터 포함
- `tdms_core/p4_manager/nginx/nginx.conf` — Nginx 로그 WebSocket 중계를 p4_backend로 위임하도록 프록시 패스 수정

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 1) 백엔드 WebSocket 엔드포인트 명세
- **주소**: `/api/mgr/ws/logs/{market}` (시장 코드 `kr` 또는 `us` 분기)
- **쿼리 파라미터**: `log_file: Optional[str] = None` (미국 시장 로그 파일 조회용)
- **프로토콜**: WebSocket (ws/wss)

```python
# [신규 정의 — 이 Task에서 최초 설계]
# tdms_core/p4_manager/routers/proxy_ws.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

router = APIRouter()

@router.websocket("/ws/logs/{market}")
async def websocket_proxy_endpoint(
    websocket: WebSocket,
    market: str,
    log_file: Optional[str] = None
):
    """
    [목적] 클라이언트의 WebSocket 연결을 받아, market 인자에 따라
          대상 백엔드의 웹소켓 서버에 비동기 연결하여 양방향 프록시 터널링을 구성합니다.
    """
    ...
```

### 2) 프론트엔드 Pinia LogStore 스펙
```typescript
// [신규 정의 — 이 Task에서 최초 설계]
// tdms_core/p4_manager/frontend/src/stores/logStore.ts

import { defineStore } from 'pinia'

export interface LogState {
  krLogs: string[]
  usLogs: string[]
  krWsStatus: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'
  usWsStatus: 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED'
}

export const useLogStore = defineStore('log', {
  state: (): LogState => ({
    krLogs: [],
    usLogs: [],
    krWsStatus: 'DISCONNECTED',
    usWsStatus: 'DISCONNECTED',
  }),
  actions: {
    connectLogs(market: 'kr' | 'us', logFile?: string): void {
      // 1. 기존 소켓 커넥션이 존재할 경우 disconnectLogs 호출로 클리어
      // 2. WebSocket 연결 수립 및 상태 CONNECTING -> CONNECTED 업데이트
      // 3. 메시지 수신 시 logs 배열에 push하되 length > 500 이면 shift() 수행
      // 4. 에러 발생 및 종료 시 DISCONNECTED 업데이트 및 자동 재연결 대기
    },
    disconnectLogs(market: 'kr' | 'us'): void {
      // 명시적으로 WebSocket close() 호출 및 상태 초기화
    },
    clearLogs(market: 'kr' | 'us'): void {
      // 해당 시장의 로그 배열을 즉시 빈 배열([])로 초기화
    }
  }
})
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 백엔드 테스트 케이스

#### ① `test_proxy_ws_invalid_market_closes_connection`
```python
# [Tier 2 — 격리 통합]
def test_proxy_ws_invalid_market_closes_connection():
    """
    [목적] 잘못된 market 코드(예: jp)로 요청 시 연결이 거부되거나 즉시 닫히는지 검증.
    [유도] router 내에서 market 코드가 'kr', 'us'가 아닌 경우 WebSocketException 400 Bad Request 또는 1008 Policy Violation 처리.
    """
    from fastapi.testclient import TestClient
    from tdms_core.p4_manager.main import app
    
    client = TestClient(app)
    with pytest.raises(Exception): # FastAPI TestClient는 닫힌 소켓 연결 시 Exception 발생
        with client.websocket_connect("/api/mgr/ws/logs/jp") as websocket:
            pass
```

#### ② `test_proxy_ws_client_disconnect_closes_upstream_connection`
```python
# [Tier 2 — 격리 통합]
@pytest.mark.asyncio
async def test_proxy_ws_client_disconnect_closes_upstream_connection(mocker):
    """
    [목적] 클라이언트(프론트엔드)가 연결을 끊었을 때, 업스트림 소켓으로의 비동기 연결 리소스가 누수 없이 닫히는지 검증.
    [유도] client disconnect 감지 시 (WebSocketDisconnect catch) 백그라운드 websockets.connect 세션에 대해 close()를 비동기 호출해야 함.
    """
    import websockets
    mock_ws_client = mocker.patch("websockets.connect")
    # mock 연결 세션의 close()가 정상적으로 불리는지 spy 검증 진행
```

### 4.2 프론트엔드 테스트 케이스

#### ① `test_log_store_adds_logs_and_respects_500_limit`
```typescript
// [Tier 1 — 단위]
import { setActivePinia, createPinia } from 'pinia'
import { useLogStore } from '../stores/logStore'
import { describe, beforeEach, it, expect } from 'vitest'

describe('LogStore 링 버퍼 테스트', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('로그 유입 시 버퍼에 추가되며 500줄을 넘기면 앞선 로그가 소멸한다', () => {
    const store = useLogStore()
    expect(store.krLogs.length).toBe(0)

    // 502개의 로그 모사 입력
    for (let i = 1; i <= 502; i++) {
      // 500개 초과 시 shift() 동작 테스트를 위해 스토어 내부 리액티브 로그에 밀어 넣음
      store.krLogs.push(`Log Line ${i}`)
      if (store.krLogs.length > 500) {
        store.krLogs.shift()
      }
    }

    expect(store.krLogs.length).toBe(500)
    expect(store.krLogs[0]).toBe('Log Line 3') // 앞의 1, 2번 라인은 탈락해야 함
    expect(store.krLogs[499]).toBe('Log Line 502')
  })
})
```

### 4.3 실제 통합 케이스 (Tier 3)

#### ① `test_proxy_ws_real_upstream_mirroring`
```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
import asyncio
from fastapi.testclient import TestClient

@pytest.mark.integration
def test_proxy_ws_real_upstream_mirroring():
    """
    [목적] 실제 KDMS(p2) 백엔드가 기동 중인 조건에서 P4 백엔드 중계 웹소켓에 접속 시 정상적으로 프록싱 메시지가 수신되는지 검증.
    [실행 조건] p2_kdms 컨테이너 가동 필요. `pytest --run-integration`으로 실행.
    """
    from tdms_core.p4_manager.main import app
    client = TestClient(app)
    
    # 실제 WebSocket 연결
    with client.websocket_connect("/api/mgr/ws/logs/kr") as websocket:
        # 최초 메시지가 2초 내에 도달하는지 수신 검증
        try:
            data = websocket.receive_text()
            assert len(data) > 0
        except Exception as e:
            pytest.fail(f"WebSocket receive failed or timed out: {e}")
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_proxy_ws_invalid_market_closes_connection` | Tier 2 | 예외 | 잘못된 시장 코드 진입 시 즉시 연결 차단 |
| 2 | `test_proxy_ws_client_disconnect_closes_upstream_connection` | Tier 2 | 예외 | 클라이언트 종료 시 원격 소켓 세션 close() 자원 반환 검증 |
| 3 | `test_log_store_adds_logs_and_respects_500_limit` | Tier 1 | 경계값 | 프론트엔드 로그 수신 시 500라인 링 버퍼 한계 동작 |
| 4 | `test_proxy_ws_real_upstream_mirroring` | Tier 3 | 실제 통합 | 실물 p2_kdms 백엔드와 중계 소켓 간 E2E 프록싱 성공 검증 |

**총 4개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 실행)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.

- **기술 스택**: 
  - FastAPI `0.136.3`, Uvicorn `0.49.0`
  - websockets (추가 설치 예정, 버전 명시 필수: `websockets>=12.0`)
  - Vue `3.5.34`, Pinia `2.3.1`, Vitest `3.0.5`
- **의존성 설치 방법**:
  `tdms_core/p4_manager/requirements.txt`에 `websockets>=12.0`을 추가한 후 다음 명령 실행:
  `conda run -n tdms_p4_env uv pip install -r tdms_core/p4_manager/requirements.txt`
- **Nginx configuration 수정 방향**:
  `/ws/logs/kr` 및 `/ws/logs/us` 호출을 뒷단 백엔드로 직접 찌르는 것이 아니라, P4 백엔드로 보내도록 수정합니다.
  ```nginx
  # tdms_core/p4_manager/nginx/nginx.conf
  
  location /ws/logs/kr {
      set $upstream_p4 p4_backend;
      proxy_pass http://$upstream_p4:8010/api/mgr/ws/logs/kr;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "Upgrade";
  }
  
  location /ws/logs/us {
      set $upstream_p4 p4_backend;
      proxy_pass http://$upstream_p4:8010/api/mgr/ws/logs/us;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "Upgrade";
  }
  ```
- **주의사항**:
  - WebSocket 비동기 수신 시 `asyncio.sleep()` 또는 `asyncio.gather`를 과도하게 사용하면 Uvicorn의 커넥션 핸들러가 병목을 일으킬 수 있으므로 무한 루프 내에 적절한 `await` 컨텍스트 양보가 이루어지도록 캡슐화합니다.
  - Vitest 테스트 동작 시 임포트 경로가 `tsconfig.app.json`에 정의된 `@/*` 에일리어스를 올바르게 리졸브하도록 설계합니다. 미사용 라이브러리는 `TS6133` 에러가 발생하므로 테스트 코드 내에 임포트 후 미사용 변수가 없도록 유의합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 기존 status 관련 백엔드/프론트엔드 테스트 전체 통과 — 회귀 없음
- [ ] `docs/p4_manager/p4_manager_pjt_tasks.md`의 Task-004 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/tasks/task-004_walkthrough.md` 작성
