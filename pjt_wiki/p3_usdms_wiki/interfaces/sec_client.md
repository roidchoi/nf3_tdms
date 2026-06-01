# SECClient

> 마지막 변경: Task-002-A
> 소스 위치: [sec_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/sec_client.py)

### 1. 개요 및 목적
- SEC EDGAR API와의 통신을 전담하며, SEC의 엄격한 Rate Limit 및 User-Agent 정책을 준수하는 robust한 클라이언트입니다.
- 연관된 문서: [[p3_usdms_wiki/interfaces/master_sync]], [[p3_usdms_wiki/environment]]

### 2. 상세 명세 (요약 금지)

#### 주요 메서드

##### 1. `__init__(self)`
- **동작**: `config.py`의 `SEC_USER_AGENT` 값을 받아 헤더를 설정하고, `requests.Session`을 3회 재시도(429, 500, 502, 503, 504 응답 코드 대상) 및 backoff 정책으로 마운트합니다.
- **제약 조건**: `SEC_USER_AGENT`가 비어 있거나 `sample` 등의 키워드가 포함될 경우 `ValueError`를 유발하여 잘못된 UA로 인한 SEC 차단(403)을 사전에 방지합니다.

##### 2. `get_master_index(self) -> dict[str, dict[str, str]]`
- **동작**: `get_company_tickers()`를 호출하여 CIK(10자리 패딩 문자열)를 Key로 하는 맵 구조로 재구성하여 반환합니다.
- **반환 예시**:
```json
{
  "0000320193": {
    "ticker": "AAPL",
    "name": "Apple Inc."
  }
}
```

##### 3. `get_company_tickers(self) -> dict[str, dict[str, Any]]`
- **동작**: `https://www.sec.gov/files/company_tickers.json`을 호출하여 SEC 전체 상장사 매핑 정보를 수집합니다. (Rate-limiting delay: 0.15s 적용)

##### 4. `get_company_facts(self, cik: str) -> dict[str, Any]`
- **동작**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json`에서 특정 CIK의 raw 재무 데이터를 수집합니다.
- **입력 파라미터**:
  - `cik` (`str`): 10자리 문자열 혹은 정수형 CIK 값 (내부에서 `.zfill(10)` 처리됨).

##### 5. `get_tickers_exchange(self) -> dict[str, str]`
- **동작**: `https://www.sec.gov/files/company_tickers_exchange.json`을 수집하고 파싱하여 Ticker별 소속 거래소를 매핑한 딕셔너리를 반환합니다.
- **반환 예시**:
```json
{
  "AAPL": "NASDAQ",
  "MSFT": "NASDAQ",
  "NYSE": "NYSE"
}
```

##### 6. `get_filings_by_date(self, target_date: Any) -> list[dict[str, Any]]`
- **동작**: SEC daily-index 파일(`company.YYYYMMDD.idx`)을 읽어와 CIK, 서식 타입(Form Type), accession 번호 등을 파싱하여 리스트로 반환합니다.
- **입력 파라미터**:
  - `target_date` (`Any`): `datetime.date`, `datetime.datetime` 또는 `YYYY-MM-DD`, `YYYYMMDD` 포맷 문자열.
- **반환 예시**:
```json
[
  {
    "cik": 320193,
    "form_type": "10-K",
    "accession": "edgar/data/320193/0000320193-20-000096.txt"
  }
]
```

### 3. 주의사항 및 의존성
- **SEC Rate Limit**: SEC EDGAR API 규정상 초당 10회(10 requests per second) 이상의 요청을 보낼 경우 IP가 일시 차단될 수 있습니다. `_enforce_rate_limit()`가 초당 최대 ~6.6회(0.15s 딜레이)로 제한하고 있으므로, 멀티스레드나 멀티프로세스로 해당 클라이언트를 다중 기동 시 주의가 필요합니다.
- **User-Agent 정보 필수**: 환경변수 `SEC_USER_AGENT`에 `회사명 연락처메일` 형태로 실제 메일 주소와 기관명이 작성되어야 차단 위험이 없습니다.
