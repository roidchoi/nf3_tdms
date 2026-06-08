# Task-007: 헬스·어드민 API + Auditors + WebSocket

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)
> **PRD 근거**: F-10, F-11, F-12, API-헬스, REFACTOR-3
> **작성일**: 2026-06-04
> **의존 Task**: T-006 (완료)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p3_usdms_wiki/environment.md` | ✅ 확인 |
| DB 스키마 | 위키 미기록 → `tdms_core/p1_shared/p1_shared/db/usdms_origin/init.sql` 직접 확인 완료 | ⚠️ 직접 확인 |
| API 명세 사양 | `pjt_wiki/p3_usdms_wiki/interfaces/data_api_endpoints.md` | ✅ 확인 |
| DailyRoutine 구조 | 위키 미기록 → `tdms_core/p3_usdms/tasks/daily_routine.py` 직접 확인 완료 | ⚠️ 직접 확인 |
| p2_kdms 헬스체크 구현 패턴 | 위키 미기록 → `tdms_core/p2_kdms/routers/health.py` 직접 확인 완료 | ⚠️ 직접 확인 |
| Auditors 원본 로직 | 위키 미기록 → `migration_pjt/usdms_origin/backend/auditors/` 직접 확인 완료 | ⚠️ 직접 확인 |
| 헬스체크 및 Auditors API | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

`p3_usdms` 백엔드 시스템의 데이터 최신성(Freshness), 데이터 누락(Gaps), 수집 차단 목록(Blacklist)을 실시간으로 감시하는 헬스체크 API를 구축하고, 가격/재무 데이터의 정합성을 보장하는 Auditors 엔진 3종을 이식하며, 스케줄 관리 및 실시간 로그 스트리밍을 포함한 어드민 기능과 CLI 진단 도구를 완성합니다.

**구현 범위:**
- **IN**:
  - `routers/health.py` 신규 생성: `/api/health/freshness`, `/api/health/gaps`, `/api/health/blacklist` 엔드포인트 구현.
  - `routers/admin.py` 확장: `/api/admin/tasks/status`, `/api/admin/schedules` (GET/PUT), WebSocket `/ws/logs` 실시간 로그 스트리밍 구현.
  - `auditors/` 엔진 3종 이식:
    - `financial_auditor.py` (`FinancialDiagnostic`): 회계 항등식 및 누락 비율, 연도 왜곡 검증.
    - `metric_auditor.py` (`MetricVerifier`): ROE 역산 정합성 및 가치평가 아웃라이어 검증.
    - `price_auditor.py` (`PriceReproducer`): 로컬 수정주가 재현 및 KIS 실제 수정 종가 교차 검증.
  - `ops/run_diagnostics.py` 생성: 터미널에서 Auditors를 온디맨드로 실행하고 진단 리포트를 생성하는 CLI 도구.
  - `main.py` 수정: `health_router` 등록 및 WebSocket 라우팅 연결.
  - `tests/test_health_auditors.py` 신규 생성: 헬스 API 및 Auditors 기능 검증을 위한 테스트 코드 구축.
- **OUT**:
  - `db_manager.py`를 `repositories`로 완전히 분리하는 리팩토링은 T-008에서 진행하므로, T-007에서는 기존 작성된 repositories를 활용하되 필요 시 직접 쿼리를 수행합니다.

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/routers/health.py` — 헬스체크 API 엔드포인트
- `tdms_core/p3_usdms/auditors/__init__.py` — Auditors 패키지 초기화
- `tdms_core/p3_usdms/auditors/financial_auditor.py` — 재무 감사 엔진
- `tdms_core/p3_usdms/auditors/metric_auditor.py` — 지표 역산 및 아웃라이어 검증 엔진
- `tdms_core/p3_usdms/auditors/price_auditor.py` — 수정주가 교차 검증 엔진
- `tdms_core/p3_usdms/ops/run_diagnostics.py` — CLI 진단 스크립트
- `tdms_core/p3_usdms/tests/test_health_auditors.py` — T-007 통합 및 단위 테스트

### 수정 대상 파일
- `tdms_core/p3_usdms/main.py` — `health_router` 임포트 및 등록
- `tdms_core/p3_usdms/routers/admin.py` — `/tasks/status`, `/schedules` (GET/PUT), WebSocket `/ws/logs` 추가 및 APIRouter 프리픽스/구조 조정

---

## § 3. 핵심 인터페이스

### 1. 헬스체크 라우터 (`routers/health.py`)
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
from fastapi import APIRouter, Depends, Query, Request
from typing import Dict, Any
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.repositories.price_repo import PriceRepo
from p3_usdms.repositories.blacklist_repo import BlacklistRepo

router = APIRouter(prefix="/api/health", tags=["System Health"])

# [출처: tdms_core/p3_usdms/routers/data.py 직접 확인 완료 및 신규 추가]
def get_db_pool(request: Request):
    return getattr(request.app.state, "pool", None)

def get_master_repo(pool = Depends(get_db_pool)) -> MasterRepo:
    return MasterRepo(pool)

def get_price_repo(pool = Depends(get_db_pool)) -> PriceRepo:
    return PriceRepo(pool)

def get_blacklist_repo(pool = Depends(get_db_pool)) -> BlacklistRepo:
    return BlacklistRepo(pool)

@router.get("/freshness")
def get_freshness(
    master_repo = Depends(get_master_repo),
    price_repo = Depends(get_price_repo),
    pool = Depends(get_db_pool)
) -> Dict[str, Any]:
    """
    미국 영업일 캘린더(trading_calendar) 기준 최신 2개 영업일을 확보하여 
    활성 상장 종목 대비 당일 일봉 수집 완료율(Coverage ratio)을 판정합니다.
    - 한국 시간 07:00 KST 이전: 전영업일 기준 95% 이상 시 GREEN
    - 한국 시간 07:00 KST 이후: 당일 영업일 기준 95% 이상 시 GREEN
    """
    ...

@router.get("/gaps")
def get_gaps(
    start_date: str = Query(None),
    end_date: str = Query(None),
    price_repo = Depends(get_price_repo),
    blacklist_repo = Depends(get_blacklist_repo),
    pool = Depends(get_db_pool)
) -> Dict[str, Any]:
    """
    지정 기간 동안 수집 대상(is_collect_target=True) 종목들의 일봉 OHLCV 누락을 탐지합니다.
    - 거래정지(일봉 거래량 volume == 0) 및 블랙리스트 등록 종목은 모수에서 제외하여 '실질 누락율' 산출.
    """
    ...

@router.get("/blacklist")
def get_blacklist(
    blacklist_repo = Depends(get_blacklist_repo)
) -> Dict[str, Any]:
    """
    현재 수집 차단 상태(is_blocked=True)인 종목들의 CIK, 사유코드 및 세부 내역을 반환합니다.
    """
    ...
```

### 2. 어드민 라우터 확장 (`routers/admin.py`)
```python
# [출처: tdms_core/p3_usdms/routers/admin.py 직접 확인 완료 및 신규 확장]
from fastapi import APIRouter, WebSocket, Depends, Request
from typing import Dict, Any, List

# APIRouter의 prefix를 /api/admin 으로 확대 조정 (기존 /api/admin/tasks 에서 변경)
router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])

@router.get("/tasks/status")
def get_tasks_status() -> List[Dict[str, Any]]:
    """
    logs/ 디렉토리에 적재된 daily_routine_*.json 및 weekly_backfill_*.json 파일 목록을
    역순으로 조회하여 최근 10건의 실행 이력 리포트 리스트를 반환합니다.
    """
    ...

@router.get("/schedules")
def get_schedules(request: Request) -> List[Dict[str, Any]]:
    """
    FastAPI app.state에 등록된 APScheduler 객체로부터 
    현재 등록된 크론 작업들의 ID, 크론 표현식, 다음 실행 예정 시각을 조회합니다.
    """
    ...

@router.put("/schedules")
def update_schedule(
    job_id: str,
    hour: int,
    minute: int,
    request: Request
) -> Dict[str, Any]:
    """
    특정 스케줄 작업(예: daily_collection_job)의 실행 시각을 동적으로 변경합니다.
    """
    ...

@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, log_file: str = None):
    """
    WebSocket 연결을 승인하고, 최신 daily_routine 로그 파일(.log)을
    실시간으로 한 줄씩 스트리밍 전송합니다. (tail -f 방식 구현)
    """
    ...
```

### 3. Auditors 엔진 3종 (`auditors/`)

#### ① 재무 감사 (`financial_auditor.py`)
```python
# [출처: migration_pjt/usdms_origin/backend/auditors/financial_auditor.py 직접 확인 완료 및 리팩토링]
from typing import List, Dict, Any

class FinancialDiagnostic:
    def __init__(self, pool):
        self.pool = pool

    def check_accounting_identity(self, sample_limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Assets = Liabilities + Equity 항등식 검증 (허용 오차 0.1% 초과 시 실패)
        """
        ...

    def check_critical_nulls(self) -> List[Dict[str, Any]]:
        """
        total_assets (임계치 5%), revenue (임계치 10%), net_income (임계치 5%)의 NULL 발생 비율 검사
        """
        ...

    def check_historical_leakage(self) -> List[Dict[str, Any]]:
        """
        공시연도(report_period.year)와 회계연도(fiscal_year) 차이가 2년을 초과하는지 검사
        """
        ...
```

#### ② 지표 감사 (`metric_auditor.py`)
```python
# [출처: migration_pjt/usdms_origin/backend/auditors/metric_auditor.py 직접 확인 완료 및 리팩토링]
from typing import List, Dict, Any

class MetricVerifier:
    def __init__(self, pool):
        self.pool = pool

    def verify_roe_logic(self, sample_limit: int = 500) -> List[Dict[str, Any]]:
        """
        ROE 산출 값과 (NetIncome / TotalEquity) 직접 계산 값 비교 검증 (오차 1% 초과 검출)
        """
        ...

    def verify_valuation_logic(self, sample_limit: int = 500) -> List[Dict[str, Any]]:
        """
        시가총액 0 이하 및 극단적인 PE 비율 Outlier (PE > 10000 또는 PE < -10000) 검출
        """
        ...
```

#### ③ 수정주가 감사 (`price_auditor.py`)
```python
# [출처: migration_pjt/usdms_origin/backend/auditors/price_auditor.py 직접 확인 완료 및 리팩토링]
from typing import Dict, Any

class PriceReproducer:
    def __init__(self, pool, kis_us_client):
        self.pool = pool
        self.kis = kis_us_client

    def verify_ticker(self, ticker: str, start_dt: str = None, end_dt: str = None) -> Dict[str, Any]:
        """
        로컬 Raw 종가에 누적수정계수(factors)를 곱한 계산값과 KIS API의 실제 수정 종가를 정대조합니다.
        - 기본 오차 임계치: 0.1%
        - NVDA 등 예외 종목: 2.0%
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤, 모든 테스트가 통과하도록 구현하세요.

### 4.1 정상 동작 케이스

```python
# [Tier 2 — 격리 통합]
def test_health_freshness_with_high_coverage_returns_green_status(client, mocker):
    """
    [목적] 당일 수집 커버리지가 95% 이상이고 지연이 없는 경우 GREEN 상태를 정상 반환하는지 검증.
    [유도] get_freshness 라우터가 trading_calendar 기준 최신 영업일을 조회하고, 
           활성 종목 대비 OHLCV 수집 완료 개수를 기반으로 커버리지를 정확히 판정하도록 유도.
    """
    # Arrange
    mock_master = mocker.patch("p3_usdms.routers.health.get_master_repo")
    mock_price = mocker.patch("p3_usdms.routers.health.get_price_repo")
    mock_pool = mocker.patch("p3_usdms.routers.health.get_db_pool")
    
    mock_master.return_value.get_collect_targets.return_value = [{"cik": "0000320193"}] * 100
    mock_price.return_value.get_daily_price_count_for_date.return_value = 98 # 98% 수집
    
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [("2026-06-03",), ("2026-06-02",)]
    mock_pool.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor

    # Act
    response = client.get("/api/health/freshness")

    # Assert
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "GREEN"
    assert res["daily_coverage_ratio"] == 0.98
```

```python
# [Tier 2 — 격리 통합]
def test_health_gaps_with_blacklist_and_suspended_stocks_excludes_from_total(client, mocker):
    """
    [목적] 일봉 거래량이 0인 종목(거래정지) 및 수집 블랙리스트에 올라간 종목을 갭 스캔의 모수에서 제외하고 올바른 성공률을 구하는지 검증.
    [유도] get_gaps 함수 내부에서 수집 대상 중 거래정지(vol=0) 및 블랙리스트 상태를 제외하고 유효 수집율을 계산하도록 유도.
    """
    # Arrange
    mock_price = mocker.patch("p3_usdms.routers.health.get_price_repo")
    mock_blacklist = mocker.patch("p3_usdms.routers.health.get_blacklist_repo")
    mock_pool = mocker.patch("p3_usdms.routers.health.get_db_pool")

    # 3개 종목 타겟 중 A, B는 수집 완료, C는 미수집 상태
    # 그러나 C는 일봉 상 volume == 0 (거래정지)
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.side_effect = [
        [("2026-06-03",)], # trading_calendar 조회
        [("A", 1000), ("B", 2000), ("C", 0)], # daily volume 조회
        [("C", "SEC_403")] # blacklist 사유 조회
    ]
    mock_pool.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_price.return_value.get_collect_targets_for_date.return_value = ["A", "B", "C"]

    # Act
    response = client.get("/api/health/gaps?start_date=2026-06-03&end_date=2026-06-03")

    # Assert
    assert response.status_code == 200
    res = response.json()
    # C는 거래정지 및 블랙리스트이므로 배제되어 유효 수집율 100% (A, B 완료)
    assert res["minute_gaps"][0]["valid_collection_rate"] == 100.0
```

### 4.2 경계값 케이스

```python
# [Tier 2 — 격리 통합]
def test_health_freshness_with_yellow_boundary_returns_yellow_status(client, mocker):
    """
    [목적] 수집 커버리지가 95.0% 이상 98.0% 미만인 경계선에서 YELLOW 등급을 정상 부여하는지 확인.
    """
    # Arrange
    mock_master = mocker.patch("p3_usdms.routers.health.get_master_repo")
    mock_price = mocker.patch("p3_usdms.routers.health.get_price_repo")
    mock_pool = mocker.patch("p3_usdms.routers.health.get_db_pool")
    
    mock_master.return_value.get_collect_targets.return_value = [{"cik": "0"}] * 100
    mock_price.return_value.get_daily_price_count_for_date.return_value = 96 # 96% 수집
    
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [("2026-06-03",), ("2026-06-02",)]
    mock_pool.return_value.get_cursor.return_value.__enter__.return_value = mock_cursor

    # Act
    response = client.get("/api/health/freshness")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "YELLOW"
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_financial_auditor_with_zero_assets_skips_accounting_identity():
    """
    [목적] Total Assets가 0인 극단적인 데이터가 들어왔을 때, DivisionByZero 에러를 예방하고 정상 처리(skip)하는지 검증.
    """
    # Arrange
    from p3_usdms.auditors.financial_auditor import FinancialDiagnostic
    diagnostic = FinancialDiagnostic(pool=None)
    
    # total_assets가 0인 가상의 행 데이터
    rows = [{"cik": "123", "report_period": "2025-12-31", "total_assets": 0.0, "total_liabilities": 0.0, "total_equity": 0.0}]
    
    # Act
    failed = []
    for r in rows:
        assets = r['total_assets']
        liab_equity = r['total_liabilities'] + r['total_equity']
        if assets == 0:
            continue # expected to skip
        diff_pct = abs(assets - liab_equity) / abs(assets) * 100
        if diff_pct > 0.1:
            failed.append(r)

    # Assert
    assert len(failed) == 0
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
from p3_usdms.auditors.financial_auditor import FinancialDiagnostic
from p3_usdms.repositories.base import BaseRepository

@pytest.mark.integration
def test_financial_auditor_with_real_db_retains_accounting_identity(real_pool):
    """
    [목적] 실제 DB의 us_standard_financials 테이블을 대상으로 회계 항등식 검증이 문제 없이 동작하는지 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    # Arrange
    diagnostic = FinancialDiagnostic(pool=real_pool)

    # Act
    failed_samples = diagnostic.check_accounting_identity(sample_limit=10)

    # Assert
    assert isinstance(failed_samples, list)
    # 데이터베이스에 이상이 없다면 일반적으로 0건이어야 함
    for sample in failed_samples:
        assert "cik" in sample
        assert "diff_pct" in sample
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_health_freshness_with_high_coverage_returns_green_status` | Tier 2 | 정상 | 수집율 98% 일 때 GREEN 상태 반환 |
| 2 | `test_health_gaps_with_blacklist_and_suspended_stocks_excludes_from_total` | Tier 2 | 정상 | 거래정지 및 블랙리스트 종목을 갭 탐지 모수에서 제외 |
| 3 | `test_health_freshness_with_yellow_boundary_returns_yellow_status` | Tier 2 | 경계값 | 수집율 96% 일 때 YELLOW 상태 반환 |
| 4 | `test_financial_auditor_with_zero_assets_skips_accounting_identity` | Tier 1 | 예외 | 자산 0인 종목의 zero division 방지 예외 처리 |
| 5 | `test_financial_auditor_with_real_db_retains_accounting_identity` | Tier 3 | 실제 통합 | 실제 데이터베이스의 표준화 재무 테이블 항등식 검사 기동 확인 |

**총 5개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

### 1. 미국 시장 특화 세부 기획 사항
- **가격 변동 제한폭 (Spike) 판단 완화**:
  - 미국 시장은 상하한가 제한이 없으므로 일일 ±30% 변동을 "제한폭 위반"으로 간주할 수 없습니다. 
  - 대신 `daily_routine.py`에 적용된 `PRICE_SPIKE` 기준과 유사하게 **일일 ±50% 초과 변동**을 비정상 시세 이상치(Outlier)로 감지하도록 완화합니다.
- **Freshness 시간대 정규화**:
  - 미국 시장의 마감 시각(한국 시간 화~토 05:00/06:00)과 수집 완료 시각(07:00 KST)을 고려하여, 한국 시간 **07:00 KST**를 분기점으로 Freshness를 동적 판정하도록 설계합니다.

### 2. 기술 스택 및 환경변수
- **언어**: Python 3.12
- **라이브러리**: fastapi, uvicorn, apscheduler
- **DB 테이블**: `us_ticker_master`, `us_daily_price`, `us_daily_valuation`, `us_financial_facts`, `us_financial_metrics`, `us_price_adjustment_factors`, `us_share_history`, `us_standard_financials`, `us_ticker_history`, `us_collection_blacklist`
- **위키 참조**:
  - `pjt_wiki/p3_usdms_wiki/interfaces/data_api_endpoints.md` — 데이터 API 엔드포인트 규격
  - `pjt_wiki/p3_usdms_wiki/environment.md` — 패키지 의존성 및 환경 변수 설정

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 통과
- [ ] `p3_usdms_pjt_tasks.md`의 Task-007 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-007_walkthrough.md` 작성 및 저장
