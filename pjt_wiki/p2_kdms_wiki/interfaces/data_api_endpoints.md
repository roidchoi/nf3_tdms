# Interface: Data API Endpoints (routers/data.py)

> **파일**: `tdms_core/p2_kdms/routers/data.py`
> **라우터 prefix**: `/api/data`
> **관련**: `[[p2_kdms_wiki/interfaces/ohlcv_repo.md]]`, `[[p2_kdms_wiki/interfaces/financial_repo.md]]`, `[[interfaces/factor_repo.md]]`, `[[p2_kdms_wiki/decisions/dec-001_pit_financial_pattern.md]]`

---

## 의존성 주입 패턴

```python
# app.state.pool → 각 레포지토리 팩토리
def get_db_pool(request: Request) -> DbConnectionPool | None
def get_master_repo(pool = Depends(get_db_pool)) -> MasterRepo
def get_factor_repo(pool = Depends(get_db_pool)) -> FactorRepo
def get_ohlcv_repo(pool = Depends(get_db_pool)) -> OhlcvRepo
def get_financial_repo(pool = Depends(get_db_pool)) -> FinancialRepo
```

---

## 엔드포인트 명세

### `GET /api/data/stocks`
- **T-번호**: T-002
- **응답**: `List[Dict[str, Any]]` — 전체 활성 종목 리스트
- **내부 호출**: `MasterRepo.get_all_active_stocks()`

---

### `GET /api/data/factors/{stk_cd}`
- **T-번호**: T-003
- **Query Params**: `price_source: str = "KIS"`
- **응답**: `List[Dict[str, Any]]` — 수정계수 이력 리스트
- **내부 호출**: `FactorRepo.get_factors_for_stock(stk_cd, price_source)`

---

### `GET /api/data/ohlcv/daily/adjusted`
- **T-번호**: T-003
- **Query Params**:
  - `stk_cd: str` (필수)
  - `start_date: str` (YYYY-MM-DD)
  - `end_date: str` (YYYY-MM-DD)
  - `price_source: str = "KIS"`
- **원리**: **On-the-fly** 계산 — `OhlcvRepo.get_daily_ohlcv()` + `FactorRepo.get_factors_for_stock()` → `event_dt > dt`인 팩터 누적곱
- **응답 딕셔너리 키**: `stk_cd`, `dt(str:YYYY-MM-DD)`, `open(int)`, `high(int)`, `low(int)`, `close(int)`, `volume(int)`, `adj_factor(float)`

---

### `GET /api/data/ohlcv/adjusted/{stk_cd}`
- **T-번호**: T-003
- **Query Params**: `start_date`, `end_date` (YYYY-MM-DD)
- **원리**: **물리 테이블 직접 조회** — `OhlcvRepo.get_adjusted_ohlcv_direct()` → `daily_ohlcv_adjusted` 테이블
- **응답 딕셔너리 키**: `stk_cd`, `dt(str)`, `open(int)`, `high(int)`, `low(int)`, `close(int)`, `volume(int)`, `adj_factor(float)`

> 💡 두 가지 수정주가 엔드포인트의 차이:  
> - `/daily/adjusted`: On-the-fly 실시간 계산 (항상 최신 팩터 반영)  
> - `/adjusted/{stk_cd}`: 물리 테이블 직접 쿼리 (빠르지만 마지막 refresh 시점 기준)

---

### `GET /api/data/financials`
- **T-번호**: T-004
- **Query Params**:
  - `stk_cd: str` (필수)
  - `as_of_date: str` (선택, ISO 형식 또는 YYYY-MM-DD, alias=`as_of`)
  - `div_cls_code: str = "1"` (`"1"` 분기, `"0"` 연간)
- **as_of 파싱 순서**: `datetime.fromisoformat()` → 실패 시 `YYYY-MM-DD` + KST 자정 변환
- **응답**: `{"statements": List[Dict], "ratios": List[Dict]}`
- **내부 호출**:
  - `FinancialRepo.get_statements_as_of(stk_cd, div_cls_code, as_of_dt)`
  - `FinancialRepo.get_ratios_as_of(stk_cd, div_cls_code, as_of_dt)`
- **직렬화**: `retrieved_at` → `.isoformat()` 변환 후 반환

---

### `GET /api/data/preview/{table}`
- **T-번호**: T-007
- **패스 파라미터**:
  - `table`: 조회할 테이블명 (아래 `ALLOWED_TABLES` 화이트리스트 10종에 한정)
- **쿼리 파라미터**:
  - `limit` (Optional, Default: `50`, Max Cap: `1000`)
  - `offset` (Optional, Default: `0`)
  - `stk_cd` (Optional): 종목코드 필터 조건
  - `start_date` / `end_date` (Optional): 날짜 범위 필터
  - `quarter` (Optional): 분기 필터 (예: `2026Q1`)
  - `market` (Optional): 시장구분 필터 (`KOSPI` / `KOSDAQ`)
  - `keyword` (Optional): 종목 검색용 키워드
  - `match_type` (Optional, Default: `'contains'`): 일치 방식 (`'contains'` | `'exact'`)
  - `search_field` (Optional, Default: `'all'`): 검색 범위 (`'all'` | `'code'` | `'name'`)
- **보안 및 제약**:
  - **SQL Injection 방지**: 테이블 화이트리스트 검증 및 SQL 바인딩 파라미터 적용.
  - **허용된 테이블 목록**:
    `stock_info`, `trading_calendar`, `daily_ohlcv`, `daily_ohlcv_adjusted`, `market_cap_by_date`, `financial_statements`, `financial_ratios`, `system_milestones`, `minute_target_history`, `minute_ohlcv_target`
