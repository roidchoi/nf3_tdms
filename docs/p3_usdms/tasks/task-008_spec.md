# Task-008: db_manager.py -> repositories/ 분리 리팩토링 및 환경변수 외부화

> **Sub Project**: p3_usdms
> **PRD 근거**: REFACTOR-1, REFACTOR-3, REFACTOR-4
> **작성일**: 2026-06-04
> **의존 Task**: T-007

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p3_usdms_wiki/environment.md` | ✅ 확인 |
| `MasterRepo.apply_targeting_rules()` 현재 시그니처 | `tdms_core/p3_usdms/repositories/master_repo.py` L120-162 직접 확인 | ⚠️ 직접 확인 |
| `MasterSync._update_target_status()` 하드코딩 내용 | `tdms_core/p3_usdms/collectors/master_sync.py` L640-673 직접 확인 | ⚠️ 직접 확인 |
| Settings 환경 설정 및 `SEC_USER_AGENT` 필수 검증 로직 | `tdms_core/p3_usdms/config.py` L26-30 직접 확인 | ⚠️ 직접 확인 |
| `main.py` APScheduler 등록 현황(`hour=6, minute=30`, `day_of_week` 미지정) | `tdms_core/p3_usdms/main.py` L82 직접 확인 | ⚠️ 직접 확인 |
| `DatabaseManager` shim 임포트 참조 현황 | `tdms_core/p3_usdms/tests/test_base_infra.py` L9 직접 확인 | ⚠️ 직접 확인 |
| `date_utils.py` 기존 KR 함수 구현 패턴 | `tdms_core/p1_shared/p1_shared/utils/date_utils.py` 직접 확인 | ⚠️ 직접 확인 |
| `trading_calendar` 테이블 컬럼(`dt`, `opnd_yn`) | `tdms_core/p3_usdms/routers/health.py` L49 쿼리 직접 확인 | ⚠️ 직접 확인 |

---

## § 1. 목표

`p3_usdms` 프로젝트의 최종 리팩토링 단계를 완료하여 레거시 호환 코드를 완전히 청소하고, 수집 임계 기준 설정을 유연하게 외부화합니다. 아울러 `p1_shared` 공통 모듈에 미국 주식시장 개장일 판별 유틸리티를 추가하고, `p3_usdms` 일일 수집 루틴 실행 시 미국 현지 공휴일에 따른 자동 스킵 및 `usdms_db` 내 `trading_calendar` 자동 동기화 메커니즘을 종합 구축합니다.

**구현 범위:**
- IN: 
  - `DatabaseManager` shim 어댑터(`collectors/db_manager.py`) 완전 제거
  - `ops/` 디렉토리 내의 중복/레거시 유틸리티 스크립트(`rebuild_all_valuations.py`, `verify_data_integrity.py`) 제거
  - 하드코딩되어 있던 수집 진입/유지 기준(시가총액, 가격)을 `.env` 및 `config.py`로 외부화하여 설정 처리
  - `MasterSync.py` 및 `MasterRepo.py`에서 외부화된 설정값을 활용하도록 변경
  - `p1_shared.utils.date_utils` 내 미국 휴장 판단 유틸리티(`is_us_trading_day` 등) 구현
  - `daily_routine.py` 기동 시 미국 수집 대상 전영업일 기준 휴장 스킵 및 `trading_calendar` 테이블 자동 동기화 로직 구현
  - `tests/test_base_infra.py` 및 기타 테스트 코드의 임포트 정리 및 단위 테스트 보강
- OUT:
  - `p2_kdms` 등 타 서브프로젝트의 소스 코드 수정

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/.env.example` — USDMS 기동 및 수집 기준 환경 변수 문서화 예시 파일
- `tdms_core/p3_usdms/tests/test_holiday_sync.py` — 미국 영업일 판단 유틸 및 `DailyRoutine` 휴장 스킵/캘린더 동기화 테스트

### 수정 대상 파일
- `tdms_core/p1_shared/p1_shared/utils/date_utils.py` — `is_us_trading_day`, `get_us_trading_days`, `last_us_trading_day` 유틸리티 함수 추가
  > ⚠️ **의존성 주의**: `p1_shared`는 이미 `holidays` 패키지를 사용 중이므로(기존 `is_kr_trading_day`) 추가 설치 불필요. `holidays.US(years=dt.year)` 방식으로 동일하게 구현.
- `tdms_core/p3_usdms/config.py` — `Settings` 클래스에 수집 타겟 기준 변수 4종 및 `SCHEDULE_DAILY_ROUTINE` 변수 추가
- `tdms_core/p3_usdms/main.py` — 하드코딩된 `scheduled_daily` 실행 일정을 `get_settings().SCHEDULE_DAILY_ROUTINE`으로 동적 로드하도록 변경
- `tdms_core/p3_usdms/tasks/daily_routine.py` — `DailyRoutine.run()` 기동 시 전날 휴장 여부 판단 스킵 및 `trading_calendar` 테이블 동기화 루틴 추가
- `tdms_core/p3_usdms/repositories/master_repo.py` — `apply_targeting_rules()` 메서드 시그니처 및 기본값 Fallback 처리
- `tdms_core/p3_usdms/collectors/master_sync.py` — `_update_target_status()` 메서드에서 환경 설정값 참조 및 쿼리 하드코딩 제거
- `tdms_core/p3_usdms/tests/test_base_infra.py` — `DatabaseManager` 제거에 따른 테스트 코드 정리 및 Config 수집 기준 검증 단위 테스트 추가
- `tdms_core/p3_usdms/tests/test_master_sync.py` — `MasterSync`의 수집 타겟팅 로직 내 환경 설정 참조 모킹 테스트 보강
- `tdms_core/p3_usdms/tests/test_valuation_metric.py` — 수집 기준 수정 관련 테스트 매개변수 정리 (필요 시)
- `/.env` (루트) — 신규 환경 변수 정의 추가

### 삭제 대상 파일
- `tdms_core/p3_usdms/collectors/db_manager.py` (전체 파일 삭제)
- `tdms_core/p3_usdms/ops/rebuild_all_valuations.py` (전체 파일 삭제)
- `tdms_core/p3_usdms/ops/verify_data_integrity.py` (전체 파일 삭제)

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 3.1 config.py Settings 클래스 변경
```python
# [출처: tdms_core/p3_usdms/config.py — 직접 확인 후 수정 사항 정의]
class Settings(BaseSettings):
    # DSN 및 환경변수
    TDMS_ENV: str = "dev"
    SEC_USER_AGENT: str = ""
    
    # DB (USDMS 전용)
    DEV_USDMS_DB_HOST: str = "127.0.0.1"
    DEV_USDMS_DB_PORT: int = 5433
    DEV_USDMS_DB_NAME: str = "usdms_db"
    DEV_USDMS_DB_USER: str = "usdms_user"
    DEV_USDMS_DB_PASSWORD: str = ""
    
    SERVER_USDMS_DB_HOST: str = ""
    SERVER_USDMS_DB_PORT: int = 5433
    SERVER_USDMS_DB_NAME: str = "usdms_db"
    SERVER_USDMS_DB_USER: str = "usdms_user"
    SERVER_USDMS_DB_PASSWORD: str = ""

    # 수집 기준 환경변수 추가 (T-008)
    TARGET_MIN_MARKET_CAP: float = 50000000.0      # $5천만 (진입)
    TARGET_MIN_PRICE: float = 1.00                 # $1.00 (진입)
    TARGET_RETAIN_MARKET_CAP: float = 35000000.0   # $3.5천만 (유지/탈퇴)
    TARGET_RETAIN_PRICE: float = 0.80              # $0.80 (유지/탈퇴)

    # 일일 루틴 스케줄 추가
    SCHEDULE_DAILY_ROUTINE: str = "07:30"          # 일일 수집 실행 일정 (HH:MM 형식, 디폴트 07:30 KST)
```

### 3.2 master_repo.py apply_targeting_rules() 시그니처 변경
```python
# [출처: pjt_wiki/p3_usdms_wiki/interfaces/master_repo.md — 직접 확인 후 수정 사항 정의]
class MasterRepo(BaseRepository):
    ...
    def apply_targeting_rules(
        self, 
        min_market_cap_entry: Optional[float] = None, 
        min_price_entry: Optional[float] = None,
        min_market_cap_exit: Optional[float] = None,
        min_price_exit: Optional[float] = None
    ) -> dict[str, int]:
        """
        Dynamic Targeting Rules를 SQL 트랜잭션으로 반영합니다.
        파라미터가 None일 경우, get_settings()의 값을 로드하여 기본값으로 사용합니다.
        
        Args:
            min_market_cap_entry: 진입 시가총액 하한 (기본값: settings.TARGET_MIN_MARKET_CAP)
            min_price_entry: 진입 가격 하한 (기본값: settings.TARGET_MIN_PRICE)
            min_market_cap_exit: 유지 시가총액 하한 (기본값: settings.TARGET_RETAIN_MARKET_CAP)
            min_price_exit: 유지 가격 하한 (기본값: settings.TARGET_RETAIN_PRICE)
        Returns:
            {"dropped_count": N, "added_count": M}
        """
        ...
```

### 3.3 date_utils.py 미국 주식시장 개장 판단 유틸리티 추가
```python
# [출처: tdms_core/p1_shared/p1_shared/utils/date_utils.py — 신규 함수 정의]
def is_us_trading_day(dt: date) -> bool:
    """
    미국 주식시장 영업일 여부를 확인합니다.
    - 주말(토, 일) 제외
    - 미국 연방 공휴일(holidays.US) 제외
    """
    ...

def get_us_trading_days(start_date: date, end_date: date) -> List[date]:
    """지정 범위 내의 미국 영업일 리스트를 반환합니다."""
    ...

def last_us_trading_day(reference: date) -> date:
    """reference 기준 직전(과거) 미국 영업일을 반환합니다."""
    ...
```

### 3.4 daily_routine.py의 미국 영업일 동기화 및 휴장 스킵 추가
```python
# [출처: tdms_core/p3_usdms/tasks/daily_routine.py — run 메서드 및 동기화 메서드 정의]
class DailyRoutine:
    ...
    async def run(self, test_limit: int = None, target_date: date = None) -> Dict[str, Any]:
        """
        일일 자동화 파이프라인 전체 오케스트레이션.
        - target_date가 지정되지 않았을 경우, KST 수집 당일 기준 전날(date.today() - timedelta(days=1))을 수집 대상일로 삼음.
        - 0. `usdms_db` 내 `trading_calendar`를 target_date 시점까지 자동 갱신 동기화 실행.
        - 1. target_date가 미국 영업일(`is_us_trading_day`)이 아니면 수집 루틴 전체 생략 후 즉시 스킵 리포트 리턴.
        - 2. 영업일일 경우에만 Step 1 ~ 5 단계별 순차 실행.
        """
        ...

    def sync_trading_calendar(self, limit_date: date) -> None:
        """
        `usdms_db`의 `trading_calendar` 테이블을 자동 동기화합니다.
        - `trading_calendar`에서 MAX(dt)를 조회합니다.
        - MAX(dt) 다음 날부터 limit_date까지 루프를 돌며 `is_us_trading_day(curr_d)`로 opnd_yn ('Y'/'N')을 매칭하여 인서트합니다.
        """
        ...
```

---

## § 3a. 기존 기능 보존 및 정리

### 제거 대상 인터페이스
- `DatabaseManager` 클래스 및 내부 `get_cursor()` 메서드는 완전히 제거됩니다.
- 더 이상 `from p3_usdms.collectors.db_manager import DatabaseManager` 형태로 임포트하거나 활용할 수 없습니다.

### 보존 및 리팩토링 대상 인터페이스
- `MasterRepo.apply_targeting_rules()`는 인자 없이 호출하더라도 환경 변수에 지정된 값을 통해 정상적으로 동작해야 합니다. (동작 호환성 보장)

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위]
# 파일: tdms_core/p3_usdms/tests/test_base_infra.py 추가
def test_config_loads_targeting_thresholds(mocker):
    """
    [목적] Settings 객체가 신규 추가된 수집 기준 및 스케줄 환경변수들을 기본값 또는 .env로부터 정확히 파싱해내는지 검증
    [유도] config.py의 Settings 클래스에 TARGET_* 및 SCHEDULE_DAILY_ROUTINE 변수가 알맞은 기본 타입으로 구현되었는지 검인
    """
    from p3_usdms.config import Settings
    
    # 1. 디폴트 값 검증
    settings = Settings(SEC_USER_AGENT="TestAgent name@test.com")
    assert settings.TARGET_MIN_MARKET_CAP == 50000000.0
    assert settings.TARGET_MIN_PRICE == 1.00
    assert settings.TARGET_RETAIN_MARKET_CAP == 35000000.0
    assert settings.TARGET_RETAIN_PRICE == 0.80
    assert settings.SCHEDULE_DAILY_ROUTINE == "07:30"

    # 2. Mock 환경변수 대입 시 파싱 검증
    mocker.patch.dict("os.environ", {
        "TARGET_MIN_MARKET_CAP": "100000000.0",
        "TARGET_MIN_PRICE": "2.50",
        "TARGET_RETAIN_MARKET_CAP": "80000000.0",
        "TARGET_RETAIN_PRICE": "2.00",
        "SCHEDULE_DAILY_ROUTINE": "08:15"
    })
    custom_settings = Settings()
    assert custom_settings.TARGET_MIN_MARKET_CAP == 100000000.0
    assert custom_settings.TARGET_MIN_PRICE == 2.50
    assert custom_settings.TARGET_RETAIN_MARKET_CAP == 80000000.0
    assert custom_settings.TARGET_RETAIN_PRICE == 2.00
    assert custom_settings.SCHEDULE_DAILY_ROUTINE == "08:15"

```

> ⚠️ **싱글톤 캐시 주의**: `get_settings()`는 내부적으로 `_settings` 싱글톤을 캐시하므로,
> 연달아 호출하는 테스트에서는 반드시 `mocker.patch("p3_usdms.config._settings", None)` 또는
> `Settings(...)` 직접 생성 방식을 사용해야 이전 테스트의 캐시 오염을 막을 수 있습니다.

```python
# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_base_infra.py 추가
# 현재 main.py 스케줄러: scheduler.add_job(scheduled_daily, "cron", hour=6, minute=30, id="daily_collection_job")
# T-008 구현 목표: day_of_week="tue-sat", hour/minute은 settings에서 동적 로드
@pytest.mark.asyncio
async def test_scheduler_daily_job_uses_configured_time(mocker):
    """
    [목적] lifespan 내의 APScheduler 등록 시 SCHEDULE_DAILY_ROUTINE으로 지정한 설정을 파싱(HH:MM)하여 add_job을 실행하는지 검증
    [유도] lifespan 실행 과정에서 AsyncIOScheduler.add_job의 호출 인자를 가로채어 설정된 값의 hour, minute와 매치되는지 검인
    """
    from p3_usdms.config import Settings
    mock_settings = Settings(
        SEC_USER_AGENT="TestAgent name@test.com",
        SCHEDULE_DAILY_ROUTINE="10:45"
    )
    mocker.patch("p3_usdms.main.get_settings", return_value=mock_settings)
    
    mock_scheduler = mocker.MagicMock()
    mocker.patch("p3_usdms.main.AsyncIOScheduler", return_value=mock_scheduler)
    
    # StartupValidator 및 pool/validator 리포트 모킹
    mocker.patch("p3_usdms.main.create_kdms_pool")
    mock_validator = mocker.patch("p3_usdms.main.StartupValidator")
    mock_validator.return_value.validate.return_value.is_healthy = True
    
    from p3_usdms.main import lifespan
    from fastapi import FastAPI
    
    app = FastAPI()
    async with lifespan(app):
        pass
        
    # scheduler.add_job 이 mock_settings에 지정된 10시 45분으로 호출되었는지 검증
    # daily_collection_job 에 대해서 cron, day_of_week="tue-sat", hour=10, minute=45 검사
    mock_scheduler.add_job.assert_any_call(
        mocker.ANY, "cron", day_of_week="tue-sat", hour=10, minute=45, id="daily_collection_job"
    )
```

```

```python
# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_master_sync.py 추가/수정
def test_master_sync_update_target_status_uses_settings_values(mocker):
    """
    [목적] MasterSync._update_target_status() 호출 시 하드코딩 대신 설정변수의 수집 타겟 값이 SQL 쿼리에 바인딩되는지 검증
    [유도] _update_target_status 내부에서 settings의 값을 쿼리에 대입하여 DB 커서가 실행되도록 유도
    """
    from p3_usdms.collectors.master_sync import MasterSync
    from p3_usdms.config import Settings
    
    mock_settings = Settings(
        SEC_USER_AGENT="TestAgent name@test.com",
        TARGET_MIN_MARKET_CAP=123456.0,
        TARGET_MIN_PRICE=7.89,
        TARGET_RETAIN_MARKET_CAP=10000.0,
        TARGET_RETAIN_PRICE=5.55
    )
    mocker.patch("p3_usdms.collectors.master_sync.get_settings", return_value=mock_settings)
    
    sync = MasterSync()
    # MasterSync._update_target_status()는 self.db.get_cursor()를 사용 (BaseRepository)
    # contextmanager 체인 전체를 모킹해야 함
    mock_cursor = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    sync.db.get_cursor = MagicMock(return_value=mock_ctx)
    
    sync._update_target_status()
    
    # execute가 두 번(retention 업데이트, entry 업데이트) 실행되었는지 확인
    # 현재 _update_target_status 구현: retention_q는 f-string으로 상수 하드코딩 → T-008에서 settings 참조로 변경 예정
    assert mock_cursor.execute.call_count == 2
    
    calls = mock_cursor.execute.call_args_list
    
    # 1. Retention 쿼리 인자 확인: exit 시가총액(10000.0), exit 가격(5.55)
    # 현재 구현은 f-string 직접 삽입이므로, 리팩토링 후에는 파라미터 바인딩(%s) 방식으로 변경됨
    retention_call_args = calls[0][0]  # (query, params_tuple) 형태
    assert len(retention_call_args) == 2, "retention_q는 파라미터 튜플로 바인딩되어야 합니다"
    assert 10000.0 in retention_call_args[1], "retention에 exit 시가총액이 바인딩되어야 합니다"
    assert 5.55 in retention_call_args[1], "retention에 exit 가격이 바인딩되어야 합니다"
    
    # 2. Entry 쿼리 인자 확인: entry 시가총액(123456.0), entry 가격(7.89)
    entry_call_args = calls[1][0]
    assert len(entry_call_args) == 2, "entry_q는 파라미터 튜플로 바인딩되어야 합니다"
    assert 123456.0 in entry_call_args[1], "entry에 진입 시가총액이 바인딩되어야 합니다"
    assert 7.89 in entry_call_args[1], "entry에 진입 가격이 바인딩되어야 합니다"
```

### 4.2 경계값 및 추가 구현 검증 케이스

```python
# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_master_sync.py 추가/수정
def test_master_repo_apply_targeting_rules_fallback_to_settings(mocker):
    """
    [목적] MasterRepo.apply_targeting_rules()에 명시적인 인자가 주어지지 않았을 때, get_settings()의 기본값들로 Fallback 처리되는지 검증
    """
    from p3_usdms.repositories.master_repo import MasterRepo
    from p3_usdms.config import Settings
    
    mock_settings = Settings(
        SEC_USER_AGENT="TestAgent name@test.com",
        TARGET_MIN_MARKET_CAP=900000.0,
        TARGET_MIN_PRICE=1.50,
        TARGET_RETAIN_MARKET_CAP=800000.0,
        TARGET_RETAIN_PRICE=1.20
    )
    mocker.patch("p3_usdms.repositories.master_repo.get_settings", return_value=mock_settings)
    
    repo = MasterRepo()
    mock_cursor = MagicMock()
    repo.get_cursor = MagicMock()
    repo.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    repo.apply_targeting_rules() # 파라미터 전달 안 함
    
    # execute 호출 인자에서 mock_settings의 값이 적용되었는지 검증
    calls = mock_cursor.execute.call_args_list
    assert len(calls) == 2
    
    # exit_query 실행 시의 인자에 800000.0, 1.20이 바인딩 되었는지 검사
    exit_args = calls[0][0][1] # tuple parameter
    assert exit_args[0] == 800000.0
    assert exit_args[1] == 1.20
    
    # entry_query 실행 시의 인자에 900000.0, 1.50이 바인딩 되었는지 검사
    entry_args = calls[1][0][1]
    assert entry_args[0] == 900000.0
    assert entry_args[1] == 1.50
```

```python
# [Tier 1 — 단위]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
def test_is_us_trading_day_weekend_and_holidays():
    """
    [목적] is_us_trading_day 유틸리티가 미국의 주말(토, 일) 및 공휴일(신정, 독립기념일 등)에 대해 올바르게 False를 반환하고, 일반 평일에 True를 반환하는지 확인
    """
    from p1_shared.utils.date_utils import is_us_trading_day
    from datetime import date
    
    # 1. 일반 평일 (2026-06-03 수요일) -> True
    assert is_us_trading_day(date(2026, 6, 3)) is True
    # 2. 주말 (2026-06-06 토요일) -> False
    assert is_us_trading_day(date(2026, 6, 6)) is False
    # 3. 미국 공휴일 (2026-05-25 메모리얼 데이) -> False
    assert is_us_trading_day(date(2026, 5, 25)) is False
```

```python
# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
@pytest.mark.asyncio
async def test_daily_routine_skips_when_holiday(mocker):
    """
    [목적] 수집 기준일(target_date)이 미국 주식시장 휴장일일 때 DailyRoutine.run()이 데이터를 수집하지 않고 스킵 리포트를 정상 반환하는지 검증
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    from datetime import date
    
    # 2026-05-25 (메모리얼 데이, 미국 공휴일)
    target_dt = date(2026, 5, 25)
    
    # DB 커서 및 리포지토리 모킹
    mocker.patch("p3_usdms.tasks.daily_routine.MasterRepo")
    mocker.patch("p3_usdms.tasks.daily_routine.BlacklistRepo")
    mocker.patch("p3_usdms.tasks.daily_routine.BlacklistManager")
    
    routine = DailyRoutine()
    
    # 캘린더 동기화 모킹 (영향 차단)
    routine.sync_trading_calendar = mocker.MagicMock()
    # 외부 수집기들 모킹
    routine.master.sync_daily = mocker.AsyncMock()
    routine.market_loader.collect_daily_updates = mocker.MagicMock()
    
    # 실행
    report = await routine.run(target_date=target_dt)
    
    # 검증: sync_daily 및 collect_daily_updates 등이 호출되지 않았고 스킵되었음을 판단
    assert report["status"] == "SKIPPED"
    assert "US Holiday" in report["msg"]
    routine.master.sync_daily.assert_not_called()
    routine.market_loader.collect_daily_updates.assert_not_called()
```

```python
# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
def test_daily_routine_syncs_trading_calendar(mocker):
    """
    [목적] sync_trading_calendar가 데이터베이스의 trading_calendar 테이블에 미국 영업일 데이터를 정상적으로 자동 동기화하는지 검증
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    from datetime import date
    
    routine = DailyRoutine()
    
    # DB 커서 모킹
    mock_cursor = mocker.MagicMock()
    routine.db.get_cursor = mocker.MagicMock()
    routine.db.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    # MAX(dt)가 2026-05-22(금)이고 target_date가 2026-05-26(화)인 시나리오
    # 2026-05-23(토), 2026-05-24(일), 2026-05-25(월: 메모리얼 데이)는 휴일/휴장('N')
    # 2026-05-26(화)는 개장('Y')
    
    # dict 타입과 tuple 타입 둘 다 지원 가능하도록 유연한 리턴 처리
    class Row(dict):
        def __getitem__(self, item):
            if isinstance(item, int):
                return date(2026, 5, 22)
            return super().__getitem__(item)
    mock_cursor.fetchone.return_value = Row({"d": date(2026, 5, 22), "max": date(2026, 5, 22)})
    
    routine.sync_trading_calendar(limit_date=date(2026, 5, 26))
    
    # execute가 총 4번(5/23, 5/24, 5/25, 5/26) 실행되었는지 확인
    calls = mock_cursor.execute.call_args_list
    insert_calls = [c for c in calls if "INSERT" in c[0][0].upper()]
    assert len(insert_calls) == 4
    
    # 2026-05-25(메모리얼 데이) -> 'N'
    memorial_day_call = [c for c in insert_calls if c[0][1][0] == date(2026, 5, 25)][0]
    assert memorial_day_call[0][1][1] == 'N'
    
    # 2026-05-26(정상 화요일) -> 'Y'
    tuesday_call = [c for c in insert_calls if c[0][1][0] == date(2026, 5, 26)][0]
    assert tuesday_call[0][1][1] == 'Y'
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_config_loads_targeting_thresholds` | Tier 1 | 정상 | 설정 추가 후 Pydantic Settings 로드 확인 (수집 기준 & 스케줄) |
| 2 | `test_is_us_trading_day_weekend_and_holidays` | Tier 1 | 경계 | `is_us_trading_day` 주말/공휴일 판별 단위 로직 검증 |
| 3 | `test_master_sync_update_target_status_uses_settings_values` | Tier 2 | 격리 통합 | `MasterSync`에서 설정 기준값 4종 쿼리 바인딩 확인 |
| 4 | `test_master_repo_apply_targeting_rules_fallback_to_settings` | Tier 2 | 격리 통합 | `MasterRepo`에서 파라미터 생략 시 Settings 기본값 Fallback 확인 |
| 5 | `test_scheduler_daily_job_uses_configured_time` | Tier 2 | 격리 통합 | `main.py` lifespan 스케줄러 등록 시 설정 실행 시간(HH:MM) 파싱 반영 확인 |
| 6 | `test_daily_routine_skips_when_holiday` | Tier 2 | 격리 통합 | 미국 주식시장 휴장일 기준 `DailyRoutine.run()` 스킵 검증 |
| 7 | `test_daily_routine_syncs_trading_calendar` | Tier 2 | 격리 통합 | `sync_trading_calendar`를 통한 `trading_calendar` 미국 영업일 동기화 검증 |

**총 7개 신규 테스트 — 전체 통과 및 기존 테스트 56개 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, fastapi, pydantic-settings, pytest
- **위키 참조 링크**:
  - `pjt_wiki/p3_usdms_wiki/environment.md` — 패키지 의존성 정보
  - `pjt_wiki/p3_usdms_wiki/interfaces/master_repo.md` — 마스터 리포지토리 인터페이스 정의
  - `pjt_wiki/p3_usdms_wiki/interfaces/master_sync.md` — 동기화 인터페이스 정의
- **주의사항**:
  - `db_manager.py` 삭제 시 `tests/test_base_infra.py` L9의 `from p3_usdms.collectors.db_manager import DatabaseManager` 임포트와 TC-04 테스트 함수를 함께 제거해야 합니다.
  - `.env`에 정의할 변수명은 PRD 가이드를 따라 `TARGET_MIN_MARKET_CAP`, `TARGET_MIN_PRICE`, `TARGET_RETAIN_MARKET_CAP`, `TARGET_RETAIN_PRICE` 및 `SCHEDULE_DAILY_ROUTINE`으로 사용합니다.
  - `MasterSync._update_target_status()`는 현재 f-string으로 값을 SQL에 직접 삽입하므로, 리팩토링 시 `%s` 파라미터 바인딩 방식으로 전환해야 SQL 인젝션을 방지하고 TC-3 테스트가 정상 동작합니다.
  - `apply_targeting_rules()` 시그니처 변경 시 기존 호출부(`weekly_backfill` 내 `self.master_repo.apply_targeting_rules()`)가 인자 없이 호출하므로 Fallback 기본값 처리는 호환성상 필수입니다.
  - `get_settings()` 싱글톤 캐시로 인해, 여러 테스트에서 다른 설정값을 주입해야 하는 경우 `mocker.patch("p3_usdms.config._settings", None)` 또는 `Settings(...)` 직접 생성 방식을 사용해야 합니다.

### 5.1 미국 시장 시차 및 요일 정책 가이드
1. **미국-한국 시차 및 스케줄 요일 제한**:
   - 미국의 월~금요일 정규 장은 한국 시간(KST) 기준으로 **화~토요일 새벽**에 마감됩니다. (서머타임: 05:00 KST 마감 / 표준시: 06:00 KST 마감)
   - 따라서 일일 루틴 스케줄러(`daily_collection_job`) 등록 시 실행 요일을 반드시 **`tue-sat`**으로 한정하여 일~월요일의 무의미한 API 호출과 차단(Rate limit) 발생 가능성을 제거합니다.
   - 스케줄러의 타임존은 일관되게 `Asia/Seoul`로 명시적으로 셋업합니다.
2. **KIS 시세 갱신 지연 및 07:30 기동 타당성**:
   - 한국투자증권(KIS) 미국 주식 API 및 SEC EDGAR 시스템의 일봉 데이터 업데이트 배치 처리가 장 마감 직후 즉시 완결되지 않고 지연될 수 있습니다.
   - 따라서 장 마감 이후 여유를 둔 **07:30 KST**를 디폴트 값으로 하여 수집 기동 안정성을 극대화합니다.
3. **07:00 KST Freshness 판정 분기점과의 과도기 갭 인지**:
   - Freshness 동적 판정 기준시(07:00 KST)와 실제 수집 시작(07:30 KST) 사이에 30분의 시간차가 존재합니다.
   - 이로 인해 화~토요일 **07:00 KST ~ 수집 완료 시점(대략 07:45 KST)** 사이에 Freshness API를 조회하면 수집률이 기준선 미만이 되어 일시적으로 `YELLOW` 또는 `RED` 경고를 리턴할 수 있습니다.
   - 이는 당일 수집이 시작되기 직전/진행 중인 **자연스러운 과도기 상태**이므로, 시스템 에러나 데이터 유실 경보(alerting)로 오인하지 않도록 모니터링 설계에 반영해 두어야 합니다.

---

## § 6. 완료 기준

- [x] § 4의 신규 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [x] 기존 테스트 전체 통과 (레거시 `DatabaseManager` 제거 후에도 회귀 에러 없음)
- [x] `collectors/db_manager.py`, `ops/rebuild_all_valuations.py`, `ops/verify_data_integrity.py` 파일 삭제 및 `git rm` 처리 완료
- [x] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 Task-008 상태를 `완료`로 업데이트
- [x] `docs/p3_usdms/tasks/task-008_walkthrough.md` 작성
