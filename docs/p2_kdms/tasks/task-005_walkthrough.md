# Task Walkthrough - T-005: 분봉 수집 (Kiwoom) 및 백필 모듈

본 문서는 T-005 (분봉 수집 및 백필 모듈 구현) 태스크에 대한 최종 작업 결과를 설명합니다. 

T-005에서는 `p1_shared`에 구축된 키움 API 인터페이스를 레퍼런스로 활용하여 P2 KDMS 환경에서 사용할 안정적이고 효율적인 분봉 데이터 연속 수집 파이프라인 및 백필 태스크를 구축하였습니다.

---

## 1. 주요 구현 내용

### 1) `collectors/kiwoom_client.py` [NEW]
* `p1_shared.api.kiwoom_api_core.KiwoomApiCore`를 확장 및 상속하여 구현되었습니다.
* 키움 OpenAPI 분봉 시세 조회 TR인 `ka10080` 규격에 맞춰 제작되었습니다.
* **연속 조회(페이지네이션)**: 응답 헤더의 `cont-yn` 및 `next-key`를 활용하여 종료 날짜/시간 또는 목표한 날짜 범위에 도달할 때까지 연속으로 요청합니다.
* **Rate Limiting**: 키움 OpenAPI 호출 제한을 엄격히 준수하기 위해 호출 간 `0.2초` 딜레이를 내장하고 있습니다.

### 2) `collectors/target_selector.py` [NEW]
* 직전 분기 평균 거래대금(`close * volume`)을 계산하여 상위 N개(기본 200개)의 종목 코드를 추출합니다.
* 선정된 타겟 종목 정보를 `minute_target_history` 테이블에 적재(`save_target_stocks`)하는 인터페이스를 구현했습니다.
* **이중 안전장치**: 데이터베이스 쿼리(`LIMIT`)와 Python 슬라이싱 처리를 모두 수행해 요청된 `top_n` 크기 이하로 결과를 반환합니다.

### 3) `tasks/backfill_task.py` [NEW]
* `trading_calendar` 테이블과 `minute_ohlcv` 테이블의 실제 수집량을 비교하여, 하루 누적 360분 미만인 날을 '완전/일부 누락일'로 탐지합니다.
* 탐지된 누락 정보 중 각 종목별 '가장 이른 공백일'을 기점으로 API 수집을 시작하도록 조율합니다.
* API 호출 결과를 파싱한 뒤 누락일에 해당하는 레코드만 필터링하여 `psycopg2` `execute_values`를 통해 대량 UPSERT를 보장합니다.
* **진척도 로깅 및 남은 시간(ETA) 계산**: 수집 과정에서 실시간 ETA 및 처리 속도(`it/s`)를 로깅하며, 공유 딕셔너리(`job_statuses`)를 실시간으로 업데이트합니다.
* **[설계 반영]**: 시가총액 갭 복구 로직은 T-006의 시가총액 일일 수집 및 스케줄러 기능과 강하게 결합되어 있으므로, 사용자 지시 사항에 따라 T-006 범위로 온전히 이관하였습니다.

### 4) `collectors/utils.py` [MODIFY]
* `DATA_MAPPER`에 `'kiwoom'` 데이터 구조(`minute_ohlcv`, `stock_info`)를 추가하여 중앙화된 데이터 매핑 체계를 확장했습니다.
* `transform_data` 함수 내부에 분봉 날짜시간(`cntr_tm`) 포맷 파싱 분기를 확장해 날짜시간 타입 객체 변환을 안전하게 처리하도록 보완했습니다.

---

## 2. 테스트 및 검증 결과

T-005는 TDD 원칙에 따라 작성된 전용 테스트 스위트를 포함하여 KDMS의 모든 기존 테스트 스위트와 함께 100% 통과(All Green)를 확인했습니다.

### 1) 신규 작성 테스트 (`tests/test_backfill_task.py`)
* `test_kiwoom_client_fetch_minute_chart_returns_normalized_records`: 키움 API 연속 조회 및 정규화 레코드 검증
* `test_target_selector_selects_top_n_by_volume`: 평균 거래대금 기준 상위 N개 종목 추출 검증
* `test_kiwoom_client_handles_api_exception_safely`: API 예외 발생 시 안전 격리 및 빈 리스트 반환 검증
* `test_backfill_task_skips_when_no_missing_days`: 누락 데이터가 이미 가득 찬 경우 수집 스킵 및 완료 상태 업데이트 검증

### 2) 테스트 실행 결과
```bash
$ PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms:tdms_core conda run -n tdms_p2_env pytest tdms_core/p2_kdms/tests/
====================================== test session starts ======================================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1
collected 50 items

tdms_core/p2_kdms/tests/test_backfill_task.py ....                                         [  8%]
tdms_core/p2_kdms/tests/test_base_repository.py .........                                  [ 26%]
tdms_core/p2_kdms/tests/test_daily_task.py ....                                            [ 34%]
tdms_core/p2_kdms/tests/test_factor_calculator.py ...                                      [ 40%]
tdms_core/p2_kdms/tests/test_factor_endpoints.py ...                                       [ 46%]
tdms_core/p2_kdms/tests/test_factor_repo.py ...                                            [ 52%]
tdms_core/p2_kdms/tests/test_financial_endpoints.py ...                                    [ 58%]
tdms_core/p2_kdms/tests/test_financial_repo.py .....                                       [ 68%]
tdms_core/p2_kdms/tests/test_financial_task.py ....                                        [ 76%]
tdms_core/p2_kdms/tests/test_kis_kr_client.py ....                                         [ 84%]
tdms_core/p2_kdms/tests/test_master_repo.py ...                                            [ 90%]
tdms_core/p2_kdms/tests/test_ohlcv_repo.py ....                                            [ 98%]
tdms_core/p2_kdms/tests/test_ohlcv_repo_adjusted.py .                                      [100%]

======================================= 50 passed in 1.58s ======================================
```
50개 테스트 전체가 성공적으로 패스하였으며, 신규 구현으로 인한 기존 기능의 사이드 이펙트는 감지되지 않았습니다.

---

## 3. 향후 과제

* **T-006 연동**: pykrx 라이브러리를 활용한 시가총액 데이터 수집기 구현 및 2025년 11월 이전부터 현재까지의 시총 갭 복구 로직 구현 예정.
* **스케줄러 통합**: `AsyncIOScheduler`를 구성하여 매일 실행되는 일일 데이터 업데이트, 재무 데이터 수집 및 분봉 백필 태스크의 통합 스케줄링 구축 완료 예정.
