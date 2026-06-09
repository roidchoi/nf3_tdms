# post_run_task (수동 태스크 기동 API)

> 마지막 변경: Task-003
> 소스 위치: `tdms_core/p4_manager/routers/manager.py` 및 `tdms_core/p4_manager/services/status_service.py`

### 1. 개요 및 목적
- 관리자 대시보드에서 특정 백엔드 태스크(예: 한국 수집 태스크, 미국 수집 태스크 등)를 수동으로 즉시 기동하기 위해 호출되는 중계 API입니다.
- 단일 호출 경로(`/api/mgr/run`)를 통해 각 백엔드의 고유 API 규격에 맞는 형식으로 번역하여 비동기 호출을 전달하며, 대상 백엔드 시스템 중단 시 에러 격리(Fault Isolation) 및 HTTP 503 처리를 수행합니다.
- 연관된 문서: [[p4_manager_wiki/codebase_map]], [[p4_manager_wiki/interfaces/get_integrated_status]]

---

### 2. 상세 명세 (요약 금지)

#### API 명세
- **엔드포인트**: `POST /api/mgr/run`
- **전송 프로토콜**: HTTP/1.1
- **인증/인가**: 없음

#### 쿼리 파라미터 (Query Parameters)
| 이름 | 타입 | 필수 여부 | 기본값 | 설명 |
|---|---|---|---|---|
| `market` | string | 필수 | - | 대상 시장 코드. `'kr'` 또는 `'us'` 중 하나여야 함. |
| `task_id` | string | 필수 | - | 기동할 백엔드 태스크 식별자. |
| `is_test` | boolean | 선택 | `true` | 한국 시장(KDMS) 수동 기동 시 테스트 모드 여부. (미국 시장에서는 전달되지 않음) |

#### 응답 코드 및 바디 포맷

##### 1) 200 OK (성공)
- **조건**: 대상 백엔드에 요청이 성공적으로 중계되어 수동 기동 처리가 성공했을 때.
- **응답 예시**:
```json
{
  "status": "success",
  "message": "Task daily_update triggered successfully"
}
```

##### 2) 400 Bad Request (잘못된 요청)
- **조건**: `market` 파라미터가 `'kr'` 또는 `'us'`가 아니거나, 필수 파라미터가 유실되었을 때.
- **응답 예시**:
```json
{
  "detail": "Invalid market or task_id"
}
```

##### 3) 503 Service Unavailable (장애 격리)
- **조건**: 중계 대상 백엔드가 다운되었거나 타임아웃, 네트워크 단절 등으로 원격 요청이 실패했을 때.
- **응답 예시**:
```json
{
  "status": "error",
  "message": "kr backend offline",
  "details": "Connection refused"
}
```

---

### 3. 주의사항 및 의존성
- **동적 중계 룰**:
  - **한국 시장 (`kr`)**: `POST {settings.P2_KDMS_URL}/api/v1/admin/tasks/{task_id}/run` 경로로 JSON 바디 `{"test_mode": is_test}`를 실어 전송합니다.
  - **미국 시장 (`us`)**: `POST {settings.P3_USDMS_URL}/api/admin/tasks/{task_id}/run` 경로로 바디 없이 요청을 중계합니다.
- **장 거래 시간 감제 경고 (프론트엔드)**:
  - 사용자 실수로 장 정규 거래 시간(09:00 ~ 15:30) 중에 테스트 모드가 아닌 운영 모드로 수동 기동 명령을 보낼 경우, 프론트엔드 UI(`TaskStatusCard.vue`)에서 1차로 경고 컨펌 모달을 노출하여 실수를 사전에 차단합니다.
- **타임아웃 및 장애 감지**:
  - 중계 요청 시 비동기 타임아웃은 `5.0초`로 제한하며, 에러 발생 시 타 시장에 영향이 없도록 `httpx.RequestError` 예외를 격리 래핑하여 503 코드를 반환합니다.
