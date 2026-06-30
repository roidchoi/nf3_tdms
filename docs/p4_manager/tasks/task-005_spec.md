# Task-005: 스케줄 조회 및 수정 모달 UI 구현

> **Sub Project**: p4_manager (통합 관리 레이어)
> **PRD 근거**: PRD v1.0 (Phase 2 스케줄 편집 통제)
> **작성일**: 2026-06-09
> **의존 Task**: T-004 (WebSocket 로그 스트리밍 이중화 프록시)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `.agents/skills/nf-task-spec-writer/references/wiki-query-protocol.md` 절차를 준수하였습니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| KDMS 스케줄 상태 | `pjt_wiki/p2_kdms_wiki/interfaces/fastapi_lifespan.md` | ✅ 확인 |
| USDMS 스케줄 인터페이스 | `pjt_wiki/p3_usdms_wiki/interfaces/health_admin_api.md` | ✅ 확인 |
| KDMS 어드민 라우터 | `tdms_core/p2_kdms/routers/admin.py` 직접 확인 | ⚠️ 직접 확인 |
| USDMS 어드민 라우터 | `tdms_core/p3_usdms/routers/admin.py` 직접 확인 | ⚠️ 직접 확인 |
| P4 스케줄 중계 및 통합 API | 이 Task에서 최초 설계 | 🆕 신규 |
| 프론트엔드 ScheduleView/Modal | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

한국/미국 주식 수집 및 파싱 스케줄러(APScheduler)의 구동 상태를 단일 관리 대시보드 상에서 조회, 수정(Reschedule), 일시정지/재개(Toggle) 제어할 수 있는 오케스트레이션 인터페이스와 다크 글래스모피즘 기반의 UI/UX를 완비합니다.

**구현 범위:**
- **IN**:
  - `p2_kdms` 백엔드 내 크론 시간 동적 수정 API (`PUT /api/v1/admin/scheduler`) 추가 구현
  - `p3_usdms` 백엔드 내 크론 일시정지/재개 API (`POST /api/admin/schedules/{job_id}/toggle`) 추가 구현
  - `p4_backend`에 한국/미국 스케줄을 표준 규격으로 감싸서 서빙하고 중계하는 라우팅 API 3종 개발
  - 프론트엔드 Pinia `scheduleStore.ts` 상태 관리 스토어 구축
  - 프론트엔드 스케줄 제어 뷰 (`ScheduleView.vue`) 및 세부 시간 설정 모달 (`ScheduleModal.vue`) 구현
- **OUT**:
  - 새로운 스케줄의 동적 생성(Create) 및 시스템 코어 스케줄의 영구 삭제(Delete) 기능은 제외 (안전 무결성 유지를 위해 수정 및 일시정지 제어만 허용)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/frontend/src/stores/scheduleStore.ts` — 한국/미국 스케줄 상태 관리 스토어
- `tdms_core/p4_manager/frontend/src/components/dashboard/ScheduleModal.vue` — 드롭다운 형태 시간 변경 및 이중 타임존 표시/안전 이중 확인 모달
- `tdms_core/p4_manager/frontend/src/views/ScheduleView.vue` — 스케줄 목록 렌더링 뷰 (Paused 상태 그레이아웃 필터)
- `tdms_core/p4_manager/frontend/src/tests/scheduleStore.spec.ts` — 스토어 단위/격리 테스트
- `tdms_core/p4_manager/frontend/src/tests/ScheduleModal.spec.ts` — 모달 거래 시간대 안전장치 및 이중 타임존 변환 렌더링 테스트
- `tdms_core/p4_manager/tests/test_scheduler_bridge.py` — 백엔드 스케줄러 중계/동기화 통합 및 격리 검증 테스트

### 수정 대상 파일
- `tdms_core/p2_kdms/routers/admin.py` — 시간 수정 API `PUT /scheduler` 추가
- `tdms_core/p3_usdms/routers/admin.py` — 상태 토글 API `POST /schedules/{job_id}/toggle` 추가
- `tdms_core/p4_manager/routers/manager.py` — P4 통합 스케줄 제어 API 3종 라우팅 정의 추가
- `tdms_core/p4_manager/frontend/src/views/DashboardView.vue` — 스케줄 탭 연결 및 네비게이션 연동

---

## § 3. 핵심 인터페이스

### 1. `p2_kdms` 신규 스케줄 reschedule API
```python
# [신규 정의 — 구현 Agent가 tdms_core/p2_kdms/routers/admin.py에 추가]

@router.put("/scheduler", summary="스케줄러 작업 실행 시간 변경")
async def reschedule_job(
    job_id: str,
    hour: int,
    minute: int
):
    """
    특정 작업(job_id)의 매일 실행 시간(hour, minute)을 동적으로 변경(reschedule)합니다.
    """
    if scheduler is None:
        raise HTTPException(status_code=500, detail="스케줄러 시스템이 정상적으로 기동되지 않았습니다.")
        
    try:
        scheduler.reschedule_job(job_id, trigger="cron", hour=hour, minute=minute)
        logger.info(f"스케줄러 작업 일정 변경 완료: {job_id} -> {hour:02d}:{minute:02d}")
        return {"status": "SUCCESS", "job_id": job_id, "hour": hour, "minute": minute}
    except Exception as e:
        logger.error(f"스케줄러 일정 변경 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"스케줄 일정 변경에 실패했습니다: {str(e)}")
```

### 2. `p3_usdms` 신규 스케줄 toggle API
```python
# [신규 정의 — 구현 Agent가 tdms_core/p3_usdms/routers/admin.py에 추가]

@router.post("/schedules/{job_id}/toggle", summary="스케줄러 작업 일시정지 또는 재개")
def toggle_job(
    job_id: str,
    action: str = Query(..., description="작업 ('pause' 또는 'resume')"),
    request: Request
):
    """
    특정 작업(job_id)을 일시 정지(pause) 또는 재개(resume)합니다.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler is not running or not registered.")
        
    if action not in ["pause", "resume"]:
        raise HTTPException(status_code=400, detail="Action must be 'pause' or 'resume'.")
        
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        
    try:
        if action == "pause":
            job.pause()
            return {"status": "PAUSED", "job_id": job_id}
        elif action == "resume":
            job.resume()
            return {"status": "RESUMED", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to change job state: {str(e)}")
```

### 3. P4 통합 중계 API (`tdms_core/p4_manager/routers/manager.py`)
```python
# [신규 정의 — 구현 Agent가 p4_manager에 구현]

@router.get("/schedules/{market}", summary="한국/미국 스케줄 목록 통합 조회")
async def get_integrated_schedules(market: str):
    """
    시장(kr/us)별 백엔드의 스케줄러 정보 및 작업 리스트를 가져와서 
    단일 표준 포맷으로 파싱하여 반환합니다.
    """
    ...

@router.put("/schedules/{market}/{job_id}", summary="한국/미국 스케줄 시간 변경 중계")
async def update_integrated_schedule(market: str, job_id: str, hour: int, minute: int):
    """
    시장(kr/us)에 맞춰 각 백엔드 스케줄러의 크론 시간 수정을 중계합니다.
    """
    ...

@router.post("/schedules/{market}/{job_id}/toggle", summary="한국/미국 스케줄 활성/비활성 제어")
async def toggle_integrated_schedule(market: str, job_id: str, action: str):
    """
    시장(kr/us)에 맞춰 각 백엔드 스케줄의 일시정지(pause)/재개(resume)를 중계합니다.
    """
    ...
```

---

## § 3a. 기존 기능 보존

### 보존 인터페이스
- `p2_kdms` 의 `POST /api/v1/admin/scheduler/{job_id}/toggle` — 기존 토글 동작 보존
- `p3_usdms` 의 `PUT /api/admin/schedules` — 기존 일정 수정 동작 보존

### 회귀 테스트 케이스
```python
# [Tier 2 — 격리 통합]
def test_kdms_toggle_api_remains_unchanged(client_mocker):
    """KDMS 기존 토글 엔드포인트가 정상 호환 및 보존되는지 검증"""
    ...
```

---

## § 4. 테스트 케이스

### 4.1 정상 동작 케이스 (Happy Path)

```python
# [Tier 2 — 격리 통합]
def test_integrated_schedules_kr_returns_standardized_list(client_mocker):
    """
    [목적] P4 백엔드에서 한국 시장(kr) 스케줄을 조회했을 때 KDMS의 원본 데이터를
           통일된 단일 스키마 포맷(job_id, name, next_run_time, trigger, is_paused)으로 변환 검증.
    [유도] get_integrated_schedules 함수 내에서 KDMS JSON 응답을 정규화 매핑 처리해야 함.
    """
    # Arrange: Mock KDMS response
    
    # Act: Request GET /api/mgr/schedules/kr
    
    # Assert: Check standardized fields
```

```python
# [Tier 2 — 격리 통합]
def test_integrated_schedules_us_returns_standardized_list(client_mocker):
    """
    [목적] P4 백엔드에서 미국 시장(us) 스케줄을 조회했을 때 USDMS의 원본 데이터를
           통일된 단일 스키마 포맷으로 변환 검증.
    [유도] get_integrated_schedules 함수 내에서 USDMS JSON 응답을 정규화 매핑 처리해야 함.
    """
```

### 4.2 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_convert_kst_to_est_timezone_conversion():
    """
    [목적] KST 시각을 EST/EDT 서머타임 변동에 따라 정확하게 역환산하는 헬퍼 함수 유닛 테스트.
    """
```

```python
# [Tier 2 — 격리 통합]
def test_reschedule_integrated_api_invalid_market_raises_400():
    """
    [목적] 존재하지 않는 시장 식별자(예: 'jp') 입력 시 400 Bad Request 리턴 검증.
    """
```

### 4.3 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
@pytest.mark.integration
def test_integrated_schedules_real_reschedule_and_verify(real_backends):
    """
    [목적] 실제 기동된 KDMS/USDMS 테스트 컨테이너와 리프록시를 거쳐 P4 API에서 보낸 PUT 요청이
           하위 백엔드 스케줄러의 다음 실행 예정 시각(next_run_time)에 동적으로 즉시 반영되는지 검증.
    """
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_integrated_schedules_kr_returns_standardized_list` | Tier 2 | 정상 | KDMS 스케줄 리턴 구조 정규화 변환 검증 |
| 2 | `test_integrated_schedules_us_returns_standardized_list` | Tier 2 | 정상 | USDMS 스케줄 리턴 구조 정규화 변환 검증 |
| 3 | `test_reschedule_integrated_api_invalid_market_raises_400` | Tier 2 | 예외 | 잘못된 마켓 변수 전달 시 예외 차단 검증 |
| 4 | `test_convert_kst_to_est_timezone_conversion` | Tier 1 | 단위 | 시간대 변환 헬퍼 정확성 검증 |
| 5 | `test_kdms_new_put_reschedule_api_success` | Tier 2 | 정상 | KDMS 추가 구현된 시간 수정 API 동작 검증 |
| 6 | `test_usdms_new_post_toggle_api_success` | Tier 2 | 정상 | USDMS 추가 구현된 토글 API 동작 검증 |
| 7 | `test_integrated_schedules_real_reschedule_and_verify` | Tier 3 | 실제 통합 | 실제 이종 백엔드 스케줄러 동적 시간 조작 무결성 검증 |

---

## § 5. 구현 참고사항

- **기술 스택**:
  - Python `3.12`, FastAPI `0.136.3`, Uvicorn `0.49.0`
  - Vue `3.5.34`, Pinia `2.3.1`, Vitest `3.0.5`
- **의존성 설치 방법**:
  추가 패키지 필요 없음. 기존 `tdms_p4_env` 콘다 환경 사용.
- **안전 통제 정책 (Safety Lock)**:
  - 주식시장 개장 및 전후 수집 가동 시간대(KST 기준 한국 09:00~16:00, 미국 22:00~06:00) 동안 스케줄 시간 변경이나 토글 스위치 비활성화 클릭 시, 화면상에 경고 배너와 함께 **"현재 수집 주기 혹은 개장 시간대입니다. 변경을 계속하시겠습니까?"** 라는 팝업 메시지를 노출하고, 이중 승인(Double Confirm) 텍스트 입력창("변경승인")을 입력받아 동작하도록 안전 제어(Safety Control)를 프론트엔드 모달에 결합합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 기존 status 및 logs 관련 백엔드/프론트엔드 테스트 전체 통과 — 회귀 없음
- [ ] `docs/p4_manager/p4_manager_pjt_tasks.md`의 Task-005 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/tasks/task-005_walkthrough.md` 작성
