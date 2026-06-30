# T-011 스케줄링 변수 중앙화 및 API 개정 결과 워크스루

## 1. 구현 내용 개요
본 작업은 소스코드 내에 분산되고 하드코딩되어 있던 크론 스케줄링 설정을 `.env` 환경 변수로 외부화하고, 스케줄 변경 시 이를 실시간으로 반영하여 동적으로 갱신될 수 있도록 전반적으로 설계를 개정하는 작업입니다.

- **공통 유틸리티 모듈 신설**: `p1_shared` 내 `schedule_utils.py`를 신설하여 크론 설정 문자열(`[day_of_week:]HH:MM`) 파싱 및 `.env` 파일과 `os.environ` 캐시를 실시간 동기화하는 함수(`parse_schedule_string`, `update_env_value`)를 구현했습니다.
  - 특히 프론트엔드가 요일 정보 없이 시간만 변경해 요청하더라도, 기존에 `.env`에 정의되어 있던 요일 정보 접두사(예: `wed,sat:`)가 유실되지 않도록 보존 결합 메커니즘을 내장시켰습니다.
  - Docker 컨테이너 간 마운트된 `.env` 파일의 Inode가 훼손되지 않도록 `open(..., 'w')` 기반의 파일 쓰기 스트림 기술자 방식을 적용했습니다.
- **KDMS 스케줄링 개정**: `p2_kdms`의 `Settings` 클래스에 스케줄 설정들을 추가하고, `main.py` 기동 시와 `routers/admin.py`에서 실행 시간을 변경하는 `reschedule_job` API 호출 시 공통 유틸리티를 활용하여 환경변수 파일과 메모리 스케줄러를 동시 갱신하도록 수정했습니다.
- **USDMS 스케줄링 개정**: `p3_usdms`의 `Settings` 클래스를 리팩토링하여 중앙 설정 변수명(`SCHEDULE_USDMS_DAILY_ROUTINE`, `SCHEDULE_USDMS_WEEKLY_MAINTENANCE`)으로 일원화하고, `main.py` 기동 시와 `routers/admin.py`의 `update_schedule` API 변경 시 동적 로드 및 보존 처리를 통합했습니다.
- **테스트 케이스 개선**: 신규 유틸리티의 단위 테스트 및 USDMS, p4_manager의 관련 테스트 코드를 업데이트하여 바뀐 경로 및 변수 사양을 맞췄습니다.

---

## 2. 변경된 파일 목록 및 상세 내용

### [p1_shared](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared)

#### [NEW] [schedule_utils.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/schedule_utils.py)
- `parse_schedule_string(schedule_str, default_days)`: 요일 접두사 분리 및 시/분 파싱
- `update_env_value(variable_name, value)`: 기존 요일 정보가 존재할 경우 보존 병합하는 기능 구현. 안전한 물리 파일 쓰기 및 캐시 동기화 보장

#### [MODIFY] [__init__.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/__init__.py)
- 새로 신설한 `parse_schedule_string`, `update_env_value` 함수를 패키지 레벨에서 참조할 수 있도록 노출

#### [NEW] [test_schedule_utils.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_schedule_utils.py)
- 6개의 단위 테스트(파싱, 경계값, 올바르지 않은 포맷 처리, 파일 쓰기 및 캐시 동기화 검증, 요일 접두사 보존 결합 테스트)를 수록하여 검증 완료

---

### [p2_kdms](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms)

#### [MODIFY] [config.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/config.py)
- Settings 클래스에 `schedule_kdms_daily_update`, `schedule_kdms_financial_update`, `schedule_kdms_backfill_minute` 변수 추가

#### [MODIFY] [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py)
- 하드코딩되었던 스케줄링 등록 부분을 config에서 읽어 parse_schedule_string을 거친 뒤 scheduler에 추가하도록 변경
- 등록 실패 예외 발생 시 하드코딩된 디폴트 값으로 예외 격리(Fallback) 보장

#### [MODIFY] [routers/admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py)
- `reschedule_job` API 호출 시 `.env` 동기화 및 메모리 스케줄러 동적 재구성 반영

---

### [p3_usdms](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms)

#### [MODIFY] [config.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/config.py)
- `SCHEDULE_DAILY_ROUTINE` 변수를 중앙화에 맞추어 `SCHEDULE_USDMS_DAILY_ROUTINE`으로 이름 변경 및 기본값 수정
- 주간 백필용 `SCHEDULE_USDMS_WEEKLY_MAINTENANCE` 변수 신설

#### [MODIFY] [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/main.py)
- 일일 수집 및 주간 유지관리 작업을 설정에서 읽어 동적 구성하도록 수정. 마찬가지로 Fallback 메커니즘 제공

#### [MODIFY] [routers/admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/admin.py)
- `update_schedule` API 변경 시 `.env` 파일과 메모리 스케줄러를 함께 동적 업데이트하도록 리팩토링

#### [MODIFY] [tests/test_base_infra.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_base_infra.py)
- 변경된 설정 변수명에 대응해 테스트 코드 수정

---

### [p4_manager](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager)

#### [MODIFY] [tests/test_scheduler_bridge.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_scheduler_bridge.py)
- KDMS의 어드민 API 라우터 경로 개정에 맞추어 `respx` 모킹 대상 경로를 `/api/v1/admin/tasks/scheduler` 로 정정

---

## 3. 테스트 및 검증 결과

### 1) p1_shared 단위 테스트 통과 (pytest)
```bash
conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/test_schedule_utils.py -v
```
- **결과**: `6 passed`

### 2) p2_kdms 전체 테스트 통과 (pytest)
```bash
conda run -n tdms_p2_env python -m pytest tests/ -v -m "not integration"
```
- **결과**: `98 passed` (기존의 모든 회귀 방어 테스트가 안전하게 동작함을 검증)

### 3) p3_usdms 전체 테스트 통과 (pytest)
```bash
conda run -n tdms_p3_env python -m pytest tests/ -v -m "not integration"
```
- **결과**: `54 passed` (새로운 스케줄 동적 주입 및 환경 검증 모두 통과)

### 4) p4_manager 전체 테스트 통과 (pytest)
```bash
conda run -n tdms_p4_env python -m pytest tdms_core/p4_manager/tests/ -v
```
- **결과**: `59 passed` (라우트 모크 변경 사항 반영 후 전체 그린 확인)
