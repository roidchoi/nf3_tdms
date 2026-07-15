# KDMS 백필 누락 감지 및 API 호출 한도 계산 고도화 (dec-009)

## 1. 배경
* **중간 누락 감지 및 API 호출 깊이 한계**: 백필 기간 도중(예: 6월 중순) 단발성으로 누락 데이터가 발생했을 때, `max_requests` 산출에 사용되는 날짜 차이(`gap_days`)가 단순히 오늘 날짜 기준이 아닌 누락 시작일로부터의 실제 개장 영업일 수로 정밀하게 산출되어야 충분한 페이징 호출 횟수가 확보됨. 그렇지 않을 경우 조기 루프 탈출로 인해 과거 데이터 백필이 스킵되는 버그가 존재했음.
* **비현실적인 분봉 누락 감지 공식**: 기존 공식은 `min(360, 일봉거래량)`을 기대 건수로 산정하여, 거래량이 매우 적은 종목(하루 1~2건 거래 등)에 대해 거의 매일 누락으로 오감지하여 무의미한 API 재호출(전구간 재수집 수준)을 발생시키고 키움 API 한도를 조기 소진하는 문제가 있었음.

## 2. 기술적 해결 방안 및 구현 설계
1. **캘린더(trading_calendar) 기반 동적 API 호출 한도 계산**:
   * 누락 검출 시작일과 종료일 사이의 실제 개장 영업일 수를 데이터베이스의 `trading_calendar` 테이블에서 조회하여 `gap_days`를 도출.
   * `gap_days`에 따른 키움 API 페이징 요청 횟수(`max_requests`)를 영업일 수만큼 정확히 동적 산정함으로써 조기 루프 탈출 방지.
2. **분봉 누락 감지를 위한 하이브리드 필터링(Hybrid Filtering)**:
   * **하이브리드 공식**: 일봉 거래량 총합과 분봉의 일별 거래량 총합의 오차율이 5% 이상인 경우 또는 실제 개장일인데 분봉 데이터가 0건인 경우에만 누락일로 판정.
   * **장점**: 거래 횟수 자체가 적어 분봉 개수가 360개에 훨씬 못 미치는 저유동성 종목들이 누락으로 오감지되는 것을 완벽히 방지하여 API 쿼타 절약 및 백필 성능을 극적으로 개선함.

## 3. 관련 파일 및 구현 위치
* `[backfill_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py)`: `_execute_backfill_jobs`에서 `trading_calendar` 쿼리를 호출해 `gap_days`를 영업일 기준으로 보정하고 루프 카운트 동적 계산.
* `[ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py)`: `get_minute_ohlcv_gap_days` 내에 일봉/분봉 거래량 오차율 5% 비교 및 0건 누락 검출 하이브리드 쿼리 구현.
* `[test_backfill_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_backfill_task.py)`: 모의 영업일 조회 반환 모킹을 추가한 동적 요청 횟수 검증 단위 테스트 작성.
