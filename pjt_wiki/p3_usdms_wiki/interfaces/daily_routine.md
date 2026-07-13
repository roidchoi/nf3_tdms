# DailyRoutine (daily_routine.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-16  
> **물리 경로**: `tdms_core/p3_usdms/tasks/daily_routine.py`  
> **상태**: ✅ 완료

---

## 1. 개요
미국 시장 데이터의 전체 자동 수집 및 정합성 연산을 조정(Orchestration)하는 중추 모듈입니다. 5단계 일일 루프 및 주간 정기 백필(자가 치유 복구 및 릴리즈 포함) 태스크를 제어합니다. 각 단계 간의 예외 차단을 통해 하나의 단계 실패가 다른 단계로 전파되지 않도록 하며(Partial Success 보장), 적재 데이터 이상치를 감지하여 롤백하는 데이터 격리 기능을 탑재하고 있습니다.

---

## 2. 인터페이스 시그니처

```python
from typing import Dict, Any, List

class DailyRoutine:
    def __init__(self):
        """
        DailyRoutine을 초기화하고 필요한 수집 모듈, 계산 엔진 및 레포지토리를 지연 로딩합니다.
        (MasterSync, MarketDataLoader, FinancialParser, MetricCalculator, ValuationCalculator)
        """

    async def run(self, test_limit: int = None, target_date: date = None) -> Dict[str, Any]:
        """
        일일 수집 파이프라인의 전체 과정을 비동기로 실행합니다.
        
        [실행 절차]
        - Step 0: 캘린더 자동 동기화 (`sync_trading_calendar`) 및 영업일 기록
          * target_date(기본값: 오늘 - 1일) 시점까지 `trading_calendar` 테이블을 자동 갱신(영업일 여부 'Y'/'N' 입력)합니다.
          * 수/토요일 배치 기동의 특성상 target_date가 미국 영업일이 아니더라도(휴장일/공휴일 등) 수집기 파이프라인 전체를 스킵하지 않고 정상 기동하여 SEC 공시 싱크 및 최신 캘린더 데이터 갱신을 누적 지속하도록 스킵 조기 종료 처리를 배제합니다.
        - Step 1: MasterSync 구동 (SEC 마스터 종목 및 이력 동기화)
        - 대상 추출: Active 수집 대상 중 Blacklist에 의해 차단되지 않은 CIK 목록을 스캔합니다.
        - 동적 Lookback 산출: DB 내 `us_daily_price` 최신 적재 날짜를 조회하여, 오늘 대비 공백 기간(days_diff)에 안전 마진(+2)을 준 동적 `lookback_days`를 결정합니다. (최소 10일, DB 데이터가 없으면 기본 30일)
        - Step 2: Market Data Update (OHLCV 시세 및 수정계수 팩터 동적 수집 적재)
        - Step 3: SEC Filing Index & Financial Parser (미국 공시 재무 제표 파싱 적재)
        - Step 3.5 & 4: Metric & Valuation Calculators (9대 비율, YoY 성장률 및 5대 가치 평가 지표 연산 적재)
          * 연산 중 예외가 발생하면 해당 CIK를 PARSE_ERROR_CRITICAL 사유로 블랙리스트 매니저에 실패 누적을 기록합니다.
        - Step 5: Health Check & Isolation (적재 데이터 변동 이상치 검사 및 오염 데이터 격리)
          * 시세 이상치(PRICE_SPIKE: 당일 cls_prc <= 0 또는 전일 대비 50% 초과 변동)
          * 밸류에이션 이상치(VALUATION_JUMP: 전일 대비 PE 지표 2.0배 초과 혹은 0.5배 미만 급등락)
          * 이상 종목 감지 시, target_date 당일 적재된 시세 및 가치평가 레코드를 DB에서 즉시 롤백(DELETE)하고 PARSE_ERROR_CRITICAL 사유로 블랙리스트 실패 누적을 기록합니다.
        
        Args:
            test_limit (int, optional): 테스트 스위트 구동 시 제한할 CIK 수
            target_date (date, optional): 수집 대상일 (생략 시 Asia/Seoul 시간대 기준 수집 당일의 전날 날짜를 수집 대상일로 계산해 적용)
        Returns:
            Dict[str, Any]: 각 단계의 성공/실패 여부, 소요 시간 및 수집 세부 사항이 포함된 리포트 딕셔너리
        """

    def sync_trading_calendar(self, limit_date: date) -> None:
        """
        `usdms_db`의 `trading_calendar` 테이블을 limit_date 시점까지 동기화합니다.
        - DB의 MAX(dt)를 구한 뒤, MAX(dt) 다음 날부터 limit_date까지 순차적으로 `is_us_trading_day()`를 확인해 opnd_yn ('Y'/'N') 컬럼을 포함하여 `trading_calendar`에 인서트합니다.
        """

    def run_weekly_backfill(self) -> Dict[str, Any]:
        """
        주간 정기 유지보수 및 자가 치유 파이프라인을 실행합니다. (주말 백그라운드 크론 구동용)
        
        [실행 절차]
        1. 차단 쿨다운(7일)이 경과한 블랙리스트 종목들의 차단을 자동으로 해제(Auto-Release)합니다.
        2. 메타데이터 미보강 종목을 대상으로 `MasterEnricher`를 기동하여 최대 50개의 yfinance 보강을 시도합니다.
        3. 신규 보강된 메타데이터 및 수정계수를 반영하여 Dynamic Targeting 규칙(`MasterRepo.apply_targeting_rules()`)을 적용,
           시가총액 및 가격 요건에 맞추어 수집 대상을 조정합니다.
           * Entry: 시총 >= 5,000만$, 가격 >= 1$ 이면 `is_collect_target = TRUE`
           * Retention: 시총 < 3,500만$, 가격 < 0.8$ 이면 `is_collect_target = FALSE`
        
        Returns:
            Dict[str, Any]: 해제된 블랙리스트 수, 보강된 수, 타겟 조정 결과를 담은 리포트 딕셔너리
        """
```

---

## 3. 실행 이력 파일 저장 및 동적 로그 바인딩 정책
* **동적 로그 핸들러 바인딩**: 실시간 웹소켓 로그 스트리밍을 원활히 지원하기 위해, `daily_routine` 실행 시 `logs/daily_routine.log` 파일을 대상으로 하는 `logging.FileHandler`를 root_logger에 기동 시 동적으로 바인딩(중복 생성 방지 설계 포함)하여 로그를 기록합니다.
  - **주의**: 파이썬 기본 로깅 레벨 제한으로 인해 `INFO` 로그가 누락되지 않도록 `p3_usdms/main.py` 기동 시점에 `logging.basicConfig(level=logging.INFO)` 설정을 명시해 주어야 합니다. (2026-06-16 보완 반영)
* **실행 이력 저장**: 실행 완료 시, 최종 리포트를 JSON 구조로 변환하여 `tdms_core/p3_usdms/logs/` 폴더 내에 저장합니다.
* **파일명 규격**:
  - 일일 루틴: `daily_routine_YYYYMMDD_HHMMSS.json`
  - 주간 루틴: `weekly_backfill_YYYYMMDD_HHMMSS.json`
* **실시간 기동 상태(is_running) 동기화**:
  - `/api/admin/tasks/status` API는 디렉토리 내 JSON 파일 목록(최근 10건)을 리턴하되, 메모리 상에서 실제 백그라운드 태스크가 한창 동작 중일 때는 `_running_task` 플래그를 체크하여 해당 태스크의 최신 상태 객체의 `"is_running"`을 `True`로, `"status"`를 `"RUNNING"`으로 동적 오버라이드하거나 추가하여 반환합니다.
  - P4 Manager의 `status_service.py`는 이 목록을 순회할 때, 동일한 `job_id`에 대해 최신(역순 정렬 상 앞쪽) 상태 정보만 캐싱하고 과거 이력에 의해 덮어씌워지지 않도록 중복 수집 방지 필터를 적용합니다. (2026-06-16 보완 반영)

