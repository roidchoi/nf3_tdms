# Task-008: 헬스·어드민 API + WebSocket 명세서

> **Task ID**: T-008  
> **Phase**: Phase 3 — API 완성  
> **의존성**: T-007 완료 필요  
> **상태**: 대기  
> **작성일**: 2026-05-27  

본 문서는 p2_kdms의 데이터 수집 시스템 상태 진단(Health Check) API와 배치 크론 스케줄 제어 API, 그리고 실시간 로그 브로드캐스팅(WebSocket) 기능을 구현하기 위한 테스트 명세입니다.

특히, 데이터베이스의 실질적 강건성(Robustness) 확보를 위해 **일시적 거래정지 종목 제외 논리**, **수정주가 ±30% 등락폭 논리 검증 (IPO 제외)**, **시가총액 및 재무제표 테이블 교차 검증** 등의 지능형 이상 탐지 규칙을 내장합니다.

---

## 1. 요구사항 및 스콥 (Scope)

### IN Scope

#### A. 헬스 체크 API 완성 (`routers/health.py` 신규 구현)

| API | Path | 설명 |
|---|---|---|
| `GET` | `/api/health/freshness` | 시세 데이터 실질 최신성 및 영업일 연동 수집률 검증 |
| `GET` | `/api/health/gaps` | 일봉/분봉의 미시적/거시적 누락 일자 및 종목 목록 탐지 (임계값 98% 적용) |
| `GET` | `/api/health/integrity` | 수정주가-원본주가 불일치, 상하한가 30% 초과, 재무-비율 불일치 자동 진단 |
| `GET` | `/api/health/milestones` | 시스템 운영 마일스톤 조회 |
| `POST` | `/api/health/milestones` | 시스템 운영 마일스톤 등록 |

#### B. 어드민 및 스케줄 API 완성 (`routers/admin.py` 확장)

| API | Path | 설명 |
|---|---|---|
| `GET` | `/api/admin/tasks/status` | 전체 백그라운드 태스크의 상태 및 최근 실패 스택트레이스 조회 |
| `POST` | `/api/admin/tasks/{task_id}/run` | 특정 태스크 비동기 즉시 1회 기동 (T-006 완료분 연동) |
| `GET` | `/api/admin/schedules` | APScheduler에 등록된 크론 스케줄 정보 조회 |
| `PUT` | `/api/admin/schedules/{schedule_id}` | 특정 스케줄의 크론 표현식 또는 시간 설정 변경 |
| `POST` | `/api/admin/schedules/{schedule_id}/toggle` | 특정 스케줄 활성화 / 일시중지 토글 |
| `DELETE` | `/api/admin/schedules/{schedule_id}` | 커스텀 등록 스케줄 삭제 |
| `WS` | `/ws/logs` | Pub/Sub 패턴 기반 다중 접속 안전 실시간 로그 스트리밍 |

#### C. Repo 및 내부 모듈 확장
- **`OhlcvRepo` / `MarketCapRepo` / `FinancialRepo`** 내 정합성 및 누락 검사 전용 SQL 질의 메서드 추가.
- **`LogBroadcaster` (Pub/Sub 패턴)**: 다수의 클라이언트가 로그를 동시에 누설 없이 받아볼 수 있는 커넥션 관리기 추가.

---

## 2. 핵심 비즈니스 논리 및 예외 규칙

### A. 미시적 누락(Micro Gaps) 임계치 및 거래정지 예외 처리
- **수집 예외 처리**:
  - 당일 일봉 거래량(`vol`)이 `0`인 종목은 정상적인 **거래정지(Suspended)** 상태이므로 분봉 데이터 미적재를 누락으로 판정하지 않고 검증에서 제외합니다.
  - `daily_ohlcv_gap` 테이블에 특정 날짜에 대해 수집 제외 사유(예: "DELISTED", "SUSPENDED")가 수동/자동 등록된 종목은 검증 모수에서 제외합니다.
- **유효 수집 성공률 판단 기준**:
  - 분봉 수집 타겟(거래대금 상위 600종목)의 정상 수집 여부를 아래 수식으로 계산합니다.
    $$\text{유효 수집 성공률} = \frac{\text{정상 수집 완료 종목 수 (거래정지 등 제외)}}{\text{전체 타겟 수 (600개)} - \text{수집 제외 종목 수}} \times 100$$
  - **판정 등급**:
    - **98% 이상**: 정상 (`GREEN`)
    - **95% 이상 ~ 98% 미만**: 주의 (`YELLOW`) -> 누락 종목 목록 리포팅 및 백필 자동 재시도 대기
    - **95% 미만**: 위험 (`RED`) -> 대량 수집 장애 경고 발생

### B. 수정주가 논리적 정합성 및 상·하한가 제한 검증
- **수정주가 산출식 일치 검사**:
  - `daily_ohlcv_adjusted` 물리 테이블의 종가(`cls_prc`)와 원본 `daily_ohlcv.cls_prc`에 누적 수정팩터(`adj_factor`)를 적용한 역산 주가의 차이가 **±0.01 이내**인지 비교합니다.
- **±30% 상·하한 등락폭 검증**:
  - 한국 시장의 가격제한폭 규정에 따라, 임의의 거래일 $t$에 대해 수정주가의 하루 등락률이 **-30.1% 미만**이거나 **+30.1% 초과**인 종목을 정합성 에러(`PriceLimitViolation`)로 검출합니다.
  - 단, 과거 시계열 백필 데이터 검증 시 2015년 6월 15일 이전 구간은 당시 제한폭인 **±15.1%**를 적용하여 유연하게 대처합니다.
- **신규 상장일(IPO) 예외 필터링**:
  - `stock_info` 테이블의 최초 상장일(`list_dt`) 정보를 조회하여, 종목별 상장일 당일($t = \text{list\_dt}$)의 데이터는 전일 주가 부재 및 시가 변동 폭 폭증이 정상적이므로 **±30% 상하한가 검증 대상에서 완전히 제외**시킵니다.

### C. 시가총액 및 전체 수집 항목 무결성 체크
- **시가총액 (`daily_market_cap`)**:
  - 당일 상장 활성 종목(`status = 'listed'`) 수 대비 시가총액 수집 건수 비율이 **98% 이상**인지 확인합니다.
  - 동일 영업일, 동일 종목에 대해 `daily_ohlcv.cls_prc`와 `daily_market_cap.cls_prc` 값을 1:1로 비교하여 불일치 종목을 선별합니다.
  - 시가총액 연산 모순(`mkt_cap != listed_shares * cls_prc` 단, 소수점/단위 환산 차이 허용)을 검사합니다.
- **재무제표 (`financial_statements` / `financial_ratios`)**:
  - 특정 종목/분기에 대해 `financial_statements`는 존재하나 `financial_ratios` 데이터는 없는 적재 불일치 대상을 스캔합니다.

---

## 3. 핵심 인터페이스 스펙

### A. GET /api/health/freshness
```
응답: JSON (HealthFreshnessResponse)
{
  "status": "GREEN" | "YELLOW" | "RED",
  "last_daily_dt": "2026-05-26",
  "last_minute_dt_tm": "2026-05-26T15:30:00+09:00",
  "daily_coverage_ratio": 0.985,      -- 최신 영업일 수집 완료율
  "active_listed_stocks": 2540,
  "collected_listed_stocks": 2502,
  "daily_lag_days": 0,                -- trading_calendar의 최신 영업일 대비 lag
  "is_daily_fresh": true
}
```

### B. GET /api/health/gaps
```
Query Params:
  start_date: YYYY-MM-DD (필수)
  end_date: YYYY-MM-DD (필수)

응답: JSON (GapCheckResponse)
{
  "analysis_period": {"start_date": "2026-05-01", "end_date": "2026-05-26"},
  "daily_gaps": [
    {
      "dt": "2026-05-20",
      "missing_stocks_count": 2,
      "missing_stocks": ["0008Z0", "005930"],
      "valid_collection_rate": 99.92
    }
  ],
  "minute_gaps": [
    {
      "dt": "2026-05-23",
      "market": "KOSPI",
      "missing_stocks_count": 1,
      "missing_stocks": ["000660"],     -- 거래정지나 사유 등록이 안 되었는데 분봉 개수(381개) 미달인 종목
      "valid_collection_rate": 99.5
    }
  ]
}
```

### C. GET /api/health/integrity
```
응답: JSON (IntegrityCheckResponse)
{
  "checked_at": "2026-05-27T16:00:00+09:00",
  "status": "GREEN" | "RED",
  "adjusted_price_mismatch_count": 0,
  "adjusted_price_mismatches": [],  -- [{"stk_cd": "005930", "dt": "2026-05-26", "expected": 70000.0, "actual": 70100.0}]
  "price_limit_violations_count": 0,
  "price_limit_violations": [],      -- [{"stk_cd": "000020", "dt": "2026-05-20", "change_rate": 35.2}]
  "market_cap_mismatch_count": 0,
  "market_cap_mismatches": [],      -- [{"stk_cd": "005930", "dt": "2026-05-26", "ohlcv_close": 70000, "mkt_cap_close": 70200}]
  "financial_ratio_mismatch_count": 0,
  "financial_ratio_mismatches": []  -- [{"stk_cd": "005930", "stac_yymm": "202512", "div_cls_code": "1", "reason": "Ratios missing"}]
}
```

### D. WS /ws/logs (WebSocket)
- **멀티캐스팅 정책**: `LogBroadcaster` 클래스가 생성한 전역 `Active Connections` 집합에 `websocket` 객체를 등록하고, 파일 로그 또는 표준 출력 이벤트를 읽어와 모든 커넥션에 브로드캐스팅합니다.
- **안전성**: 한 클라이언트의 수신 지연이 다른 클라이언트나 API 응답 루프를 블로킹하지 않도록 `asyncio.create_task` 기반 비동기 전송 처리합니다.

---

## 4. 테스트 케이스 설계 (TDD 완료 기준)

> **테스트 파일**: `tdms_core/p2_kdms/tests/test_health_t008.py`  
> **WebSocket 테스트**: `tdms_core/p2_kdms/tests/test_logs_ws_t008.py`

### A. Freshness 및 Gap 검증 테스트

#### TC-01: `test_health_freshness_green_when_high_coverage`
```
목적: 수집 커버리지가 95% 이상이고 지연이 없는 경우 GREEN 반환 검증
설정: 
  trading_calendar 최신 영업일 = 2026-05-26
  stock_info listed 종목 = 100개
  daily_ohlcv 에 2026-05-26 기준 적재된 종목 = 98개
호출: GET /api/health/freshness
검증:
  - status_code == 200
  - status == "GREEN"
  - daily_coverage_ratio == 0.98
  - is_daily_fresh == True
```

#### TC-02: `test_health_freshness_red_when_stale`
```
목적: 수집 데이터가 최신 영업일 대비 1거래일 이상 지연된 경우 RED 반환
설정: 
  trading_calendar 최신 영업일 = 2026-05-26 (개장일)
  daily_ohlcv 최신 수집 데이터 날짜 = 2026-05-22 (2거래일 지연)
호출: GET /api/health/freshness
검증:
  - status_code == 200
  - status == "RED"
  - is_daily_fresh == False
```

#### TC-03: `test_health_gaps_excludes_suspended_stocks_from_rate`
```
목적: 일봉 상 거래량이 0인 종목을 분봉 누락 모수에서 제외하고 성공률 계산
설정:
  분봉 타겟 종목: ["A", "B", "C"]
  "A", "B"는 분봉 적재 완료 (381개)
  "C"는 분봉 없음, 그러나 일봉 daily_ohlcv.vol == 0 (거래정지)
호출: GET /api/health/gaps?start_date=2026-05-26&end_date=2026-05-26
검증:
  - status_code == 200
  - "C" 종목은 분봉 누락(gaps) 목록에 없음
  - valid_collection_rate == 100.0 (거래정지 제외로 2/2 수집 완료 판정)
```

#### TC-04: `test_health_gaps_warning_when_rate_under_98`
```
목적: 수집 성공률이 95% 이상 98% 미만인 경우 WARNING 등급 및 누락 목록 제공
설정:
  분봉 타겟 종목: 100개
  정상 수집: 97개
  누락(거래량 > 0 이고 무사유): 3개
호출: GET /api/health/gaps?start_date=2026-05-26&end_date=2026-05-26
검증:
  - status_code == 200
  - minute_gaps[0]["valid_collection_rate"] == 97.0
  - minute_gaps[0]["missing_stocks_count"] == 3
  - minute_gaps[0]["missing_stocks"] 에 누락 종목 3개 코드 포함됨
```

---

### B. 수정주가 및 정합성 테스트

#### TC-05: `test_integrity_adjusted_price_mismatch_detection`
```
목적: 물리 수정주가와 팩터 역산 공식 결과가 불일치하는 경우 검출 확인
설정:
  daily_ohlcv.cls_prc = 10000
  price_adjustment_factors.adj_factor = 0.5
  daily_ohlcv_adjusted.cls_prc = 5500 (기대값 5000 대비 불일치 오차 > ±0.01)
호출: GET /api/health/integrity
검증:
  - status_code == 200
  - adjusted_price_mismatch_count == 1
  - adjusted_price_mismatches[0]["stk_cd"] == 해당 종목 코드
```

#### TC-06: `test_integrity_price_limit_violation_over_30_percent`
```
목적: 일별 변동폭이 30%를 초과하는 종목이 수정주가에 적재된 경우 이상 검출
설정:
  daily_ohlcv_adjusted (종목 A)의 t-1일 종가 = 10000, t일 종가 = 13500 (35% 상승)
호출: GET /api/health/integrity
검증:
  - status_code == 200
  - price_limit_violations_count == 1
  - price_limit_violations[0]["stk_cd"] == 해당 종목
```

#### TC-07: `test_integrity_price_limit_excludes_ipo_listing_date`
```
목적: 최초 상장일(IPO) 당일의 변동률은 30% 초과하더라도 검출에서 제외
설정:
  stock_info 의 list_dt = 2026-05-26
  daily_ohlcv_adjusted 의 t일(2026-05-26) 변동률 = 100% 상승 (상장일 변동)
호출: GET /api/health/integrity
검증:
  - status_code == 200
  - price_limit_violations_count == 0 (상장일 예외 처리로 패스)
```

#### TC-08: `test_integrity_market_cap_close_mismatch`
```
목적: daily_ohlcv의 종가와 daily_market_cap의 종가가 불일치하는 종목 검출
설정:
  daily_ohlcv 종가 = 70000
  daily_market_cap 종가 = 70500
호출: GET /api/health/integrity
검증:
  - status_code == 200
  - market_cap_mismatch_count == 1
  - market_cap_mismatches[0]["ohlcv_close"] == 70000
```

#### TC-09: `test_integrity_financials_missing_ratios_mismatch`
```
목적: 재무제표는 있는데 재무비율이 없는 적재 불완전 감지
설정:
  financial_statements (202512, 분기 1) 적재됨
  financial_ratios (202512, 분기 1) 없음
호출: GET /api/health/integrity
검증:
  - status_code == 200
  - financial_ratio_mismatch_count == 1
```

---

### C. WebSocket 멀티캐스팅 테스트

#### TC-10: `test_ws_logs_broadcast_to_multiple_clients`
```
목적: 2개 이상의 WebSocket 클라이언트가 동시 접속했을 때 경쟁 없이 모든 클라이언트에 로그가 전달되는지 검증
설정:
  FastAPI TestClient의 websocket_connect를 통해 두 개의 WebSocket 연결 수립
  LogBroadcaster.broadcast("Test log message") 호출
검증:
  - 클라이언트 1 수신 데이터 == "Test log message"
  - 클라이언트 2 수신 데이터 == "Test log message"
  - 연결이 정상적으로 유지됨
```

---

## 5. Proposed Files (변경 예정 파일 목록)

### [NEW] `routers/health.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/health.py`
- `/api/health/freshness`, `/api/health/gaps`, `/api/health/integrity`, `/api/health/milestones` 구현
- 상하한가 30% 검증(IPO 제외), 유효 수집 성공률 계산 논리 탑재

### [MODIFY] `routers/admin.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py`
- APScheduler 스케줄 조회, 갱신(`PUT`), 토글(`toggle`), 삭제(`DELETE`) 엔드포인트 구현
- `WS /ws/logs`에 다중 접속 처리가 가능한 `LogBroadcaster` 연동

### [NEW] `utils/log_broadcaster.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/utils/log_broadcaster.py`
- Pub/Sub 기반 WebSocket 브로드캐스터 구현 클래스

### [NEW] `tests/test_health_t008.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_health_t008.py`
- TC-01 ~ TC-09 (상하한가, IPO 제외, 누락 성공률 임계치, 시총 종가 검증 등)

### [NEW] `tests/test_logs_ws_t008.py`
**경로**: `file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_logs_ws_t008.py`
- TC-10 (WebSocket 멀티캐스팅 동시 수신 단위 테스트)

---

## 6. Verification Plan (검증 계획)

### 자동화 테스트
```bash
# 헬스 및 정합성 검증 테스트 실행
conda run --no-capture-output -n tdms_p2_env python -m pytest \
  tests/test_health_t008.py tests/test_logs_ws_t008.py -v
```

### 수동 E2E 검증
1. `daily_ohlcv`와 `daily_market_cap` 임의 종목 종가 불일치 주입 후 `GET /api/health/integrity` 호출 -> `market_cap_mismatches` 탐지 여부 확인
2. `daily_ohlcv_adjusted`에 하루 35% 상승 가격 주입 -> `price_limit_violations` 탐지 여부 확인. 상장일 당일 변동 건은 패스 여부 확인.
3. 분봉 수집 타겟 600종목 중 10개 종목 임의 삭제 후 `GET /api/health/gaps` 호출 -> 유효 성공률 98.33%로 '정상' 판정 및 10개 누락 리스트업 확인.
