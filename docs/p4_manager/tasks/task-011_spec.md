# Task-011: 스케줄 환경 변수 통합 마이그레이션

> **Sub Project**: p4_manager (및 p2_kdms, p3_usdms, p1_shared 연동)
> **PRD 근거**: F-05 (스케줄 조회 및 수정)
> **작성일**: 2026-06-12
> **의존 Task**: T-010 (DB 물리 동기화 연동 및 감사 리포팅)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `.agents/skills/nf-task-spec-writer/references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| EnvDetector 및 로딩 방식 | `pjt_wiki/p1_shared_wiki/interfaces/env_detector.md` | ✅ 확인 |
| KDMS settings 관리 | `pjt_wiki/p2_kdms_wiki/interfaces/settings_config.md` | ✅ 확인 |
| KDMS 기동 라이프사이클 | `pjt_wiki/p2_kdms_wiki/interfaces/fastapi_lifespan.md` | ✅ 확인 |
| USDMS 헬스/스케줄 API | `pjt_wiki/p3_usdms_wiki/interfaces/health_admin_api.md` | ✅ 확인 |
| 스케줄 파싱 및 env 쓰기 유틸 | 위키 미기록 → `tdms_core/p1_shared/p1_shared/utils/`에 신규 구현 예정 | ⚠️ 직접 확인 및 신규 설계 |

---

## § 1. 목표

`.env` 파일에 정의된 `SCHEDULE_KDMS_*` 및 `SCHEDULE_USDMS_*` 스케줄 변수를 한국(`p2_kdms`) 및 미국(`p3_usdms`) 백엔드 스케줄러가 로드하여 동적으로 크론 작업을 등록하도록 외부화합니다. 또한, 통합 대시보드 UI나 API를 통해 스케줄 변경 시 메모리 상의 스케줄러(`reschedule_job`)와 마운트된 `.env` 파일의 텍스트가 동시에 실시간으로 업데이트 및 동기화되어 컨테이너 재기동 시에도 수정된 일정이 보존되도록 보장합니다.

**구현 범위:**
- **IN:**
  - `p1_shared` 내 공통 스케줄 문자열 파싱 헬퍼 및 `.env` 파일 업데이트 유틸리티 구현
  - `p2_kdms` 설정 모델(`config.py`)에 스케줄링 변수 추가 및 기동 시 동적 스케줄러 등록 마이그레이션
  - `p2_kdms` 스케줄 변경 API 개정을 통한 `.env` 물리적 파일 갱신 및 결합 동기화
  - `p3_usdms` 설정 모델 내 레거시 스케줄링 변수명 일원화 및 주간 유지보수 스케줄의 완전한 외부화
  - `p3_usdms` 스케줄 변경 API 개정을 통한 `.env` 물리적 파일 갱신 및 결합 동기화
- **OUT:**
  - 프론트엔드 UI 컴포넌트(`ScheduleView.vue` 등)의 신규 수정 (기존 F-05 UI 연동 규격 유지)
  - 새로운 배치 작업 태스크(daily, financial, backfill 외의 신규 태스크) 추가

---

## § 2. 구현 대상

### 신규 생성 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/schedule_utils.py` — 공통 스케줄 파싱 및 `.env` 파일 실시간 업데이트 유틸리티
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_schedule_utils.py` — 단위 및 격리 통합 테스트

### 수정 대상 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/config.py` — `Settings` 클래스에 `schedule_kdms_daily_update`, `schedule_kdms_financial_update`, `schedule_kdms_backfill_minute` 환경 변수 추가
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py` — 기동 시 `schedule_utils`를 이용해 크론 일정을 동적으로 파싱하여 APScheduler에 등록
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py` — 스케줄 변경 API(`reschedule_job`) 호출 시 스케줄러 변경과 함께 `.env` 내의 매핑된 설정 값 실시간 갱신 적용
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/config.py` — 레거시 `SCHEDULE_DAILY_ROUTINE` 변수명을 `SCHEDULE_USDMS_DAILY_ROUTINE`으로 마이그레이션하고, `SCHEDULE_USDMS_WEEKLY_MAINTENANCE` 환경 변수 추가
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/main.py` — 기동 시 `SCHEDULE_USDMS_DAILY_ROUTINE` 및 `SCHEDULE_USDMS_WEEKLY_MAINTENANCE` 설정을 파싱하여 동적으로 스케줄 등록
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/admin.py` — 스케줄 변경 API(`update_schedule`) 호출 시 스케줄러 변경과 함께 `.env` 파일 값 실시간 갱신 적용

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 3.1 공통 스케줄 파서 및 .env 쓰기 유틸리티 (`p1_shared`)

```python
# [출처: tdms_core/p1_shared/p1_shared/utils/schedule_utils.py — 신규 정의]
from typing import Tuple, Optional

def parse_schedule_string(schedule_str: str, default_days: Optional[str] = None) -> Tuple[int, int, Optional[str]]:
    """
    스케줄 설정 문자열([day_of_week:]HH:MM)을 파싱하여 hour, minute, day_of_week을 반환한다.
    
    Args:
        schedule_str: "17:10", "sat:14:00", "wed,sat:07:30" 등의 스케줄 포맷
        default_days: 요일 정보가 없을 경우 적용할 기본 요일 패턴 (예: "mon-fri")
        
    Returns:
        Tuple[hour, minute, day_of_week]
        
    Raises:
        ValueError: 파싱이 불가하거나 시간 형식이 잘못되었을 때 발생
    """
    ...

def update_env_value(variable_name: str, value: str) -> None:
    """
    바인드 마운트된 .env 파일의 변수 값을 물리적으로 덮어쓰고, os.environ 캐시를 동기화한다.
    inode 손실 방지를 위해 파일을 새로 생성하지 않고 덮어쓰기 방식으로 처리한다.
    
    Args:
        variable_name: .env 내의 타깃 변수명 (예: "SCHEDULE_KDMS_DAILY_UPDATE")
        value: 설정할 새로운 값 (예: "18:00" 또는 "sat:15:30")
    """
    ...
```

### 3.2 KDMS 설정 모델 추가 (`p2_kdms`)

```python
# [출처: tdms_core/p2_kdms/config.py — 수정 대상]
class Settings(BaseSettings):
    # (기존 설정 유지...)
    
    # Layer B — 공통 스케줄링 일정 추가
    schedule_kdms_daily_update: str = "17:10"
    schedule_kdms_financial_update: str = "sat:14:00"
    schedule_kdms_backfill_minute: str = "sat:16:00"
```

### 3.3 USDMS 설정 모델 추가 (`p3_usdms`)

```python
# [출처: tdms_core/p3_usdms/config.py — 수정 대상]
class Settings(BaseSettings):
    # (기존 설정 유지...)
    
    # 레거시 SCHEDULE_DAILY_ROUTINE 변수를 SCHEDULE_USDMS_DAILY_ROUTINE으로 일원화
    SCHEDULE_USDMS_DAILY_ROUTINE: str = "wed,sat:07:30"
    
    # 주간 백필 및 유지보수 스케줄 추가
    SCHEDULE_USDMS_WEEKLY_MAINTENANCE: str = "sat:09:00"
```

---

## § 3a. 기존 기능 보존 (수정 Task에만 작성)

### 보존 인터페이스
- `GET /api/v1/admin/tasks/scheduler` (`p2_kdms`) — 기존 UI 및 중계 API와 호환 유지
- `PUT /api/v1/admin/tasks/scheduler` (`p2_kdms` rescheduling) — 변경 불가, 파라미터 `job_id`, `hour`, `minute` 규격 유지
- `GET /api/admin/schedules` (`p3_usdms`) — 기존 UI 및 중계 API와 호환 유지
- `PUT /api/admin/schedules` (`p3_usdms` rescheduling) — 변경 불가, 파라미터 `job_id`, `hour`, `minute` 규격 유지

### 요일 정보 보존 결합 규칙
사용자가 시간을 변경할 때, 기존 변수값에 요일 접두사(예: `sat:`, `wed,sat:`)가 있었다면 요일 부분을 추출하여 새 시간과 결합한 뒤 `.env` 파일에 기록해야 합니다.
```python
# [Tier 1 — 단위]
def test_reschedule_combines_existing_day_prefix_with_new_time():
    """
    기존 스케줄이 'wed,sat:07:30' 일 때 hour=9, minute=0으로 변경 시,
    최종 .env 기록 값은 'wed,sat:09:00'이어야 함을 검증한다.
    """
    ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤, 모든 테스트가 통과하도록 구현하세요.

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위]
def test_parse_schedule_string_with_only_time():
    """
    [목적] 요일 정보가 없는 HH:MM 포맷 파싱 검증
    [유도] parse_schedule_string("17:10", "mon-fri") -> (17, 10, "mon-fri")
    """
    hour, minute, day_of_week = parse_schedule_string("17:10", default_days="mon-fri")
    assert hour == 17
    assert minute == 10
    assert day_of_week == "mon-fri"

# [Tier 1 — 단위]
def test_parse_schedule_string_with_day_prefix():
    """
    [목적] 요일 접두사가 존재하는 day_of_week:HH:MM 포맷 파싱 검증
    [유도] parse_schedule_string("sat:14:00") -> (14, 0, "sat")
    """
    hour, minute, day_of_week = parse_schedule_string("sat:14:00")
    assert hour == 14
    assert minute == 0
    assert day_of_week == "sat"

# [Tier 2 — 격리 통합]
def test_update_env_value_writes_correctly_and_refreshes_cache(tmp_path, mocker):
    """
    [목적] 지정된 환경 변수의 값이 .env 파일에 실시간 덮어쓰기되는지 검증
    """
    temp_env = tmp_path / ".env"
    temp_env.write_text("SCHEDULE_KDMS_DAILY_UPDATE=17:10\n", encoding="utf-8")
    
    # settings 또는 파일 경로 조작 모킹
    mocker.patch("p1_shared.utils.schedule_utils.ENV_FILE_PATH", str(temp_env))
    
    update_env_value("SCHEDULE_KDMS_DAILY_UPDATE", "18:00")
    
    updated_content = temp_env.read_text(encoding="utf-8")
    assert "SCHEDULE_KDMS_DAILY_UPDATE=18:00" in updated_content
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
def test_parse_schedule_string_boundary_values():
    """
    [목적] 시간과 분의 최대 경계값(23:59) 파싱 검증
    """
    hour, minute, day_of_week = parse_schedule_string("23:59")
    assert hour == 23
    assert minute == 59
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_parse_schedule_string_invalid_format_raises_value_error():
    """
    [목적] 올바르지 않은 스케줄 패턴 문자열 입력 시 ValueError 발생
    """
    import pytest
    with pytest.raises(ValueError):
        parse_schedule_string("invalid_format")
        
    with pytest.raises(ValueError):
        parse_schedule_string("25:00")  # 범위를 벗어난 시간
        
    with pytest.raises(ValueError):
        parse_schedule_string("12:60")  # 범위를 벗어난 분
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

@pytest.mark.integration
def test_scheduler_dynamic_loading_from_env():
    """
    [목적] 실제 .env 파일 환경 변수값을 활용해 스케줄러가 정상 등록되는지 통합 검증
    [실행 조건] pytest --run-integration
    """
    # 1. 환경변수 읽기 및 파싱
    daily_update_str = os.environ.get("SCHEDULE_KDMS_DAILY_UPDATE", "17:10")
    from p1_shared.utils.schedule_utils import parse_schedule_string
    h, m, days = parse_schedule_string(daily_update_str, default_days="mon-fri")
    
    # 2. 임시 스케줄러에 등록 시도
    scheduler = AsyncIOScheduler()
    job = scheduler.add_job(
        func=lambda: print("test"),
        trigger="cron",
        day_of_week=days,
        hour=h,
        minute=m,
        id="test_daily_job"
    )
    assert job is not None
    assert job.trigger is not None
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_parse_schedule_string_with_only_time` | Tier 1 | 정상 | 요일 없는 HH:MM 형식 파싱 |
| 2 | `test_parse_schedule_string_with_day_prefix` | Tier 1 | 정상 | 요일 접두사 포함 포맷 파싱 |
| 3 | `test_parse_schedule_string_boundary_values` | Tier 1 | 경계값 | 23:59 최대 범위 값 정상 파싱 검증 |
| 4 | `test_parse_schedule_string_invalid_format_raises_value_error` | Tier 1 | 예외 | 올바르지 않은 스케줄 규격 및 수치 입력 예외 처리 |
| 5 | `test_update_env_value_writes_correctly_and_refreshes_cache` | Tier 2 | 격리 통합 | .env 파일 실시간 물리적 갱신 및 환경 변수 동기화 |
| 6 | `test_reschedule_combines_existing_day_prefix_with_new_time` | Tier 1 | 회귀 | 기존 요일 설정을 유지한 채 시간만 업데이트하는 매칭 로직 검증 |
| 7 | `test_scheduler_dynamic_loading_from_env` | Tier 3 | 실제 통합 | .env의 중앙 스케줄 사양에 맞춰 APScheduler 등록 가동성 검증 |

**총 7개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

- **기술 스택**: 
  - Python 3.12 (p1_shared, p2_kdms, p3_usdms 공통)
  - `pydantic-settings` 2.x
  - `apscheduler` 3.x
- **위키 참조 링크**:
  - `pjt_wiki/p1_shared_wiki/environment.md`
  - `pjt_wiki/p2_kdms_wiki/interfaces/settings_config.md`
  - `pjt_wiki/p3_usdms_wiki/interfaces/health_admin_api.md`
- **주의사항**:
  - `p2_kdms`, `p3_usdms`, `p4_backend` 모두 동일한 로컬 파일인 `.env`를 공유하므로 컨테이너 내부의 `/app/.env`를 안전하게 덮어쓰기 방식으로 열어서 수정해야 합니다. (임시 파일을 새로 만든 후 `move` 하는 방식은 Docker의 바인드 마운트 Inode 소실 이슈를 유발할 수 있으므로 절대 지양합니다.)
  - 요일 포맷 파싱 시, 대소문자 변환(`lower()`) 및 공백 제거 처리를 포함하여 강건성(Robustness)을 확보해 주십시오.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] p2/p3 기존 유닛/통합 테스트 전체 통과 — 회귀 없음
- [ ] `docs/p4_manager/p4_manager_pjt_tasks.md`의 Task-011 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/task-011_walkthrough.md` 작성
