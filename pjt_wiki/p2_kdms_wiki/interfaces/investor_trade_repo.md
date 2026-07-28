# InvestorTradeRepo Interface

`InvestorTradeRepo`는 한국 주식 투자자 매매동향(일별 수급) 데이터를 저장하고 관리하기 위한 데이터베이스 액세스 계층(Repository) 인터페이스입니다.

## 파일 위치
- `tdms_core/p2_kdms/repositories/investor_trade_repo.py`

## 주요 클래스 및 메서드 시그니처

### `InvestorTradeRepo`
```python
class InvestorTradeRepo:
    def __init__(self, pool) -> None: ...
```

#### 1. `upsert_daily_investor_trade(self, data: List[Dict[str, Any]]) -> int`
한국투자증권(KIS) API로부터 파싱 및 수집된 일별 투자자 매매동향 데이터를 `daily_investor_trade` 테이블에 벌크 **UPSERT**합니다.
*   **작동 방식**:
    *   102개 컬럼 전체를 대상으로 벌크 바인딩하여 `INSERT INTO daily_investor_trade (...) VALUES %s` 수행.
    *   중복 발생 시 `ON CONFLICT (dt, stk_cd) DO UPDATE` 분기를 타고 `dt`, `stk_cd`를 제외한 100개 수급 지표 컬럼을 최신 값으로 업데이트합니다.
*   **파라미터**:
    *   `data`: 한국 주식 수급 지표 102개 컬럼이 정형화된 dict 구조의 list.
*   **반환값**:
    *   저장된 레코드 개수 (`int`)

#### 2. `get_active_symbols_for_date(self, dt: date) -> List[str]`
지정된 날짜(`dt`)가 포함된 분기(예: `2026Q3`)의 분봉 수집 대상 종목코드 리스트를 `minute_target_history` 테이블로부터 중복 없이 조회합니다.
*   **작동 방식**:
    *   주어진 `dt` 날짜 정보에 맞춰 `YYYYQ{1-4}` 형식의 분기 문자열을 동적 산출하고, 해당 분기에 속한 모든 활성 symbol을 반환합니다.
*   **파라미터**:
    *   `dt`: 조회 기준이 되는 영업일 날짜 객체 (`date`)
*   **반환값**:
    *   종목코드 리스트 (`List[str]`)

#### 3. `get_daily_investor_trade(self, stk_cd: str, start_date: date, end_date: date) -> List[Dict[str, Any]]`
[NEW] 특정 종목의 지정 기간 내 일별 투자자 매매동향 데이터를 데이터베이스에서 조회하여 오름차순(`dt ASC`)으로 반환합니다.
*   **작동 방식**:
    *   `daily_investor_trade` 테이블에서 `stk_cd` 및 `dt BETWEEN start_date AND end_date` 조건으로 조회합니다.
    *   결과 필드 디스크립터(`cur.description`)를 매핑하여 DB 레코드를 동적으로 `dict` 데이터 구조로 맵핑 및 가공하여 리턴합니다.
*   **파라미터**:
    *   `stk_cd`: 대상 주식 종목코드 (`str`)
    *   `start_date`: 조회 시작 날짜 (`date`)
    *   `end_date`: 조회 종료 날짜 (`date`)
*   **반환값**:
    *   각 날짜별 102개 수급 컬럼 값이 담긴 결과 딕셔너리 리스트 (`List[Dict[str, Any]]`)
