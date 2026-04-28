# 인터페이스: SEC PIT 패턴 (pit_sec_pattern.md)

> **소스 파일**: `migration_pjt/usdms_origin/docs/spec_usdms_core_logic.md`
> **관련 모듈**: `backend/engines/valuation_calculator.py`, `backend/collectors/financial_parser.py`
> **마지막 업데이트**: 2026-04-28

---

## 개요

USDMS의 PIT(Point-in-Time) 핵심은 `filed_dt`(공시일)입니다. 특정 날짜(`dt`)의 가치평가를 계산할 때, 그 날짜 이전에 공시된(`filed_dt <= dt`) 가장 최신 재무 데이터를 사용합니다.

---

## PIT Valuation 매칭 알고리즘

```python
# backend/engines/valuation_calculator.py
import pandas as pd

# 1. 가격 데이터: dt 기준
price_df  # index: dt

# 2. 주식 수: filed_dt 기준 과거 가장 최신 값 (1순위)
share_df  # index: filed_dt

# 3. 재무 데이터: filed_dt 기준 과거 가장 최신 값
fin_df    # index: filed_dt

# PIT 매칭: merge_asof (backward direction)
# 특정 dt에 대해 filed_dt <= dt 중 가장 최신 값을 매칭
merged = pd.merge_asof(
    price_df.sort_index(),
    fin_df.sort_values('filed_dt'),
    left_index=True,
    right_on='filed_dt',
    direction='backward'
)
```

---

## 재무 표준화 그룹화 로직 (FinancialParser)

### 핵심 문제
SEC 공시의 `filed_dt` 차이로 인해 같은 회계 기간의 데이터가 여러 건 산재

### 해결책: `(FY, FP)` 그룹화
```python
# fiscal_year + fiscal_period 기준으로 그룹화
# Balance Sheet (Instant): 기간 내 최신 filed_dt 값 채택
# Income Statement (Duration):
#   FY: 누적값 그대로 사용
#   Q1: 그대로 사용
#   Q2, Q3: YTD 역산 → Q2_discrete = Q2_YTD - Q1_YTD
#   Q4: Q4 = FY - Q3_YTD
```

---

## PIT Key 요약

| 데이터 | PIT Key | 설명 |
|---|---|---|
| `us_financial_facts` | `filed_dt` | SEC 공시일 |
| `us_standard_financials` | `filed_dt` | SEC 공시일 |
| `us_share_history` | `filed_dt` | DEI 태그 공시일 |
| `us_daily_price` | `dt` | 시세 날짜 |
| `us_daily_valuation` | `dt` | 가치평가 산출 날짜 |

---

## 신규 프로젝트(p2_usdms) 적용 시 참고

- `merge_asof(direction='backward')` 패턴 그대로 유지
- `us_share_history` (1순위) / `us_standard_financials.shares_outstanding` (2순위) fallback 구조 유지
- TTM 계산: 분기 데이터일 경우 `Value × 4` (간이 TTM) 사용 — 추후 정확한 Rolling Sum 으로 개선 가능
