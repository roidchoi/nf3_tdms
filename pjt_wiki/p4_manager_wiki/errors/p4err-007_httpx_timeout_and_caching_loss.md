# [P4-ERR-007] HTTPX 타임아웃 및 캐싱 덮어쓰기 장애

- **분류**: P4 Manager 에러
- **Severity**: High
- **발생 Task ID**: T-105
- **Context Link**: `tdms_core/p4_manager/services/status_service.py`

## 1. 현상
- USDMS 미국 시장의 실시간 상태를 조회할 때 화면상에서 `OFFLINE`으로 고정되는 현상 발생.
- `daily_routine` 태스크가 백그라운드에서 한창 기동되고 있음에도, 상태 조회 API `/api/mgr/status` 및 대시보드 화면상에는 "완료됨"(`is_running: false`)으로 오인 표시됨.

## 2. 원인
1. **HTTPX ReadTimeout**: `status_service.py`에서 타겟 백엔드(USDMS) 헬스 및 상태 체크 시 사용하는 httpx 비동기 클라이언트의 기본 타임아웃이 2.0초로 과도하게 짧게 책정되었습니다. DB 쿼리 부하 등으로 응답이 2초를 초과하여 `httpx.ReadTimeout` 예외가 반복 유발되고, 통합 관리 레이어에서는 이를 오프라인(`OFFLINE`)으로 오판했습니다.
2. **캐싱 중복 덮어쓰기**: USDMS 태스크 리포트 목록을 역순으로 순회(가장 최신 파일부터 과거 파일 순)하여 캐싱 맵을 구성할 때, 동일한 `job_id`에 대해 이미 최신(실행 중인) 정보가 수집 캐시에 매핑되었으나, 뒤이어 등장하는 과거의 완료(is_running: false) 리포트 이력들에 의해 최신 실행 중 상태가 `false`로 덮어씌워지는 결함이 존재했습니다.

## 3. 해결책
1. **타임아웃 상향**:
   - `fetch_and_cache_status` 메서드 내부의 httpx 비동기 클라이언트 생성자에서 timeout 인자를 기존 `2.0`에서 `10.0`초로 상향 조정하였습니다.
2. **덮어쓰기 방지 로직 삽입**:
   - `status_service.py`에서 태스크 상태를 파싱해 담을 때, 이미 캐시에 등록된 태스크인 경우 루프를 건너뛰는 방어 코드를 추가했습니다.
   ```python
   if job_id in tasks_data:
       continue
   ```

## 4. 검증 결과
- timeout 상향 조치 후 `ReadTimeout` 발생이 전면 차단되어 USDMS 온라인 상태가 `ONLINE`으로 즉각 복구되었습니다.
- 루프 순회 중복 방지 로직 삽입 후 실행 중 상태가 과거 완료 상태 파일들에 의해 유실되지 않고 정상적으로 캐시에 보존됨을 검증했습니다.
