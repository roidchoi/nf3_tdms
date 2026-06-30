# Task-003 Spec: 통합 대시보드 UI 및 태스크 수동 제어

## 1. 위키 선조회 결과

| 조회 대상 | 소스 파일 / 위키 경로 | 확인된 정보 | 상태 |
|---|---|---|---|
| **Nginx 프록시 정보** | `p4_manager_wiki/interfaces/api_routing_map.md` | `/api/mgr/*` → `p4_backend:8010`, `/` → static | 확인 완료 |
| **KDMS 즉시 실행 API** | `p2_kdms_wiki/codebase_map.md` | `POST /api/v1/admin/tasks/{task_id}/run` (JSON body: `{"test_mode": true}`) | 확인 완료 |
| **USDMS 즉시 실행 API** | `p3_usdms_wiki/interfaces/health_admin_api.md` | `POST /api/admin/tasks/{task_id}/run` (태스크 ID: `daily_routine`, `weekly_backfill`) | 확인 완료 |
| **P4 백엔드 구성** | `tdms_core/p4_manager/main.py` | FastAPI `APIRouter` 및 `tdms_core` 임포트 환경 | 확인 완료 |

---

## 2. 요구사항 및 변경 범위

### 2.1 요구사항 (PRD 근거)
- **F-03: 태스크 즉시 실행**: 관리자 대시보드에서 특정 백엔드 태스크(일일 수집, 재무 정보, 백필 등)를 수동 기동할 수 있어야 함.
- **F-04: 장애 격리(Fault Isolation)**: 한쪽 시장 백엔드가 다운되었거나 예외가 발생하더라도 대시보드 UI가 멈추지 않고, 다른 시장 조작이 유지되어야 함.
- **AESTHETICS (프리미엄 UI/UX)**: Sleek Dark 테마 및 HSL tailored Glow 테두리 애니메이션 적용, 장중 운영 실행 경고 안전 스위치 Switch UI 설계.

### 2.2 Scope
- **In-Scope**:
  - FastAPI 백엔드: `POST /api/mgr/run` 엔드포인트 구현 및 중계 로직 탑재.
  - 프론트엔드 프로젝트: `tdms_core/p4_manager/frontend` 에 Vite + Vue3 + TS SPA 구조 신규 구축 및 `vitest` 유닛 테스트 환경 구성.
  - 프론트엔드 뷰: `DashboardView.vue`, `TaskStatusCard.vue` 컴포넌트 완성 및 Switch UI 테스트 모드 탑재, 실시간 거래 시간대 판정 경고 모달 연동.
  - 빌드 파이프라인: `frontend.Dockerfile`을 Multi-stage 빌드로 변경.
- **Out-Scope**:
  - WebSocket 실시간 로그 중계 (T-004 범위).
  - 스케줄 관리 및 수정 모달 (T-005 범위).

---

## 3. 백엔드 API 설계

### `POST /api/mgr/run`
- **Description**: 한국/미국 백엔드 태스크 즉시 실행 중계.
- **Request Query Parameters**:
  - `market`: `'kr'` 또는 `'us'` (Required)
  - `task_id`: 실행할 태스크 식별자 (Required)
  - `is_test`: `bool` (Optional, 기본값 `True`, 한국 시장 등의 테스트 모드 전송용)
- **Response Format**:
  - `200 OK` (실행 요청 성공): `{"status": "success", "message": "Task {task_id} triggered successfully"}`
  - `400 Bad Request` (유효하지 않은 파라미터): `{"detail": "Invalid market or task_id"}`
  - `503 Service Unavailable` (대상 백엔드 다운 시 장애 격리): `{"status": "error", "message": "{market} backend offline", "details": "..."}`

---

## 4. 테스트 케이스 설계

이 Task는 백엔드(Python/FastAPI)와 프론트엔드(Vue3/TS) 컴포넌트로 나뉘므로, 각각 `pytest`와 `vitest` 테스트 케이스로 세분화하여 설계합니다.

### 4.1 백엔드 테스트 케이스 요약 (`pytest`)

| ID | 계층 | 대상 및 조건 | 기대 결과 | 파일 경로 |
|---|---|---|---|---|
| B-1 | Tier 2 (격리) | 유효한 한국(kr) 태스크 기동 요청 | p2 백엔드 성공 호출 중계 및 200 반환 | `tdms_core/p4_manager/tests/test_status.py` |
| B-2 | Tier 2 (격리) | 유효한 미국(us) 태스크 기동 요청 | p3 백엔드 성공 호출 중계 및 200 반환 | `tdms_core/p4_manager/tests/test_status.py` |
| B-3 | Tier 2 (격리) | 잘못된 파라미터 (유효하지 않은 market) | 400 Bad Request 에러 반환 | `tdms_core/p4_manager/tests/test_status.py` |
| B-4 | Tier 2 (격리) | 대상 백엔드 접속 불능 (Timeout/ConnectionError) | 503 Service Unavailable 장애 격리 처리 | `tdms_core/p4_manager/tests/test_status.py` |

### 4.2 프론트엔드 컴포넌트 테스트 케이스 요약 (`vitest`)

| ID | 계층 | 대상 및 조건 | 기대 결과 | 파일 경로 |
|---|---|---|---|---|
| F-1 | UI 단위 | `TaskStatusCard.vue` 렌더링 | 타이틀, 아이콘, 진행바, 현재 상태 뱃지 정상 출력 | `tdms_core/p4_manager/frontend/src/tests/TaskStatusCard.spec.ts` |
| F-2 | UI 단위 | 테스트 모드 Switch UI 상태 변경 | 내부 `isTestMode` 토글 반응형 갱신 | `tdms_core/p4_manager/frontend/src/tests/TaskStatusCard.spec.ts` |
| F-3 | UI 단위 | 정규 거래 시간 내 운영 모드 즉시 실행 클릭 | 장중 거래 안전 경고(`confirm` 또는 경고 테두리) 발생 및 실행 취소 가능 | `tdms_core/p4_manager/frontend/src/tests/TaskStatusCard.spec.ts` |
| F-4 | UI 단위 | 즉시 실행 버튼 활성화 클릭 | `adminStore.runTask` API Action이 바른 인자값으로 호출됨 | `tdms_core/p4_manager/frontend/src/tests/TaskStatusCard.spec.ts` |
| F-5 | UI 단위 | `DashboardView.vue` 내 통합 헬스 요약 표시 | KR/US 백엔드의 `ONLINE`/`OFFLINE` 상태가 HSL Glow 테두리와 매핑됨 | `tdms_core/p4_manager/frontend/src/tests/DashboardView.spec.ts` |

---

## 5. 상세 테스트 케이스 명세 (구현 코드 유도용)

### B-1: 유효한 한국(kr) 태스크 기동 요청 (Tier 2)
```python
# tdms_core/p4_manager/tests/test_status.py
import pytest
from fastapi.testclient import TestClient
import respx
from httpx import Response

def test_run_kr_task_success(client: TestClient):
    """
    [Tier 2 - 격리 통합]
    [목적] GET /api/mgr/run?market=kr&task_id=daily_update 호출 시
           FastAPI 백엔드가 p2_kdms에 POST 요청을 보내고 200 응답을 정상 중계하는지 검증.
    """
    with respx.mock:
        # p2_kdms 태스크 즉시 실행 모킹
        respx.post("http://p2_kdms:8000/api/v1/admin/tasks/daily_update/run").mock(
            return_value=Response(200, json={"status": "success"})
        )
        
        response = client.post("/api/mgr/run?market=kr&task_id=daily_update&is_test=true")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
```

### B-4: 대상 백엔드 접속 불능 (Tier 2 - Fault Isolation)
```python
# tdms_core/p4_manager/tests/test_status.py
import httpx

def test_run_task_backend_offline_fault_isolation(client: TestClient):
    """
    [Tier 2 - 격리 통합]
    [목적] 대상 백엔드가 다운(ConnectionError)되었을 때 503을 반환하여 장애를 격리하는지 검증.
    """
    with respx.mock:
        respx.post("http://p3_usdms:8005/api/admin/tasks/daily_routine/run").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        
        response = client.post("/api/mgr/run?market=us&task_id=daily_routine")
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert "offline" in response.json()["message"]
```

### F-3: 정규 거래 시간 내 운영 모드 즉시 실행 클릭 (UI 단위)
```typescript
// tdms_core/p4_manager/frontend/src/tests/TaskStatusCard.spec.ts
import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import TaskStatusCard from '../components/dashboard/TaskStatusCard.vue'

describe('TaskStatusCard.vue 안전 장치 제어', () => {
  it('정규 거래 시간 중 운영 모드로 즉시 실행 요청 시 window.confirm 경고창이 노출되어야 한다', async () => {
    // 윈도우 confirm 모킹
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false)
    
    // 장 운영시간으로 임시 강제 고정 (예: 11:30)
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 9, 11, 30)) // 한국 거래 시간중
    
    const wrapper = mount(TaskStatusCard, {
      props: {
        taskId: 'daily_update',
        title: '일일 업데이트',
        icon: '📅',
        status: { is_running: false, last_status: 'success' },
        schedule: undefined
      }
    })

    // 1. 테스트 모드 Switch UI 해제 -> 운영 모드 전환
    const switchInput = wrapper.find('input[type="checkbox"]')
    await switchInput.setValue(false) // isTestMode = false

    // 2. 즉시 실행 버튼 클릭
    const runBtn = wrapper.find('.run-btn')
    await runBtn.trigger('click')

    // 3. window.confirm이 경고 문구와 함께 호출되었는지 단언
    expect(confirmSpy).toHaveBeenCalled()
    expect(confirmSpy.mock.calls[0][0]).toContain('장 거래 시간입니다')

    vi.useRealTimers()
  })
})
```

---

## 6. 구현 시 주의사항 및 가이드라인
1. **Node 가상환경**: `npm` 실행 시 WSL/Ubuntu에 활성화되어 있는 로컬 Node 버전 및 `.nvmrc` 설정을 준수하여 패키지 설치 및 빌드를 수행합니다.
2. **Nginx.conf 정합성**: Nginx가 `http://p4_backend:8010`과 `http://p2_kdms:8000`, `http://p3_usdms:8005`로 정상적으로 중계할 수 있도록 도커 DNS 리졸브 및 도커 컴포즈 내부 네트워크 설정을 확인합니다.
3. **Vanilla CSS 미학**: Scoped CSS 정의 시 CSS 변수(`--primary`, `--glow-color`)를 활용하여 그라디언트 및 흐림 효과(`filter: blur()`)를 명확하게 매핑하고, 다크 슬레이트 기반의 Premium Glassmorphism을 연출합니다.
