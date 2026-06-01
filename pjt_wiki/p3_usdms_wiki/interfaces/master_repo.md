# MasterRepo

> 마지막 변경: Task-002-A
> 소스 위치: [master_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/master_repo.py)

### 1. 개요 및 목적
- `us_ticker_master` 및 `us_ticker_history` 테이블에 안전하게 액세스하고 데이터 조작을 전담하는 Repository 레이어 컴포넌트입니다.
- 연관된 문서: [[p3_usdms_wiki/interfaces/master_sync]]

### 2. 상세 명세 (요약 금지)

#### 주요 메서드

##### 1. `get_active_tickers(self) -> list[dict]`
- **동작**: `us_ticker_master` 테이블에서 현재 활성화된(`is_active = TRUE`) 모든 종목 정보를 리스트로 조회합니다.

##### 2. `get_collect_targets(self) -> list[dict]`
- **동작**: `us_ticker_master` 테이블에서 수집 대상으로 지정된(`is_collect_target = TRUE`) 모든 종목 정보를 리스트로 조회합니다.

##### 3. `get_ticker_history(self, cik: str) -> list[dict]`
- **동작**: 특정 CIK의 티커 변경 이력을 날짜 오름차순(`start_dt ASC`)으로 정렬하여 반환합니다.

##### 4. `get_cik_by_ticker(self, ticker: str) -> Optional[str]`
- **동작**: 최신 티커명을 기준으로 연결된 CIK(10자리 패딩 문자열)를 역조회합니다. 없는 경우 `None`을 반환합니다.

---

#### DB 테이블 스키마 명세

##### 1. `us_ticker_master`
| 컬럼명 | SQL 타입 | Python 타입 | 제약 조건 | 설명 |
|---|---|---|---|---|
| `cik` | `VARCHAR(10)` | `str` | `PRIMARY KEY` | SEC 고유 식별자 (10자리 패딩) |
| `latest_ticker` | `VARCHAR(20)` | `str` | `NOT NULL` | 대표/최신 티커 심볼 |
| `latest_name` | `VARCHAR(255)` | `str` | `NOT NULL` | 기업 영문 정식 명칭 |
| `exchange` | `VARCHAR(20)` | `str` | - | 정규화된 소속 거래소 |
| `sector` | `VARCHAR(100)` | `str` | - | yfinance 기반 섹터 분류 |
| `industry` | `VARCHAR(255)` | `str` | - | yfinance 기반 산업군 분류 |
| `country` | `VARCHAR(100)` | `str` | - | 국가 명칭 |
| `quote_type` | `VARCHAR(50)` | `str` | - | 종목의 자산 구분 (예: EQUITY) |
| `market_cap` | `NUMERIC(20, 2)` | `Decimal` / `float` | - | yfinance 기반 시가 총액 ($) |
| `current_price` | `NUMERIC(12, 4)` | `Decimal` / `float` | - | 대표/최신 가격 ($) |
| `is_active` | `BOOLEAN` | `bool` | `DEFAULT TRUE` | 상장 유지 여부 |
| `is_collect_target` | `BOOLEAN` | `bool` | `DEFAULT FALSE` | 일일 수집(OHLCV 등) 대상 여부 |
| `created_at` | `TIMESTAMP` | `datetime` | `DEFAULT NOW()` | 데이터 적재일시 |
| `updated_at` | `TIMESTAMP` | `datetime` | `DEFAULT NOW()` | 최종 수정일시 |

##### 2. `us_ticker_history`
| 컬럼명 | SQL 타입 | Python 타입 | 제약 조건 | 설명 |
|---|---|---|---|---|
| `cik` | `VARCHAR(10)` | `str` | `PRIMARY KEY` (복합) | SEC 고유 식별자 |
| `ticker` | `VARCHAR(20)` | `str` | `PRIMARY KEY` (복합) | 해당 기간의 티커 심볼 |
| `start_dt` | `DATE` | `date` | `PRIMARY KEY` (복합) | 변경 이력 시작일 (포함) |
| `end_dt` | `DATE` | `date` | `DEFAULT '9999-12-31'` | 변경 이력 종료일 (포함) |

### 3. 주의사항 및 의존성
- **CIK 자릿수 패딩**: DB 저장 및 조회를 보장하기 위해 CIK 인자는 항상 10자리 문자열(`.zfill(10)`)이어야 합니다.
- **SCD Type 2의 유효 기간(end_dt)**: 현재 유효한 티커의 이력은 `end_dt = '9999-12-31'`을 기본값으로 가집니다.
