# T-010 수집 공백일 자동 감지 및 고효율 범위 백필 Walkthrough

T-010 Task에서는 스케줄러 정지 등의 이유로 며칠간 수집 누락(공백 영업일)이 발생했을 때, 비효율적으로 하루 단위 루프를 돌며 개별 수집 API를 반복 실행하는 대신, **1회 호출로 공백 기간 전체의 일봉 및 시가총액을 일괄 수집/계산/적재**하고 **분봉 수집 시에도 공백 영업일에 비례하여 max_requests를 동적 스케일링**하는 고성능 자동 백필 파이프라인을 성공적으로 구현 및 검증 완료하였습니다.

## 1. 구현 내용 요약

### 1-1. 영업일 공백 탐지 헬퍼 구현 (`ohlcv_repo.py`)
- **`get_last_collected_date()`**: 데이터베이스 내 `daily_ohlcv` 테이블을 조회하여 전체 종목 통틀어 최종 수집된 최종 영업일(`date`)을 찾아 반환합니다.
- **`get_trading_days_count(start, end)`**: `trading_calendar` 테이블을 기반으로 지정한 두 날짜 사이에 실제로 한국 시장이 개장한 개장 영업일(opnd_yn='Y')의 총 개수를 반환합니다.
- **`get_open_trading_days(start, end)`**: 공백의 구체적인 날짜 범위를 파악하기 위해 두 날짜 사이 개장 영업일(`date` 목록)을 오름차순 리스트로 반환합니다.

### 1-2. KIS API 단일/범위 분기 및 일괄 수집 구현 (`kis_kr_client.py`)
- KIS 일봉 차트 조회 엔드포인트 `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` 가 시작일(`FID_INPUT_DATE_1`)과 종료일(`FID_INPUT_DATE_2`)을 통한 범위 조회를 완벽히 지원하므로, 단 1회 API 호출로 여러 영업일 데이터를 배열 형태로 가져오는 `fetch_daily_ohlcv_range(stk_cd, start_date, end_date)` 메서드를 추가했습니다.
- 이를 통해 네트워크 오버헤드를 1/N로 절감하고 수집 속도를 극대화했습니다.

### 1-3. 일일 수집 스케줄러 진입점 및 범위 처리 고도화 (`daily_task.py`)
- **수집 범위 동적 산출**:
  - `run_daily_update` 함수 구동 시 DB 상 최종 수집 영업일(`last_collected_date`)과 17시 기준 오늘 혹은 어제에 해당하는 최종 수집 목표일(`target_date`)을 식별합니다.
  - 이 두 날짜 사이의 개장 영업일 목록(`open_days`)을 추출하여 `start_date = min(open_days)`, `end_date = max(open_days)`로 정의해 범위 수집을 기동합니다.
  - 만약 공백이 없다면 기존처럼 안전하게 단일 날짜로 호출되어 불필요한 중복 수집 및 오버헤드를 원천 차단합니다.
- **벌크 연산 및 대량 적재**:
  - `DailyTask.run`이 `end_date`를 추가 수용하는 범위 구조로 확장되었습니다.
  - KIS 일봉 시세를 일괄적으로 `upsert_daily_ohlcv(ohlcv_list)`에 벌크로 입력합니다.
  - 수집 범위 내 여러 날짜에 걸쳐 각 영업일별 시가총액을 다중 빌드하여 `upsert_daily_market_cap`으로 일괄 upsert 합니다.
  - 수정주가 물리 테이블인 `daily_ohlcv_adjusted` 의 데이터 정합성을 일괄 보정하기 위해 `refresh_adjusted_ohlcv_batch(start_update_dt, end_date, 'KIS')` 를 호출하여 공백 전체 범위에 걸쳐 벌크 갱신하도록 최적화했습니다.
- **키움 분봉 수집 동적 Pagination**:
  - 키움 분봉 연속 조회 API(`get_minute_chart`)는 최신 기준일(`end_date`)로부터 과거로 연속 조회하는 구조입니다.
  - 공백 영업일 수(`trading_days`)를 토대로 `max_requests = max(1, (trading_days * 380) // 600 + 1)` 공식을 연산해 Pagination 횟수를 동적으로 확대 연장합니다.
  - 확보된 전체 분봉 중 `[start_date, end_date]` 범위에 해당하는 분봉들만 정밀 필터링한 후 `upsert_minute_ohlcv` 로 일괄 벌크 적재하여 외부 날짜 침범 및 중복 API 호출을 방지합니다.

### 1-4. 기존 모의 환경과의 완벽한 하위 호환성 (Backward Compatibility)
- 기존 테스트 및 구 버전 스크립트들이 `task.run(target_date)` 형태로 단일 날짜 매개변수를 넘기거나, 키워드 인자 `task.run(target_date=...)` 로 호출하고, `kis_client.fetch_daily_ohlcv` 를 모킹하고 있는 호환성을 지원하기 위해 `DailyTask.run` 의 첫 번째 인자명을 `target_date` 로 유지하고 `end_date` 를 Optional 처리하였습니다.
- 단일 날짜 호출 시에는 `fetch_daily_ohlcv_range` 대신 기존의 `fetch_daily_ohlcv` API를 호출하도록 분기 처리하여, 기존 95개 테스트 케이스의 동작과 파이프라인의 안전성을 100% 보존하였습니다.

---

## 2. 테스트 검증 결과

기존 테스트 스위트의 회귀(Regression) 방지와 신규 T-010 백필 범위 동작 검증을 위해 단위/시나리오 테스트를 실행하여, **총 98개의 모든 테스트가 통과(All Green)**함을 확인하였습니다.

```bash
$ PYTHONPATH=.:.. conda run -n tdms_p2_env pytest tests/
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 98 items

tests/test_backfill_task.py ....                                         [  4%]
tests/test_base_repository.py .........                                  [ 13%]
tests/test_blacklist.py ...                                              [ 16%]
tests/test_daily_task.py ......                                          [ 22%]
tests/test_data_api_t007.py .....................                        [ 43%]
tests/test_factor_calculator.py ...                                      [ 46%]
tests/test_factor_endpoints.py ...                                       [ 50%]
tests/test_factor_repo.py ...                                            [ 53%]
tests/test_financial_endpoints.py ...                                    [ 56%]
tests/test_financial_repo.py .....                                       [ 61%]
tests/test_financial_task.py ....                                        [ 65%]
tests/test_health_t008.py .........                                      [ 74%]
tests/test_kis_kr_client.py ....                                         [ 78%]
tests/test_logs_ws_t008.py .                                             [ 79%]
tests/test_market_cap_scheduler.py .........                             [ 88%]
tests/test_master_repo.py ...                                            [ 91%]
tests/test_ohlcv_repo.py ....                                            [ 95%]
tests/test_ohlcv_repo_adjusted.py .                                      [ 96%]
tests/test_range_backfill_t010.py ...                                    [100%]

============================== 98 passed in 2.78s ==============================
```

### 2-1. T-010 신규 시나리오 테스트 내역 (`tests/test_range_backfill_t010.py`)
1. **`test_range_based_daily_task_success`**: 공백 5일 발생 시 KIS 범위 API를 단 1회 호출하고, 5일간의 일봉, 시가총액을 일괄 계산하여 벌크 업서트하고 물리 수정주가 테이블을 해당 공백 기간에 대응하여 1회에 갱신하는 범위 백필 로직 검증 성공.
2. **`test_range_based_minute_task_success`**: 공백 3일 발생 시 동적으로 계산된 `max_requests = 2` 파라미터를 넘겨 키움 API를 호출하고, 수집된 분봉 중 3일의 개장 범위에 속하는 데이터만 정교하게 필터링하여 일괄 적재하는 로직 검증 성공.
3. **`test_run_daily_update_calculates_correct_dates_with_gaps`**: 장 스케줄러 배치 구동 시 DB 상 최종 수집일과 현재 실행 시점(17시 기준 종료)을 바탕으로 수집 범위 `start_date` 와 `end_date` 를 동적으로 오차 없이 정확히 산정하는 검증 성공.

---

## 3. 관련 파일 링크

- **구현 소스**:
  - [repositories/ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py)
  - [collectors/kis_kr_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/kis_kr_client.py)
  - [tasks/daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py)
- **테스트 소스**:
  - [tests/test_range_backfill_t010.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_range_backfill_t010.py)
