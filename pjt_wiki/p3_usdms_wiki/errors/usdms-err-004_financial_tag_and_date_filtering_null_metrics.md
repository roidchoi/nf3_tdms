---
id: USDMS-ERR-004
sub_project: p3_usdms
severity: high
status: resolved
last_seen: 2026-06-18
related: [[p3_usdms_wiki/codebase_map.md]], [[p3_usdms_wiki/interfaces/schema_usdms_db.md]]
---

# [USDMS-ERR-004] 재무 팩트 수집 필터링 및 날짜 어긋남에 의한 지표(ROE/ROIC) 누락 오류

### 발생 패턴 및 재현 조건
- **환경**: WSL 2 (Ubuntu 24.04 LTS), PostgreSQL / TimescaleDB, Python 3.12
- **발생 시점**: SEC EDGAR API로부터 수집된 원천 팩트 데이터를 이산화 및 표준화하여 `us_standard_financials` 에 적재하는 `FinancialParser._standardize_financials_v2` 호출 시 및 이를 기반으로 재무 지표를 계산하여 `us_financial_metrics` 에 적재하는 `MetricCalculator.calculate_and_save` 시점.
- **재현 방법**:
  1. `0000314489` (FIRST BUSEY CORP) 등 금융/일반 업종 중 52-53주 회계연도 및 미세 날짜 어긋남이 있는 CIK의 원천 XBRL 데이터를 조회.
  2. 기존 파서 로직으로 표준화 수행 시 대차대조표 팩트(`total_equity` 등)가 통째로 증발하여 NULL로 표준화되는 현상 관찰.
  3. `us_financial_metrics` 테이블에서 `roe`, `roic` 컬럼이 `-` (NULL)로 조회됨을 확인.

### 실제 에러 로그 (요약 금지)
코드 실행 상의 예외 크래시는 발생하지 않으나, 데이터가 대량 누락되는 논리 오류(Silent Data Drop) 형태입니다.
- **DB 조회 결과 현상**:
```sql
SELECT cik, report_period, filed_dt, roe, roa, roic, op_margin
FROM us_financial_metrics
WHERE cik = '0000314489' AND report_period = '2026-03-31';

-- 결과
    cik     | report_period |  filed_dt  | roe |          roa          | roic |     op_margin      
------------+---------------+------------+-----+-----------------------+------+--------------------
 0000314489 | 2026-03-31    | 2026-05-07 |     | 0.0027710842972702983 |      | 0.3243933263348859
```

### 원인 및 누락율 왜곡 요인 (상세)
1. **영업이익 폴백 태그 수집 누락**:
   - `financial_parser.py` 내부에서 수집 메모리/DB 절약을 위해 `XBRLMapper.get_all_tracked_tags()`에 포함된 태그만 필터링하여 수집함.
   - 그러나 `XBRLMapper.map_fact` 메서드 내부에 하드코딩된 영업이익(`op_income`) 용 폴백 태그 4종이 `MAPPING`에 누락되어 사전 필터링 과정에서 유실됨.
2. **미세 마감 날짜 어긋남 필터링 유실 (주요 원인)**:
   - `_standardize_financials_v2` 함수가 동일 `(fy, fp)` 그룹 내에서 `max_end_date` 와 완벽하게 일치하는 `period_end` 를 가진 팩트만 살리는 구조였음.
   - 52-53주 회계연도 기업이나 특정 dei 팩트 마감 시점 차이로 인해, 손익계산서 마감일과 대차대조표(B/S) 마감일이 1~2일 미세하게 다른 경우 B/S 팩트 데이터(자산, 자본, 부채 등) 전체가 필터링으로 인해 삭제되어 `total_equity`가 NULL이 됨.
   - 자본총계가 소실됨으로써 이를 분모로 활용하는 `roe` 와 `roic` 지표가 모두 계산 불가능하여 NULL로 적재됨.
3. **누락율 평균의 함정 (왜곡 원인)**:
   - 전체 데이터 중 **2026년 이전 과거 적재분 (164,441건, 96%)** 은 레거시 파이프라인으로 정상 적재되어 ROE 누락율이 **2.66%** 에 불과했음.
   - 반면 **2026년 이후 최신 tmds 적재분 (7,044건, 4%)** 은 날짜 매칭 버그가 있는 신규 파서가 작동하여 ROE 누락율이 **50.37%** 에 달함.
   - 이로 인해 전체 평균 누락율을 냈을 때는 `3.26%` -> `4.89%` 로 미미하게 상승한 것처럼 보였으나, 실제 최신 데이터(초반 조회 화면)에서는 약 50%의 기업이 전부 비어 보였던 것임.
4. **FinancialRepo.upsert_standard_financials 데이터베이스 적재 누락 (핵심 원인)**:
   - `FinancialParser`가 완화된 규칙으로 자본총계 및 기타 재무 필드들을 정상 파싱하였음에도 불구하고, 실제 DB에 적재하는 `FinancialRepo.upsert_standard_financials` 메서드의 SQL 쿼리(INSERT 및 ON CONFLICT UPDATE)와 바인딩 튜플에 `total_equity`, `current_assets`, `cash_and_equiv`, `inventory` 등 대량의 컬럼이 완전히 빠져 있었음.
   - 이로 인해 파서가 올바르게 추출한 표준 재무 필드들이 DB에 전혀 기록되지 못하고 묵살되는 심각한 Silent Data Drop 현상이 지속되었음.

### 해결법
- **해결 절차**:
  1. `xbrl_mapper.py` 의 `get_all_tracked_tags()` 메서드를 수정하여 하드코딩된 영업이익 폴백 태그 4종을 수집 대상 목록에 포함시킴.
  2. `financial_parser.py` 의 `_standardize_financials_v2` 함수에서 엄격한 날짜 필터링을 `max_end_date` 기준 **30일 이내 윈도우 허용 필터**로 교체하여 날짜 어긋남에 의한 유실을 복구함.
  3. `financial_repo.py` 의 `upsert_standard_financials` 벌크 업서트 SQL 문 및 튜플 데이터 바인딩에 누락된 11개 표준화 컬럼(`total_equity`, `current_assets` 등)을 완벽하게 추가함.
  4. `test_financial_collect.py` 에 단위 테스트를 보강하여 회귀 방어 조치 완료.
- **수정된 코드**:
```python
# tdms_core/p3_usdms/collectors/financial_parser.py
# 날짜 매칭 완화 (기존) group = group[group['period_end'] == max_end_date]
group = group[(max_end_date - group['period_end']).dt.days <= 30]

# tdms_core/p3_usdms/collectors/xbrl_mapper.py
# get_all_tracked_tags() 내에 하드코딩 폴백 태그 4종 추가
fallback_tags = [
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxes',
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
    'IncomeLossBeforeIncomeTaxes',
]
all_tags.update(fallback_tags)

# tdms_core/p3_usdms/repositories/financial_repo.py
# upsert_standard_financials 쿼리 및 바인딩 데이터에 누락 컬럼 대량 보강
# total_equity, current_assets, cash_and_equiv, inventory, account_receivable, retained_earnings, total_liabilities, current_liabilities, cogs, sgna_expense, tax_provision 컬럼을 sql 문에 반영 완료.
```

### 발생 및 해결 이력
- 2026-06-18: `us_financial_metrics` 테이블 데이터 누락 감사 중 발견 및 즉시 패치 완료.
- 2026-06-18: 패치 후 `backfill_metrics_2026.py` 고속 백필 스크립트(연산 속도 40배 최적화)를 기동하여 3,640개 CIK 재처리 완료 (100% 성공). 2026년 이후 ROE 누락율이 **50.37%에서 1.20%로 정상 수렴**하여 데이터 무결성을 최종 확보함.


