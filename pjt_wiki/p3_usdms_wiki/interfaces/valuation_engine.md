# Valuation & Metrics Engine (valuation_calculator.py / metric_calculator.py)

> 마지막 변경: Task-004
> 소스 위치: `tdms_core/p3_usdms/engines/`

### 1. 개요 및 목적
- 미국 주식 CIK 대상 일별 시가총액, 5대 가치지표(PE, PB, PS, PCR, EV/EBITDA), 9대 재무비율 및 3대 YoY 성장률을 산출하는 연산 핵심 엔진 모듈입니다.
- 연관된 문서: [[p3_usdms_wiki/interfaces/valuation_repo]], [[migration-pjt/ref_usdms_wiki/interfaces/pit_sec_pattern]]

### 2. 상세 명세 (요약 금지)

#### A. 가치평가 산출 엔진 (`ValuationCalculator`)
- **PIT 매칭**: `pd.merge_asof` 기반 `direction='backward'` 매칭을 사용하여 시세 날짜(`dt`)에 대해 공시일(`filed_dt <= dt`) 기준의 가장 최신 재무 데이터와 발행 주식 수를 결합합니다.
- **주식수 Hybrid Fallback**: `us_share_history`에 정보가 누락된 경우, `us_standard_financials`의 `shares_outstanding` 컬럼을 2순위로 참조합니다.
- **간이 TTM 연간화**: 분기별 데이터인 경우 `* 4`배를 적용하고, `fiscal_period == 'FY'` 연간 보고서인 경우 원본값을 그대로 활용합니다.
- **주요 산출 공식**:
  - `mkt_cap` = 종가 × 주식수
  - `ev` = 시가총액 + 부채총계 - 현금및현금성자산 (부채 및 현금 결측 시 0.0 처리)
  - `pe` = 시가총액 / 순이익_ttm (0 또는 결측 시 `None`)
  - `pb` = 시가총액 / 자본총계
  - `ps` = 시가총액 / 매출액_ttm
  - `pcr` = 시가총액 / 영업현금흐름_ttm
  - `ev_ebitda` = 기업가치 / EBITDA_ttm

#### B. 재무비율 & 성장률 산출 엔진 (`MetricCalculator`)
- **9대 재무비율 공식**:
  - `roe` = 순이익 / 자본총계
  - `roa` = 순이익 / 자산총계
  - `roic` = 영업이익 / (자본총계 + 부채총계)
  - `op_margin` = 영업이익 / 매출액
  - `net_margin` = 순이익 / 매출액
  - `gp_a_ratio` = 매출총이익 / 자산총계
  - `debt_ratio` = 부채총계 / 자산총계
  - `current_ratio` = 유동자산 / 유동부채
  - `interest_coverage` = 영업이익 / 이자비용
- **YoY 성장률 공식**:
  - `rev_growth_yoy` = (매출 - 전년동기매출) / abs(전년동기매출)
  - `op_growth_yoy` = (영업이익 - 전년동기영업이익) / abs(전년동기영업이익)
  - `eps_growth_yoy` = (당기EPS - 전년동기EPS) / abs(전년동기EPS)

### 3. 주의사항 및 성능 최적화
- **메모리 누수 방지**: 대용량 계산 루프 진행 시 Pandas DataFrame이 메모리에 계속 잔류하는 현상을 방지하기 위해 매 루프 말미에 `del` 명령어로 참조를 해제하고 명시적으로 `gc.collect()`를 가동합니다.
- **벌크 캐시(Bulk Cache) 주입 최적화**: 500개 이상 대량 종목 루프의 I/O 병목을 제거하기 위해, 루프 실행 전에 CIK 전체의 최신 DB 가공일 데이터를 한 번에 가져와 캐시 파라미터(`latest_val_dates_cache`, `latest_fin_dates_cache`, `latest_met_dates_cache`)로 주입하여 무가공 대상(업데이트 없음)을 극속 스킵(Early Return) 처리합니다.
