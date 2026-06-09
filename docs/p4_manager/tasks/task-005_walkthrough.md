# Task-005 Walkthrough: 스케줄 조회 및 수정 모달 UI 구현

## 1. 구현 내용 요약
한국 시장(`p2_kdms`)과 미국 시장(`p3_usdms`) 백엔드의 비대칭적인 스케줄 제어 API 규격을 동기화(교차 마이그레이션)하고, 이를 P4 통합 백엔드에서 단일 인터페이스로 추상화하여 중계하는 시스템을 구축했습니다. 프론트엔드에서는 안전성이 보장된 다크 글래스모피즘 테마의 스케줄러 제어 뷰 및 시간 변경 모달을 완비했습니다.

### 수정 및 생성된 파일 목록:
- **`tdms_core/p2_kdms/routers/admin.py`** (수정)
  - 시간 동적 변경 API `PUT /api/v1/admin/scheduler` 신규 추가 구현
- **`tdms_core/p3_usdms/routers/admin.py`** (수정)
  - 스케줄 일시정지 및 재개 토글 API `POST /api/admin/schedules/{job_id}/toggle` 신규 추가 구현
- **`tdms_core/p4_manager/routers/manager.py`** (수정)
  - P4 통합 스케줄 제어 중계 API 3종 구현 (`GET /schedules/{market}`, `PUT /schedules/{market}/{job_id}`, `POST /schedules/{market}/{job_id}/toggle`)
  - 비동기 `httpx.AsyncClient` 통신 및 백엔드 오프라인 예외 처리(Fault Isolation) 적용
- **`tdms_core/p4_manager/frontend/src/stores/scheduleStore.ts`** (신규)
  - Pinia를 활용한 한국/미국 주식 수집 스케줄 관리 스토어 구축
- **`tdms_core/p4_manager/frontend/src/components/dashboard/ScheduleModal.vue`** (신규)
  - 드롭다운 방식 시간 선택, 미국 시간대(EST) 실시간 이중 변환 표시, 장중 개장 시간대 변경 방지 "변경승인" 이중 컨펌 안전장치 탑재
- **`tdms_core/p4_manager/frontend/src/views/ScheduleView.vue`** (신규)
  - 스케줄 카드 그리드 렌더링, Paused 카드 그레이아웃 필터, 한국/미국 탭 전환 관리 화면 구현
- **`tdms_core/p4_manager/frontend/src/views/DashboardView.vue`** (수정)
  - 상단 탭 구조('모니터링 보드', '스케줄 및 크론') 도입 및 `ScheduleView` 연동

---

## 2. 테스트 결과

### 백엔드 테스트 (`pytest`)
격리된 Mock API 환경에서 6종 테스트를 수행하여 중계 기능 및 예외 처리를 검증 완료했습니다:
- `test_get_integrated_schedules_kr_success`: 한국 스케줄 규격 표준화 변환 성공 검증
- `test_get_integrated_schedules_us_success`: 미국 스케줄 규격 표준화 변환 성공 검증
- `test_get_integrated_schedules_invalid_market`: 잘못된 마켓 인자 전달 시 예외 차단
- `test_update_integrated_schedule_kr_success`: 한국 스케줄 시간 변경 중계 성공 검증
- `test_toggle_integrated_schedule_us_success`: 미국 스케줄 토글 중계 성공 검증
- `test_toggle_integrated_schedule_invalid_action`: 허용되지 않은 동작(예: delete) 차단

```bash
tests/test_scheduler_bridge.py::test_get_integrated_schedules_kr_success PASSED
tests/test_scheduler_bridge.py::test_get_integrated_schedules_us_success PASSED
tests/test_scheduler_bridge.py::test_get_integrated_schedules_invalid_market PASSED
tests/test_scheduler_bridge.py::test_update_integrated_schedule_kr_success PASSED
tests/test_scheduler_bridge.py::test_toggle_integrated_schedule_us_success PASSED
tests/test_scheduler_bridge.py::test_toggle_integrated_schedule_invalid_action PASSED
```

### 프론트엔드 테스트 (`Vitest`)
Pinia 스토어 및 안전장치 콤보 박스 모달의 기능 6종을 검증 완료했습니다:
- `scheduleStore` fetch/update/toggle API 연동 테스트 4종 100% 통과
- `ScheduleModal.vue` 미국 EST 시간 환산 정확도 테스트 및 장중 "변경승인" 이중 안전 승인 필드 기능 테스트 2종 100% 통과

```bash
 ✓ src/tests/scheduleStore.spec.ts (4 tests) 7ms
 ✓ src/tests/ScheduleModal.spec.ts (2 tests) 39ms
```

---

## 3. 다음 작업 진행 시 주의사항
- **T-006 공통 헬스 모니터링**: 스케줄러 변경에 따른 수집 갭 상태(Gap details)를 다음 헬스 모니터링 뷰에서 유기적으로 연동하여 시각화할 수 있도록 고려해야 합니다.
- **T-011 스케줄 환경 변수 통합 마이그레이션**: 이후 Phase 4에서 하위 백엔드 코드의 기존 로컬 환경 설정이 P4 중앙의 `.env` 파일과 유기적으로 동기화되도록 연동 설계를 준비해야 합니다.
