# 대시보드 주간 백필 카드 UI 및 다중 백필 제어 개선 (p4dec-011)

## 1. 배경
* **백필 제어의 파편화**: 기존 대시보드는 "분봉 백필"에 대한 단일 제어 버튼만 노출되고 있었음. 그러나 백필 주기 상 "일봉 백필"(`backfill_daily_data`) 및 "시가총액 백필"(`backfill_market_cap`)도 주간/월간 수동 및 스케줄 기동을 공유하므로, 개별 기동할 수 있는 단일화된 통합 인터페이스가 요구되었음.
* **레이아웃 비대화 방지 요구**: 3종 백필의 최종 상태를 모두 나열할 경우 카드 자체의 줄이 불필요하게 비대해져 대시보드의 미적 밸런스가 무너지는 문제가 지적됨.

## 2. UI 설계 및 구현 상세
1. **한국 시장(kr) 주간 백필 전용 다중 버튼 레이아웃**:
   * `taskId === 'backfill_minute_data'` (주간 백필) 카드는 테스트 모드 토글을 숨김.
   * `btn-group-horizontal` 클래스를 적용해 **[분봉]**, **[일봉]**, **[시총]**의 가로 배열 미니 버튼 그룹을 렌더링.
   * 세 작업 중 하나라도 기동 상태(`is_running`)가 되면, 전체 버튼을 비활성화(`disabled`)하여 중복 실행 및 리소스 오버랩 방지.
2. **가장 최근 실행된 태스크의 단일 상태 표시**:
   * `statusStore.status.kr.tasks` 내 3개 태스크의 `last_run_time`을 비교.
   * 가장 늦은 실행 시각(가장 최근)을 보유한 백필 태스크를 자동 식별하여 `[종류]-[상태]` (예: `분봉-success`, `일봉-failed`) 형태로 단 한 줄의 마지막 상태만 콤팩트하게 노출.
   * 카드 크기의 수직 팽창을 완벽히 억제하여 기존 대시보드의 균형 잡힌 글래스모피즘(Glassmorphism) 스타일을 유지.

## 3. 관련 파일 및 구현 위치
* `[TaskStatusCard.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/components/dashboard/TaskStatusCard.vue)`: `latestBackfillStatusText` computed 속성을 추가하여 시간순 내림차순 정렬로 최종 실행 태스크 판별. template에서 조건부 분기로 3종 버튼 및 상태 요약 바인딩.
* `[DashboardView.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/views/DashboardView.vue)`: 임시로 추가되었던 개별 일봉/시총 백필 카드를 롤백하고 단일 주간 백필 카드 형태로 복구.
