# Task-003: 수정계수 수집 + 역산 API 및 수정주가 물리 테이블 저장 (KIS)

> **Sub Project**: p2_kdms
> **PRD 근거**: F-02 (수정계수 계산 및 관리), API-데이터 (`/api/data/factors`, `/api/data/ohlcv/daily/adjusted`, `/api/data/ohlcv/adjusted/{stk_cd}`)
> **작성일**: 2026-05-21
> **의존 Task**: T-002 (일일 OHLCV + 종목 마스터 수집)

---

## § 1. 목표

KIS 일봉 시세 데이터(원본 및 수정 종가)를 비교 분석하여 수정계수(Adjustment Factor) 이벤트를 감지/역산하고 이를 `price_adjustment_factors` 테이블에 CRUD 형태로 영속화합니다. 또한, 수정주가 일봉 데이터를 물리적으로 관리하기 위해 `daily_ohlcv_adjusted` 테이블을 개설하고, 배치 갱신 로직(`refresh_adjusted_ohlcv_batch`)을 구현합니다. 최종적으로 온더플라이 실시간 역산 API 및 물리 테이블 직접 조회 API 엔드포인트를 제공합니다.

**구현 범위:**
- **IN**:
  - `collectors/factor_calculator.py` — 원본/수정 종가의 비율 변동을 탐지하여 수정계수 이벤트를 역산하고, 직접 곱하기 형식(Multiplication Format)의 팩터 리스트로 변환하는 비즈니스 로직.
  - `repositories/factor_repo.py` — `price_adjustment_factors` 테이블에 대한 CRUD 작업 및 `price_source` ('KIS' / 'KIWOOM') 구분 처리.
  - `repositories/ohlcv_repo.py` — `daily_ohlcv_adjusted` 물리 테이블 관리 및 SQL CTE 기반 일괄 수정주가 갱신 로직(`refresh_adjusted_ohlcv_batch`).
  - `tasks/daily_task.py` — 일일 수집 후 수정계수 계산 및 `daily_ohlcv_adjusted` 테이블 갱신 자동 수행 연동.
  - `migrations/003_add_daily_ohlcv_adjusted.sql` 및 `p1_shared/db/kdms_origin/init.sql` — `daily_ohlcv_adjusted` 테이블 마이그레이션 스키마 추가.
  - `routers/data.py` — 특정 종목의 수정계수를 조회하는 `/api/data/factors` 엔드포인트, 실시간 역산 수정주가를 반환하는 `/api/data/ohlcv/daily/adjusted` 엔드포인트 및 물리 테이블에서 직접 조회하는 `/api/data/ohlcv/adjusted/{stk_cd}` 엔드포인트 구현.
  - 관련 단위 테스트 및 통합 테스트 (`test_factor_calculator.py`, `test_factor_repo.py`, `test_factor_endpoints.py`, `test_ohlcv_repo_adjusted.py`).
- **OUT**:
  - 분봉 수정계수 테이블의 생성 및 관리 (분봉 수정 시에는 본 일봉 수정계수를 공유하여 동적 역산 적용).
  - 전체 스케줄러 자동화(APScheduler 연동) (T-006).

---

## § 2. 구현 대상

### 신규 생성 파일
- [factor_calculator.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/factor_calculator.py) — 주가 변동 비율을 기반으로 수정계수 이벤트를 추출하는 함수 정의.
- [factor_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/factor_repo.py) — `price_adjustment_factors` 테이블에 데이터를 입출력하는 저장소 구현.
- [003_add_daily_ohlcv_adjusted.sql](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/migrations/003_add_daily_ohlcv_adjusted.sql) — `daily_ohlcv_adjusted` 테이블 추가용 DB 마이그레이션 SQL 스키마.
- [test_factor_calculator.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_factor_calculator.py) — 계산식 검증용 단위 테스트.
- [test_factor_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_factor_repo.py) — DB CRUD 및 정렬 쿼리 테스트.
- [test_ohlcv_repo_adjusted.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_ohlcv_repo_adjusted.py) — `refresh_adjusted_ohlcv_batch` 및 물리 테이블 검증용 테스트.
- [test_factor_endpoints.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_factor_endpoints.py) — FastAPI 라우터 및 실시간/직접 조회 API 연동 테스트.

### 수정 대상 파일
- [init.sql](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/db/kdms_origin/init.sql) — `daily_ohlcv_adjusted` 물리 테이블 DDL 선언부 통합 추가.
- [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py) — `KDMS_EXPECTED_TABLES`에 `"daily_ohlcv_adjusted"` 추가 및 `data` 라우터 등록.
- [ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py) — `refresh_adjusted_ohlcv_batch` 메소드 추가.
- [daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py) — 원본 시세 수집 후 수정계수 계산 및 물리 테이블 갱신 기능 통합.
- [data.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/data.py) — 신규 조회, 역산 및 물리 조회 엔드포인트 라우터 함수 추가.

---

### 핵심 인터페이스

```python
# collectors/factor_calculator.py
import pandas as pd
from typing import List, Dict, Any

def calculate_factors(df: pd.DataFrame, stk_cd: str, price_source: str) -> List[Dict[str, Any]]:
    """
    수정 및 원본 주가 데이터를 포함한 DataFrame을 받아 수정계수(Price Adjustment Factor) 이벤트를 탐지하고 역산합니다.
    
    계산 규칙:
      - raw_price * price_ratio = adj_price (직접 곱하기 형식, < 1)
      - raw_volume * volume_ratio = adj_volume (직접 곱하기 형식, > 1)
      - 비율 변동률(1% 이상)이 감지되었을 때만 이벤트를 기록합니다.
      
    Args:
        df: 'dt', 'adj_close', 'raw_close' 컬럼을 포함하며 날짜순(오름차순)으로 정렬된 DataFrame.
        stk_cd: 종목 코드.
        price_source: 시세 출처 (예: 'KIS').
        
    Returns:
        List[Dict[str, Any]]: price_adjustment_factors 테이블에 적재 가능한 레코드 딕셔너리 목록.
            [{"stk_cd", "event_dt", "price_ratio", "volume_ratio", "price_source", "details"}, ...]
    """
    ...


# repositories/factor_repo.py
from datetime import date
from p1_shared.db.connection import DbConnectionPool

class FactorRepo:
    """price_adjustment_factors 테이블 관리를 위한 저장소 클래스."""

    def __init__(self, pool: DbConnectionPool) -> None:
        self.pool = pool

    def upsert_adjustment_factors(self, factors: list[dict]) -> int:
        """수정계수 이벤트 리스트를 DB에 벌크 Upsert합니다. ON CONFLICT DO UPDATE."""
        ...

    def delete_adjustment_factors(self, stk_cd: str, price_source: str) -> None:
        """특정 종목과 시세 출처에 해당하는 모든 수정계수 데이터를 삭제합니다."""
        ...

    def get_factors_for_stock(self, stk_cd: str, price_source: str) -> list[dict]:
        """특정 종목의 전체 수정계수 이력을 event_dt 오름차순으로 정렬하여 조회합니다."""
        ...


# repositories/ohlcv_repo.py (추가 메소드)
class OhlcvRepo:
    # ... 기존 메소드 생략 ...
    
    def refresh_adjusted_ohlcv_batch(
        self, 
        start_date: date, 
        end_date: date, 
        src_table: str = "daily_ohlcv", 
        factor_table: str = "price_adjustment_factors", 
        dst_table: str = "daily_ohlcv_adjusted"
    ) -> int:
        """
        지정 기간 동안의 전 종목 수정주가를 SQL CTE를 통해 일괄 계산하고 물리 테이블인 daily_ohlcv_adjusted에 직접 저장합니다.
        (메모리 절약을 위해 Pandas를 거치지 않고 DB 레벨에서 모든 계산 및 Upsert 처리를 완결합니다.)
        
        Args:
            start_date: 계산 시작일
            end_date: 계산 종료일
            src_table: 원본 일봉 시세 테이블명
            factor_table: 수정계수 정보 테이블명
            dst_table: 저장 대상 물리 테이블명
        Returns:
            int: Upsert 완료된 행(row) 수
        """
        ...


# tasks/daily_task.py (추가 로직 연동)
class DailyTask:
    # ... 기존 속성 및 생성자 ...
    
    def run(self, target_date: date) -> dict:
        """
        일일 수집 실행을 조율합니다.
        1. 종목 마스터 수집 및 갱신
        2. 원시 일봉 OHLCV 수집 및 저장
        3. [추가] 신규 수정계수 감지 및 price_adjustment_factors 테이블 Upsert
        4. [추가] refresh_adjusted_ohlcv_batch()를 호출하여 물리 테이블 daily_ohlcv_adjusted 업데이트
        """
        ...


# routers/data.py (추가 엔드포인트)
@router.get("/api/data/factors/{stk_cd}", response_model=FactorResponse)
def get_stock_factors(stk_cd: str, price_source: str = Query("KIS")):
    """특정 종목의 수정계수 변경 이력을 조회합니다."""
    ...

@router.get("/api/data/ohlcv/daily/adjusted", response_model=OhlcvResponse)
def get_adjusted_daily_ohlcv(
    stk_cd: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    price_source: str = Query("KIS")
):
    """
    특정 종목의 원본 일봉 OHLCV 데이터를 조회한 후, 해당 기간에 등록된 수정계수들을 기반으로
    실시간 수정주가 및 수정거래량을 역산하여 반환합니다. (온더플라이 계산 방식, DB 조회 없음)
    """
    ...

@router.get("/api/data/ohlcv/adjusted/{stk_cd}", response_model=OhlcvResponse)
def get_adjusted_ohlcv_direct(
    stk_cd: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """
    daily_ohlcv_adjusted 물리화 테이블을 직접 조회하여 미리 계산되어 저장된 수정주가 일봉을 반환합니다.
    (CTE 계산 없이 직접 테이블 조회가 수행되므로 응답 속도가 대폭 향상됩니다.)
    """
    ...
```

---

## § 3. 기존 기능 보존

### 보존 인터페이스
- `main.py` 내의 FastAPI lifespan 구조 및 `StartupValidator` 연동 구조가 변형 없이 정상 유지되어야 함.
- T-002에서 신규 추가된 `/api/data/stocks` API의 경로 및 명세가 정상 유지되어야 함.

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤, 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# tests/test_factor_calculator.py

def test_calculate_factors_detects_split_correctly():
    """
    [목적] 삼성전자 50:1 액면분할(2018-05-04)과 유사한 상황을 가정하여, 가격 비율 변동을 성공적으로 감지하고 
           '곱셈 형식'의 수정계수(Price Ratio = 0.02, Volume Ratio = 50.0)를 산출하는지 검증.
    [유도] ratio 변동 임계값을 초과하는 행을 정확하게 감지하고, USDMS 호환을 위해 곱셈 형식으로 팩터 값을 변환하여 JSON 상세 데이터를 구성하도록 유도.
    """
    import pandas as pd
    from collectors.factor_calculator import calculate_factors
    
    test_data = {
        "dt": [pd.Timestamp("2018-05-02"), pd.Timestamp("2018-05-03"), pd.Timestamp("2018-05-04")],
        "raw_close": [2650000.0, 2650000.0, 51900.0],
        "adj_close": [53000.0, 53000.0, 51900.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    
    assert len(factors) == 1
    event = factors[0]
    assert event["stk_cd"] == "005930"
    assert event["event_dt"] == pd.Timestamp("2018-05-04").date()
    assert float(event["price_ratio"]) == 0.02
    assert float(event["volume_ratio"]) == 50.0
    assert event["price_source"] == "KIS"
    
    import json
    details = json.loads(event["details"])
    assert details["raw_close"] == 51900.0
    assert details["adj_close"] == 51900.0
    assert details["prev_raw_close"] == 2650000.0
    assert details["prev_adj_close"] == 53000.0
```

### 4.2 경계값 케이스

```python
# tests/test_factor_calculator.py

def test_calculate_factors_returns_empty_when_no_adjustments():
    """
    [목적] 원본 종가와 수정 종가의 비율이 일정하여 수정계수 변경 이벤트가 존재하지 않는 경우 빈 리스트를 반환하는지 검증.
    [유도] threshold(1%) 이하의 변동률은 이벤트 목록에서 제외하도록 경계값 필터링 로직 유도.
    """
    import pandas as pd
    from collectors.factor_calculator import calculate_factors

    test_data = {
        "dt": [pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-02"), pd.Timestamp("2026-05-03")],
        "raw_close": [70000.0, 70500.0, 71000.0],
        "adj_close": [70000.0, 70500.0, 71000.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    assert factors == []
```

### 4.3 예외/오류 처리 케이스

```python
# tests/test_factor_calculator.py

def test_calculate_factors_avoids_division_by_zero():
    """
    [목적] 시세 데이터 오염으로 원본 종가(raw_close)가 0이거나 이전 비율이 0인 행이 포함된 경우 ZeroDivisionError를 방지하고 정상 연산 처리하는지 검증.
    [유도] numpy.where 또는 if 조건절을 통한 분기 처리로 분모가 0이 될 수 있는 시나리오 방어 코드 유도.
    """
    import pandas as pd
    from collectors.factor_calculator import calculate_factors

    test_data = {
        "dt": [pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-02"), pd.Timestamp("2026-05-03")],
        "raw_close": [70000.0, 0.0, 71000.0],
        "adj_close": [70000.0, 70500.0, 71000.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    assert isinstance(factors, list)
```

### 4.4 통합/연계 케이스

```python
# tests/test_ohlcv_repo_adjusted.py

def test_refresh_adjusted_ohlcv_batch_executes_cte(mocker):
    """
    [목적] refresh_adjusted_ohlcv_batch 가 DB 레벨에서 SQL CTE 구문을 활용하여 원본 시세에 수정계수를 결합 및 누적곱 처리하고, 
           물리 테이블인 daily_ohlcv_adjusted 에 일괄 UPSERT를 완료하는지 검증.
    [유도] EXP(SUM(LN(price_ratio))) 함수와 함께 INSERT INTO ... SELECT 구문이 정상 바인딩 및 실행되는지 유도.
    """
    # mock cursor 및 execute를 이용해 CTE 쿼리가 정상 실행되고 affected row count가 반환되는지 테스트 작성
    pass


# tests/test_daily_task.py (확장 테스트)

def test_daily_task_runs_factor_calculation_and_refresh(mocker):
    """
    [목적] DailyTask.run 실행 시 단순 일봉 적재뿐만 아니라 수정계수의 자동 감지 및 물리 테이블 갱신 과정까지 일관되게 조율되는지 검증.
    """
    # ...
    pass


# tests/test_factor_endpoints.py

def test_endpoint_adjusted_ohlcv_calculates_correct_prices(test_client, mocker):
    """
    [목적] GET /api/data/ohlcv/daily/adjusted API 호출 시 DB 원본 일봉과 수정계수 데이터를 조인하여 
           정확한 누적 수정 주가 및 수정 거래량을 실시간 계산(온더플라이)하는지 검증.
    """
    pass


def test_endpoint_adjusted_ohlcv_direct_queries_physical_table(test_client, mocker):
    """
    [목적] GET /api/data/ohlcv/adjusted/{stk_cd} API가 복잡한 CTE 연산 없이 물리 테이블인 daily_ohlcv_adjusted 테이블을 
           직접 SELECT 쿼리로 최적화 조회하는지 검증.
    """
    pass
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_calculate_factors_detects_split_correctly` | 정상 | 액면분할 감지 시 곱셈 형식(Price Ratio < 1, Volume Ratio > 1)으로의 올바른 부호 변환 및 이벤트 계산 |
| 2 | `test_calculate_factors_returns_empty_when_no_adjustments` | 경계값 | 수정계수 변경(변동률 1% 초과)이 없는 경우 감지 리스트를 빈 값으로 처리 |
| 3 | `test_calculate_factors_avoids_division_by_zero` | 예외 | 원본 주가 또는 ratio가 0이 되어 발생 가능한 ZeroDivision 예방 |
| 4 | `test_refresh_adjusted_ohlcv_batch_executes_cte` | 통합 | DB 레벨의 내림차순 누적곱 SQL CTE 연산 작동 및 물리 테이블 일괄 UPSERT 동작 확인 |
| 5 | `test_daily_task_runs_factor_calculation_and_refresh` | 통합 | 일일 배치 작업(DailyTask) 완료 시 수정계수 검출 및 물리 테이블의 동기식 갱신 결합 프로세스 작동 검증 |
| 6 | `test_endpoint_adjusted_ohlcv_calculates_correct_prices` | 연계 | API 레벨에서 원본 시세와 수정계수 누적곱을 통해 실시간(온더플라이) 수정 주가/거래량이 정상 제공되는지 검증 |
| 7 | `test_endpoint_adjusted_ohlcv_direct_queries_physical_table` | 연계 | API 레벨에서 daily_ohlcv_adjusted 물리 테이블을 통해 직접 가속화 조회 처리되는지 검증 |

**총 7개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

### 5.1 수정계수 형식 및 곱셈 표준 규칙
1. **나눗셈 형식(레거시/Kiwoom)**:
   - 레거시나 키움의 경우 `adjusted_price = raw_price / price_ratio` 형태로 처리되는 경우가 많으며, 50:1 액면분할 시 `price_ratio`가 `50.0`으로 저장됩니다.
2. **곱셈 형식(신규 표준/USDMS 호환)**:
   - 신규 구현(T-003) 및 USDMS 호환을 위해, 데이터베이스의 `price_adjustment_factors` 테이블에는 **직접 곱하기 승수** 형태로 변환하여 저장합니다.
   - **수정주가 계산식**:
     $$adj\_price = raw\_price \times price\_ratio$$
     (예: 50:1 분할인 경우 $price\_ratio = 0.02$)
   - **수정거래량 계산식**:
     $$adj\_volume = raw\_volume \times volume\_ratio$$
     (예: 50:1 분할인 경우 $volume\_ratio = 50.0$)

### 5.2 실시간 수정주가 역산 누적곱 알고리즘 (Dynamic Recalculation)
- `/api/data/ohlcv/daily/adjusted` 조회 시 온더플라이(On-the-fly) 계산을 위해 아래 알고리즘으로 동적 계산하여 반환합니다.
- 특정 날짜 $d$에 적용할 **누적 수정 비율(Cumulative Factor)**은 다음과 같습니다.
  
  $$CumPriceFactor(d) = \prod_{e\_dt > d} PriceRatio(e\_dt)$$
  $$CumVolumeFactor(d) = \prod_{e\_dt > d} VolumeRatio(e\_dt)$$

  - 즉, 해당 조회일 $d$ 이후에 발생한 모든 수정계수 이벤트의 비율들을 전부 곱한 값을 원본 주가/거래량에 곱해줍니다.
  - 날짜 $d$ 이후에 발생한 이벤트가 없다면 누적 비율은 `1.0`이 됩니다.

### 5.3 물리 테이블 기반 배치 갱신 CTE 쿼리 (Batch Refresh)
- `refresh_adjusted_ohlcv_batch` 구현 시 메모리 효율을 위해 다음 SQL CTE 구조를 적용합니다:
  ```sql
  WITH best_source AS (
      SELECT DISTINCT ON (stk_cd) stk_cd, price_source
      FROM price_adjustment_factors
      ORDER BY stk_cd ASC, CASE WHEN price_source = 'KIS' THEN 1 ELSE 2 END
  ),
  factors AS (
      SELECT 
          f.stk_cd, 
          f.event_dt, 
          CASE WHEN f.price_source = 'KIWOOM' THEN 1.0 / NULLIF(f.price_ratio, 0) 
               ELSE f.price_ratio END AS price_ratio
      FROM price_adjustment_factors f
      JOIN best_source b ON f.stk_cd = b.stk_cd AND f.price_source = b.price_source
  ),
  cum_factors AS (
      SELECT
          stk_cd,
          event_dt,
          EXP(SUM(LN(price_ratio)) OVER (
              PARTITION BY stk_cd
              ORDER BY event_dt DESC
          )) AS adj_factor
      FROM factors
  ),
  raw_prices AS (
      SELECT dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol
      FROM daily_ohlcv
      WHERE dt BETWEEN %(start_date)s AND %(end_date)s
  ),
  mapped_prices AS (
      SELECT
          p.*,
          (
              SELECT f.adj_factor
              FROM cum_factors f
              WHERE f.stk_cd = p.stk_cd
                AND p.dt < f.event_dt
              ORDER BY f.event_dt ASC
              LIMIT 1
          ) AS adj_factor
      FROM raw_prices p
  )
  INSERT INTO daily_ohlcv_adjusted (dt, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol, adj_factor, updated_at)
  SELECT
      dt,
      stk_cd,
      ROUND((open_prc * COALESCE(adj_factor, 1.0))::numeric, 2),
      ROUND((high_prc * COALESCE(adj_factor, 1.0))::numeric, 2),
      ROUND((low_prc  * COALESCE(adj_factor, 1.0))::numeric, 2),
      ROUND((cls_prc  * COALESCE(adj_factor, 1.0))::numeric, 2),
      ROUND((vol      / COALESCE(adj_factor, 1.0))::numeric, 0)::BIGINT,
      COALESCE(adj_factor, 1.0),
      NOW()
  FROM mapped_prices
  ON CONFLICT (dt, stk_cd) DO UPDATE SET
      open_prc   = EXCLUDED.open_prc,
      high_prc   = EXCLUDED.high_prc,
      low_prc    = EXCLUDED.low_prc,
      cls_prc    = EXCLUDED.cls_prc,
      vol        = EXCLUDED.vol,
      adj_factor = EXCLUDED.adj_factor,
      updated_at = EXCLUDED.updated_at;
  ```

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 7개 전체 통과
- [ ] 기존 T-001, T-002의 테스트 케이스 전체 통과 (회귀 발생 차단)
- [ ] `docs/p2_kdms/p2_kdms_pjt_tasks.md`에서 T-003 상태를 `완료`로 변경
- [ ] [task-003_walkthrough.md](file:///home/roid2/pjt/nf3/01_nf3_tdms/docs/p2_kdms/tasks/task-003_walkthrough.md) 작성 완료 및 검토 승인
