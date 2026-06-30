# Walkthrough: T-006 공통 헬스 모니터링 및 시장별 특화 패널 구현

T-006 작업에서는 South Korea(KDMS) 및 United States(USDMS) 백엔드의 데이터 신선도(Freshness), 데이터 누락 갭(Gaps), 그리고 한국 마케팅 마일스톤(Milestones) 및 미국 CIK 수집 차단 목록(Blacklist) API를 P4 통합 매니저에서 중계 및 정규화하고, 이를 다크 글래스모피즘 테마의 단일 뷰(`HealthView.vue`)에서 제어 및 분석할 수 있도록 프론트엔드 연동까지 완성했습니다.

## 1. 주요 변경 사항

### 1.1. 미국 백엔드 (p3_usdms)
* **[NEW]** `POST /api/health/blacklist/{cik}/release` API 신설
  * `BlacklistRepo.release_blacklist` 메서드를 호출하여 수집 차단 상태(`is_blocked=True`)를 즉시 해제 및 관리자 노트를 남기는 통신 단계를 구축했습니다.
  * 10자리 CIK 패딩 보장 로직을 적용했습니다.

### 1.2. 통합 매니저 백엔드 (p4_manager)
* **[MODIFY]** `tdms_core/p4_manager/routers/manager.py`에 헬스 중계 API 6종 구축
  1. `GET /api/mgr/health/freshness/{market}`: 한국/미국 최종 수집일 및 커버리지 연동
  2. `GET /api/mgr/health/gaps/{market}`: 한국 분봉 누락 종목(`missing_stocks`)과 미국 갭 수(`gaps_count`) 정보를 표준화 구조(`gaps: [{"date": ..., "status": ..., "total_targets": ..., "valid_targets": ..., "missing_count": ..., "missing_items": [...]}]`)로 정규화 파싱
  3. `GET /api/mgr/health/kr/milestones`: 한국 마일스톤 이력 중계
  4. `POST /api/mgr/health/kr/milestones`: 한국 마일스톤 생성/수정 중계
  5. `GET /api/mgr/health/us/blacklist`: 미국 수집 차단 종목 목록 중계
  6. `POST /api/mgr/health/us/blacklist/{cik}/release`: 미국 특정 CIK 차단 해제 트리거 중계
* **장애 격리 (Fault Isolation)**
  * 하위 백엔드가 오프라인이거나 통신 장애(`httpx.RequestError`) 발생 시, P4 백엔드 전체가 무너지지 않도록 에러를 캐치하고 `{"status": "RED", "offline": true}` 등의 기본 규격을 `200 OK`로 반환하는 세이프 가드를 적용했습니다.

### 1.3. 프론트엔드 (p4_manager/frontend)
* **[NEW]** `src/stores/healthStore.ts`
  * API 6종에 대응하는 Pinia 상태 관리 스토어를 작성하고 로딩 플래그 및 오프라인 상태 필드(`blacklistOffline`)를 선언했습니다.
* **[NEW]** `src/components/dashboard/MilestoneTimeline.vue` (KR 특화)
  * 한국 시장 마케팅 마일스톤 이력을 타임라인(점묘선 형태)으로 렌더링하고, 글래스모피즘 기반 다이얼로그 모달을 통해 새 마일스톤을 동적 기입/추가합니다.
* **[NEW]** `src/components/dashboard/BlacklistPanel.vue` (US 특화)
  * 미국 수집 차단 상태인 CIK 목록을 표로 조회하고, '차단 해제' 클릭 시 이중 확인 컨펌 다이얼로그가 기동되어 실수를 사전에 방지하도록 통제합니다.
* **[NEW]** `src/views/HealthView.vue`
  * 상단에 실시간 신선도 현황 프로그레스 바 카드를 표출하고, 탭에 따라 갭 누락 정밀 분석 표(정규화 데이터 기반)와 시장별 특화 패널을 교차 마운트합니다.
* **[MODIFY]** `src/views/DashboardView.vue`
  * 대시보드 내비게이션 바에 3번째 탭("🏥 데이터 헬스 모니터")을 배치하고 탭 상태가 `health`일 때 `HealthView` 컴포넌트가 마운트되도록 변경했습니다.

## 2. 검증 결과

### 2.1. 백엔드 유닛 테스트 통과
* `tdms_p3_env` 환경에서 미국 차단 해제 격리 테스트(`test_health_release.py`) 1종 성공.
* `tdms_p4_env` 환경에서 P4 매니저 헬스 중계 API 9종 모의 테스트(`test_health_bridge.py`) 성공.
* `tdms_p4_env` 환경에서 기존 스케줄러 중계 API 테스트(`test_scheduler_bridge.py`) 6종 성공.

```bash
# USDMS 테스트
(tdms_p3_env) pytest tdms_core/p3_usdms/tests/test_health_release.py -v
--> 1 passed in 1.25s

# P4 Manager 테스트
(tdms_p4_env) pytest tdms_core/p4_manager/tests/test_health_bridge.py -v
--> 9 passed in 0.34s
```

### 2.2. 프론트엔드 단위 테스트 및 타입 체킹 빌드 검증
* `vitest run`을 통해 16개의 단위 테스트가 100% 통과했습니다.
* `npm run build` (`vue-tsc -b && vite build`) 실행 시 `verbatimModuleSyntax` 컴파일 규칙을 완벽하게 충족하며 번들 빌드가 완료되었습니다.
