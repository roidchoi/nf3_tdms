# [USDMS-ERR-006] 테스트 실행 시 실 DB 오염으로 인한 AAPL 수집 중단 장애

## 1. 개요 및 에러 현상
- **발생일**: 2026-07-09
- **심각도**: Critical
- **오류 요약**: 로컬 pytest 실행 시 `test_daily_routine_health_check_isolates_and_rolls_back_anomalies` 등의 모킹되지 않은 부분이 실제 개발 DB의 블랙리스트 테이블(`us_collection_blacklist`)에 차단 처리를 쓰면서, 실 수집기 실행 시 대표 종목인 AAPL (CIK: `0000320193`)에 대한 수집이 누락 및 중단되는 사태가 발생함.
- **오류 내용**:
  - 당초 AAPL의 수집이 `2026-06-29` 이후로 누락된 현상을 추적한 결과, DB 내 블랙리스트 테이블에 등록된 것을 인지함.
  - 가격 이상치 발생을 테스트하기 위해 생성한 Mock 데이터 셋의 이상치(100달러 -> 200달러 인위적 변경)가 `DailyRoutine` 테스트 도중 모킹되지 않은 `blacklist_mgr` 에 의해 실제 쓰기로 가동됨.

---

## 2. 발생 원인 분석
- `DailyRoutine` 생성자에서 내부적으로 `BlacklistManager`를 직접 초기화하고 있었음.
- 이로 인해 단위 테스트 환경(`pytest`)에서도 실제 DB 커넥션을 맺고 `record_failure`를 호출하여 테이블 데이터를 오염시켰음.
- 기존 DB 커넥션 풀(`DbConnectionPool`)에 테스트 환경을 감지하여 실 DB 접근을 차단하는 강력한 세이프가드(Safety Guard) 장치가 부재했음.

---

## 3. 해결 방안 및 후속 조치
- **의존성 주입 지원 리팩토링**:
  - `tdms_core/p3_usdms/tasks/daily_routine.py` 의 `DailyRoutine` 생성자를 수정하여 외부에서 `master_repo`, `blacklist_repo`, `blacklist_mgr` 등을 MagicMock이나 대체 인스턴스로 주입받을 수 있도록 수정.
  - `tdms_core/p3_usdms/tests/test_daily_routine.py` 에 존재하는 모든 테스트용 `DailyRoutine` 생성 부문에 Mock 객체들을 완벽히 주입하도록 갱신.
- **실 DB 연결 차단 세이프가드 추가**:
  - `tdms_core/p1_shared/p1_shared/db/connection.py` 의 `DbConnectionPool` 초기화 시, 환경 변수 `PYTEST_CURRENT_TEST` 또는 `sys.modules.get("pytest")`를 감지하도록 구현.
  - 명시적으로 `RUN_INTEGRATION_TESTS` 환경변수가 활성화되지 않은 일반 테스트 상태에서 실 DB(TimescaleDB) 접속을 감지할 시 `RuntimeError`를 내뱉어 차단하도록 하여, 추후 어떠한 테스트 실수로도 실 DB가 오염되지 않도록 구조적으로 격리.
- **데이터 백필 복구**:
  - AAPL 블랙리스트 해제 SQL 쿼리 수행.
  - 누락된 `2026-06-30` ~ `2026-07-08` 시세, 재무 metrics 및 valuation 데이터를 적재하는 고속 백필 스크립트를 작성하여 완벽하게 복원 완료.

---

## 4. 관련 코드 컨텍스트
- [daily_routine.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tasks/daily_routine.py)
- [test_daily_routine.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_daily_routine.py)
- [connection.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/db/connection.py)
