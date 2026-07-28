# UsFinancialRoutine (us_financial_routine.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-07-17  
> **물리 경로**: `tdms_core/p3_usdms/tasks/us_financial_routine.py`  
> **상태**: ✅ 완료

---

## 1. 개요
미국 시장의 SEC EDGAR 재무 공시(facts)를 수집하고, 실질 적재 여부에 따라 핀포인트 재무비율 계산(`MetricCalculator`) 및 일별 전종목 가치평가 연산(`ValuationCalculator`)을 종합 조정(Orchestration)하는 전용 루틴 모듈입니다.
기존 `DailyRoutine` 내부에 강하게 결합되어 있던 재무 수집 및 연산 절차를 별도 파이프라인으로 완전히 분리하여 수집 효율과 모니터링 안정성을 극대화하였습니다.

---

## 2. 인터페이스 시그니처

```python
from typing import Dict, Any, List
from datetime import date

class UsFinancialRoutine:
    def __init__(self):
        """
        UsFinancialRoutine을 초기화하고 지연 로딩을 수행합니다.
        (MasterRepo, FinancialRepo, ValuationRepo, FinancialParser, MetricCalculator, ValuationCalculator)
        """

    async def run(self, test_limit: int = None, target_date: date = None, force_all: bool = False) -> Dict[str, Any]:
        """
        재무 수집 및 지표/가치평가 계산 파이프라인 전체 과정을 비동기로 실행합니다.

        [실행 절차]
        - Step 1: SEC Daily Index 스캔
          * target_date(기본값: 오늘)를 기준으로 지난 5일(T-5 ~ T-1) 동안 SEC EDGAR에 제출된 회사 공시 인덱스를 스캔합니다.
          * 실패 시 다운로드 노티스를 주고 당일 수집 단계를 안전하게 통과(스킵)합니다.
        - Step 2: 수집 대상 CIK 필터링 (개선사항)
          * 스캔된 CIK 중 DB 상의 활성 종목이며 실질적인 수집 대상(`is_collect_target = True`, 약 380개 CIK)인 종목들만 타겟 CIK(`target_ciks`)로 선별합니다.
          * 불필요한 비대상 기업에 대한 API 요청 시간을 줄여 수집 효율을 약 60% 이상 대폭 단축합니다.
        - Step 3: SEC Filing Index & Financial Parser (핀포인트 facts 수집 및 실질 적재 추적)
          * `FinancialParser.run(target_ciks)`를 실행하여, 실제 데이터베이스 `us_standard_financials`에 신규 표준 재무제표가 적재(Upsert 발생)된 CIK 리스트(`ingested_ciks`)를 반환받습니다.
        - Step 4: Metric & Valuation Calculators (이원화 연산 및 핀포인트 계산)
          * 9대 재무비율 및 YoY 성장률(`MetricCalculator`): 데이터 변동이 발생한 기업에 대해서만 계산하도록 오직 `ingested_ciks`에 대해서만 핀포인트 연산을 기동합니다.
          * 5대 가치평가 지표(`ValuationCalculator`): 매일 변동하는 시세(주가)를 즉각 반영하기 위해 전체 활성 종목(`all_active_ciks`)을 대상으로 전수 연산을 기동합니다.
          * 계산 루프 내부(청크 단위)에 `await asyncio.sleep(0.01)` 비동기 양보를 도입하여 실시간 웹소켓 로그 스트리밍 시 블로킹 현상을 방지하며, 청크 완료 시점마다 진행률, 연산 속도(symbols/s), 경과 시간, ETA를 요약 로깅(Progress Logging)합니다.
        - Step 5: Health Check & Audit
          * `FinancialDiagnostic` 및 `MetricVerifier`를 기동하여 적재 및 계산 무결성을 정밀 검증하고 이상치 발생 시 격리 처리합니다.

        Args:
            test_limit (int, optional): 테스트 구동 시 제한할 CIK 수
            target_date (date, optional): 공시 인덱스를 스캔할 기준일 (생략 시 오늘 날짜)
            force_all (bool, optional): 참일 경우, 5일간 공시 인덱스 스캔을 배제하고 수집 대상 전체 CIK를 타겟으로 일괄 수집/연산을 강제 수행
        Returns:
            Dict[str, Any]: 성공 여부, 소요 시간, 각 단계별 처리 건수 및 상세 통계를 포함한 결과 리포트
        """
```

---

## 3. 실행 이력 파일 저장 및 실시간 로그 일원화 정책
* **실시간 로그 파일 일원화**: 실시간 대시보드 웹소켓 스트리밍 연동이 단일 로그 스트림만 주시하더라도 시세와 재무 로그를 모두 수집할 수 있도록 로그 파일명을 **`daily_routine.log`로 일원화**하였습니다.
* **실행 이력 저장**: 수집 및 연산 처리가 완료되면 상세 결과를 담은 이력 JSON 파일을 `logs/p3_usdms/` 폴더 내에 저장합니다.
  - 파일명 규격: `us_financial_YYYYMMDD_HHMMSS.json`
* **실시간 진행상황 요약 로깅 (Progress Logging)**:
  - `Step 4` 가치평가 및 재무비율 계산 시 매 청크(100개 CIK)가 완료될 때마다 다음 정보가 요약되어 `daily_routine.log` 에 파일 및 콘솔로 기록됩니다.
  - 포맷: `[Step 4] Valuation Calculation Progress: 96.8% (3700/3823) | Speed: 1.3 symbols/s | Elapsed: 2919s | ETA: 00:01:37`
  - 이를 통해 장시간 소요되는 벌크 계산 과정에서 모니터링 누락 없이 안전하게 진행률을 확인할 수 있습니다.
* **로그 타임존 관련 주의사항**:
  - 도커 컨테이너 내부 환경은 기본적으로 UTC(세계표준시) 시간대를 사용하므로, 로그 타임스탬프(`[2026-07-18 06:16:20]`)는 한국 시간(KST)보다 9시간 느리게 기입됩니다.
* **UI 통합 상태 연동**: P4 Manager 백엔드(`status_service.py`)에서 `us_financial` 키워드로 상태 리포트와 스케줄 크론을 정규화 매핑하여, 대시보드의 `US Financial` 탭 품질 요약 패널에 실시간 렌더링되도록 연동하였습니다.
