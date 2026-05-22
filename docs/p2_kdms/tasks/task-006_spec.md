# Task-006: 시가총액 수집 및 전체 스케줄 자동화 완성 명세서

본 문서는 한국 시장 데이터 백엔드(p2_kdms) 프로젝트의 일별 시가총액 수집, 과거 시총 백필(2018년 ~ 현재), 그리고 전체 수집 프로세스의 스케줄 자동화(`AsyncIOScheduler`)와 수동 실행 기능을 구현하기 위한 테스트 명세 및 설계 요구사항을 다룹니다.

한국거래소(KRX) 홈페이지 개편에 따른 pykrx 스크래핑 봇 차단 이슈를 우회하기 위해, 데일리 시가총액은 KIS API 데이터(마스터 상장주식수 × 당일 종가)로 계산하여 적재하고, 과거 시총 백필은 공공데이터포털(금융위원회 주식시세정보 API)을 연동하여 정확한 시계열 데이터를 보장합니다.

---

## 1. 요구사항 및 스콥 (Scope)

### IN Scope
1. **공공데이터 API 클라이언트 (`collectors/pub_data_client.py`)**
   - 공공데이터포털 "금융위원회_주식시세정보 API" (`GetStockSecuritiesInfoService/getStockPriceInfo`) 연동 클라이언트 구현.
   - 지정일의 코스피/코스닥 전 종목 시총 정보(종가, 시가총액, 거래량, 거래대금, 상장주식수)를 일괄 수집 (`numOfRows=5000`, `resultType='json'`).
   - 단축코드 `stk_cd` 6자리 정규화 (예: `A005930` -> `005930`) 및 문자열 숫자의 정수/실수 타입 정형화.
2. **시가총액 저장소 (`repositories/market_cap_repo.py`)**
   - `daily_market_cap` 테이블에 대한 데이터베이스 CRUD 및 누락 정보 관리.
   - `upsert_daily_market_cap`: 일별 시가총액 데이터 벌크 UPSERT (`ON CONFLICT (dt, stk_cd) DO UPDATE SET`).
   - `get_market_cap_missing_dates`: 개장일 대비 `daily_market_cap` 테이블의 데이터 누락 영업일 목록 반환.
3. **데일리 태스크 시가총액 계산 통합 (`tasks/daily_task.py`)**
   - KIS 마스터 파일에서 파싱한 당일 상장주식수(`listed_shares`)와 당일 수집한 KIS OHLCV 종가(`cls_prc`)를 곱하여 시가총액 역산 (`mkt_cap = cls_prc * listed_shares`).
   - 역산된 시가총액 및 당일 시세 정보를 `daily_market_cap` 테이블에 일괄 적재.
4. **과거 시가총액 백필 태스크 (`tasks/backfill_task.py`)**
   - 공공데이터 API 클라이언트를 통해 2018년부터 현재까지의 누락된 일별 시가총액 데이터를 수집 및 복구하는 `run_backfill_market_cap` 함수 구현.
   - `job_statuses` 딕셔너리를 활용하여 진척도( progress, last_log, is_running 등) 상태 기록.
5. **어드민 라우터 및 상태 관리 (`routers/admin.py`)**
   - `POST /api/v1/admin/tasks/{id}/run`: 스케줄러 (`AsyncIOScheduler`)에 `trigger='date'`로 즉시 비동기 실행되도록 job 추가.
   - `GET /api/v1/admin/tasks/{id}/status`: 실행 중인 태스크(daily_update, financial_update, backfill_minute, backfill_market_cap) 상태 조회.
6. **FastAPI Lifespan 스케줄러 등록 (`main.py`)**
   - `AsyncIOScheduler(timezone="Asia/Seoul")` 시작 및 Lifespan 종료 시 자원 회수 (`shutdown`).
   - 3종 Cron 스케줄 활성화:
     - `daily_update`: 월~금 17:10 실행
     - `financial_update`: 토요일 09:00 실행
     - `backfill_minute_data`: 토요일 10:20 실행

### OUT Scope
- KIS 실시간 시세 및 수정계수 계산 알고리즘 자체의 수정 (T-003 범위)
- 재무제표 스크래핑 알고리즘 자체의 수정 (T-004 범위)
- 분봉 백필 수집 상세 로직 수정 (T-005 범위)

---

## 2. 데이터베이스 및 통신 스펙

### 1) 금융위원회_주식시세정보 API (getStockPriceInfo)
- **Endpoint**: `https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo`
- **Method**: `GET`
- **Request Parameters**:
  - `serviceKey`: 공공데이터포털 발급 인증키 (디코딩된 키 권장)
  - `basDt`: 기준일자 (format: `YYYYMMDD`)
  - `numOfRows`: `5000` (전 종목 일괄 처리를 위해 최대 크기 지정)
  - `resultType`: `json`
- **Response Fields mapping**:
  - `srtnCd` -> `stk_cd` (앞 1자리 문자 제거 후 6자리로 정규화)
  - `clpr` -> `cls_prc` (종가, `int`)
  - `mrktTotAmt` -> `mkt_cap` (시가총액, `int`)
  - `trqu` -> `vol` (거래량, `int`)
  - `trPrc` -> `amt` (거래대금, `int`)
  - `lstgStCnt` -> `listed_shares` (상장주식수, `int`)

### 2) `daily_market_cap` 테이블 스펙
```sql
CREATE TABLE IF NOT EXISTS daily_market_cap (
    dt DATE NOT NULL,
    stk_cd VARCHAR(6) NOT NULL,
    cls_prc BIGINT,           -- 종가 (원)
    mkt_cap BIGINT,           -- 시가총액 (원)
    vol BIGINT,               -- 거래량
    amt BIGINT,               -- 거래대금 (원)
    listed_shares BIGINT,     -- 상장주식수
    PRIMARY KEY (dt, stk_cd)
);
```

---

## 3. 테스트 케이스 설계 (TDD 완료 기준)

구현 Agent는 다음 6가지 핵심 테스트 케이스를 통과하도록 테스트 코드와 실제 로직을 작성해야 합니다.

### 1) 정상 동작 테스트 (Happy Path)
- **`test_pub_data_client_fetch_market_cap_success`**
  - [검증]: `PubDataClient`가 모의 공공데이터 API 응답을 받아서 단축코드를 정규화하고 데이터를 정상 파싱하여 기대 형식의 딕셔너리 리스트를 리턴하는지 검증.
- **`test_market_cap_repo_upsert_stores_properly`**
  - [검증]: `MarketCapRepo.upsert_daily_market_cap`에 시가총액 데이터 목록을 전달했을 때, DB에 정상적으로 벌크 UPSERT 처리되는지 검증.
- **`test_daily_task_calculates_and_stores_market_cap`**
  - [검증]: `DailyTask`가 구동될 때 KIS 마스터의 상장주식수(`listed_shares`)와 일봉 종가(`cls_prc`)를 활용해 시가총액을 계산하고 `daily_market_cap` 테이블에 정상적으로 적재하는지 연동 검증.

### 2) 예외 처리 및 경계값 테스트
- **`test_pub_data_client_handles_api_error`**
  - [검증]: 공공데이터 API 호출 과정에서 네트워크 에러나 빈 응답(또는 인증 에러) 발생 시 예외를 전파하거나 로그를 남기고 안전하게 빈 리스트를 반환하는지 검증.
- **`test_backfill_market_cap_runs_and_updates_status`**
  - [검증]: `run_backfill_market_cap` 실행 시 누락일을 조회하여 공공데이터 API에서 가져온 데이터를 적재하고, 전역 `job_statuses`에 진행률, 진행상태, 성공 여부가 올바르게 업데이트되는지 검증.
- **`test_admin_run_task_triggers_scheduler_job`**
  - [검증]: `/api/v1/admin/tasks/{id}/run` 요청 시 실행중인 태스크가 없다면 `scheduler.add_job`을 통해 비동기로 즉시 작업이 추가 및 실행되는지 검증.

---

## 4. Proposed Files (변경 예정 파일 목록)

### [NEW] `collectors/pub_data_client.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/pub_data_client.py)
- 공공데이터포털 API 연동용 REST 클라이언트 구현.

### [NEW] `repositories/market_cap_repo.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/market_cap_repo.py)
- `daily_market_cap` 테이블에 대한 데이터베이스 CRUD 및 누락 영업일 계산 리포지토리.

### [NEW] `routers/admin.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py)
- 태스크 수동 실행 API 및 상태 조회 엔드포인트 구현.

### [MODIFY] `tasks/daily_task.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py)
- 데일리 수집 시 KIS 데이터 기반 시가총액 실시간 계산 및 적재 로직 통합.

### [MODIFY] `tasks/backfill_task.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py)
- 공공데이터 API 기반 역사적 시가총액 데이터 백필 함수 `run_backfill_market_cap` 추가.

### [MODIFY] `main.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py)
- Lifespan 이벤트를 활용한 `AsyncIOScheduler` 초기화 및 3종 Cron 스케줄 활성화, 어드민 라우터 등록.

### [NEW] `tests/test_market_cap_scheduler.py` (file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_market_cap_scheduler.py)
- 공공데이터 API 파싱, 시가총액 적재, 백필 태스크 상태 갱신, 스케줄러 작동 등을 포괄적으로 검증하는 테스트 스위트.

---

## 5. Verification Plan (검증 계획)

- **자동화 테스트**:
  - `PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms:tdms_core conda run --no-capture-output -n tdms_p2_env pytest tdms_core/p2_kdms/tests/test_market_cap_scheduler.py -v`
  - 작성된 테스트 스위트의 모든 테스트 케이스가 통과하는지 확인.
- **수동 검증**:
  - Swagger UI(`/docs`)를 통해 어드민 수동 태스크 실행 API가 올바르게 작동하는지 확인.
  - 실행 후 `daily_market_cap` 테이블에 데이터가 정상 적재되었는지 데이터베이스 커리를 날려 확인.
