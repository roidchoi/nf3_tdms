# Interface: OhlcvRepo

> **파일**: `tdms_core/p2_kdms/repositories/ohlcv_repo.py`
> **클래스**: `OhlcvRepo`
> **Graphify**: God Node #1 (degree=39) — 가장 많은 연결을 가진 핵심 저장소
> **관련**: `[[p2_kdms_wiki/interfaces/financial_repo.md]]`, `[[interfaces/factor_repo.md]]`, `[[p2_kdms_wiki/codebase_map.md]]`

---

## 클래스 시그니처

```python
class OhlcvRepo:
    def __init__(self, pool: DbConnectionPool) -> None
```

---

## 메서드 목록

### `upsert_daily_ohlcv(records: list[dict]) -> int`
- **위치**: Line 10
- **테이블**: `daily_ohlcv`
- **충돌 키**: `ON CONFLICT (stk_cd, dt) DO UPDATE`
- **입력 딕셔너리 키**: `stk_cd`, `dt`, `open`, `high`, `low`, `close`, `volume`
- **컬럼 매핑**: `open→open_prc`, `high→high_prc`, `low→low_prc`, `close→cls_prc`, `volume→vol`
- **반환**: `cursor.rowcount` (int)

---

### `get_latest_date(stk_cd: str) -> date | None`
- **위치**: Line 50
- **쿼리**: `SELECT MAX(dt) FROM daily_ohlcv WHERE stk_cd = %s`
- **반환**: `date` 또는 `None`

---

### `record_gap(stk_cd: str, target_date: date, reason: str) -> None`
- **위치**: Line 67
- **테이블**: `daily_ohlcv_gap`
- **충돌 키**: `ON CONFLICT (stk_cd, dt) DO UPDATE SET reason, updated_at`
- **용도**: 수집 실패 종목의 실패 사유 기록

---

### `refresh_adjusted_ohlcv_batch(start_date: date, end_date: date, price_source: str = 'KIS') -> int`
- **위치**: Line 86
- **테이블**: `daily_ohlcv_adjusted` (물리 테이블)
- **원리**: SQL CTE로 `price_adjustment_factors`에서 `event_dt > dt`인 팩터의 `EXP(SUM(LN(ratio)))` 누적곱 계산 → UPSERT
- **충돌 키**: `ON CONFLICT (dt, stk_cd) DO UPDATE`
- **반환**: 처리 행 수 (int)

---

### `get_daily_ohlcv(stk_cd: str, start_date: date, end_date: date) -> list[dict]`
- **위치**: Line 156
- **테이블**: `daily_ohlcv`
- **반환 딕셔너리 키**: `stk_cd(str)`, `dt(date)`, `open(int)`, `high(int)`, `low(int)`, `close(int)`, `volume(int)`

---

### `get_adjusted_ohlcv_direct(stk_cd: str, start_date: date, end_date: date) -> list[dict]`
- **위치**: Line 182
- **테이블**: `daily_ohlcv_adjusted` (물리 테이블 직접 조회)
- **반환 딕셔너리 키**: `stk_cd`, `dt`, `open(int)`, `high(int)`, `low(int)`, `close(int)`, `volume(int)`, `adj_factor(float)`

---

### `get_minute_target_history(quarter: str, market: str, table_name: str = 'minute_target_history') -> list[dict]`
- **위치**: Line 209
- **반환 키**: `quarter`, `market`, `symbol`, `avg_trade_value(float)`, `rank(int)`

---

### `upsert_minute_target_history(targets: list[dict], table_name: str = 'minute_target_history') -> None`
- **위치**: Line 231
- **충돌 키**: `ON CONFLICT (quarter, market, symbol) DO UPDATE`

---

### `upsert_minute_ohlcv(data: list[dict], table_name: str = 'minute_ohlcv') -> int`
- **위치**: Line 249
- **충돌 키**: `ON CONFLICT (dt_tm, stk_cd) DO UPDATE`
- **구현**: `psycopg2.extras.execute_values` (컬럼 동적 처리)

---

### `fetch_ohlcv_for_factor_calc(stk_cd: str, ...) -> pd.DataFrame`
- **위치**: Line 269
- **반환**: `pd.DataFrame` (컬럼: `dt`, `adj_close`, `raw_close`) — 두 테이블 inner join
- **용도**: `FactorCalculator.calculate_factors()` 에 입력 데이터 제공

---

## 관련 테이블

| 테이블명 | 설명 |
|---|---|
| `daily_ohlcv` | 원본 일봉 (PK: stk_cd, dt) |
| `daily_ohlcv_adjusted` | 수정주가 물리 테이블 (PK: dt, stk_cd) |
| `daily_ohlcv_gap` | 수집 실패 기록 (PK: stk_cd, dt) |
| `minute_ohlcv` | 분봉 데이터 (PK: dt_tm, stk_cd) |
| `minute_target_history` | 분봉 수집 대상 이력 (PK: quarter, market, symbol) |
