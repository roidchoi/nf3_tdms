# [DEC-011] US Financial Routine and Pinpoint Metrics Computation Pipeline

## Status
- **상태**: Approved ✅
- **결정일**: 2026-07-17
- **작성자**: Antigravity

---

## 1. 맥락 (Context)
- 기존 USDMS 수집기(`DailyRoutine`)는 하루에 한 번 기동되어 마스터 동기화, 시세 수집, 재무 공시 스캔 및 facts 수집, 그리고 이에 연쇄된 재무비율(`MetricCalculator`) 및 가치지표(`ValuationCalculator`) 연산을 하나의 동기식 파이프라인에서 묶어서 기동하고 있었음.
- 또한, 시세 수집 시에 `target_group` 해시 샤딩(MOD 2)이 묶여있어 특정 요일에 시세 수집 대상이 배제되는 등 정합성 누락 리스크가 높았음.
- 재무 공시 수집 또한 전체 활성 기업(977 CIK)을 대상으로 인덱스 스캔 후 facts 호출을 시도함에 따라 불필요한 SEC API 트래픽을 과도하게 소모하였고, 데이터 변화가 없는 대부분의 기업에 대해 매 루프마다 재무비율을 반복 연산하는 대형 오버헤드가 발생하고 있었음.
- 게다가, 대량 연산 시 파이썬 이벤트 루프가 블로킹되어 대시보드로 실시간 로그 웹소켓 데이터가 즉각 플러시되지 않고 한꺼번에 쏟아지는 모니터링 저하 문제도 수반됨.

---

## 2. 결정 사항 (Decision)
- **시세/재무 수집의 E2E 파이프라인 분리 (이원화)**:
  1. `DailyRoutine`을 순수 시세/팩터 수집 전용으로 경량화하고, 가격 수집 대상의 해시 샤딩을 전면 제거하여 매일 전체 종목 시세를 전수 수집함으로써 시세 정합성을 확보한다.
  2. 재무 수집 및 연산을 관장하는 `UsFinancialRoutine` 태스크를 신설하고 크론 스케줄을 이원화한다.
- **수집 대상 종목 필터링 적용**:
  - SEC index 스캔 결과 중 수집 대상 여부(`is_collect_target = True`, 약 380개 CIK)인 종목만 핀포인트 타겟팅하여 수집을 기동함으로써 트래픽 및 소요 시간을 약 60% 이상 대폭 단축한다.
- **실질 적재(Ingested) 기반 핀포인트 비율 계산**:
  - `FinancialParser`가 실제 표준 재무제표(`us_standard_financials`) 테이블에 신규 업서트(Upsert) 성공한 종목(`ingested_ciks`) 리스트만 반환하도록 개선한다.
  - `MetricCalculator`(재무비율 및 YoY 성장률)는 오직 `ingested_ciks`에 대해서만 핀포인트로 연산을 실행하게 하여 중복 계산 리소스를 원천 제거한다.
  - 반면, 주가 변동을 매일 반영해야 하는 `ValuationCalculator`(PE, PBR 등)는 전체 활성 CIK 종목을 타겟으로 매일 갱신 연산을 수행한다.
- **실시간 웹소켓 양보, 로그 일원화 및 진행률 로깅**:
  - 대량 연산 청크 중간에 `await asyncio.sleep(0.01)` 비동기 sleep을 적용해 메인 이벤트 루프의 웹소켓 로그 송출 시간을 확보한다.
  - 로그 파일명을 `daily_routine.log`로 단일화하여 웹소켓이 끊김 없이 실시간으로 대시보드 하단에 로그를 노출하게 보정한다.
  - 장시간 소요되는 계산 단계에서 진행 상황을 파악할 수 있도록, 청크(`chunk_size=100`) 처리 완료 시점마다 진행률, 연산 속도(symbols/s), 경과 시간, ETA를 요약한 진행 상황 로그를 실시간으로 출력한다.
- **스케줄러 기동 상태 제어 격리**:
  - 스케줄러에 등록되어 구동되는 각 태스크(`daily_routine`, `us_financial`, `weekly_backfill`)의 기동 시점과 완료 시점에, 기존 레거시 `set_routine_running` 대신 `set_running_task`를 사용하여 개별 태스크 문자열 명칭을 격리 지정한다. 이로 인해 스케줄러 기동으로 인한 상태 오매핑 문제를 차단하고 통합 대시보드의 running 뱃지 정합성을 보장한다.

---

## 3. 구현 내용 (Implementation)
- `tdms_core/p3_usdms/tasks/us_financial_routine.py` 신설 및 `UsFinancialRoutine` 구현.
- `financial_parser.py` 내부 `process_company`가 DB Upsert 성공 여부를 boolean으로 리턴하고 `run`이 `Tuple[int, List[str]]`을 리턴하도록 변경.
- `main.py`에 `UsFinancialRoutine`을 매일 6시 비동기 APScheduler 크론 탭에 등록.
- `run_financial.py` CLI 도구를 추가하여 `--force-all` 및 `--limit` 기동 지원.

---

## 4. 결과 및 영향 (Consequences)
- **장점**:
  - 불필요한 SEC EDGAR API Rate Limit 소모 차단 및 수집 대기 시간의 획기적 절감 (약 60% 시간 절약).
  - 데이터베이스 중복 계산(CPU/Memory) 부하 극소화.
  - 웹소켓을 통한 E2E 모니터링 로그의 실시간성 확보 및 줄바꿈 없는 렌더링 완성.
- **주의 사항**:
  - 신규 공시 스캔이 실패하거나 누락되었을 시 강제로 전체 CIK를 긁어오기 위한 수동 CLI 강제 기동(`run_financial.py --force-all`) 요령 숙지 필요.

---
## 관련 엔티티
- [[p3_usdms_wiki/interfaces/daily_routine]]
- [[p3_usdms_wiki/interfaces/us_financial_routine]]
- [[p3_usdms_wiki/interfaces/financial_parser]]
