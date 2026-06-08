# 인터페이스: KisUSClient (kis_us_client.md)

> **파일명**: `tdms_core/p3_usdms/collectors/kis_us_client.py`  
> **상속 클래스**: `p1_shared.api.kis_api_core.KisApiCore`  
> **마지막 업데이트**: 2026-06-01 (Task-002-B)  

---

## 1. 개요
한국투자증권(KIS) 해외 주식 REST API를 통해 미국의 특정 주식 일일 가격(OHLCV) 및 수정주가 매칭용 종가를 조회하기 위한 인터페이스입니다. `KisApiCore`의 자동 토큰 발급 및 재시도 메커니즘을 상속받아 사용합니다.

---

## 2. 주요 메서드 시그니처

### `get_ohlcv`
yfinance 스타일의 일일 주가 및 수정 종가 데이터를 포함하는 `pd.DataFrame`을 반환합니다.

```python
def get_ohlcv(
    self, 
    ticker: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    exchange: Optional[str] = None, 
    add_adjusted: bool = True
) -> pd.DataFrame
```

- **매개변수**:
  - `ticker`: 종목 코드 (예: `AAPL`, `BRK-B`). 내부적으로 하이픈(-)은 KIS 호환을 위해 슬래시(`/`)로 변환됩니다.
  - `start_date`: 시작 일자 (`YYYYMMDD`). 기본값은 `"19800101"` 입니다.
  - `end_date`: 종료 일자 (`YYYYMMDD`). 기본값은 오늘 날짜입니다.
  - `exchange`: 해외 주식 거래소 코드 (`NAS`, `NYS`, `AMS`). 생략 시 `_find_exchange`가 자동 탐색을 실행합니다.
  - `add_adjusted`: `True`일 경우 수정 종가(`Adj Close`) 칼럼을 포함하기 위해 KIS API를 추가(MODP='1') 조회하여 병합합니다.
- **반환값**: Index가 `Date`이고 `['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']` 열을 포함하는 DataFrame을 반환합니다.

---

## 3. 내부 도우미 메서드

### `_find_exchange`
거래소가 정의되지 않았을 때 주요 거래소(`NAS` -> `NYS` -> `AMS`)를 순차 탐색하여 실제 종목이 존재하는 거래소를 찾아 반환합니다.
```python
def _find_exchange(self, ticker: str) -> Optional[str]
```

### `_fetch_chunk`
KIS API 해외주식 기간별시세 TR(`HHDFS76240000`)에 대해 1회 최대 100건 단위의 데이터 청크 조회를 요청합니다.
```python
def _fetch_chunk(self, ticker: str, exchange: str, base_date: str, mod_yn: str) -> list[dict]
```

### `_collect_period_data`
지정된 시작일부터 종료일 범위의 가격을 100개 단위로 페이지네이션하며 수집하여 정렬된 DataFrame으로 가공합니다.
```python
def _collect_period_data(self, ticker: str, exchange: str, start_date: str, end_date: str, mod_yn: str) -> pd.DataFrame
```
