# [KDMS-ERR-003] 태스크 실행 상태 기록 시 KST 시간대 처리 불일치 장애

- **분류**: KDMS 에러
- **Severity**: Medium
- **발생 Task ID**: T-105
- **Context Link**: `tdms_core/p2_kdms/tasks/financial_task.py`, `tdms_core/p2_kdms/tasks/backfill_task.py`

## 1. 현상
- 재무 업데이트(`financial_update`) 및 분봉 백필(`backfill_minute_data`)을 수동/크론 실행 시, 마지막 실행 시간(`last_run_time`) 정보가 한국 로컬 표준시(KST, +09:00)가 정상 반영되지 않고 UTC 기준 등으로 어긋나게 출력되는 오류.

## 2. 원인
- 태스크 실행 시작 및 완료 시점의 시간 정보를 취득할 때, 타임존 정보가 없는 naive datetime(`datetime.now()`)을 사용했기 때문에 발생했습니다.
- 완료 시점에 상태 갱신을 위해 시간값을 문자열로 변환할 때 `.isoformat()`을 적용하지 않고 저장하여 타임존 정보(+09:00)가 유실되고, P4 Manager에서 파싱 시 시간대 인식이 어긋나게 되었습니다.

## 3. 해결책
- `financial_task.py` 및 `backfill_task.py` 내부에서 시간 기록에 사용하는 `datetime.now()`를 모두 타임존 지정 방식인 `datetime.now(KST)` (`KST = ZoneInfo("Asia/Seoul")`)로 전면 개편했습니다.
- 종료 시각을 `job_statuses` 딕셔너리에 적재 시 `.isoformat()`을 사용하여 KST 오프셋이 정상 포함된 문자열 형태로 제공되도록 일원화했습니다.

## 4. 검증 결과
- 수정 후 수동 실행 테스트 결과, `last_run_time` 필드 정보에 한국 로컬 표준시 오프셋과 실제 기동 시각이 `"2026-06-16T15:55:05.739195+09:00"` 형식으로 완벽하게 반환되는 것을 확인했습니다.
