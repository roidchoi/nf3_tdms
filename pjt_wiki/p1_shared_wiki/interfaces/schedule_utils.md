# Schedule Utils Interface (공통 스케줄링 유틸리티)

`schedule_utils.py`는 TDMS 내에서 사용되는 각 스케줄 관리 변수들을 파싱하고, 스케줄을 재조정(Reschedule)할 때 설정 변수 값들을 `.env` 환경 변수 파일에 실시간 갱신 및 유지하는 공통 유틸리티 모듈입니다.

- **파일 위치**: `tdms_core/p1_shared/p1_shared/utils/schedule_utils.py`
- **단위 테스트**: `tdms_core/p1_shared/tests/test_schedule_utils.py`

---

## 1. 주요 함수 시그니처

### `parse_schedule_string`
```python
def parse_schedule_string(schedule_str: str, default_days: Optional[str] = None) -> Tuple[int, int, Optional[str]]:
```
- **역할**: 스케줄 설정 문자열(`[day_of_week:]HH:MM`)을 파싱하여 `hour`, `minute`, `day_of_week` 튜플을 반환합니다.
- **파라미터**:
  - `schedule_str`: `"17:10"`, `"sat:14:00"`, `"wed,sat:07:30"` 등
  - `default_days`: 요일 접두사가 없는 경우 적용할 기본 요일값 (예: `"mon-fri"`)
- **반환값**: `(hour, minute, day_of_week)`
- **예외**: 시간 범위(0~23) 및 분 범위(0~59) 초과 시, 또는 형식 불일치 시 `ValueError` 발생

---

### `update_env_value`
```python
def update_env_value(variable_name: str, value: str) -> None:
```
- **역할**: 지정된 `.env` 환경 변수의 값을 실시간으로 물리 업데이트(덮어쓰기)하고, `os.environ` 환경 변수 캐시를 동기화합니다.
- **파라미터**:
  - `variable_name`: 업데이트할 타깃 변수명 (예: `"SCHEDULE_KDMS_DAILY_UPDATE"`)
  - `value`: 새롭게 설정할 시간 혹은 스케줄 패턴 (예: `"18:00"`)
- **요일 접두사 보존 결합 규칙**:
  - 만약 기존 `.env`에 정의된 값이 요일 정보를 포함하고 있고(예: `"wed,sat:07:30"`), 신규 `value`가 요일 정보가 없는 시간 값(예: `"09:00"`)이라면, 기존의 요일 정보 접두사(`"wed,sat"`)를 자동으로 추출하여 새 시간과 병합한 최종 문자열(`"wed,sat:09:00"`)로 환경 변수에 기록합니다.
  - 이를 통해 API 단에서 시간만 변경해서 전달받더라도 기존 배치의 요일 설정이 파괴되지 않고 정상 보존됩니다.
- **Inode 손상 방지**:
  - Docker 바인드 마운트 파일의 Inode 유실을 방지하기 위해, 임시 파일 복사 후 덮어쓰기가 아닌 물리 쓰기 스트림 스트레이트 쓰기(`open(..., 'w')`)로 구현되었습니다.
