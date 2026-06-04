# Walkthrough - USDMS Data Querying REST API Completion (T-006)

T-006 데이터 조회 REST API 7종 전면 개편 및 리포지토리 확장을 성공적으로 완료하였습니다. 단위/모의 통합 테스트(Tier 1 + Tier 2) 및 실제 로컬 데이터베이스 연동 테스트(Tier 3)를 수행하여 대용량 API 성능 Throttling, 온더플라이 수정주가 변환 정합성, Point-in-Time 재무 필터링, 그리고 SQL Injection 방어 및 Apache Arrow IPC 바이너리 스트리밍을 정밀 검증하였습니다.

---

## 구현 파일 목록 및 역할

1. **[base.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/base.py)**:
   - `BaseRepository.__init__`에 optional하게 `pool` 객체를 주입받을 수 있도록 생성자 시그니처 확장.
   - 테스트 환경에서 mock connection pool 또는 실제 DB pool 피스처를 유연하게 바인딩할 수 있도록 유연성 제공.

2. **[master_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/master_repo.py)**:
   - 필터 조건(`exchange`, `is_collect_target`)을 동적으로 적용하여 active=True인 티커 목록을 가져오는 `get_tickers_filtered` 메서드 구현.

3. **[financial_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/financial_repo.py)**:
   - 특정 CIK의 표준 재무제표에 대한 공시일 기준 범위 조회(`get_standard_financials_range`) 및 Look-ahead bias가 제거된 Point-in-Time 조회(`get_standard_financials_pit`) 구현.

4. **[valuation_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/valuation_repo.py)**:
   - 일별 가치평가 데이터 범위 조회를 위한 `get_valuations` 및 분기별 재무비율 범위 조회를 위한 `get_metrics` 구현.

5. **[requirements.txt](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/requirements.txt)**:
   - Apache Arrow IPC 스트리밍 인코딩 지원을 위한 `pyarrow>=15.0.0` 패키지 추가.

6. **[routers/data.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/data.py)**:
   - 7종 조회 엔드포인트 구현 핵심 라우터.
   - `_format_response_arrow_or_json` 헬퍼를 탑재하여 `Accept: application/vnd.apache.arrow.stream` 헤더 존재 시 Apache Arrow Stream IPC 바이너리로 즉시 반환.
   - 날짜 범위 미지정 시 최근 1년 강제 부여 및 15년 초과 범위 요청 시 `400 Bad Request` Throttling 예외 처리.
   - `preview/{table}` 엔드포인트에서 10종 화이트리스트 테이블 검증 및 바인딩 파라미터 적용으로 SQL Injection 완전 방어 및 limit=1000 Cap 적용.

7. **[test_data_router.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_data_router.py)**:
   - 단위/모킹 통합 테스트 9개(필터링, 온더플라이 보정 정합성, PIT 분기, Throttling 차단, Arrow 스트림 복원 등) 구축.
   - 실제 로컬 데이터베이스와 통신하여 7개 엔드포인트 결과의 통신 성공과 데이터 정규화 포맷을 검증하는 Tier 3 통합 테스트 1개 구축.

---

## 주요 설계 및 기술적 결정

* **온더플라이(On-the-fly) 역순 누적곱 수정주가 보정전략**:
  - 데이터베이스의 물리적 일봉 시세를 건드리지 않고, 호출 시점에 `PriceRepo`에 누적된 수정계수 이력을 로드해 **역순 단일 루프($O(N + M)$) 연산**으로 open/high/low/cls 가격을 일괄 보정합니다.
  - Ex-Date 당일 및 이후 주가는 원본을 유지하고, 그 이전 주가들에 대해서만 누적수정계수 곱 연산을 완벽히 누적 적용합니다.
* **Point-in-Time (PIT)을 통한 Look-ahead Bias 방지**:
  - `as_of` 일자 이전의 공시일(`filed_dt <= as_of`) 기준 데이터로 범위를 강제하고, 동일 `report_period` 내에서 가장 최신의 수정 공시본만 `DISTINCT ON (report_period)`를 통해 필터링함으로써 미래 시점의 정보가 미리 활용되는 Look-ahead bias를 근절하였습니다.
* **Apache Arrow IPC 스트리밍 인코딩**:
  - 대용량 데이터 전송 시 JSON의 문자열 변환 및 파싱 오버헤드를 줄이기 위해, 요청 헤더를 판별하여 `pyarrow` 기반 스트리밍 바이너리 인코딩을 지원합니다. CPU 연산 및 대역폭 전송 효율을 향상시켰습니다.
* **테이블 미리보기 SQL Injection 보안 필터링**:
  - 화이트리스트 테이블 10종(`ALLOWED_TABLES`)에 포함되지 않은 경우 `400 Bad Request` 에러를 냅니다.
  - 테이블 동적 바인딩을 제외한 검색 조건(`stk_cd`, `start_date`, `end_date`, `limit`, `offset`)은 전부 바인딩 파라미터(`%s`)로 대입하여 SQL Injection 위험을 제거하였습니다.

---

## 테스트 결과 요약

* **Tier 1 & 2 (단위/모킹 통합 테스트)**:
  - `test_get_tickers_with_filters`: **PASSED**
  - `test_get_daily_prices_raw_returns_original`: **PASSED**
  - `test_get_daily_prices_adjusted_performs_on_the_fly_calculation`: **PASSED**
  - `test_get_financials_with_pit_enabled`: **PASSED**
  - `test_get_preview_limits_maximum_records`: **PASSED**
  - `test_get_preview_forbidden_table_returns_400`: **PASSED**
  - `test_get_preview_with_empty_date_column_skips_where_date_clause`: **PASSED**
  - `test_get_daily_prices_default_range_throttling`: **PASSED**
  - `test_get_daily_prices_arrow_serialization`: **PASSED**
* **Tier 3 (실 DB 통합 테스트)**:
  - `test_api_endpoints_e2e_with_real_db`: **PASSED** (7종 REST API 엔드포인트가 실제 PostgreSQL DB에 연결되어 100% 무사 통과)
