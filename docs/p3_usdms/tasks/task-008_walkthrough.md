# T-008 리팩토링 및 미국 휴장 통합 Walkthrough

T-008 작업에서는 레거시 `DatabaseManager` 의존성을 완전히 청산하고, 수집 기준 임계치를 환경변수로 외부화했으며, 미국 주식시장 휴장 검출 및 `trading_calendar` 테이블의 자동 동기화 기능을 구현했습니다.

---

## 1. 구현 파일 목록 및 역할

| 파일 경로 | 변경 유형 | 역할 |
|---|---|---|
| [date_utils.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/date_utils.py) | **MODIFY** | 미국 공휴일(`holidays.US`) 및 주말을 판별하는 `is_us_trading_day`, `get_us_trading_days`, `last_us_trading_day` 신규 구현 |
| [config.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/config.py) | **MODIFY** | 진입/유지 기준(시가총액, 가격) 및 수집 기동 시각(`SCHEDULE_DAILY_ROUTINE`) 환경변수/Pydantic 필드 추가 |
| [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/main.py) | **MODIFY** | APScheduler 일계 기동 일정을 지정된 환경변수(`SCHEDULE_DAILY_ROUTINE`)를 파싱하여 `tue-sat` 스케줄로 동적 등록하도록 개선 |
| [master_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/master_repo.py) | **MODIFY** | `apply_targeting_rules()` 호출 시 파라미터가 없으면 `get_settings()`의 값으로 자동 Fallback 되도록 보완 |
| [master_sync.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/master_sync.py) | **MODIFY** | `_update_target_status()` 내의 하드코딩된 필터링 쿼리를 외부 설정 임계치 대입 및 안전한 `%s` 파라미터 바인딩으로 전면 수정 |
| [daily_routine.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tasks/daily_routine.py) | **MODIFY** | 일일 루틴 기동 시 `sync_trading_calendar()`를 먼저 수행하고, 수집 기준일(target_date)이 영업일이 아닌 경우 실행 스킵 처리 구현 |
| [db_manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/db_manager.py) | **DELETE** | 레거시 GOD NODE(임시 호환 shim) 영구 삭제 |
| [rebuild_all_valuations.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/ops/rebuild_all_valuations.py) | **DELETE** | 불필요해진 레거시 운영 스크립트 삭제 |
| [verify_data_integrity.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/ops/verify_data_integrity.py) | **DELETE** | 불필요해진 레거시 정밀 검증 스크립트 삭제 |

---

## 2. 설계상 주요 결정사항

1. **`is_us_trading_day` 통합 관리**:
   `p1_shared` 내의 공통 `date_utils.py`에 구현하여 다른 모듈에서도 통일되게 활용하도록 하였으며, `holidays` 패키지를 추가 의존성 없이 로드하도록 기존 설치 패키지를 재활용했습니다.
2. **`target_date` 파라미터 격리**:
   `DailyRoutine.run()` 호출 시 `target_date`를 수동 주입할 수 있게 하여 배치 스케줄러(KST 07:30에 전일 미국 장 마감 수집)뿐만 아니라 백필 상황에서도 과거 날짜 기준 안전한 격리 테스트가 가능하게 설계했습니다.
3. **`_detect_anomalies_and_quarantine` 안전화**:
   당일 이상치 검사 쿼리 내의 `CURRENT_DATE` 하드코딩을 제거하고 모두 파라미터화된 `%s` 바인딩(`target_date` 기반)으로 교체하여, 오염 데이터를 지우거나 탐지할 때 시스템 당일 시점 오인으로 인한 데이터 손실을 사전에 예방했습니다.

---

## 3. 테스트 및 검증 결과

* **단위 및 격리 통합 테스트(Tier 1 + 2)**: **총 53개 테스트 케이스 100% 통과(All Green)**
  ```bash
  tests/test_holiday_sync.py::test_is_us_trading_day_weekend_and_holidays PASSED
  tests/test_holiday_sync.py::test_daily_routine_skips_when_holiday PASSED
  tests/test_holiday_sync.py::test_daily_routine_syncs_trading_calendar PASSED
  tests/test_base_infra.py::test_config_loads_targeting_thresholds PASSED
  tests/test_base_infra.py::test_scheduler_daily_job_uses_configured_time PASSED
  tests/test_master_sync.py::test_master_sync_update_target_status_uses_settings_values PASSED
  tests/test_master_sync.py::test_master_repo_apply_targeting_rules_fallback_to_settings PASSED
  # 총 53 Passed
  ```

---

## 4. 후속 Task 진행 시 주의사항 (T-009 연동)

* **테스트 캐시**: `Settings` 클래스가 싱글톤 형태(`get_settings()`)로 동작하므로, 테스트 코드 상에서 환경변수를 mocking 할 때 캐시 영향이 미치지 않도록 `mocker.patch("p3_usdms.config._settings", None)` 구문을 필히 적용해야 합니다.
* **스케줄러 기동 요일**: KST 화요일~토요일(Tue-Sat) 아침 07:30에 동기화 스케줄이 정상 작동하는지 모니터링해야 합니다. KST 일요일 및 월요일 아침은 미국 장이 주말에 마감된 상태이므로 스킵 로그가 찍히게 됩니다.
