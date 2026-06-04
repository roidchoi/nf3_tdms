# USDMS Data API Endpoints

미국 시장 데이터 백엔드(`p3_usdms`)에서 데이터 조회(REST API) 서비스를 제공하는 엔드포인트 7종의 사양서입니다.

---

## 1. 개요
- **베이스 경로**: `/api/data`
- **목적**: 수집 완료된 미국 주식 마스터, 일봉 시세, 가격 수정계수, PIT 표준재무, 일별 가치평가 및 재무비율 지표를 제어/조회할 수 있는 RESTful 인터페이스 제공.
- **성능 방어**: 
  - 특정 기간 조회 API(`price/daily`, `valuation`, `metrics`)에 대해 기본 조회 범위(1년) 및 최대 제한 조회 범위(15년)를 강제 적용(Throttling).
  - 테이블 미리보기 엔드포인트(`preview/{table}`) 호출 시 최대 페이징 제한(1000건) 적용 및 SQL Injection 보안 가드가 구축됨.

---

## 2. API 상세 명세

### ① 미국 주식 마스터 조회
- **엔드포인트**: `GET /api/data/tickers`
- **쿼리 파라미터**:
  - `exchange` (Optional): 특정 거래소 필터 (예: `NASDAQ`, `NYSE`)
  - `is_collect_target` (Optional): 수집 대상 여부 필터 (`true`/`false`)
- **설명**: 활성화된 미국 주식 종목 정보를 조회합니다. 파라미터가 없으면 활성화된 모든 종목을 반환합니다.

### ② 일봉 OHLCV 시세 조회 (온더플라이 보정 지원)
- **엔드포인트**: `GET /api/data/price/daily`
- **쿼리 파라미터**:
  - `cik` (MANDATORY): SEC CIK 번호 (10자리 zero-padded 문자열)
  - `start_dt` (Optional): 시작일 (`YYYY-MM-DD`, 미지정 시 최근 1년)
  - `end_dt` (Optional): 종료일 (`YYYY-MM-DD`, 미지정 시 오늘)
  - `adjusted` (Optional, Default: `false`): 수정주가 보정 여부
- **동작 특징**:
  - `adjusted=true` 요청 시, 주가 데이터와 가격 수정계수를 결합하여 역순 누적곱 연산을 수행합니다. Ex-Date 이전 시세에 누적수정계수가 온더플라이로 곱해집니다.
  - 시작/종료일이 지정되지 않으면 기본 1년을 대입하며, 조회 기간이 15년을 초과할 경우 `400 Bad Request` 에러를 반환합니다.
  - `Accept: application/vnd.apache.arrow.stream` 요청 헤더 감지 시 Apache Arrow Stream IPC 바이너리로 인코딩하여 스트리밍 전달합니다.

### ③ 가격 수정계수 이력 조회
- **엔드포인트**: `GET /api/data/price/factors`
- **쿼리 파라미터**:
  - `cik` (MANDATORY): SEC CIK 번호
- **설명**: 특정 종목에 발생한 액면분할, 병합 등 가격 수정 이벤트(Adjustment Factors)의 전체 이력을 조회합니다.

### ④ 표준화 재무제표 조회 (Point-in-Time 지원)
- **엔드포인트**: `GET /api/data/financials`
- **쿼리 파라미터**:
  - `cik` (MANDATORY): SEC CIK 번호
  - `pit` (Optional, Default: `true`): Point-in-Time 조회 활성화 여부
  - `as_of_date` (Optional): PIT 조회 기준 시각 (ISO 형식 또는 `YYYY-MM-DD`, 미입력 시 현재 시각)
  - `start_dt` (Optional): 범위 조회 시 시작일 (`YYYY-MM-DD`, `pit=false`일 때 사용)
  - `end_dt` (Optional): 범위 조회 시 종료일 (`YYYY-MM-DD`, `pit=false`일 때 사용)
- **설명**: 
  - `pit=true` 시 look-ahead bias 방지를 위해 `filed_dt <= as_of_date` 인 데이터 중 report_period별 최신 공시본만 `DISTINCT ON`으로 추려냅니다.
  - `pit=false` 시 공시일 기준으로 기간 필터 범위 조회를 수행합니다.

### ⑤ 일별 가치평가 지표 조회
- **엔드포인트**: `GET /api/data/valuation`
- **쿼리 파라미터**:
  - `cik` (MANDATORY): SEC CIK 번호
  - `start_dt` / `end_dt` (Optional): 조회 기간 지정 (기본 1년, 최대 15년 제한)
- **설명**: PE, PB, PS, PCR, EV/EBITDA 등 매일 계산되는 가치평가 배수 데이터의 시계열을 조회합니다. (Apache Arrow Stream 직렬화 지원)

### ⑥ 분기별 재무비율 조회
- **엔드포인트**: `GET /api/data/metrics`
- **쿼리 파라미터**:
  - `cik` (MANDATORY): SEC CIK 번호
  - `start_dt` / `end_dt` (Optional): 조회 기간 지정 (기본 1년, 최대 15년 제한)
- **설명**: ROE, ROA, ROIC, 영업이익률, 순이익률, 부채비율, 성장률(YoY) 등의 분기별 재무비율 목록을 조회합니다. (Apache Arrow Stream 직렬화 지원)

### ⑦ 데이터베이스 테이블 미리보기 (Preview)
- **엔드포인트**: `GET /api/data/preview/{table}`
- **패스 파라미터**:
  - `table`: 조회할 테이블명 (아래 `ALLOWED_TABLES` 화이트리스트 10종에 한정)
- **쿼리 파라미터**:
  - `limit` (Optional, Default: `50`, Max Cap: `1000`)
  - `offset` (Optional, Default: `0`)
  - `stk_cd` (Optional): CIK 또는 ticker 등의 특정 종목 필터 조건
  - `start_date` / `end_date` (Optional): 날짜 컬럼을 보유한 테이블에 대한 범위 필터
- **보안 및 제약**:
  - **SQL Injection 방지**: 테이블 화이트리스트 검증 및 SQL의 모든 조건 필터는 바인딩 파라미터(`%s`)로만 대입합니다.
  - **허용된 테이블 목록**:
    `us_ticker_master`, `us_ticker_history`, `us_collection_blacklist`, `us_financial_facts`, `us_standard_financials`, `us_share_history`, `us_daily_price`, `us_price_adjustment_factors`, `us_daily_valuation`, `us_financial_metrics`
