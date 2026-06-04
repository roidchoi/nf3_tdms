# [P2DEC-002] 수정주가 이중 제공 전략 (On-the-fly + 물리 테이블)

> **Sub Project**: p2_kdms
> **Status**: active
> **Date**: 2026-05-26
> **Task**: T-003
> **관련**: `[[p2_kdms_wiki/interfaces/ohlcv_repo.md]]`, `[[p2_kdms_wiki/interfaces/data_api_endpoints.md]]`

---

## 배경

KIS/Kiwoom API에서 제공하는 수정주가를 신뢰하지 않고,  
**원본 가격(daily_ohlcv) + 수정계수(price_adjustment_factors)를 분리 저장**하여  
두 가지 방식으로 수정주가를 제공한다.

---

## 두 가지 수정주가 제공 방식

### 방식 1: On-the-fly (실시간 계산) — `/api/data/ohlcv/daily/adjusted`
```
OhlcvRepo.get_daily_ohlcv() + FactorRepo.get_factors_for_stock()
  → 각 날짜 dt에 대해 event_dt > dt인 팩터들의 price_ratio, volume_ratio 누적곱
  → 조정 가격 = round(원본 * cum_price_factor)
```
- **장점**: 항상 최신 팩터 기준으로 실시간 계산
- **단점**: 팩터 데이터가 많을수록 계산 비용 증가

### 방식 2: 물리 테이블 직접 조회 — `/api/data/ohlcv/adjusted/{stk_cd}`
```
OhlcvRepo.get_adjusted_ohlcv_direct() → daily_ohlcv_adjusted 테이블
```
- **장점**: 단순 SELECT, 빠른 응답
- **단점**: OhlcvRepo.refresh_adjusted_ohlcv_batch() 실행 시점 기준 — 실시간성 없음

### 물리 테이블 갱신 (DailyTask 내부)
```sql
-- OhlcvRepo.refresh_adjusted_ohlcv_batch() 내부 CTE
WITH calculated_factors AS (
  SELECT ..., EXP(SUM(LN(f.price_ratio))) FILTER(event_dt > r.dt) AS cum_price_factor ...
)
INSERT INTO daily_ohlcv_adjusted ... ON CONFLICT (dt, stk_cd) DO UPDATE SET ...
```

---

## 수정계수 역산: FactorCalculator

```python
# collectors/factor_calculator.py
def calculate_factors(df: pd.DataFrame) -> list[dict]:
    """
    df 컬럼: dt, raw_close, adj_close
    비율 = adj_close / raw_close
    연속 비율 변동점을 팩터 이벤트로 추출
    """
```
- ZeroDivisionError 방어: `raw_close == 0`이거나 이전 비율이 0인 행 필터링

---

## 영향 범위
- `collectors/factor_calculator.py`
- `repositories/ohlcv_repo.py` (refresh_adjusted_ohlcv_batch, get_adjusted_ohlcv_direct)
- `repositories/factor_repo.py`
- `routers/data.py` (두 가지 수정주가 엔드포인트)

---

## 대안 검토

| 대안 | 거부 이유 |
|---|---|
| API 제공 수정주가 그대로 사용 | 출처별 차이, 과거 데이터 불일치 위험 |
| On-the-fly만 제공 | 빠른 조회가 필요한 클라이언트에 부적합 |
| 물리 테이블만 제공 | 팩터 갱신 직후~refresh 전 불일치 시구간 발생 |
