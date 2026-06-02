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