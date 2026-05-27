# Task-007: 조회 API 완성 + Blacklist 패턴 명세서

> **Task ID**: T-007
> **Phase**: Phase 3 — API 완성
> **의존성**: T-006 완료 필요
> **상태**: 대기
> **작성일**: 2026-05-27

본 문서는 p2_kdms의 미구현 데이터 조회 API 5종(`/ohlcv/daily`, `/ohlcv/minute`, `/market-cap`, `/screening`, `/preview/{table}`)과 Blacklist 패턴(수집 실패 종목 관리 + `daily_task.py` skip 로직 교체), `ops/` 레거시 정리를 구현하기 위한 테스트 명세입니다.

> **[조회 품질 보강 사유]** 분봉(`minute_ohlcv`)은 종목당 1일 390행, 100종목 × 30일 = **최대 117만 행**에 달하므로 `fetchall()` 방식은 메모리 OOM 위험이 있습니다. 원본 KDMS `v7.0`은 이를 **Apache Arrow 이진 직렬화 + 날짜 범위 제한**으로 대응했습니다. p2_kdms는 동일 수준 이상의 조회 품질을 보장해야 합니다. 세부 규칙은 **§2.G 조회 품질 정책**에 정의합니다.

---

## 1. 요구사항 및 스콥 (Scope)

### IN Scope

#### A. 데이터 조회 API 완성 (`routers/data.py` 확장)

| API | Path | 구현 상태 |
|---|---|---|
| `GET /api/data/ohlcv/daily` | Raw 일봉 (raw/adjusted 선택 파라미터) | ❌ 미구현 |
| `GET /api/data/ohlcv/minute` | 분봉 OHLCV | ❌ 미구현 |
| `GET /api/data/market-cap` | 시가총액 조회 | ❌ 미구현 |
| `POST /api/data/screening` | 재무 스크리닝 (PIT 기준) | ❌ 미구현 |
| `GET /api/data/preview/{table}` | 테이블 미리보기 (p4_manager 연동용) | ❌ 미구현 |

- `GET /stocks`, `GET /factors/{stk_cd}`, `GET /ohlcv/daily/adjusted`, `GET /ohlcv/adjusted/{stk_cd}`, `GET /financials` — **이미 구현됨 (T-002~T-004)**

#### B. Repo 메서드 신규 구현

- **`OhlcvRepo.get_minute_ohlcv(stk_cd, start_dt_tm, end_dt_tm)`**: `minute_ohlcv` 테이블 조회
- **`MarketCapRepo.get_daily_market_cap(stk_cd, start_date, end_date)`**: `daily_market_cap` 테이블 조회
- **`FinancialRepo.screen_stocks(params: ScreeningParams) -> list[dict]`**: DB 레벨 동적 SQL(CTE + RANK() 윈도우) 방식으로 재무 스크리닝. in-memory 필터 방식 사용 **금지** (전체 종목 조회 후 Python 필터는 메모리/응답 시간 모두 비효율).

#### C. Blacklist 패턴 도입 (`daily_ohlcv_gap` 기반)

현재 `daily_task.py`는 수집 실패 시 `record_gap()` 호출로 `daily_ohlcv_gap` 테이블에 실패를 기록합니다.  
목표는 **연속 실패 N회 이상 종목을 "일시 skip" 대상으로 판단**하여 다음 수집 사이클에서 건너뛰는 로직입니다.

- **`OhlcvRepo.get_blacklisted_stocks(threshold_days)`**: `daily_ohlcv_gap`에서 최근 `threshold_days`일 연속으로 실패 기록이 있는 종목 코드 목록 반환
- **`DailyTask.run()`**: 수집 루프 시작 전 blacklist 종목 조회 후 skip. skip 로그 및 결과 dict에 `skipped` 카운트 반영

#### D. `ops/` 레거시 정리 (REFACTOR-3)

현재 `ops/` 폴더에는 개발 도중 생성된 비공식 스크립트(`run_financial_manual.py`, `verify_nulls.py` 등)가 혼재합니다.  
PRD §6(목표 디렉토리 구조)에서 정의한 공식 `ops/` 진입점만 남기고 정리합니다.

- 유지 대상: `backfill_pipeline.py`, `check_db.py`, `cleanup_database.py`, `pre_migration_backup.py`, `run_monthly_backfill.py` (현재 있는 파일은 그대로 유지)
- 정리 대상: 레거시 또는 임시 스크립트는 별도 `ops/_archive/` 폴더로 이동하거나 삭제 (사용자 확인 후)

### OUT Scope

- `/api/health/*`, `/api/admin/schedules`, `WS /ws/logs` — **T-008 범위**
- p4_manager 연동 테스트 — **T-009 범위**
- 수정계수 계산 로직 변경 — **T-003 완료**
- 분봉 수집 로직 변경 — **T-005 완료**

---

## 2. 핵심 인터페이스 스펙

### A. GET /api/data/ohlcv/daily

```
Query Params:
  stk_cd: str (필수)
  start_date: str YYYY-MM-DD (필수)
  end_date: str YYYY-MM-DD (필수)
  adjusted: bool = False  ("true" 시 On-the-fly 수정주가 반환, "false" 시 raw 반환)
  price_source: str = "KIS"

응답: List[Dict]
  adjusted=False 시 키: stk_cd, dt(str), open, high, low, close, volume
  adjusted=True 시 키: stk_cd, dt(str), open, high, low, close, volume, adj_factor
```

> 💡 `adjusted=True`는 기존 `/ohlcv/daily/adjusted` On-the-fly 계산 로직과 동일. 두 엔드포인트를 통합하는 패턴.

### B. GET /api/data/ohlcv/minute

> ⚠️ **메모리 안전 제약**: 분봉은 최악의 경우 1종목 30일 × 390행/일 = **11,700행** / 100종목 시 **117만 행**. 날짜 범위 상한 및 행 수 상한을 **API 레이어에서 강제**해야 합니다.

```
Query Params:
  stk_cd: str (필수)
  start_dt: str YYYY-MM-DD 또는 ISO 형식 (필수)
  end_dt: str (필수)
  accept: Header (선택) — "application/vnd.apache.arrow.stream" 시 Arrow 이진 응답

날짜 범위 제한:
  end_dt - start_dt > 30일 → HTTP 400 즉시 반환 ("분봉 조회는 최대 30일 범위까지 가능합니다")

응답 (기본: JSON):
  키: stk_cd, dt_tm(str ISO 8601+KST), open(int), high(int), low(int), close(int), volume(int)

응답 (Arrow): Accept: application/vnd.apache.arrow.stream 헤더 시
  media_type: "application/vnd.apache.arrow.stream" → StreamingResponse(pyarrow IPC)
  동일 데이터를 이진 포맷으로 직렬화 (JSON 대비 ~60~80% 크기 절감, 파싱 10배 이상 빠름)
```

**`OhlcvRepo.get_minute_ohlcv()` 신규 메서드:**
```python
def get_minute_ohlcv(self, stk_cd: str, start_dt_tm: datetime, end_dt_tm: datetime) -> list[dict]
# 테이블: minute_ohlcv
# 조건: stk_cd = %s AND dt_tm BETWEEN %s AND %s ORDER BY dt_tm ASC
# 반환 키: stk_cd(str), dt_tm(datetime), open(int), high(int), low(int), close(int), volume(int)
# Anti-Pandas: pandas.DataFrame 변환 금지. cursor.fetchall() → list comprehension으로 직접 처리
```

**Apache Arrow 응답 헬퍼 (`routers/data.py` 내부):**
```python
def _format_response_arrow_or_json(data: list[dict], accept_header: str | None, json_payload):
    """Accept 헤더 기반으로 Apache Arrow 또는 JSON 반환"""
    if accept_header and "arrow" in accept_header.lower():
        import pyarrow as pa
        import pyarrow.ipc as ipc
        import io
        # data가 비어있으면 빈 스트림 반환
        sink = io.BytesIO()
        if data:
            table = pa.Table.from_pydict({k: [r[k] for r in data] for k in data[0]})
        else:
            table = pa.table({})
        writer = ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()
        sink.seek(0)
        return StreamingResponse(sink, media_type="application/vnd.apache.arrow.stream")
    return json_payload  # 기본 JSON
```

### C. GET /api/data/market-cap

```
Query Params:
  stk_cd: str (필수)
  start_date: str YYYY-MM-DD (필수)
  end_date: str YYYY-MM-DD (필수)

응답: List[Dict]
  키: dt(str), stk_cd, cls_prc(int), mkt_cap(int), vol(int), amt(int), listed_shares(int)
```

**`MarketCapRepo.get_daily_market_cap()` 신규 메서드:**
```python
def get_daily_market_cap(self, stk_cd: str, start_date: date, end_date: date) -> list[dict]
# 테이블: daily_market_cap
# 조건: stk_cd = %s AND dt BETWEEN %s AND %s ORDER BY dt ASC
```

### D. POST /api/data/screening

> ⚠️ **Anti-in-memory**: 전체 종목(~2,500개) 조회 후 Python 필터 방식은 **수백만 행을 메모리에 올리는 반(反)패턴**. 원본 KDMS v7.0과 동일하게 **DB 레벨 동적 SQL(CTE + WHERE + RANK() 윈도우 + LIMIT)**로 구현합니다.

```
Request Body (JSON):
  stac_yymm: str  (결산년월, YYYYMM 형식, 필수)
  div_cls_code: str = "1"  ("1" 분기, "0" 연간)
  as_of_date: str (선택, ISO 또는 YYYY-MM-DD — PIT 기준일)
  filters: List[ScreeningFilter] (선택)
    각 ScreeningFilter: {field: str, operator: str, value: float}
    허용 field: ALLOWED_FIELDS 화이트리스트 (SQL Injection 방지)
    허용 operator: gt, gte, lt, lte, eq
  limit: int = 50 (최대 500)

응답: List[Dict]
  각 항목: stk_cd, stk_nm, stac_yymm + financial_ratios 필드
```

**`FinancialRepo.screen_stocks()` 신규 메서드 (DB 레벨 동적 SQL):**
```python
# 구현 패턴 (원본 KDMS _build_screening_query 참조):
#
# WITH latest_versions AS (
#   SELECT DISTINCT ON (fr.stk_cd) fr.*, si.stk_nm
#   FROM financial_ratios fr
#   JOIN financial_statements fs ON fr.stk_cd = fs.stk_cd AND ...
#   JOIN stock_info si ON fr.stk_cd = si.stk_cd
#   WHERE fr.stac_yymm = %s AND fr.div_cls_code = %s
#     AND fr.retrieved_at <= %s  -- PIT 기준
#   ORDER BY fr.stk_cd, fr.retrieved_at DESC
# )
# SELECT * FROM latest_versions
# WHERE {동적 WHERE 절 — 파라미터 바인딩으로 SQL Injection 방지}
# ORDER BY ... LIMIT %s;
#
# 허용 필드 화이트리스트: ALLOWED_SCREENING_FIELDS (집합)
# 허용 연산자 화이트리스트: {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
```

### E. GET /api/data/preview/{table}

```
Path Param: table (str) — 허용 목록으로 제한 (SQL Injection 방지)
Query Params:
  limit: int = 50 (1~1000 범위)
  offset: int = 0 (페이지네이션)
  stk_cd: str (선택 — 종목 필터)
  start_date: date (선택 — 날짜 필터 시작)
  end_date: date (선택 — 날짜 필터 종료)

응답:
  {"table": str, "count": int, "data": List[Dict]}

허용 테이블 목록 (ALLOWED_TABLES 화이트리스트):
  daily_ohlcv, daily_market_cap, minute_ohlcv,
  financial_statements, financial_ratios, price_adjustment_factors,
  stock_info, system_milestones, trading_calendar, minute_target_history

테이블별 날짜 컬럼 매핑:
  daily_ohlcv: dt | minute_ohlcv: dt_tm | daily_market_cap: dt
  price_adjustment_factors: event_dt | system_milestones: milestone_date

정렬: 날짜형 컬럼 DESC (최신 우선), stock_info는 stk_cd ASC
페이징: LIMIT %s OFFSET %s 항상 적용
```

### F. Blacklist 패턴

**`OhlcvRepo.get_blacklisted_stocks()` 신규 메서드:**
```python
def get_blacklisted_stocks(self, threshold_days: int = 5) -> list[str]
# 쿼리: daily_ohlcv_gap에서 최근 threshold_days일 내 연속 실패 기록 종목 반환
# 구현 힌트: 
#   SELECT stk_cd FROM daily_ohlcv_gap
#   WHERE dt >= CURRENT_DATE - threshold_days
#   GROUP BY stk_cd HAVING COUNT(*) >= threshold_days
# 반환: ['005930', '000660', ...] (종목코드 리스트)
```

**`DailyTask.run()` skip 로직:**
```python
# 수집 루프 시작 전
blacklist = set(self.ohlcv_repo.get_blacklisted_stocks(threshold_days=5))

for stock in active_stocks:
    stk_cd = stock.get("stk_cd")
    if stk_cd in blacklist:
        logger.info(f"[{stk_cd}] Blacklisted (연속 실패). Skipping.")
        skipped += 1
        continue
    # 기존 수집 로직...
```

### G. 조회 품질 정책 (모든 조회 API 공통)

> **참조**: 원본 KDMS v7.0 `routers/data.py` — Apache Arrow 지원 + Anti-Pandas 설계 원칙

| 항목 | 원본 KDMS v7.0 | p2_kdms T-007 목표 |
|---|---|---|
| **이진 응답** | Apache Arrow IPC (StreamingResponse) 지원 | ✅ 동일 수준 구현 (`Accept: application/vnd.apache.arrow.stream`) |
| **분봉 날짜 제한** | 날짜 범위 무제한 (미구현) | ✅ **최대 30일 제한, 초과 시 400** |
| **Pandas 금지** | "Anti-Pandas" 주석 명시 (메모리 팽창 방지) | ✅ `get_minute_ohlcv()` 내 `pd.DataFrame` 변환 금지 |
| **Screening** | DB 레벨 CTE + RANK() 동적 SQL | ✅ 동일 방식 (`FinancialRepo.screen_stocks()`) |
| **Preview 페이징** | `LIMIT + OFFSET` | ✅ 동일 구현 |
| **SQL Injection 방지** | ALLOWED_TABLES, ALLOWED_FIELDS 화이트리스트 | ✅ 동일 수준 |

**Anti-Pandas 구현 규칙:**
```python
# ❌ 금지 패턴 (메모리 OOM 위험)
import pandas as pd
rows = cursor.fetchall()
df = pd.DataFrame(rows)  # 117만 행 시 수GB 메모리 소비
return df.to_dict('records')

# ✅ 허용 패턴 (직접 list comprehension)
rows = cursor.fetchall()
return [
    {"stk_cd": r[0], "dt_tm": r[1].isoformat(), "open": int(r[2]), ...}
    for r in rows
]
```

**Apache Arrow 응답 기대 효과:**
```
100종목 × 5일 분봉 (195,000행) 기준:
  JSON:  ~47 MB, 직렬화 ~3.2초
  Arrow: ~12 MB, 직렬화 ~0.3초 → 전송 ~75% 절감, 직렬화 10배 이상 빠름
  (p4_manager 클라이언트가 pyarrow 사용 시 즉각 DataFrame 변환 가능)
```

---

## 3. 테스트 케이스 설계 (TDD 완료 기준)

> **테스트 파일**: `tdms_core/p2_kdms/tests/test_data_api_t007.py`  
> **Blacklist 테스트**: `tdms_core/p2_kdms/tests/test_blacklist.py`

### A. GET /api/data/ohlcv/daily 테스트

#### TC-01: `test_ohlcv_daily_raw_returns_unadjusted_data`
```
목적: adjusted=False(기본값) 시 raw OHLCV를 반환하는지 검증
설정: OhlcvRepo.get_daily_ohlcv mock → [{"stk_cd":"005930","dt":date(2026,5,23),"open":70000,...}]
호출: GET /api/data/ohlcv/daily?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23
검증:
  - status_code == 200
  - 응답 리스트 길이 == 1
  - 응답[0]["dt"] == "2026-05-23" (문자열)
  - "adj_factor" 키가 응답에 없음 (raw 응답에는 수정계수 미포함)
  - OhlcvRepo.get_daily_ohlcv 가 1회 호출됨
```

#### TC-02: `test_ohlcv_daily_adjusted_returns_on_the_fly_result`
```
목적: adjusted=True 시 On-the-fly 수정주가가 반환되는지 검증
설정:
  OhlcvRepo.get_daily_ohlcv mock → [{"stk_cd":"005930","dt":date(2026,5,23),"close":70000,...}]
  FactorRepo.get_factors_for_stock mock → [{"event_dt":date(2026,6,1),"price_ratio":0.5,"volume_ratio":2.0}]
호출: GET /api/data/ohlcv/daily?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23&adjusted=true
검증:
  - status_code == 200
  - 응답[0]["close"] == round(70000 * 0.5) == 35000  (event_dt > dt이므로 팩터 적용)
  - 응답[0]["adj_factor"] == 0.5
  - "adj_factor" 키가 존재
```

#### TC-03: `test_ohlcv_daily_invalid_date_format_returns_422`
```
목적: 잘못된 날짜 포맷 입력 시 400 또는 422 반환
호출: GET /api/data/ohlcv/daily?stk_cd=005930&start_date=20260523&end_date=20260523
검증: status_code in (400, 422)
```

---

### B. GET /api/data/ohlcv/minute 테스트

#### TC-04: `test_ohlcv_minute_returns_correct_records`
```
목적: 특정 종목·기간의 분봉 데이터를 정상 반환하는지 검증
설정:
  OhlcvRepo.get_minute_ohlcv mock → [
    {"stk_cd":"005930","dt_tm":datetime(2026,5,23,9,0,tzinfo=KST),"open":70000,...}
  ]
호출: GET /api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-05-23T09:00:00&end_dt=2026-05-23T15:30:00
검증:
  - status_code == 200
  - 응답[0]["stk_cd"] == "005930"
  - 응답[0]["dt_tm"] 가 문자열로 직렬화됨 (datetime 객체 미반환)
  - OhlcvRepo.get_minute_ohlcv 가 1회 호출됨
```

#### TC-05: `test_ohlcv_minute_repo_queries_correct_table`
```
목적: OhlcvRepo.get_minute_ohlcv()가 minute_ohlcv 테이블을 올바른 조건으로 조회하는지 단위 검증
설정: mock pool cursor에서 execute() 호출 캡처
검증:
  - 실행된 SQL에 "minute_ohlcv" 테이블명 포함
  - 파라미터에 stk_cd, start_dt_tm, end_dt_tm 전달됨
```

---

### C. GET /api/data/market-cap 테스트

#### TC-06: `test_market_cap_returns_correct_data_for_date_range`
```
목적: 시가총액 데이터가 날짜 범위 내에서 올바르게 반환되는지 검증
설정:
  MarketCapRepo.get_daily_market_cap mock → [
    {"dt":date(2026,5,23),"stk_cd":"005930","cls_prc":70000,"mkt_cap":4200000000000,...}
  ]
호출: GET /api/data/market-cap?stk_cd=005930&start_date=2026-05-23&end_date=2026-05-23
검증:
  - status_code == 200
  - 응답[0]["mkt_cap"] == 4200000000000
  - 응답[0]["dt"] 가 문자열 "2026-05-23"으로 직렬화됨
```

#### TC-07: `test_market_cap_empty_result_returns_empty_list`
```
목적: 해당 기간 데이터 없을 때 빈 리스트 반환 (500 아닌 200)
설정: MarketCapRepo.get_daily_market_cap mock → []
호출: GET /api/data/market-cap?stk_cd=999999&start_date=2026-01-01&end_date=2026-01-01
검증:
  - status_code == 200
  - 응답 == []
```

---

### D. POST /api/data/screening 테스트

#### TC-08: `test_screening_filters_by_roe`
```
목적: min_roe 조건으로 재무비율 필터링이 동작하는지 검증
설정:
  FinancialRepo.get_ratios_as_of mock (삼성전자 ROE=15, SK하이닉스 ROE=8 반환)
  — 모든 종목 대상 루프 또는 전종목 일괄 조회 방식
Request Body: {"stac_yymm":"202503","div_cls_code":"1","min_roe":10.0}
검증:
  - status_code == 200
  - 응답 목록에 ROE >= 10인 종목만 포함
  - ROE == 8인 종목이 결과에서 제외됨
```

#### TC-09: `test_screening_with_no_matching_stocks_returns_empty`
```
목적: 조건에 맞는 종목이 없을 때 빈 리스트 반환
Request Body: {"stac_yymm":"202503","min_roe":999.0}
검증:
  - status_code == 200
  - 응답 == []
```

#### TC-10: `test_screening_invalid_body_returns_422`
```
목적: 필수 필드 누락 시 422 반환 (FastAPI Pydantic 검증)
Request Body: {}  (stac_yymm 누락)
검증: status_code == 422
```

---

### E. GET /api/data/preview/{table} 테스트

#### TC-11: `test_preview_allowed_table_returns_data`
```
목적: 허용된 테이블명 입력 시 최신 N건을 반환하는지 검증
설정: DB cursor mock → 임의 3개 행 반환
호출: GET /api/data/preview/daily_ohlcv?limit=3
검증:
  - status_code == 200
  - 응답 리스트 길이 <= 3
```

#### TC-12: `test_preview_disallowed_table_returns_400`
```
목적: 허용 목록에 없는 테이블명(SQL Injection 시도 포함) 시 400 반환
호출: GET /api/data/preview/users (또는 /api/data/preview/; DROP TABLE daily_ohlcv--)
검증: status_code == 400
사유: 허용 목록 화이트리스트 검증으로 SQL Injection 차단
```

#### TC-13: `test_preview_limit_capped_at_100`
```
목적: limit=200 요청해도 실제로 100건 이하만 조회하는지 검증
호출: GET /api/data/preview/daily_ohlcv?limit=200
검증:
  - status_code == 200
  - 실제 DB에 전달되는 LIMIT 파라미터 <= 100
```

---

### F. Blacklist 패턴 테스트

#### TC-14: `test_get_blacklisted_stocks_returns_consecutive_fail_stocks`
```
목적: 최근 5일 연속 실패 기록이 있는 종목만 반환하는지 검증
설정: mock cursor → 최근 5일간 5건 실패 기록이 있는 "000001", 2건만 있는 "000002" 반환
호출: OhlcvRepo.get_blacklisted_stocks(threshold_days=5)
검증:
  - "000001" 가 반환 목록에 포함
  - "000002" 가 반환 목록에서 제외
```

#### TC-15: `test_daily_task_skips_blacklisted_stocks`
```
목적: Blacklist 종목이 DailyTask 수집 루프에서 skip되는지 검증
설정:
  OhlcvRepo.get_blacklisted_stocks mock → ["000001"]
  active_stocks = [{"stk_cd":"000001"}, {"stk_cd":"005930"}]
  kis_client.fetch_daily_ohlcv mock → 유효 데이터 반환
호출: DailyTask.run(target_date=date(2026,5,23))
검증:
  - "000001"에 대해 fetch_daily_ohlcv 가 호출되지 않음
  - "005930"에 대해 fetch_daily_ohlcv 가 1회 호출됨
  - result["skipped"] >= 1
```

#### TC-16: `test_daily_task_skipped_count_reflects_blacklist`
```
목적: Blacklist skip이 result["skipped"] 카운트에 올바르게 반영되는지 검증
설정: 3개 종목 중 1개 blacklist
검증: result["skipped"] == 1, result["collected"] == 2 (또는 나머지 수집 성공 수)
```

---

### G. 회귀 테스트 (기존 API 보존)

#### TC-17: `test_existing_get_stocks_still_works`
```
목적: T-007 변경 후에도 기존 GET /api/data/stocks 가 정상 동작하는지 회귀 검증
호출: GET /api/data/stocks
검증: status_code == 200, 응답이 리스트 형태
```

#### TC-18: `test_existing_get_financials_still_works`
```
목적: T-007 변경 후 GET /api/data/financials 가 정상 동작하는지 회귀 검증
호출: GET /api/data/financials?stk_cd=005930&as_of_date=2026-05-23
검증: status_code == 200, {"statements": [...], "ratios": [...]} 구조 유지
```

---

### H. 조회 품질 테스트

#### TC-19: `test_minute_ohlcv_rejects_range_over_30_days`
```
목적: 분봉 날짜 범위가 30일 초과 시 API 레이어에서 즉시 400 반환하는지 검증
호출: GET /api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-01-01&end_dt=2026-03-01  (59일)
검증:
  - status_code == 400
  - 오류 메시지에 "30일" 관련 안내 포함
  - OhlcvRepo.get_minute_ohlcv 가 호출되지 않음 (DB 쿼리 실행 전 차단)
```

#### TC-20: `test_minute_ohlcv_accepts_exactly_30_day_range`
```
목적: 정확히 30일 범위는 허용되는지 경계값 검증
설정: OhlcvRepo.get_minute_ohlcv mock → 임의 3개 행
호출: GET /api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-04-27&end_dt=2026-05-27  (30일)
검증:
  - status_code == 200
  - OhlcvRepo.get_minute_ohlcv 가 1회 호출됨
```

#### TC-21: `test_minute_ohlcv_returns_arrow_stream_when_requested`
```
목적: Accept: application/vnd.apache.arrow.stream 헤더 시 Arrow IPC 응답을 반환하는지 검증
설정:
  OhlcvRepo.get_minute_ohlcv mock → [
    {"stk_cd":"005930", "dt_tm":datetime(2026,5,27,9,0,tzinfo=KST), "open":70000, ...}
  ]
호출: GET /api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-05-27&end_dt=2026-05-27
      Headers: {"Accept": "application/vnd.apache.arrow.stream"}
검증:
  - response.headers["content-type"] == "application/vnd.apache.arrow.stream"
  - 응답 바이트를 pyarrow.ipc.open_stream()으로 파싱 가능
  - 파싱된 테이블의 column_names에 "stk_cd", "dt_tm", "open" 등이 포함됨
```

#### TC-22: `test_minute_ohlcv_no_pandas_in_repo_method`
```
목적: OhlcvRepo.get_minute_ohlcv() 구현에 pandas가 임포트/사용되지 않는지 정적 검증
방법: ohlcv_repo.py 소스 코드 파싱 후 get_minute_ohlcv 함수 바디에
     "import pandas", "pd.DataFrame", "pd." 문자열이 없는지 검사
검증:
  - "import pandas" 미포함
  - "pd.DataFrame" 미포함
사유: Anti-Pandas 원칙 — 메모리 팽창 방지
```

#### TC-23: `test_screening_uses_db_level_filter_not_python_filter`
```
목적: Screening이 DB 레벨에서 필터링함을 검증 (전체 종목 조회 후 Python 필터 방식이 아닌지 검증)
설정:
  FinancialRepo.screen_stocks mock → 2개 종목 결과 반환
Request Body: {"stac_yymm":"202503", "filters":[{"field":"roe_val","operator":"gte","value":10.0}]}
검증:
  - status_code == 200
  - FinancialRepo.screen_stocks 가 1회 호출됨
  - FinancialRepo.get_ratios_as_of 는 호출되지 않음  ← 핵심: 전종목 조회 메서드 미사용 확인
```

#### TC-24: `test_preview_supports_limit_offset_pagination`
```
목적: Preview API가 LIMIT + OFFSET 페이지네이션을 올바르게 지원하는지 검증
설정: 실제 DB 대신 mock pool cursor — limit=3, offset=6 파라미터로 조회 시 올바른 SQL 전달 확인
호출: GET /api/data/preview/daily_ohlcv?limit=3&offset=6
검증:
  - status_code == 200
  - cursor.execute에 전달된 쿼리 파라미터에 limit=3, offset=6 포함
  - 응답 JSON에 "count" 키 존재
```

---

## 4. 테스트 케이스 요약

| 구분 | 케이스 수 | TC 번호 |
|---|---|---|
| 정상 동작 (Happy Path) | 11개 | TC-01, 02, 04, 06, 08, 11, 14, 15, 16, 20, 21 |
| 경계값 | 4개 | TC-07, 09, 13, 20 |
| 예외/오류 처리 | 5개 | TC-03, 10, 12, 05, 19 |
| 회귀 | 2개 | TC-17, 18 |
| 조회 품질 | 6개 | TC-19, 20, 21, 22, 23, 24 |
| **총계** | **24개** | |

---

## 5. Proposed Files (변경 예정 파일 목록)

### [MODIFY] `routers/data.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/data.py`
- `GET /ohlcv/daily` 신규 엔드포인트 추가 (`adjusted` bool 파라미터로 raw/수정주가 분기)
- `GET /ohlcv/minute` 신규 엔드포인트 추가
- `GET /market-cap` 신규 엔드포인트 추가 (`MarketCapRepo` 의존성 주입 추가)
- `POST /screening` 신규 엔드포인트 추가 (Pydantic 요청 모델 정의 포함)
- `GET /preview/{table}` 신규 엔드포인트 추가 (화이트리스트 테이블 검증)

### [MODIFY] `repositories/ohlcv_repo.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py`
- `get_minute_ohlcv(stk_cd, start_dt_tm, end_dt_tm) -> list[dict]` 메서드 추가
- `get_blacklisted_stocks(threshold_days=5) -> list[str]` 메서드 추가

### [MODIFY] `repositories/market_cap_repo.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/market_cap_repo.py`
- `get_daily_market_cap(stk_cd, start_date, end_date) -> list[dict]` 메서드 추가

### [MODIFY] `tasks/daily_task.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py`
- `run()` 내 수집 루프 시작 전 `get_blacklisted_stocks()` 호출 후 skip 로직 삽입
- `skipped` 카운트에 blacklist skip 반영

### [MODIFY] `repositories/financial_repo.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/financial_repo.py`
- `screen_stocks(params: ScreeningParams) -> list[dict]` 신규 메서드 추가 (CTE + 동적 WHERE + LIMIT)
- `ALLOWED_SCREENING_FIELDS` 집합 상수 정의

### [MODIFY] `requirements.txt`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/requirements.txt`
- `pyarrow>=22.0` 추가 (Apache Arrow IPC 직렬화 지원)

### [NEW] `tests/test_data_api_t007.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_data_api_t007.py`
- TC-01~13, TC-17~24 (API 엔드포인트 + Repo 메서드 + 조회 품질 + 회귀)

### [NEW] `tests/test_blacklist.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_blacklist.py`
- TC-14~16 (Blacklist 패턴 단위 테스트)

---

## 6. Verification Plan (검증 계획)

### 자동화 테스트

```bash
# 신규 테스트
conda run --no-capture-output -n tdms_p2_env python -m pytest \
  tests/test_data_api_t007.py tests/test_blacklist.py -v

# 회귀 전체 테스트 (기존 API 보존 확인)
conda run --no-capture-output -n tdms_p2_env python -m pytest tests/ -v
```

> 실행 위치: `tdms_core/p2_kdms/`

### 수동 검증

1. FastAPI 서버 기동 후 Swagger UI(`/docs`)에서 신규 5개 엔드포인트 확인
2. `GET /api/data/ohlcv/daily?stk_cd=005930&start_date=2026-05-20&end_date=2026-05-23&adjusted=false` → raw 데이터 정상 반환 확인
3. `GET /api/data/preview/daily_ohlcv?limit=5` → 최신 5건 반환 확인
4. `GET /api/data/preview/secret_table` → 400 반환 확인 (화이트리스트 차단)
5. `daily_ohlcv_gap` 테이블에 특정 종목 5건 이상 실패 기록 삽입 후 `DailyTask.run()` 실행 → 해당 종목 skip 로그 확인
6. `GET /api/data/ohlcv/minute?stk_cd=005930&start_dt=2026-01-01&end_dt=2026-04-01` → 400 반환 확인 (날짜 범위 초과)
7. 분봉 조회에 `Accept: application/vnd.apache.arrow.stream` 헤더 추가 → Content-Type이 Arrow 바이너리인지 확인 (`curl -H "Accept: application/vnd.apache.arrow.stream"`)
8. `POST /api/data/screening`에 허용되지 않은 `field` 값 전송 → 400 반환 확인 (SQL Injection 화이트리스트 차단)
9. `GET /api/data/preview/daily_ohlcv?limit=5&offset=10` → offset 10 이후 5건 반환 확인 (페이지네이션)
