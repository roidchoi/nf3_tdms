# Valuation Repo (valuation_repo.py)

> 마지막 변경: Task-004
> 소스 위치: `tdms_core/p3_usdms/repositories/valuation_repo.py:1`

### 1. 개요 및 목적
- 미국 주식의 가치평가(Valuation) 및 재무비율(Metrics) 계산에 필요한 일별 가격, 주식수 이력, 표준재무 데이터를 DB에서 읽어오고 연산 결과를 Upsert하는 데이터베이스 I/O 캡슐화 레이어입니다.
- 연관된 문서: [[p3_usdms_wiki/interfaces/valuation_engine]], [[migration-pjt/ref_usdms_wiki/interfaces/db_schema]]

### 2. 상세 명세 (요약 금지)

#### 주요 함수 명세
1. **`load_prices(cik: str, start_date: str = None) -> List[Dict]`**:
   - `us_daily_price` 테이블에서 특정 CIK의 날짜(`dt`) 및 종가(`cls_prc`)를 조회합니다.
   - 반환타입: `List[Dict]` (`dt`, `cls_prc` 포함)

2. **`load_shares(cik: str) -> List[Dict]`**:
   - `us_share_history` 테이블에서 CIK의 공시일(`filed_dt`)별 총 발행주식 수(`val`)를 조회합니다.
   - 반환타입: `List[Dict]` (`filed_dt`, `val` 포함)

3. **`load_financials(cik: str) -> List[Dict]`**:
   - `us_standard_financials` 테이블에서 가치평가 및 비율 계산에 필요한 모든 재무 데이터 및 기본 발행주식 수(`shares_outstanding`)를 조회합니다.
   - 반환타입: `List[Dict]`

4. **`save_valuations(valuations: List[Tuple])`**:
   - `us_daily_valuation` 테이블에 가치평가 데이터를 50건 단위 배치로 나누어 Upsert합니다.
   - 쿼리: `ON CONFLICT (dt, cik) DO UPDATE SET ...`

5. **`save_metrics(metrics: List[Tuple])`**:
   - `us_financial_metrics` 테이블에 재무비율 및 성장률 데이터를 일괄 Upsert합니다.

6. **`get_all_latest_valuation_dates(ciks: List[str]) -> Dict[str, Any]`**:
   - CIK 목록에 대한 최신 가치평가 계산 일자(`dt`)를 한 번에 조회하여 딕셔너리로 반환합니다.

7. **`get_all_latest_financial_filed_dates(ciks: List[str]) -> Dict[str, Any]`**:
   - CIK 목록에 대한 최신 표준재무 공시일(`filed_dt`)을 한 번에 조회하여 딕셔너리로 반환합니다.

8. **`get_all_latest_metric_filed_dates(ciks: List[str]) -> Dict[str, Any]`**:
   - CIK 목록에 대한 최신 재무비율 계산 대상 공시일(`filed_dt`)을 한 번에 조회하여 딕셔너리로 반환합니다.

### 3. 주의사항 및 의존성
- TimescaleDB Chunk Lock Contention을 피하기 위해 `save_valuations` 수행 시 데이터를 50건씩 분할하여 배치 처리합니다.
- `np.nan`, `np.inf` 등의 결측치가 SQL 쿼리로 흘러가지 않도록 파이썬 `None`으로 엄격히 매핑하는 `clean_val` 헬퍼가 필수 적용됩니다.
