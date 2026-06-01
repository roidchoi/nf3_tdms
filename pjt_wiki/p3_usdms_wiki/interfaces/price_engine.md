# 인터페이스: PriceEngine (price_engine.md)

> **파일명**: `tdms_core/p3_usdms/collectors/price_engine.py`  
> **마지막 업데이트**: 2026-06-01 (Task-002-B)  

---

## 1. 개요
Raw Close 주가와 Adjusted Close 주가의 비율 변화를 추적하여 기업의 주식 분할(Stock Split), 배당(Dividend) 등으로 인한 가격 변동 수정계수를 역산하여 산출하고 DB에 적재하는 논리 엔진입니다.

---

## 2. 주요 메서드 시그니처

### `calculate_factors_from_ratio`
입력받은 가격 데이터프레임에서 수정주가 비율의 변화 지점을 검출하고 수정계수를 계산하여 리포지토리를 통해 적재합니다.

```python
def calculate_factors_from_ratio(self, cik: str, df: pd.DataFrame) -> None
```

- **매개변수**:
  - `cik`: 대상 회사의 SEC CIK 식별자
  - `df`: `Close` (미수정 종가)와 `Adj Close` (수정 종가) 컬럼 및 `Date` 인덱스를 보유한 DataFrame
- **핵심 연산 원리**:
  1. $Ratio_t = {Adj\ Close_t \over Raw\ Close_t}$ 를 산출합니다. (0 종가는 `NaN`으로 치환해 ZeroDivision 방지)
  2. $Prev\_Ratio_t = Ratio_{t-1}$ 로 전일 비율을 획득합니다.
  3. 변동 절댓값인 $\Delta = |Ratio_t - Prev\_Ratio_t|$ 가 $1e-5$ 임계값 이상인 지점을 수정 이벤트로 검출합니다.
  4. 검출된 날짜 $t$에 대해 과거 주가에 일괄 적용할 수정 비율인 $Factor = {Prev\_Ratio_t \over Ratio_t}$ 를 산출합니다.
  5. 산출된 레코드들을 중복 제거한 뒤 `PriceRepo.upsert_price_factors`를 호출하여 물리 테이블 `us_price_adjustment_factors`에 반영합니다.
- **예외 처리**: `Close` 또는 `Adj Close` 열이 누락되거나 DataFrame이 비어 있는 경우, 조용히 로그만 남기고 에러 없이 처리를 중단하여 수집 파이프라인의 전체 붕괴를 예방합니다.
