# [USDMS-ERR-003] 로깅 기본값 누락 및 백그라운드 실행 상태 유실 장애

- **분류**: USDMS 에러
- **Severity**: High
- **발생 Task ID**: T-105
- **Context Link**: `tdms_core/p3_usdms/main.py`, `tdms_core/p3_usdms/routers/admin.py`

## 1. 현상
- `DailyRoutine` 등 미국 주식 수집 태스크가 로컬 백그라운드에서 실행되는 동안, 생성되는 로그 파일(`logs/daily_routine.log`)에 `INFO` 수준의 세부 동작 로그가 전혀 기록되지 않고 파일이 비어 있었습니다.
- 백그라운드 태스크가 한창 구동 중임에도 P4 Manager로 상태를 전달하는 `/api/admin/tasks/status` API가 `is_running: false`를 지속 반환하여 대시보드에서 실시간 기동 중 인디케이터가 표시되지 않는 상태 동기화 장애가 발생했습니다.

## 2. 원인
1. **로깅 설정 누락**: 백엔드 진입점인 `main.py`에 기본 `logging.basicConfig(level=logging.INFO)` 레벨 설정이 빠져 있어, 파이썬 기본 로거 레벨이 `WARNING`으로 머물렀습니다. 이로 인해 파이프라인의 핵심 `logger.info()` 출력들이 파일로 리디렉션되지 못하고 유실되었습니다.
2. **실시간 구동 상태 피드백 부재**: `/tasks/status` API가 디스크에 완료 시점에만 생성되는 JSON 리포트 파일(`daily_routine_*.json`)을 단순 수집하여 반환하는 구조였습니다. 백그라운드 스레드에서 태스크가 돌고 있는 실행 중 정보(`is_running: true`, `status: RUNNING`)를 메모리 플래그로부터 병합하여 동적 갱신해 줄 경로가 부재했기 때문에 발생했습니다.

## 3. 해결책
1. **로깅 초기화 명시**:
   - `main.py` 상단에 `logging.basicConfig(level=logging.INFO)` 설정을 명시적으로 추가하여 컨테이너 기동 시 `INFO` 이상 로그 출력을 정상 보장하도록 하였습니다.
2. **메모리 기반 구동상태 동적 오버라이드**:
   - `admin.py` 내부의 단순 boolean 형 플래그 `_is_running_flag`를 구체적 태스크 명을 저장하는 `_running_task: Optional[str]`로 변경했습니다.
   - `get_tasks_status` API에서 파일 리포트를 읽어 응답용 목록을 만들 때, 현재 `_running_task` 변수에 저장된 값(예: `"daily_routine"`)이 있다면, 리포트 목록 중 해당 태스크에 부합하는 가장 최신의 리포트 요소의 `"is_running"`을 `True`로, `"status"`를 `"RUNNING"`으로 즉시 덮어쓰도록 수정했습니다.

## 4. 검증 결과
- 수정 후 `logs/daily_routine.log` 파일에 SEC Master Sync 등 상세 INFO 수준 과정이 실시간으로 안정 적재됨을 확인했습니다.
- 백그라운드 수집 기동 중에 API 상태 조회 시 `is_running: true`와 `status: "running"`이 정확하게 반환되는 상태 동기화 기능을 최종 검증 완료했습니다.
