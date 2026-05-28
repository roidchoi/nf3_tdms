# Task-005: 분봉 수집 (Kiwoom) 및 백필 명세서

본 문서는 Kiwoom OpenAPI를 활용한 대상 종목의 분봉(1분봉) 데이터 수집 클라이언트 구현, 직전 분기 평균 거래대금 기준 Target 선정 모듈 개발, 그리고 백그라운드 분봉 백필 파이프라인의 설계 및 테스트 명세를 다룹니다.

시가총액 데이터 수집 및 갭 복구(2025년 11월 이전부터 현재까지)는 시가총액 수집 기능(T-006)과 밀접하게 연계되어 있어 이번 T-005의 구현 범위에서 제외하며, T-006에서 통합 구현하도록 설계합니다.

---

## 1. 요구사항 및 스콥 (Scope)

### IN Scope
1. **Kiwoom OpenAPI Client (`collectors/kiwoom_client.py`)**
   - `p1_shared.api.kiwoom_api_core.KiwoomApiCore`를 기반으로 작동하는 `KiwoomClient` 구현.
   - 분봉 차트 조회 API(TR `ka10080`) 호출 및 `cont-yn` / `next-key`를 활용한 페이지네이션 수집 구현.
2. **Target Selector (`collectors/target_selector.py`)**
   - 직전 분기 평균 거래대금(`종가 * 거래량`) 기준 상위 N개(기본값 200개) 종목을 선정하는 로직 개발.
   - 선정된 종목 리스트를 `minute_target_history` 테이블에 기록 및 관리하는 인터페이스 제공.
3. **Backfill Task Pipeline (`tasks/backfill_task.py`)**
   - 영업일 캘린더(`trading_calendar`)와 실제 분봉 수집 수량을 대조하여 '완전/일부 누락일' 탐지 (일별 360분/건 미만 대상).
   - 종목별 '가장 이른 공백일'을 기준으로 Kiwoom API를 호출하여 누락 영역 데이터만 필터링한 뒤 `minute_ohlcv`에 일괄 UPSERT.
   - `job_statuses` 딕셔너리를 활용한 진척도 로깅 (Phase 명칭, 진행률 %, it/s, ETA, 성공/실패 여부).

### OUT Scope
- 시가총액 수집 및 누락일 갭 복구 (2025년 11월 이전 포함 전체) -> **[T-006 구현 범위]**
- KIS 실시간 시세 처리 (T-002 및 T-003 범위)
- FastAPI APScheduler 통합 및 스케줄러 등록 (T-006 범위)

---

## 2. 데이터베이스 및 통신 스펙

### 1) Kiwoom API 분봉 조회 (ka10080)
- **Endpoint**: `/api/dostk/chart`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "stk_cd": "종목코드",
    "tic_scope": "1",
    "upd_stkpc_tp": "1"
  }
  ```
- **Request Headers**:
  - `cont-yn`: `'Y'` (연속 조회) 또는 `'N'` (최초 조회)
  - `next-key`: 다음 페이지를 조회하기 위한 키 값
- **Response Keys**:
  - `stk_min_pole_chart_qry`: 분봉 데이터 리스트 (개별 원소 내 `cntr_tm` 필드를 날짜 판별자로 사용)

---

## 3. 테스트 케이스 설계 (TDD 완료 기준)

구현 Agent는 다음 4가지 테스트 케이스를 우선 통과하도록 로직을 설계해야 합니다.

### 1) 정상 동작 테스트 (Happy Path)
- **`test_kiwoom_client_fetch_minute_chart_returns_normalized_records`**
  - [검증]: `KiwoomClient`가 모의 API 응답 데이터(예: 600개 레코드 및 `cont-yn='Y'`)를 페이지네이션 규칙에 따라 정상 파싱하고, `stk_min_pole_chart_qry` 내 데이터를 반환하는지 확인.
- **`test_target_selector_selects_top_n_by_volume`**
  - [검증]: DB 내 `daily_ohlcv` 데이터를 기준으로 특정 분기의 평균 거래대금(`close * volume`)을 계산하여 정상적으로 상위 N개 종목 리스트를 추출하는지 검증.

### 2) 예외 처리 및 경계값 테스트
- **`test_kiwoom_client_handles_api_exception_safely`**
  - [검증]: API 통신 중 `requests.HTTPError` 또는 `KiwoomAPIError`가 발생했을 때 적절한 커스텀 예외를 발생시키거나 안전하게 빈 리스트를 리턴하는지 검증.
- **`test_backfill_task_skips_when_no_missing_days`**
  - [검증]: 모든 영업일의 분봉 개수가 360개 이상이어서 누락일이 전혀 감지되지 않을 때, API 호출 없이 즉시 스킵 처리되는지 검증.

---

## 4. Proposed Files (변경 예정 파일 목록)

### [NEW] `collectors/kiwoom_client.py`(file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/kiwoom_client.py)
- `KiwoomApiCore` 래퍼 및 연속 조회 로직 구현.

### [NEW] `collectors/target_selector.py`(file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/target_selector.py)
- 거래대금 기반 종목 선별기.

### [NEW] `tasks/backfill_task.py`(file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py)
- 누락일 탐지, 분봉 백필 및 진척도 기입 파이프라인.

### [NEW] `tests/test_backfill_task.py`(file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_backfill_task.py)
- T-005 단위 및 통합 검증을 위한 테스트 코드.

---

## 5. Verification Plan (검증 계획)

- **자동화 테스트**:
  - `PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms:tdms_core conda run --no-capture-output -n tdms_p2_env pytest tdms_core/p2_kdms/tests/test_backfill_task.py`
  - 4개 핵심 테스트가 모두 Green인지 체크.
