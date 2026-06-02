# Walkthrough - Task-003: SEC XBRL 재무 파싱 + 주식수 이력

SEC EDGAR의 Company Facts API 데이터를 기반으로 한 EAV 로우 facts 적재, US-GAAP 표준 매핑, 분기 누적값(YTD) 기반 이산값(Discrete Quarter) 계산 및 주식 수 변경 이력 관리 기능을 완결하였습니다.

---

## 1. 구현된 파일 목록 및 역할

- **`tdms_core/p3_usdms/collectors/xbrl_mapper.py`**
  - US-GAAP에 공시되는 비표준/fallback 태그들을 20여 개의 분석용 표준 회계 필드에 우선순위 매핑
  - 자본지출(Capex) 등 비용 성격 데이터의 부호 양수화 정규화(`normalize_sign`) 지원
- **`tdms_core/p3_usdms/collectors/financial_parser.py`**
  - CIK별 raw company facts를 Fetch하여 DEI(주식수) 및 US-GAAP 팩츠 데이터를 EAV 구조로 정제
  - `_standardize_financials_v2`를 적용하여 `(fy, fp)` 그룹화 연산 및 `Q2_discrete = Q2_YTD - Q1` 등의 누적값 차감을 통한 분기별 discrete 수치 도출
  - API 타임아웃 오류 시 예외 격리(Graceful Isolation)
- **`tdms_core/p3_usdms/repositories/financial_repo.py`**
  - `us_financial_facts` (EAV 형식 삭제 후 벌크 삽입)
  - `us_standard_financials` (표준 정제 데이터 upsert)
  - `us_share_history` (주식 수 이력 upsert)
- **`tdms_core/p3_usdms/tests/test_financial_collect.py`**
  - Tier 1: `XBRLMapper` 및 `_classify_duration` 검증
  - Tier 2: `_standardize_financials_v2` 분기 이산치 계산 및 Mock API 타임아웃 격리 검증
  - Tier 3: 실제 `usdms_timescaledb` 컨테이너 상의 물리 테이블 저장 및 데이터 조회 교차 검증

---

## 2. 설계상 주요 결정사항

- **EAV 삭제 후 삽입 (Overwrite) 패턴 유지**: `us_financial_facts` 테이블의 중복 및 과거 불완전 수정 보고서 혼선 방지를 위해, 특정 기업 파싱 시작 시 CIK 단위로 데이터를 깨끗이 날린(`delete_raw_facts_by_cik`) 뒤 재생성하는 레거시의 안전한 정책을 그대로 계승했습니다.
- **분기 이산화 역산 계산 고도화**: 단순 공시 일자가 아닌 회계 연도와 기간 `(fy, fp)`을 키로 데이터를 결합하여 Instant(재무상태표) 항목과 Duration(손익계산서/현금흐름표) 항목의 매칭을 확보하였으며, `tqdm` 진행바와 `pandas`를 이용한 고속 연산을 정착시켰습니다.

---

## 3. 테스트 및 검증 결과

### 3.1 단위 및 격리 통합 테스트 (Tier 1 & 2)
```bash
conda run -n tdms_p3_env pytest tdms_core/p3_usdms/tests/test_financial_collect.py -v -m "not integration"
```
- **결과**: **6개 테스트 케이스 전체 통과**
- **검증 항목**: XBRL 매핑 우선순위, 대체 태그 매칭, Capex 부호 정규화, Q2 이산화 역산값(220YTD - 100Q1 = 120Q2) 연산 정확성 및 API Timeout 격리 정상 수렴.

### 3.2 실제 DB 통합 테스트 (Tier 3)
```bash
conda run -n tdms_p3_env pytest tdms_core/p3_usdms/tests/test_financial_collect.py -v -m "integration" --run-integration
```
- **결과**: **1개 통합 테스트 케이스 통과**
- **검증 항목**: 실제 TimescaleDB 컨테이너에 EAV 벌크 삽입, 표준 재무 및 주식 수 이력 업서트(Conflict 발생 시 update) 쿼리가 타겟 복합 PK 제약조건 하에서 충돌 없이 저장 및 롤백까지 정상 작동함을 검증.

---

## 4. 다음 단계 진행 시 주의사항

- `T-003`에서 정제되어 적재된 재무 데이터 및 주식수 이력은 다음 Task인 **`T-004` (가치평가 및 재무비율 산출)**에서 가치지표(PE, PB, PS 등) 계산 시 `merge_asof(direction='backward')`를 통한 PIT 매칭용 원천 정보로 사용됩니다. 
- 따라서 `T-004` 구현 시 `us_standard_financials` 및 `us_share_history` 테이블 데이터의 시계열 무결성을 전제로 지표 연산을 전개해야 합니다.
