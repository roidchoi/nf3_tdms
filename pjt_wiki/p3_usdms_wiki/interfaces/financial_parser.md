# Interface: FinancialParser

SEC XBRL 원시 정보를 수집하고 가공하여 표준 재무 및 주식 수 이력을 도출하는 파이프라인 엔진입니다.

> **파일 경로**: `tdms_core/p3_usdms/collectors/financial_parser.py`
> **마지막 업데이트**: 2026-07-17

---

## 1. 개요
SEC EDGAR API로부터 특정 기업의 전체 재무 팩츠 데이터셋을 수집한 뒤, 주식 수 이력을 먼저 정제해 `us_share_history`에 저장합니다.
그 후 US-GAAP에 공시된 로우 데이터(EAV)를 `us_financial_facts`에 덮어쓰고, 회계적 분기 정보(10-K, 10-Q)를 이산화 역산 알고리즘(`_standardize_financials_v2`)에 통과시켜 정제 완료된 분석 표준 재무 데이터를 `us_standard_financials`에 적재합니다.
개선 이후, 실제 DB에 **신규 데이터 적재가 발생한 CIK 리스트를 식별하여 반환**함으로써, `MetricCalculator`가 필요한 종목만 핀포인트로 비율 연산을 수행하도록 지원합니다.

---

## 2. API Reference

### `FinancialParser.process_company(cik: str) -> bool`
단일 CIK 기업에 대한 전체 수집/정제/적재 파이프라인을 구동합니다.
1. `SECClient`를 이용해 facts fetch
2. DEI 데이터를 활용한 주식 수 이력 추출 및 저장
3. `us_financial_facts` EAV 벌크 교체 저장
4. `_standardize_financials_v2`를 활용한 표준 재무 도출 및 적재

- **Parameters**:
  - `cik` (str): 10자리 CIK 식별자
- **Returns**: `bool` - 실제 데이터베이스 `us_standard_financials`에 신규 표준 재무 레코드가 적재(Upsert)되었을 시 `True`, 이미 데이터가 있거나 수집/적재 실패 시 `False`
- **Exceptions**: `Exception` 발생 시 로그로 에러가 기록되며 호출 측의 `run` 루프에서 격리됩니다.

### `FinancialParser.run(ciks: List[str]) -> Tuple[int, List[str]]`
여러 CIK 목록을 받아서 순차적으로 파이프라인 처리를 수행합니다. Rate Limit 지연(0.5초)이 내장되어 있습니다.

- **Parameters**:
  - `ciks` (List[str]): CIK 리스트
- **Returns**: `Tuple[int, List[str]]` - `(성공적으로 처리를 끝마친 수집 카운트, 실제 DB에 표준 재무 데이터 적재/변동이 일어난 ingested_ciks 리스트)`

### `FinancialParser._standardize_financials_v2(cik: str, raw_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
(fy, fp) 조합으로 그룹화하여 Balance Sheet의 Instant 정보와 Income Statement / Cash Flow의 Duration 정보를 결합하고, YTD 누적값 차감을 통해 순수 분기별 이산치(Discrete Quarter)를 계산합니다.

- **Parameters**:
  - `cik` (str): 기업 CIK
  - `raw_facts` (List[Dict[str, Any]]): EAV 로우 facts 목록
- **Returns**: `List[Dict[str, Any]]` - `us_standard_financials` 테이블 스키마에 부합하는 정제 레코드 목록
