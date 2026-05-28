# Task-004: PIT 재무제표 수집 및 Point-in-Time 조회 인프라 구축

> **Sub Project**: p2_kdms
> **PRD 근거**: F-03 (PIT 재무제표 수집), API-데이터 (`/api/data/financials`), SCHED (`financial_update` 스케줄)
> **작성일**: 2026-05-21
> **의존 Task**: T-003 (수정계수 수집 + 역산 API 및 물리 테이블 반영)

---

## § 1. 목표

한국투자증권(KIS) OpenAPI의 7개 재무 관련 엔드포인트를 활용하여 국내 상장 주식의 재무제표(대차대조표, 손익계산서) 및 재무비율을 정기적으로 수집하는 파이썬 파이프라인을 구축합니다. 수집된 데이터는 시점 이탈 편향(Look-ahead Bias)을 배제하기 위해 데이터 수집 시점을 버전 관리하는 **Point-in-Time (PIT)** 방식(`retrieved_at` 컬럼)으로 축적하며, 특정 조회 시점(`as_of_date`) 기준의 스냅샷 데이터를 정확하게 역산/조회할 수 있는 엔드포인트를 제공합니다.

**구현 범위:**
- **IN**:
  - `collectors/kis_kr_client.py` — KIS 재무제표 및 재무비율 API 7종을 순차적으로 호출하여 통합 딕셔너리로 결합하는 `fetch_all_financial_data` 수집 로직 및 데이터 정규화 형변환 필터링 구현.
  - `repositories/financial_repo.py` — `financial_statements` 및 `financial_ratios` 테이블을 조회/기록하는 저장소 레이어 및 `as_of_date` 기준 최신 PIT 레코드를 추출하는 쿼리 작성.
  - `tasks/financial_task.py` — 수집 주기(주 1회, 토요일 09:00)에 기동할 배치 파이프라인. 전체 활성 종목을 순회하며 변경을 감지하고, 변동 사항이 발생한 항목에 한해서만 새로운 PIT 레코드를 벌크 삽입하는 기능. `job_statuses` 전역 변수에 지능형 tqdm 스타일 진행 상태 갱신.
  - `routers/data.py` (또는 별도 데이터 라우터) — `/api/data/financials` 엔드포인트를 통해 특정 종목의 PIT 재무 상태 및 비율 데이터를 제공. `as_of_date` 파라미터 필터링 지원.
  - 관련 단위 테스트 및 통합 테스트 (`test_financial_repo.py`, `test_financial_task.py`, `test_financial_endpoints.py`).
- **OUT**:
  - `AsyncIOScheduler` 스케줄러 자체의 구동 및 백그라운드 예약 연동 (T-006에서 전체 스케줄 통합 진행 예정).
  - 재무 스크리닝 API (`POST /api/data/screening`) 및 시가총액 비교 연동 (T-007).

---

## § 1.1 과거 데이터 적재 시점 제약 및 주의사항 (중요)

> [!WARNING]
> **과거 대량 적재 데이터의 PIT 한계**
> - 기존 `kdms_db`에 존재하는 **2025년 11월 8일 이전**의 모든 재무 및 재무비율 데이터는 일일 수집을 통한 실시간 적재가 아닌, 과거 데이터 대량 수집(Bulk Load) 방식으로 적재되었습니다.
> - 이로 인해 2025년 11월 8일 이전 결산분들의 `retrieved_at` 타임스탬프는 실제 발표일이 아니라 **일괄 대량 수집일(예: 2025-11-08 전후)**로 일치되어 있습니다.
> - **영향**:
>   - `as_of_date`를 2025년 11월 8일 이전(예: 2025년 6월)으로 설정하여 PIT 조회를 시도하면, 해당 시점에 데이터가 이미 발표되었음에도 불구하고 `retrieved_at` 필터링에 걸려 데이터가 조회되지 않는 현상이 발생합니다.
> - **대응 방침**:
>   1. **코드 및 주석 명기**: `financial_repo.py` 내의 조회 쿼리 메소드 주석 및 API 문서에 이 제약 조건을 명시적으로 기술하여 분석가가 오사용하지 않도록 예방합니다.
>   2. **백테스팅 가이드**: 2025년 11월 8일 이전 시점을 대상으로 한 시뮬레이션에서는 `as_of_date`를 활용한 엄격한 PIT 필터링이 불가하며, 2025년 11월 8일 이후 시점부터 완전한 Look-ahead Bias 배제 백테스팅이 가능함을 사용자 매뉴얼에 명시합니다.
>   3. **쿼리 보완**: API 및 Repository 쿼리 함수에 `as_of_date`가 대량 적재 기준시점(예: `2025-11-08 00:00:00 KST`) 이전일 경우, `retrieved_at` 필터를 무력화하거나 전체 데이터를 반환하도록 옵션을 제공하여 데이터가 아예 비어서 나오는 오작동을 방지하는 구조로 구현합니다.

---

## § 2. 구현 대상

### 신규 생성 파일
- [financial_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/financial_repo.py) — `financial_statements` 및 `financial_ratios` 데이터에 대한 Point-in-Time CRUD 쿼리 구현.
- [financial_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/financial_task.py) — 전체 종목 대상 재무 수집/비교/적재 프로세스.
- [test_financial_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_financial_repo.py) — 저장소 레이어의 삽입, 변경 탐지 조회, PIT 쿼리 검증.
- [test_financial_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_financial_task.py) — 수집 루프, API 예외 전파 시의 강건성, `job_statuses` 갱신 모킹 테스트.
- [test_financial_endpoints.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_financial_endpoints.py) — `/api/data/financials` 조회 API 통합 테스트.

### 수정 대상 파일
- [kis_kr_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/kis_kr_client.py) — KIS 재무 API 7종에 대한 호출 및 데이터 포맷팅/타입 변환(Decimal 정규화 등) 메소드 추가.
- [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py) — `KDMS_EXPECTED_TABLES` 목록에 `"financial_statements"`, `"financial_ratios"` 테이블 등록 확인.
- [data.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/data.py) — 재무 정보 조회 엔드포인트 `/api/data/financials` 바인딩 및 Pydantic 데이터 모델 통합.

---

## § 3. 핵심 인터페이스

### 3.1 KIS 수집 클라이언트 (`collectors/kis_kr_client.py` 추가 메소드)
```python
from typing import Dict, List, Any

class KisKrClient:
    # ... 기존 메소드 ...

    def fetch_financial_data_by_type(self, stk_cd: str, api_type: str, div_cls_code: str = "1") -> List[Dict[str, Any]]:
        """
        KIS OpenAPI의 개별 재무 엔드포인트를 호출하고 결과를 리스트로 반환합니다.
        
        Args:
            stk_cd: 6자리 종목 코드
            api_type: 'balance_sheet' | 'income_statement' | 'financial_ratio' | 
                      'profit_ratio' | 'other_major_ratios' | 'stability_ratio' | 'growth_ratio'
            div_cls_code: '0' (연간) 또는 '1' (분기)
        """
        # API 별 Endpoint & TR_ID 구성:
        # - balance_sheet:      ('/uapi/domestic-stock/v1/finance/balance-sheet', 'FHKST66430100')
        # - income_statement:   ('/uapi/domestic-stock/v1/finance/income-statement', 'FHKST66430200')
        # - financial_ratio:    ('/uapi/domestic-stock/v1/finance/financial-ratio', 'FHKST66430300')
        # - profit_ratio:       ('/uapi/domestic-stock/v1/finance/profit-ratio', 'FHKST66430400')
        # - other_major_ratios: ('/uapi/domestic-stock/v1/finance/other-major-ratios', 'FHKST66430500')
        # - stability_ratio:    ('/uapi/domestic-stock/v1/finance/stability-ratio', 'FHKST66430600')
        # - growth_ratio:       ('/uapi/domestic-stock/v1/finance/growth-ratio', 'FHKST66430800')
        ...

    def fetch_all_financial_data(self, stk_cd: str, div_cls_code: str = "1") -> Dict[str, List[Dict[str, Any]]]:
        """
        특정 종목의 7대 재무 엔드포인트를 모두 호출하여 통합 딕셔너리로 결합해 반환합니다.
        실전 전용이며, API 호출 오류(예: 미지원 종목) 시 KisAPIError 또는 적절한 예외를 전파합니다.
        """
        ...
```

### 3.2 재무 정보 저장소 (`repositories/financial_repo.py`)
```python
from datetime import datetime
from p1_shared.db.connection import DbConnectionPool

class FinancialRepo:
    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def get_latest_statement(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> dict | None:
        """
        stk_cd, stac_yymm, div_cls_code 기준 DB에 가장 최근(retrieved_at DESC) 저장된 재무제표 레코드를 반환합니다.
        """
        ...

    def get_latest_ratio(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> dict | None:
        """
        stk_cd, stac_yymm, div_cls_code 기준 DB에 가장 최근(retrieved_at DESC) 저장된 재무비율 레코드를 반환합니다.
        """
        ...

    def insert_statements(self, statements: list[dict]) -> int:
        """
        financial_statements 테이블에 PIT 버전을 벌크 인서트(INSERT)합니다.
        자산/부채/매출 등 수치형 컬럼은 Decimal(NUMERIC) 타입 처리를 지원해야 합니다.
        """
        ...

    def insert_ratios(self, ratios: list[dict]) -> int:
        """
        financial_ratios 테이블에 PIT 버전을 벌크 인서트(INSERT)합니다.
        수치형 컬럼은 float/Decimal 매핑을 지원해야 합니다.
        """
        ...

    def get_statements_as_of(self, stk_cd: str, div_cls_code: str, as_of_date: datetime) -> list[dict]:
        """
        특정 시점(as_of_date) 기준으로 유효한(retrieved_at <= as_of_date) 재무제표 스냅샷 데이터를 
        각 결산년월(stac_yymm) 별로 가장 최신 버전을 선택하여 내림차순(stac_yymm DESC)으로 반환합니다.
        
        SQL 예시:
        SELECT DISTINCT ON (stac_yymm) *
        FROM financial_statements
        WHERE stk_cd = %s AND div_cls_code = %s AND retrieved_at <= %s
        ORDER BY stac_yymm DESC, retrieved_at DESC;
        """
        ...

    def get_ratios_as_of(self, stk_cd: str, div_cls_code: str, as_of_date: datetime) -> list[dict]:
        """
        특정 시점(as_of_date) 기준으로 유효한(retrieved_at <= as_of_date) 재무비율 스냅샷 데이터를
        각 결산년월(stac_yymm) 별로 가장 최신 버전을 선택하여 내림차순(stac_yymm DESC)으로 반환합니다.
        """
        ...
```

### 3.3 재무 수집 백그라운드 태스크 (`tasks/financial_task.py`)
```python
from typing import Dict, Any

def run_financial_update(job_statuses: Dict[str, Any], test_mode: bool = False) -> None:
    """
    KIS 재무정보 수집 및 PIT 버전 관리 루프를 구동합니다.
    
    동작 순서:
      1. DB의 stock_info에서 활성 상태 종목(active_only=True)을 추출합니다. (test_mode=True인 경우 5개 이하 샘플링)
      2. 각 종목에 대해 `KisKrClient.fetch_all_financial_data`를 호출하여 재무 정보를 수집합니다.
      3. 수집된 데이터를 변환 규칙에 따라 정규화합니다. (0/0.0/None 등은 동일하게 무시 처리하며 타입 캐스팅 수행)
      4. stac_yymm 결산년월별로 병합한 후, `FinancialRepo.get_latest_statement/ratio`를 호출하여 DB의 최신 데이터와 대조합니다.
      5. 소수점 및 수치 비교 정규화를 통해 변경점이 발견되거나 신규 결산분인 경우, 새로운 `retrieved_at` 버전을 인서트 대상 리스트에 추가합니다.
      6. 루프 완료 후 `FinancialRepo.insert_statements`, `insert_ratios`를 벌크 수행하여 기록합니다.
      7. 예외(KisAPIError 등)가 나더라도 전체 루프가 붕괴되지 않고 로깅 후 다음 종목으로 진행해야 합니다.
      8. `job_statuses["financial_update"]`에 tqdm 스타일의 실시간 진행률(it/s, ETA, 현재 대상 종목, 로그)을 성실하게 기록합니다.
    """
    ...
```

---

## § 4. 테스트 케이스 설계

### 4.1 `KisKrClient` 재무 수집 단위 테스트 (`tests/test_financial_client.py`)
* **`test_fetch_financial_data_by_type_success`** (정상 동작)
  - KIS OpenAPI balance_sheet 조회를 Mocking하여 정상적인 필드들(stac_yymm, cras, fxas 등)을 포함한 list가 반환되는지 확인.
* **`test_fetch_all_financial_data_returns_integrated_dict`** (정상 동작)
  - 7개 API 응답이 모두 정상 반환되었을 때, 통합 딕셔너리가 모든 7개 키(`balance_sheet`, `income_statement` 등)를 올바르게 반환하는지 검증.
* **`test_fetch_financial_data_api_failure_raises_exception`** (예외 처리)
  - KIS API 호출 시 HTTP 401 혹은 KIS 리턴 코드 오류(rt_cd != '0')가 발생하면 예외가 정상적으로 발생하는지 검증.

### 4.2 `FinancialRepo` Point-in-Time 쿼리 단위 테스트 (`tests/test_financial_repo.py`)
* **`test_insert_and_get_latest_version`** (정상 동작)
  - 동일한 `(stk_cd, stac_yymm, div_cls_code)` 값을 가지되 다른 `retrieved_at` 시점을 가지는 복수 레코드를 인서트 한 뒤, `get_latest_statement`를 조회하면 가장 늦은(최신) 시각의 데이터가 온전하게 리턴되는지 확인.
* **`test_get_statements_as_of_point_in_time`** (Point-in-Time 검증)
  - 예시:
    - 2026-03-31 수집분 (매출 100억)
    - 2026-04-15 재수집 정정분 (매출 110억)
    - `as_of_date`를 **2026-04-10**으로 지정하여 조회했을 때, 4-15 정정분이 아닌 3-31 시점의 데이터(매출 100억)가 출력되는지 정확하게 PIT 격리 검증.
* **`test_empty_db_returns_none_or_empty_list`** (경계값)
  - 레코드가 아예 없을 때 `get_latest_statement`는 `None`을 반환하고 `get_statements_as_of`는 빈 리스트 `[]`를 반환하는지 체크.

### 4.3 `run_financial_update` 태스크 단위 테스트 (`tests/test_financial_task.py`)
* **`test_run_financial_update_detects_changes_and_inserts`** (변경 감지 및 삽입)
  - API 수집 데이터와 DB의 최신 데이터가 다를 때(예: `sale_account`가 다름), 새로운 버전(`retrieved_at`가 현재 시간)으로 INSERT 대상에 추가되어 DB 인서트가 수행되는지 검증.
* **`test_run_financial_update_skips_on_no_changes`** (중복 스킵)
  - API 수집 데이터와 DB 최신 데이터가 수치적으로 완벽하게 같으면(Decimal/Float 차이 극복 및 0/None 동일 취급 필터 통과), INSERT 대상에 포함되지 않고 무시되는지 검증.
* **`test_run_financial_update_handles_api_exception_safely`** (예외 처리 강건성)
  - 특정 종목 수집 중 KIS API 장애가 발생하여 에러를 던져도 다음 종목으로 건너뛰어 루프를 완료하는지 확인.
* **`test_run_financial_update_updates_job_statuses_progress`** (진행 상태 기록)
  - 태스크 기동 시 `job_statuses` 딕셔너리에 `is_running=True`, `progress` 상승(0% -> 100%) 및 tqdm 스타일 `last_log` 등이 실시간 기입되는지 확인.

### 4.4 `/api/data/financials` API 엔드포인트 연동 테스트 (`tests/test_financial_endpoints.py`)
* **`test_get_financials_endpoint_returns_json`** (정상 동작)
  - `GET /api/data/financials?stk_cd=005930&div_cls_code=1` 호출 시 200 OK와 함께 재무제표 및 재무비율 목록이 타임스탬프 순서대로 적절히 반환되는지 확인.
* **`test_get_financials_endpoint_with_as_of_date_filtering`** (PIT 필터링)
  - `as_of_date` 파라미터를 쿼리 스트링에 전달했을 때, 과거 시점 스냅샷 데이터만 추출하여 응답 모델을 만족하는지 확인.
* **`test_get_financials_invalid_params_returns_422`** (오류 처리)
  - 필수 파라미터가 없거나 형식이 어긋날 때 FastAPI 기본 Validation Error(422)를 반환하는지 체크.

---

## § 5. 완료 기준 체크리스트

**수집 및 데이터 정합성:**
- [ ] KIS 재무 API 7종이 순차적으로 올바른 TR_ID와 파라미터로 호출되는가?
- [ ] 수집된 필드가 `DATA_MAPPER['kis']`의 설계 스펙과 부합하도록 완벽하게 형변환되어 정규화되는가?
- [ ] DB에 동일한 키의 데이터가 존재하더라도 수치가 다르면 업데이트가 아니라 **신규 `retrieved_at` 로우**로 삽입(PIT 버전 보존)되는가?

**태스크 기동 및 복구력:**
- [ ] 전체 종목 수집 시 네트워크 타임아웃, 예외 발생 등에 대응하는 안전장치가 루프에 내장되어 있는가?
- [ ] tqdm 스타일 진행률 계산에 의해 초당 처리수(it/s) 및 남은 시간(ETA)이 `job_statuses`에 정확히 전달되는가?
- [ ] `test_mode`를 지원하여 테스트 수행 시에는 극소수의 종목(예: 삼성전자)만 샘플링하여 5초 내로 태스크가 조기 정상 종료되는가?

**인프라 및 API:**
- [ ] `/api/data/financials` 호출 시 정상적인 PIT 조회 로직(`DISTINCT ON (stac_yymm) ... ORDER BY retrieved_at DESC`)을 수행하는가?
- [ ] `as_of_date` 쿼리 파라미터 필터링이 정상적으로 적용되는가?
- [ ] 모든 단위 및 통합 테스트 10개 이상이 에러 없이 무결하게 성공 완료되는가?
