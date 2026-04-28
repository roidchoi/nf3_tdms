
# 📘 데이터 정합성 검증 및 유지관리 계획서 (v3.0 Updated)

**Date:** 2025-12-13
**Version:** 3.0 (Added Financial & Valuation Scope)
**Scope:** us_ticker_master, us_daily_price, **us_standard_financials, us_financial_metrics, us_daily_valuation**

---
## 1. 리포팅 및 데이터 영속성 (Reporting & Persistence)

검증 결과는 추후 대시보드 연동과 RCA(Root Cause Analysis)를 위해 구조화된 파일로 영구 저장됩니다.

### **A. 저장 경로 및 파일명 전략**

- **Root Directory:** `./logs/db_health/`
    
- **정밀 진단 (Deep Diagnostic):**
    
    - 경로: `./logs/db_health/deep_diagnostic/`
    - 파일명: `deep_diag_{YYYYMMDD}_{HHMMSS}.json`
        
- **일일 점검 (Daily Routine):**
    
    - 경로: `./logs/db_health/daily_routine/`
    - 파일명: `daily_rout_{YYYYMMDD}_{HHMMSS}.json`

### **B. JSON 리포트 스키마 (RCA Optimized)**

```json
{
  "meta": {
    "report_id": "uuid-v4",
    "timestamp": "2025-12-11T10:00:00",
    "type": "DEEP_DIAGNOSTIC",
    "duration_ms": 4500
  },
  "summary": {
    "status": "RED",            // GREEN (Pass), YELLOW (Warn), RED (Fail)
    "total_checks": 15,
    "failed_checks": 2,
    "critical_count": 1
  },
  "details": [
    {
      "category": "MARKET_DATA",
      "check_name": "ohlc_logic_consistency",
      "status": "FAIL",
      "severity": "CRITICAL",
      "logic": "High < Low OR High < Open OR High < Close",
      "failed_samples": [
        { "ticker": "TSLA", "dt": "2024-01-05", "high": 100, "low": 105, "msg": "High is lower than Low" }
      ]
    }
  ]
}
```


---

## 2. 정기 정밀 진단 (Periodic Deep Diagnostic)

주기: 주 1회(주말), 월 1회, 또는 대규모 패치 직후.
목표: 데이터베이스 전수 조사를 통한 무결성 보증.
### **A. 메타데이터 진단 (Metadata Integrity)**

#### **1. 마스터 정합성 (Master Consistency)**
- **타겟 커버리지 (Target Coverage):**
    - 검증: 전체 타겟(`is_collect_target=true`) 대비 수집 종목 비율 $\ge$ 99.5%.
- **수집 대상 적합성 (Target Validity):**
    - 검증: 타겟 종목 중 `OTC`, `PINK`, `NULL` 등 수집 불가 거래소 포함 여부 (0건).
- **상태 모순 (State Contradiction):**
    - 검증: `is_active=false` (비활성)인데 `is_collect_target=true` (수집 대상)인 논리적 오류.
- **식별자 충돌 (Identifier Conflict):**
    - 검증: `latest_ticker` 중복 여부 (0건).

#### **2. 히스토리 정합성 (History Integrity)**
- **시계열 연속성:**
    - 검증: 동일 CIK 내 `start_dt` ~ `end_dt` 기간 중복 여부 (0건).
- **마스터 연동:**
    - 검증: History 최신 레코드(`9999-12-31`)와 Master `latest_ticker` 불일치 여부.
- **고아 레코드 (Orphan Check):**
    - 검증: Master에 없는 CIK가 History에 존재하는지 확인.

### **B. 시세 데이터 진단 (Market Data Quality)**

#### **1. 값의 유효성 (Value Validity)**
- **가격 무결성:**
    - 검증: `open`, `high`, `low`, `close` 전수 조사. `0`, `음수`, `NULL` 존재 여부 (0건).
- **거래량 무결성:**
    - 검증: `vol < 0` (0건) 및 `vol = 0`인 대형주(S&P 500 등) 존재 여부 확인.

#### **2. OHLC 논리 검증 (Logical Consistency)**
- **High/Low 모순:**
    - 검증: `high < low` 인 레코드 탐지.
- **Range 모순:**
    - 검증: `high < max(open, close)` 또는 `low > min(open, close)` 탐지.

#### **3. 시계열 완전성 (Temporal Completeness)**
- **데이터 밀도 (Density):**
    - 검증: 종목별 Row Count가 평균 대비 2표준편차 이상 적은 종목 추출.
- **구간 단절 (Gap Detection):**
    - 검증: 평일(Trading Day) 기준 5일 이상 데이터가 연속으로 비어있는 구간 탐지.

### **C. 팩터 및 엔진 진단 (Factor & Logic)**

#### **1. 수정주가 재현성 (Reproduction Accuracy) [핵심]**
- **대상:** 전체 종목 중 5% 무작위 샘플링 + 주요 종목(NVDA, AAPL 등).
- **검증:** `verify_price_reproduction.py` (Full Mode).
- **기준:** 오차율 0.1% 미만 종목 비율 **99.9% 이상**.

#### **2. 알려진 이벤트 교차 검증 (Known Event Check)**
- **검증:** 주요 종목의 실제 분할/배당일에 팩터가 존재하는지 확인.
    - 예: NVDA (2024-06-10, Split), AAPL (2020-08-31, Split).

#### **3. 이상치 및 노이즈 (Outliers & Noise)**
- **노이즈 팩터:** `factor_val`이 1.0에 매우 근접(0.999~1.001)한 데이터 과다 존재 여부.
- **극단적 팩터:** `factor_val`이 음수이거나 비정상적으로 큰 값(>100) 존재 여부.

### **D. 재무 데이터 진단 (Financial Data Integrity) [NEW]**

재무 데이터의 회계적 정합성(Accounting Identity)과 시점 무결성(PIT)을 검증합니다.

#### **1. 회계 항등식 검증 (Accounting Identity)**
* **Balance Sheet 균형:**
    * 검증: `total_assets` $\approx$ `total_liabilities` + `total_equity`.
    * 기준: 오차율 0.1% 미만 (반올림 오차 허용).
* **Income Statement 흐름:**
    * 검증: `net_income`과 (`revenue` - `expenses`)의 괴리율 확인.
    * 기준: 주요 항목 누락 여부 확인용 (오차 허용 범위 5% 이내).

#### **2. 과거 데이터 침범 감지 (Historical Leakage Check)**
* **연도 불일치 (Year Drift):**
    * 검증: `fiscal_year`와 실제 `report_period`의 연도가 2년 이상 차이 나는지 확인.
    * 목적: 10-K 내 과거 비교 데이터가 최신 연도로 잘못 매핑되는 현상(이전 버그) 방지.
* **값의 완벽한 중복 (Exact Duplication):**
    * 검증: 동일 기업 내에서 서로 다른 `fiscal_year`의 매출(`revenue`)이 1달러 단위까지 똑같은 케이스 검출.

#### **3. 시계열 및 주기성 (Temporal & Periodicity)**
* **보고서 누락 (Missing Report):**
    * 검증: `fiscal_period`가 `Q1`, `Q2`, `Q3`, `FY` 순서대로 존재하는지 확인. (중간에 Q2가 없는지).
* **수정 공시 처리 (Restatement):**
    * 검증: 동일 `report_period`에 대해 `filed_dt`가 다른 데이터 존재 시, 최신 `filed_dt` 데이터가 `is_active` 상태인지 확인.

#### **4. 표준화 실패 감지 (Standardization Fallback)**
* **필수값 누락 (Critical Nulls):**
    * 검증: `total_assets`, `revenue`, `net_income` 등 핵심 3대 지표가 `NULL`인 비율 확인.
    * 기준: 전체 데이터의 5% 미만이어야 함 (특수 업종 제외).

---

### **E. 가치지표 및 메트릭 진단 (Valuation & Metrics) [NEW]**

산출된 2차 지표(Metrics)와 3차 지표(Valuation)의 논리적 타당성을 검증합니다.

#### **1. 메트릭 산출 로직 역산 (Reverse Calculation)**
* **ROE 정합성:**
    * 검증: `metrics.roe` $\approx$ `standard.net_income` / `standard.total_equity`.
    * 기준: 오차 0.01(1%) 미만.
* **성장률(YoY) 논리:**
    * 검증: `rev_growth_yoy`가 0(0%)인 경우, 실제 원본 데이터(`revenue`)가 전년도와 동일한지 확인 (계산 누락 vs 실제 동결 구분).

#### **2. 가치지표 범위 및 이상치 (Range & Outlier)**
* **시가총액 정합성:**
    * 검증: `daily_valuation.mkt_cap` $\approx$ `daily_price.close` $\times$ `share_history.val`.
    * 기준: 오차 1% 미만.
* **음수 지표 확인:**
    * 검증: `mkt_cap`, `pb`, `ps` 등 이론적으로 음수가 될 수 없는 지표의 음수값 존재 여부.
* **극단적 값 (Extreme Values):**
    * 검증: `PE > 10,000` 또는 `PB > 500` 등 비정상적 아웃라이어 비율 모니터링.

#### **3. PIT(Point-in-Time) 준수 여부**
* **미래 참조 방지 (No Look-ahead):**
    * 검증: Valuation 산출에 사용된 재무 데이터의 `filed_dt`가 주가 일자(`dt`)보다 **이전**인지 샘플링 검사.

---

## 3. 일일 업데이트 및 상시 모니터링 (Daily Routine)

주기: 매일 장 마감 배치 종료 후.
목표: 증분 데이터(Increment)의 최신성 및 이상 징후 포착.

### **A. 운영 현황 (Operations)**

- **일일 수집 성공률:** 활성 타겟 대비 최신일 데이터 적재율 (99% 이상).
- **생존 신고 (Liveness):** 활성 타겟의 `last_seen_dt` 갱신 여부.
- **신규/상폐 감지:** 당일 `created_at` 및 `is_active` 변경 건수.
- **티커 변경 추적:** 당일 `us_ticker_history` 신규 추가 건수.

* **재무 공시 수집 현황:**
    * 당일 신규 수집된 `us_financial_facts` 행 개수.
    * 당일 업데이트된 `us_standard_financials` 기업 수.
* **주식 수 변동 감지:**
    * 당일 `us_share_history`에 신규 추가된 레코드 수.

### **B. 이상 징후 (Anomalies)**

- **가격 급등락 (Price Spikes):** 전일 대비 변동폭 $\pm$50% 이상 종목 추출 (분할 미반영 가능성).
- **신규 팩터 생성:** 당일 생성된 팩터 유무 확인 (이벤트 반영 여부).

* **재무 급변 (Financial Shock):**
    * 전분기 대비 매출이나 자산이 50% 이상 급감한 기업 알림 (합병, 분할, 혹은 파싱 오류 가능성).
* **가치지표 급변 (Valuation Jump):**
    * 주가는 그대로인데 PER가 하루 만에 2배 이상 뛴 경우 (수정 공시로 인한 EPS 급락 의심).

---

## 4. 실행 도구 및 담당 (Updated)

| **구분** | **스크립트** | **실행 시점** | **비고** |
| :--- | :--- | :--- | :--- |
| **정밀 진단** | `run_deep_diagnostic.py` | 수동 / 주간 | **재무/가치지표 검증 모듈(`backend/auditors/financial_auditor.py`) 통합** |
| **일일 점검** | `monitor_daily_routine.py` | 매일 (자동) | 공시 수집 현황 추가 |
| **재현 검증** | `backend/auditors/price_auditor.py` | 진단 시 호출 | 수정주가 검증 |
| **역산 검증** | **`backend/auditors/metric_auditor.py`** | 진단 시 호출 | **[NEW] 재무지표 샘플링 역산 테스트** |
