# Sub Project 기술 의사결정 (decisions.md)

> **Sub Project**: p3_usdms **범위**: 이 Sub Project 내부에만 영향을 미치는 결정 **마지막 업데이트**: 2026-05-26 (Task-초기화)

---

## 사용 지침

전체 시스템에 영향을 미치는 결정은 `parent_wiki/decisions.md`에 기록. 이 파일은 이 Sub Project 내부 결정만 다룬다.

---

<!-- 항목 템플릿 --> <!-- --- id: {SUB}DEC-{N} date: YYYY-MM-DD task: Task-{ID} status: active / superseded / reverted --- ## [{SUB}DEC-{N}] {결정 제목} (Task-{ID}) ### 배경 {왜 이 결정이 필요했는가} ### 결정 내용 {무엇을 결정했는가} ### �|ID|제목|Task|상태|
|---|---|---|---|
|USDMS_DEC-001|SEC XBRL 재무 데이터 이산화 계산 및 Overwrite 벌크 갱신 전략|T-003|Active|
|USDMS_DEC-002|자가 치유형(Self-Healing) 가치평가 및 지표 복구 엔진 최적화|T-005|Active|
|USDMS_DEC-003|일시적/영구적 에러의 이원화 예외 처리 및 자동 쿨다운 릴리즈 루프|T-005|Active|
|USDMS_DEC-004|수집 마감 분기점 및 거래정지/차단 배제 기반 실질 갭 진단 정책|T-007|Active|
|USDMS_DEC-005|수/토요일 시분할 일정에 따른 미국 휴장일 전체 스킵 로직 제거 및 캘린더 싱크 보존|—|Active|
|USDMS_DEC-006|2분할 MOD 2 해시 샤딩 기반 가치평가 연산 최적화 및 시세 전수 수집 분리|—|Active|
|USDMS_DEC-007|USDMS 스케줄러 동적 리로드 및 진행률 로깅 개선 (tqdm 배제)|—|Active|
|USDMS_DEC-008|misfire_grace_time 15분(900초) 롤백 및 스케줄 충돌 방지 정책|—|Active|

---

## USDMS_DEC-001: SEC XBRL 재무 데이터 이산화 계산 및 Overwrite 벌크 갱신 전략 (T-003)

### 배경
- 레거시 USDMS v5.0 오리지널 파서는 `(period_end, filed_dt)` 조합으로 그룹화하여 Balance Sheet of Instant 정보와 Income Statement / Cash Flow of Duration 정보가 분리 적재되는 구조적 문제가 있었음.
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
- 미국 일봉 수집 배치 작업의 마감 시각 and 한국 표준시(KST) 시차 조건에 따라 단순 날짜 비교 시 미수집 오탐지가 발생함.
- 거래량 0(거래정지/Suspended) 종목이나 네트워크/API 오류로 격리 차단된 블랙리스트 종목이 전체 미수집 갭으로 단순 산입되어, 인프라나 특이 종목 상태로 인한 허위 알람을 유발하였음.
- 테스트 시 실제 외부 KIS API 및 로컬 DB 인프라가 개입하지 않는 완전 격리된 모킹 단위 검증 체계 and 실시간 배치 로그 스트리밍 모듈이 부재함.

### 결정 내용
1. **KST 07:00 완료 분기점 판정**: 헬스 체크 시각이 07:00 KST 이전이면 전영업일 수집 커버리지를 검증하고, 07:00 KST 이후에는 당일 수집 완료율을 체크하여 수집 주기와 일치하도록 보장함.
2. **실질 누락 갭 필터링**: 수집 대상 모수에서 거래량 0인 레코드와 `is_blocked = TRUE`인 블랙리스트 종목을 제외하여 인프라적 오작동에 의한 오경보를 배제하고 '순수 데이터 유실률'을 계산함.
3. **FastAPI dependency_overrides 격리 및 Mocking**: 단위 테스트 기동 시 실제 DB 커넥션을 모킹 객체(`MagicMock`)로 완전히 치환하고 스케줄러 개입을 원천 차단하여 중요 로직만을 1초 이내에 보장하는 Tier 1/2 테스트 스위트 구축.
4. **WebSocket tail -f 실시간 로그 스트리밍**: HTTP API 호출에 의존하지 않고, 최초 연결 시 기존 로그 100줄을 전달한 뒤 비동기 루프 및 `asyncio.sleep` 폴링을 통해 최신 덧붙여진 로그 데이터만을 지속 텍스트로 송신하는 실시간 중계 아키텍처 수립.

### 영향 범위
- `tdms_core/p3_usdms/routers/health.py`
- `tdms_core/p3_usdms/routers/admin.py`
- `tdms_core/p3_usdms/tests/test_health_auditors.py`

---

## USDMS_DEC-005: 수/토요일 시분할 일정에 따른 미국 휴장일 전체 스킵 로직 제거 및 캘린더 싱크 보존

### 배경
- 당사의 USDMS 수집 스케줄링은 매일이 아닌 **수요일, 토요일 배치**로 시분할 가동되어 미국 장마감 이후 전 영업일의 데이터를 가져오는 패턴을 가집니다.
- 기존 daily_routine 내에 "target_date가 미국 영업일이 아닐 경우 전체 루틴 스킵" 로직이 있어, 2026-07-03 금요일(미국 독립기념일 대체휴일)이 휴장일이었던 여파로 토요일 배치 가동 시 SEC 공시 싱크 및 캘린더 최신화 등의 전체 수집이 스킵되는 심각한 데이터 정합성 누락 현상이 발생했습니다.

### 결정 내용
1. **미국 영업일 기준 조기 종료(스킵) 로직 전면 제거**:
   - `daily_routine.py` 에서 target_date가 미국 영업일이 아닐 때 `SKIPPED` 처리하여 파이프라인 전체를 중단하고 빠져나오는 로직을 제거하여, 전 영업일이 휴장일이었을지라도 당일 기동된 배치는 SEC Ticker 싱크 등의 프로세스를 중단 없이 완수하도록 변경했습니다.
2. **캘린더 동기화 및 기록 유지**:
   - 수집 조기 종료 스킵은 제거하되, `sync_trading_calendar` 호출은 보존하여 `trading_calendar` 테이블 상의 휴일 여부 데이터('Y'/'N')는 정상적으로 업데이트 및 갱신되도록 유지합니다.

### 영향 범위
- `tdms_core/p3_usdms/tasks/daily_routine.py`
- `tdms_core/p3_usdms/tests/test_holiday_sync.py` (단위 테스트 리팩토링 검증 완료)

---

## USDMS_DEC-006: 2분할 MOD 2 해시 샤딩 기반 가치평가 연산 최적화 및 시세 전수 수집 분리

### 배경
- USDMS 밸류에이션 및 메트릭 재연산 배치 시 전체 약 8,000개 CIK 종목을 전수 계산하게 되어 6시간 이상의 과도한 실행 시간이 소요되었습니다.
- 또한 연산 도중 대용량 데이터 로드로 인해 Docker 공유 메모리 부하 에러(Bus error)가 발생하는 성능 한계가 있었습니다.
- 2분할 MOD 2 해시 샤딩 도입 시, 매일 생성되는 시세 데이터(일봉 가격 수집)까지 격일로 분할 수집되어 시세 정합성이 누락되는 피드백 리스크가 식별되었습니다.

### 결정 내용
1. **시세 전수 수집 및 재무/연산만 샤딩 분리**:
   - 일일 가격 수집(Step 2 가격수집) 단계에서는 샤딩 배제 후 전체 활성 종목(`all_ciks`)을 타겟팅하여 매일 최신 시세가 빠짐없이 수집되도록 보장합니다.
   - 데이터 가동 부하가 크고 주중 분산 처리가 허용되는 Step 3~4(재무정보 파서 및 밸류에이션/메트릭 계산 연산 루프)에만 MOD 2 해시 샤딩을 한정 적용하여 자원을 효율화합니다.
2. **결정론적 MOD 2 해시 샤딩 도입**:
   - 주 2회 수요일과 토요일에 수집 배치가 분할 수행되는 스케줄링 구조에 정밀 매핑하기 위해, CIK를 MOD 2 결정론적 해싱으로 나누어 수요일에는 MOD 2 = 0 인 그룹, 토요일에는 MOD 2 = 1 인 그룹을 계산하도록 하여 계산량을 50% 수준으로 완전히 양분시켰습니다.
3. **공유 메모리 크기 확장**:
   - 대규모 벌크 적재 및 쿼리 도중 발생하는 Bus error 방지를 위해, `docker-compose.yml` 상의 `shm_size` 설정을 `64mb`에서 `512mb`로 8배 확장 적용했습니다.
4. **수동 기동 옵션 호환**:
   - 수동 전체 재연산 기동 시에는 샤딩이 적용되지 않고 전 종목이 안전하게 연산되도록 `target_group=-1` 파라미터를 탑재해 스케줄링 배치와 분리 통제합니다.

### 영향 범위
- `tdms_core/p3_usdms/engines/valuation_calculator.py` (MOD 2 샤딩 연산 로직 구현)
- `tdms_core/p3_usdms/tasks/daily_routine.py` (배치 스케줄 타겟 그룹 바인딩 및 시세 수집 단계 샤딩 제외 적용)
- `docker-compose.yml` (shm_size 512mb 확장)
- `tdms_core/p3_usdms/tests/test_daily_routine.py` (단위 테스트 갱신)

---

## USDMS_DEC-007: USDMS 스케줄러 동적 리로드 및 진행률 로깅 개선 (tqdm 배제)

### 배경
- 가치평가 루프 연산(CIK 순회) 도중 진행 정보가 출력되지 않아 종료 시간 예측과 배치 모니터링이 매우 어려웠습니다.
- 기존에 시도했던 tqdm 방식의 로그는 비동기 표준 에러 출력으로 인해 파일 적재 시 로그 크기를 과도하게 키우고 포맷을 훼손하여 관리 효율성을 저해했습니다.
- 크론 스케줄 관리 페이지에서 일정 변경 시, 요일(`day_of_week`)을 함께 넘길 수 없고 도커 이미지를 재빌드하거나 재부팅해야 일정이 로드되는 비효율이 있었습니다.

### 결정 내용
1. **tqdm 배제 및 logger.info 기반 정밀 진행률 로깅**:
   - tqdm 라이브러리를 전면 배제하고, `DailyRoutine._run_calculations` 및 수집 루프 내부에 `logger.info` 기반의 순수 텍스트 프로그레스 계산 로직을 탑재했습니다.
   - 50개 CIK/Ticker 주기 및 수집 완료 시점마다 `[진행률 %, 속도 (it/s), 경과시간 (Elapsed), 예상완료시간 (ETA), 현재 수집중인 종목]` 형태로 INFO 수준 로그를 출력하여 정상 구동을 깔끔하게 검증할 수 있도록 개선했습니다.
2. **.env 메모리 리로드 및 동적 일정 갱신**:
   - `.env` 파일 쓰기 이후 `POST /api/admin/schedules/reload` API를 신설하여 `dotenv.load_dotenv(override=True)`를 강제 호출해 `os.environ` 딕셔너리를 메모리에 즉시 재배치하고, APScheduler 스케줄을 실시간 리스케줄합니다.
3. **요일(day_of_week) 편집 지원**:
   - 일정 변경 PUT API(`update_schedule`)에 요일 매개변수를 유입하여 스케줄러가 요일 크론 트리거 설정을 안전하게 보존하도록 변경했습니다.

### 영향 범위
- `tdms_core/p3_usdms/tasks/daily_routine.py` (logger.info 기반 진행률 로깅 반영)
- `tdms_core/p3_usdms/routers/admin.py` (reload 스케줄 API 신설 및 요일 파라미터 확장)

---

## USDMS_DEC-008: misfire_grace_time 15분(900초) 롤백 및 스케줄 충돌 방지 정책

### 배경
- WSL2 및 개발 PC 절전 모드 진입/해제 시점이나 서버 과부하로 인해 기동 일정이 과도하게 밀린 스케줄러 배치 작업들이 한꺼번에 중첩되어 돌게 되는 현상이 관찰되었습니다.
- 이는 DB 커넥션 과부하 및 동일 날짜 데이터 적재 충돌 등의 데이터 오염 리스크를 유발했습니다.

### 결정 내용
1. **misfire_grace_time 15분 제한**:
   - 지연 허용치를 과다하게 크게 설정할 경우, 지연된 다수의 작업이 동시 병렬 가동을 시도하게 되어 리소스 경합 및 수집 정합성을 손상시키는 리스크를 차단하기 위해 `misfire_grace_time`을 **15분(900초)**으로 강하게 통제합니다.
2. **coalesce 및 max_instances 제한 바인딩**:
   - APScheduler `job_defaults`에 `coalesce = True`를 지정하여 동일 작업 누적 시 1회만 병합 실행되도록 보장하고, `max_instances = 1`을 통해 단일 작업의 중복 병렬 구동을 원천 통제했습니다.

### 영향 범위
- `tdms_core/p3_usdms/main.py` (lifespan 내 scheduler job_defaults 설정 보완)
- `tdms_core/p3_usdms/routers/admin.py` (스케줄 관리 스펙 및 롤백 조치 공유)
�스 체크 시각이 07:00 KST 이전이면 전영업일 수집 커버리지를 검증하고, 07:00 KST 이후에는 당일 수집 완료율을 체크하여 수집 주기와 일치하도록 보장함.
2. **실질 누락 갭 필터링**: 수집 대상 모수에서 거래량 0인 레코드와 `is_blocked = TRUE`인 블랙리스트 종목을 제외하여 인프라적 오작동에 의한 오경보를 배제하고 '순수 데이터 유실률'을 계산함.
3. **FastAPI dependency_overrides 격리 및 Mocking**: 단위 테스트 기동 시 실제 DB 커넥션을 모킹 객체(`MagicMock`)로 완전히 치환하고 스케줄러 개입을 원천 차단하여 중요 로직만을 1초 이내에 보장하는 Tier 1/2 테스트 스위트 구축.
4. **WebSocket tail -f 실시간 로그 스트리밍**: HTTP API 호출에 의존하지 않고, 최초 연결 시 기존 로그 100줄을 전달한 뒤 비동기 루프 및 `asyncio.sleep` 폴링을 통해 최신 덧붙여진 로그 데이터만을 지속 텍스트로 송신하는 실시간 중계 아키텍처 수립.

### 영향 범위
- `tdms_core/p3_usdms/routers/health.py`
- `tdms_core/p3_usdms/routers/admin.py`
- `tdms_core/p3_usdms/tests/test_health_auditors.py`

---

## USDMS_DEC-005: 수/토요일 시분할 일정에 따른 미국 휴장일 전체 스킵 로직 제거 및 캘린더 싱크 보존

### 배경
- 당사의 USDMS 수집 스케줄링은 매일이 아닌 **수요일, 토요일 배치**로 시분할 가동되어 미국 장마감 이후 전 영업일의 데이터를 가져오는 패턴을 가집니다.
- 기존 daily_routine 내에 "target_date가 미국 영업일이 아닐 경우 전체 루틴 스킵" 로직이 있어, 2026-07-03 금요일(미국 독립기념일 대체휴일)이 휴장일이었던 여파로 토요일 배치 가동 시 SEC 공시 싱크 및 캘린더 최신화 등의 전체 수집이 스킵되는 심각한 데이터 정합성 누락 현상이 발생했습니다.

### 결정 내용
1. **미국 영업일 기준 조기 종료(스킵) 로직 전면 제거**:
   - `daily_routine.py` 에서 target_date가 미국 영업일이 아닐 때 `SKIPPED` 처리하여 파이프라인 전체를 중단하고 빠져나오는 로직을 제거하여, 전 영업일이 휴장일이었을지라도 당일 기동된 배치는 SEC Ticker 싱크 등의 프로세스를 중단 없이 완수하도록 변경했습니다.
2. **캘린더 동기화 및 기록 유지**:
   - 수집 조기 종료 스킵은 제거하되, `sync_trading_calendar` 호출은 보존하여 `trading_calendar` 테이블 상의 휴일 여부 데이터('Y'/'N')는 정상적으로 업데이트 및 갱신되도록 유지합니다.

### 영향 범위
- `tdms_core/p3_usdms/tasks/daily_routine.py`
- `tdms_core/p3_usdms/tests/test_holiday_sync.py` (단위 테스트 리팩토링 검증 완료)

---

## USDMS_DEC-006: 2분할 MOD 2 해시 샤딩 기반 가치평가 연산 최적화

### 배경
- USDMS 밸류에이션 및 메트릭 재연산 배치 시 전체 약 8,000개 CIK 종목을 전수 계산하게 되어 6시간 이상의 과도한 실행 시간이 소요되었습니다.
- 또한 연산 도중 대용량 데이터 로드로 인해 Docker 공유 메모리 부하 에러(Bus error)가 발생하는 성능 한계가 있었습니다.

### 결정 내용
1. **결정론적 MOD 2 해시 샤딩 도입**:
   - 주 2회 수요일과 토요일에 수집 배치가 분할 수행되는 스케줄링 구조에 정밀 매핑하기 위해, CIK를 MOD 2 결정론적 해싱으로 나누어 수요일에는 MOD 2 = 0 인 그룹, 토요일에는 MOD 2 = 1 인 그룹을 계산하도록 하여 계산량을 50% 수준으로 완전히 양분시켰습니다.
2. **공유 메모리 크기 확장**:
   - 대규모 벌크 적재 및 쿼리 도중 발생하는 Bus error 방지를 위해, `docker-compose.yml` 상의 `shm_size` 설정을 `64mb`에서 `512mb`로 8배 확장 적용했습니다.
3. **수동 기동 옵션 호환**:
   - 수동 전체 재연산 기동 시에는 샤딩이 적용되지 않고 전 종목이 안전하게 연산되도록 `target_group=-1` 파라미터를 탑재해 스케줄링 배치와 분리 통제합니다.

### 영향 범위
- `tdms_core/p3_usdms/engines/valuation_calculator.py` (MOD 2 샤딩 연산 로직 구현)
- `tdms_core/p3_usdms/tasks/daily_routine.py` (배치 스케줄 타겟 그룹 바인딩)
- `docker-compose.yml` (shm_size 512mb 확장)
- `tdms_core/p3_usdms/tests/test_daily_routine.py` (단위 테스트 갱신)

---

## USDMS_DEC-007: USDMS 스케줄러 동적 리로드 및 진행률 로깅 개선

### 배경
- 가치평가 루프 연산(CIK 순회) 도중 진행 정보가 출력되지 않아 종료 시간 예측과 배치 모니터링이 매우 어려웠습니다.
- 크론 스케줄 관리 페이지에서 일정 변경 시, 요일(`day_of_week`)을 함께 넘길 수 없고 도커 이미지를 재빌드하거나 재부팅해야 일정이 로드되는 비효율이 있었습니다.

### 결정 내용
1. **tqdm 방식의 실시간 진행률 로깅 도입**:
   - `DailyRoutine._run_calculations` CIK 루프 내부에 진행 정보 분석 로직을 탑재하여 50개 CIK 주기마다 진행 퍼센테이지, 속도(CIK/s), 경과시간, ETA를 로그로 실시간 스트리밍합니다.
2. **.env 메모리 리로드 및 동적 일정 갱신**:
   - `.env` 파일 쓰기 이후 `POST /api/admin/schedules/reload` API를 신설하여 `dotenv.load_dotenv(override=True)`를 강제 호출해 `os.environ` 딕셔너리를 메모리에 즉시 재배치하고, APScheduler 스케줄을 실시간 리스케줄합니다.
3. **요일(day_of_week) 편집 지원**:
   - 일정 변경 PUT API(`update_schedule`)에 요일 매개변수를 유입하여 스케줄러가 요일 크론 트리거 설정을 안전하게 보존하도록 변경했습니다.

### 영향 범위
- `tdms_core/p3_usdms/tasks/daily_routine.py` (tqdm 실시간 진행률 로깅 반영)
- `tdms_core/p3_usdms/routers/admin.py` (reload 스케줄 API 신설 및 파라미터 확장)