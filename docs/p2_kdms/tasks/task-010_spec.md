# Task-010: 수집 공백일 자동 감지 및 고효율 범위 백필 명세서

## 1. 개요
본 Task는 스케줄러 정지나 시스템 장애 등으로 인해 수일(예: 5일)간의 수집 공백이 발생했을 때, 비효율적인 날짜별 개별 루프 반복을 지양하고 **단 1회의 종목별 범위 API 호출(Pagination/Range)을 통해 누락된 전 기간의 일봉, 시가총액, 수정계수 및 분봉 데이터를 고효율로 일괄 수집 및 적재**하는 기능을 구현합니다.

---

## 2. 요구사항 및 주요 설계 변경 사항

### 2-1. 공백 영업일 감지 메커니즘 (`daily_task.py` 연계)
- **최종 적재일 조회**: `daily_ohlcv` 테이블에서 각 종목 또는 전체 기준 마지막으로 데이터가 정상 수집된 최근 날짜(`last_collected_date`)를 DB에서 조회합니다.
  - 쿼리 예시: `SELECT MAX(dt) FROM daily_ohlcv`
- **대상 기간 획득**: 기동 시점 기준 수집 목표일인 `target_date`(17:00 전후 기준 오늘/어제)를 도출합니다.
- **공백 영업일 검출**: `trading_calendar` 테이블에서 `opnd_yn = 'Y'`인 영업일 중 `[last_collected_date + 1일, target_date]` 범위에 해당하는 개장일 리스트를 조회합니다.
  - 만약 공백이 없다면 단일 `target_date`만 수집 대상으로 설정합니다.
  - 공백 영업일 목록이 존재한다면, 이의 최솟값(`start_date`)과 최댓값(`end_date`)을 범위 수집의 시작일과 종료일로 동적 결정합니다.

### 2-2. 일봉 수집 범위화 (`KisKrClient` 및 `DailyTask`)
- **API 범위 메서드 추가**: `KisKrClient.fetch_daily_ohlcv_range(stk_cd, start_date, end_date)`
  - FID_INPUT_DATE_1: `start_date`, FID_INPUT_DATE_2: `end_date`로 지정하여 KIS OpenAPI `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`를 1회 호출합니다.
  - `output2` 배열에서 `start_date <= dt <= end_date` 범위에 속하는 모든 거래일 OHLCV 목록을 수집하여 반환합니다.
- **일괄 벌크 UPSERT**: `DailyTask.run(start_date, end_date)`에서 반환된 일별 OHLCV 리스트를 `ohlcv_repo.upsert_daily_ohlcv()`를 통해 일괄 적재합니다.
- **시가총액 일괄 계산**: 수집된 기간의 일봉 종가에 상장주수를 곱해 날짜별 시가총액 레코드를 한 번에 빌드하고 `market_cap_repo.upsert_daily_market_cap()`으로 일괄 적재합니다.
- **수정계수 역산 및 물리 갱신**: 
  - `end_date`를 기점으로 과거 45일 범위의 raw와 adjusted 시세를 조회하여 수정계수(Factor)를 역산합니다. KIS API 범위 조회를 사용하므로 공백 기간 동안 발생한 분할/병합/증자 등의 이벤트가 단 1회의 범위 연산으로 모두 계산되어 반영됩니다.
  - 물리 수정주가 테이블(`daily_ohlcv_adjusted`) 갱신 또한 `[start_date - 30일, end_date]` 범위로 넓혀 일괄 적용합니다.

### 2-3. 분봉 수집 동적 Pagination 획득
- **키움 연속 수집**: `kiwoom_client.get_minute_chart(stk_cd, start_date=end_date, max_requests=N)`
  - 기준일(`end_date`)로부터 과거로 Pagination 조회를 수행하므로, 공백 영업일 수에 비례하여 `max_requests`를 동적으로 확대합니다.
  - 공식: `max_requests = max(1, (공백 영업일수 * 380) // 600 + 1)` (1일 380개 레코드, 1회 수집 시 약 600~900개 적재 안전 마진)
  - 반환된 전체 분봉 중 `start_date <= dt <= end_date` 범위에 들어오는 레코드만 필터링하여 일괄 `upsert_minute_ohlcv()`로 저장합니다.

---

## 3. TDD 테스트 시나리오
본 구현은 아래의 테스트 케이스를 통해 완벽히 작동함을 검증해야 합니다.

### 3-1. `test_range_based_daily_task_success`
- **시나리오**: 마지막 적재일이 5영업일 전이고, 공백 영업일이 5일 존재하는 가상 상황을 Mocking합니다.
- **검증**:
  1. `run_daily_update` 호출 시 `start_date`와 `end_date`가 정상적으로 5일 기간으로 자동 산출되는지 확인.
  2. KIS API 호출이 종목당 1회(`fetch_daily_ohlcv_range`)만 일어나며, 5일치의 일봉 데이터가 한 번에 적재되는지 검증.
  3. 시가총액 데이터도 5일치 일괄 적재되는지 확인.
  4. 수정계수 및 물리 수정주가 갱신 또한 정상 범위로 호출되는지 검증.

### 3-2. `test_range_based_minute_task_success`
- **시나리오**: 공백 영업일이 3일 존재하는 상황에서 분봉 수집을 테스트합니다.
- **검증**:
  1. `max_requests`가 동적으로 계산되어 `2` 이상으로 설정되어 기동되는지 확인.
  2. 수집된 다량의 분봉 데이터 중 3일의 범위에 매칭되는 데이터만 필터링되어 일괄 업서트되는지 검증.

---

## 4. 작업 파일 및 영향 범위
- **수정**:
  - [collectors/kis_kr_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/kis_kr_client.py): 범위 기반 일봉 조회 메서드 추가
  - [repositories/ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py): 최종 적재 영업일 조회 헬퍼 등 리포지토리 보강
  - [tasks/daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py): `DailyTask.run` 및 `run_daily_update` 리팩토링 및 분봉 범위 수집 지원
- **추가**:
  - [tests/test_range_backfill_t010.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_range_backfill_t010.py): T-010 관련 단위/통합 테스트
