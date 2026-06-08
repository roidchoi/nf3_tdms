# Sub Project 기술 의사결정 (decisions.md)

> **Sub Project**: p3_usdms **범위**: 이 Sub Project 내부에만 영향을 미치는 결정 **마지막 업데이트**: 2026-05-26 (Task-초기화)

---

## 사용 지침

전체 시스템에 영향을 미치는 결정은 `parent_wiki/decisions.md`에 기록. 이 파일은 이 Sub Project 내부 결정만 다룬다.

---

<!-- 항목 템플릿 --> <!-- --- id: {SUB}DEC-{N} date: YYYY-MM-DD task: Task-{ID} status: active / superseded / reverted --- ## [{SUB}DEC-{N}] {결정 제목} (Task-{ID}) ### 배경 {왜 이 결정이 필요했는가} ### 결정 내용 {무엇을 결정했는가} ### 영향 범위 - {영향받는 모듈/파일} ### 대안 검토 | 대안 | 거부 이유 | |------|----------| | {대안} | {이유} | ### 관련 링크 - `interfaces.md#{섹션}` (인터페이스 영향) - `parent_wiki/decisions.md#{DEC-ID}` (상위 결정과 연관 시) -->

---

## 의사결정 목록

|ID|제목|Task|상태|
|---|---|---|---|
|USDMS_DEC-001|SEC XBRL 재무 데이터 이산화 계산 및 Overwrite 벌크 갱신 전략|T-003|Active|
|USDMS_DEC-002|자가 치유형(Self-Healing) 가치평가 및 지표 복구 엔진 최적화|T-005|Active|
|USDMS_DEC-003|일시적/영구적 에러의 이원화 예외 처리 및 자동 쿨다운 릴리즈 루프|T-005|Active|
|USDMS_DEC-004|수집 마감 분기점 및 거래정지/차단 배제 기반 실질 갭 진단 정책|T-007|Active|

---

## USDMS_DEC-001: SEC XBRL 재무 데이터 이산화 계산 및 Overwrite 벌크 갱신 전략 (T-003)

### 배경
- 레거시 USDMS v5.0 오리지널 파서는 `(period_end, filed_dt)` 조합으로 그룹화하여 Balance Sheet의 Instant 정보와 Income Statement / Cash Flow의 Duration 정보가 분리 적재되는 구조적 문제가 있었음.
- 분기 누적값(YTD) 형태의 손익계산서/현금흐름표 정보를 그대로 사용할 경우, 개별 분기(Q2, Q3) 실적이 왜곡되어 가치평가 및 성장률 연산 오류를 유발함.

### 결정 내용
1. **(fy, fp) 그룹화**: 회계 연도(fy)와 회계 분기(fp)를 기준으로 데이터를 결합하여 Instant와 Duration 항목의 완결된 셋을 구성함.
2. **분기 이산치 역산 계산 (`_derive_discrete_from_ytd`)**:
   - `Q2_discrete = Q2_YTD - Q1`
   - `Q3_discrete = Q3_YTD - Q2_YTD`
   공식을 통해 YTD 누적치에서 이전 기간 수치를 차감하여 순수 개별 분기 실적을 역산 도출함.
3. **CIK 단위 Overwrite 벌크 갱신**: EAV 데이터의 중복 및 과거 불완전 보고서 정정을 고려하여, 수집 개시 시점 해당 CIK의 로우 facts를 일괄 삭제(`delete_raw_facts_by_cik`)하고 통째로 벌크 적재하는 방식을 유지함.
4. **무부채 zero-debt 대응 개선**: `total_debt` 계산 시 장/단기 부채 중 하나라도 수집되었다면 둘 다 `0`이라 하더라도 `None` 대신 `0.0`을 유지함으로써 무부채 우량 기업의 가치평가 산출 에러를 차단함.
5. **fy(회계연도) 정수 타입 캐스팅 개선**: 소수점/문자형 혼선 및 결측치를 미연에 방지하고자 `groupby` 연산 직전 `fy` 컬럼을 정수형(`int`)으로 정밀 캐스팅 적용함.

### 영향 범위
- `tdms_core/p3_usdms/collectors/financial_parser.py`
- `tdms_core/p3_usdms/repositories/financial_repo.py`

---

## USDMS_DEC-002: 자가 치유형(Self-Healing) 가치평가 및 지표 복구 엔진 최적화 (T-005)

### 배경
- 수집 장애, 강제 중단 또는 연산 유실 등으로 인해 특정 종목의 가격은 적재되었으나 일별 가치평가(`us_daily_valuation`)가 적재되지 못한 공백(Gap)이 발생할 경우, 기존에는 10년 치 전체 데이터를 재연산해야 하여 약 4시간 이상의 과부하가 걸렸음.
- 증분 재계산을 기동하기 위해 갭 날짜를 판별하는 쿼리가 10년 치 대량 데이터 조인 병목으로 인해 42초 이상 소요되어 스케일러빌리티 위협이 됨.

### 결정 내용
1. **60일 룩백 자가 치유 갭 감지 기법**: 
   - `ValuationCalculator.calculate_and_save` 실행 시 최근 60일의 룩백 윈도우 내에서 주가는 기 적재되어 있으나 PE 등 가치지표가 누락된 최초의 날짜(`gap_dt`)를 자동 스캔하여, 해당 시점부터 가치평가를 증분 재계산하도록 연동함.
2. **갭 스캔 쿼리 인덱스 및 범위 한정 최적화**:
   - `ValuationRepo.get_earliest_valuation_gap_date`에 `start_date` 파라미터를 추가하여 쿼리 조회 대상을 최근 60일(`dt >= start_date`)로 강제 한정하여 조인 병목을 해결하고 탐색 속도를 1ms 이하로 단축시킴.
3. **재무제표 부재 종목 스킵 (`EXISTS` 가드)**:
   - ETF나 CEF 등 재무제표가 아예 없어 갭 탐색 시 무한 정체되는 현상을 방지하고자, 갭 판별 SQL 내에 `EXISTS (SELECT 1 FROM us_standard_financials)` 조건을 결합하여 재무제표 및 주식수가 실재하는 종목에 대해서만 갭을 추적하게 함.

### 영향 범위
- `tdms_core/p3_usdms/engines/valuation_calculator.py`
- `tdms_core/p3_usdms/repositories/valuation_repo.py`

---

## USDMS_DEC-003: 일시적/영구적 에러의 이원화 예외 처리 및 자동 쿨다운 릴리즈 루프 (T-005)

### 배경
- 레거시 수집기는 429 Rate Limit이나 일시적인 네트워크 장애가 생겼을 때에도 무조건 블랙리스트에 올리거나, 또는 블랙리스트 기능을 완전히 끄는 하드코딩이 팽배해 장기 수집 시 정상 종목이 영구 소실되거나 IP 밴을 초래하는 등의 불합리가 존재했음.
- 차단된 종목들의 차단을 풀기 위해서 관리자의 수동 직접 개입이 강제되는 비효율이 있었음.

### 결정 내용
1. **실패 원인의 명확한 분류 및 이원화 분기 (`record_failure`)**:
   - `TRANSIENT_ERRORS` (429, Timeout 등) 발생 시 `is_blocked = FALSE`인 상태를 유지한 채 `fail_count`만 1 누적.
   - `PERMANENT_ERRORS` (404, Delisted 등) 발생 시 즉시 `is_blocked = TRUE`로 격리.
2. **차단 승격(Promotion) 및 Cooldown 자동 해제 루프**:
   - 일시적 오류라도 5회(`threshold`) 누적 기록 시 영구 차단으로 승격시켜 시스템 마비 전파를 방어.
   - 주간 루틴(`run_weekly_backfill`) 수행 시 마지막 실패일로부터 7일(`cool_off_days`)이 경과한 차단 종목을 스캔하여 자동으로 차단을 해제(`is_blocked=FALSE`, `fail_count=0`)해 재진입 기회를 부여하는 자가 치유 라이프사이클 구축.
3. **yfinance 불능 종목 강제 Target 배제**:
   - yfinance 보강 실패 에러가 `HTTP_404`, `DELISTED`로 판명될 경우, 블랙리스트 차단과 함께 DB의 메타데이터를 `Unknown` 및 `is_collect_target = FALSE`로 강제 업데이트하여 매일 불필요하게 스캔하는 현상을 차단함.

### 영향 범위
- `tdms_core/p3_usdms/utils/blacklist_manager.py`
- `tdms_core/p3_usdms/collectors/master_enricher.py`
- `tdms_core/p3_usdms/tasks/daily_routine.py`

---

## USDMS_DEC-004: 수집 마감 분기점 및 거래정지/차단 배제 기반 실질 갭 진단 정책 (T-007)

### 배경
- 미국 일봉 수집 배치 작업의 마감 시각과 한국 표준시(KST) 시차 조건에 따라 단순 날짜 비교 시 미수집 오탐지가 발생함.
- 거래량 0(거래정지/Suspended) 종목이나 네트워크/API 오류로 격리 차단된 블랙리스트 종목이 전체 미수집 갭으로 단순 산입되어, 인프라나 특이 종목 상태로 인한 허위 알람을 유발하였음.
- 테스트 시 실제 외부 KIS API 및 로컬 DB 인프라가 개입하지 않는 완전 격리된 모킹 단위 검증 체계와 실시간 배치 로그 스트리밍 모듈이 부재함.

### 결정 내용
1. **KST 07:00 완료 분기점 판정**: 헬스 체크 시각이 07:00 KST 이전이면 전영업일 수집 커버리지를 검증하고, 07:00 KST 이후에는 당일 수집 완료율을 체크하여 수집 주기와 일치하도록 보장함.
2. **실질 누락 갭 필터링**: 수집 대상 모수에서 거래량 0인 레코드와 `is_blocked = TRUE`인 블랙리스트 종목을 제외하여 인프라적 오작동에 의한 오경보를 배제하고 '순수 데이터 유실률'을 계산함.
3. **FastAPI dependency_overrides 격리 및 Mocking**: 단위 테스트 기동 시 실제 DB 커넥션을 모킹 객체(`MagicMock`)로 완전히 치환하고 스케줄러 개입을 원천 차단하여 순수 로직만을 1초 이내에 보장하는 Tier 1/2 테스트 스위트 구축.
4. **WebSocket tail -f 실시간 로그 스트리밍**: HTTP API 호출에 의존하지 않고, 최초 연결 시 기존 로그 100줄을 전달한 뒤 비동기 루프 및 `asyncio.sleep` 폴링을 통해 최신 덧붙여진 로그 데이터만을 지속 텍스트로 송신하는 실시간 중계 아키텍처 수립.

### 영향 범위
- `tdms_core/p3_usdms/routers/health.py`
- `tdms_core/p3_usdms/routers/admin.py`
- `tdms_core/p3_usdms/tests/test_health_auditors.py`