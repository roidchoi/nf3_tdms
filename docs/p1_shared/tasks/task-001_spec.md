# Task-001: 패키지 기반 + 공통 유틸 + 로거

> **Sub Project**: p1_shared
> **PRD 근거**: FR-01, FR-02, FR-03, FR-04, FR-05
> **작성일**: 2026-04-30
> **의존 Task**: 없음 (최우선 착수)

---

## § 1. 목표

`p1_shared` 패키지의 뼈대(pyproject.toml)와 5개 공통 모듈(예외·재시도·날짜·로거)을 구현하여, p2·p3가 `pip install -e ../p1_shared` 한 줄로 공통 기반을 즉시 사용할 수 있게 한다.

**구현 범위:**
- IN:
  - `pyproject.toml` + `__init__.py` 패키지 정의 및 editable install 검증
  - `db/exceptions.py` — DB 관련 공통 예외 클래스
  - `utils/retry.py` — sync/async 지수 백오프 재시도 데코레이터
  - `utils/date_utils.py` — KR/US 영업일 유틸리티 6개 함수
  - `ops/logger.py` — 공통 로거 팩토리 + `WebSocketQueueHandler`
  - 각 모듈 단위 테스트
- OUT:
  - DB 커넥션 풀 (`db/connection.py`) → T-003
  - 환경 감지 (`utils/env_detector.py`) → T-002
  - API 클라이언트 계열 → T-004, T-005

---

## § 2. 구현 대상

### 신규 생성 파일

```
/home/roid2/pjt/nf3/01_nf3_tdms/p1_shared/
├── pyproject.toml
├── __init__.py
├── db/
│   ├── __init__.py
│   └── exceptions.py
├── utils/
│   ├── __init__.py
│   ├── retry.py
│   └── date_utils.py
├── ops/
│   ├── __init__.py
│   └── logger.py
└── tests/
    ├── __init__.py
    ├── test_exceptions.py
    ├── test_retry.py
    ├── test_date_utils.py
    └── test_logger.py
```

### 핵심 인터페이스

```python
# db/exceptions.py
class DbConnectionError(Exception):
    """DB 커넥션 획득 실패."""
    ...

class DbOperationError(Exception):
    """쿼리 실행 또는 트랜잭션 실패."""
    ...

# utils/retry.py
def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    동기 함수용 지수 백오프 재시도 데코레이터.

    Args:
        max_attempts: 최대 시도 횟수 (1 이상)
        delay_seconds: 첫 재시도 대기 시간(초)
        backoff: 대기 시간 배수 (delay → delay*backoff → ...)
        exceptions: 재시도를 트리거할 예외 타입 튜플
    Raises:
        마지막 시도에서도 exceptions에 해당하는 예외 발생 시 그대로 전파
    """
    ...

def async_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """비동기 함수용 재시도 데코레이터. 시그니처는 retry와 동일."""
    ...

# utils/date_utils.py
from datetime import date

def is_kr_trading_day(d: date) -> bool:
    """한국 주식시장 영업일 여부 (주말·공휴일 제외)."""
    ...

def is_us_trading_day(d: date) -> bool:
    """미국 주식시장 영업일 여부 (주말·공휴일 제외)."""
    ...

def get_kr_trading_days(start: date, end: date) -> list[date]:
    """[start, end] 기간 내 한국 영업일 목록 (오름차순)."""
    ...

def get_us_trading_days(start: date, end: date) -> list[date]:
    """[start, end] 기간 내 미국 영업일 목록 (오름차순)."""
    ...

def last_kr_trading_day(reference: date | None = None) -> date:
    """기준일(기본: 오늘) 이전 마지막 한국 영업일."""
    ...

def last_us_trading_day(reference: date | None = None) -> date:
    """기준일(기본: 오늘) 이전 마지막 미국 영업일."""
    ...

# ops/logger.py
import asyncio, logging

def get_logger(name: str, ws_queue: asyncio.Queue | None = None) -> logging.Logger:
    """
    공통 로거 팩토리.
    - Rich 콘솔 핸들러 (컬러 출력, level=INFO)
    - 파일 핸들러 (logs/{name}_{date}.log, 일별 rotate)
    - ws_queue 제공 시 WebSocketQueueHandler 추가

    Args:
        name: 로거 이름 (모듈명 권장)
        ws_queue: asyncio.Queue — p4_manager 실시간 스트리밍용. None이면 미추가.
    Returns:
        설정이 완료된 logging.Logger 인스턴스
    """
    ...

class WebSocketQueueHandler(logging.Handler):
    """asyncio.Queue에 로그 레코드를 비동기로 삽입하는 핸들러."""

    def __init__(self, queue: asyncio.Queue): ...

    def emit(self, record: logging.LogRecord) -> None:
        """
        queue.put_nowait()로 record를 삽입.
        QueueFull 발생 시 무시 (로깅이 앱을 멈춰선 안 됨).
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# tests/test_exceptions.py
def test_db_connection_error_is_catchable_as_exception():
    """
    [목적] DbConnectionError가 Exception으로 catch 가능함을 검증
    [유도] DbConnectionError(Exception) 상속 강제
    """
    from p1_shared.db.exceptions import DbConnectionError

    with pytest.raises(Exception):
        raise DbConnectionError("연결 실패")


def test_db_operation_error_carries_message():
    """
    [목적] DbOperationError에 메시지가 보존됨을 검증
    [유도] 생성자에서 message를 args에 저장하는 기본 Exception 동작 확인
    """
    from p1_shared.db.exceptions import DbOperationError

    err = DbOperationError("INSERT 실패")
    assert "INSERT 실패" in str(err)


# tests/test_retry.py
def test_retry_succeeds_on_first_attempt_without_sleep(mocker):
    """
    [목적] 첫 시도에 성공하면 sleep 없이 결과 반환
    [유도] 성공 시 재시도 루프가 실행되지 않아야 함
    """
    from p1_shared.utils.retry import retry

    mock_sleep = mocker.patch("time.sleep")

    @retry(max_attempts=3, delay_seconds=1.0)
    def always_success():
        return "ok"

    result = always_success()
    assert result == "ok"
    mock_sleep.assert_not_called()


def test_retry_calls_function_up_to_max_attempts_on_failure(mocker):
    """
    [목적] 계속 실패 시 max_attempts 횟수만큼 호출됨을 검증
    [유도] 재시도 루프를 max_attempts 횟수로 제한하는 로직 강제
    """
    from p1_shared.utils.retry import retry

    mocker.patch("time.sleep")
    call_count = 0

    @retry(max_attempts=3, exceptions=(ValueError,))
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise ValueError("실패")

    with pytest.raises(ValueError):
        always_fail()

    assert call_count == 3


def test_retry_applies_exponential_backoff(mocker):
    """
    [목적] 재시도 간격이 backoff 배수로 증가함을 검증
    [유도] sleep 호출 시 delay * backoff^n 패턴 강제
    """
    from p1_shared.utils.retry import retry

    mock_sleep = mocker.patch("time.sleep")

    @retry(max_attempts=3, delay_seconds=1.0, backoff=2.0, exceptions=(RuntimeError,))
    def always_fail():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        always_fail()

    # 1차 재시도: sleep(1.0), 2차 재시도: sleep(2.0)
    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [1.0, 2.0]


import asyncio
import pytest

@pytest.mark.asyncio
async def test_async_retry_succeeds_on_second_attempt(mocker):
    """
    [목적] 비동기 함수에서 1회 실패 후 2회째 성공하면 결과 반환
    [유도] async_retry가 코루틴을 올바르게 await하는 구현 강제
    """
    from p1_shared.utils.retry import async_retry

    mocker.patch("asyncio.sleep", return_value=None)
    attempt = 0

    @async_retry(max_attempts=3, delay_seconds=0.0, exceptions=(IOError,))
    async def flaky():
        nonlocal attempt
        attempt += 1
        if attempt < 2:
            raise IOError("일시 오류")
        return "recovered"

    result = await flaky()
    assert result == "recovered"
    assert attempt == 2


# tests/test_date_utils.py
from datetime import date

def test_is_kr_trading_day_returns_true_for_normal_weekday():
    """
    [목적] 평범한 평일(공휴일 아님)이 True를 반환함을 검증
    [유도] 주말·공휴일 필터링 로직이 정상 평일은 통과시켜야 함
    """
    from p1_shared.utils.date_utils import is_kr_trading_day

    monday = date(2024, 1, 2)  # 2024-01-02: 월요일, 공휴일 아님
    assert is_kr_trading_day(monday) is True


def test_is_kr_trading_day_returns_false_for_weekend():
    """
    [목적] 주말이 False를 반환함을 검증
    [유도] weekday() >= 5 조건 처리 강제
    """
    from p1_shared.utils.date_utils import is_kr_trading_day

    saturday = date(2024, 1, 6)
    sunday = date(2024, 1, 7)
    assert is_kr_trading_day(saturday) is False
    assert is_kr_trading_day(sunday) is False


def test_get_kr_trading_days_excludes_weekends_and_returns_sorted():
    """
    [목적] 반환 목록에 주말이 없고 오름차순임을 검증
    [유도] 필터 + 정렬 로직 강제
    """
    from p1_shared.utils.date_utils import get_kr_trading_days

    days = get_kr_trading_days(date(2024, 1, 1), date(2024, 1, 7))
    for d in days:
        assert d.weekday() < 5  # 주말 없음
    assert days == sorted(days)  # 오름차순


def test_last_kr_trading_day_returns_friday_when_reference_is_monday():
    """
    [목적] 월요일 기준 시 직전 금요일 반환을 검증
    [유도] 역방향 탐색 로직 강제 (reference 포함 X, 이전일 탐색)
    """
    from p1_shared.utils.date_utils import last_kr_trading_day

    monday = date(2024, 1, 8)   # 월요일
    expected_friday = date(2024, 1, 5)  # 직전 금요일 (공휴일 아님)
    assert last_kr_trading_day(monday) == expected_friday


# tests/test_logger.py
def test_get_logger_returns_logger_with_name():
    """
    [목적] get_logger()가 지정한 name의 Logger 인스턴스를 반환함을 검증
    [유도] logging.getLogger(name) 기반 팩토리 구현 강제
    """
    from p1_shared.ops.logger import get_logger

    logger = get_logger("test_module")
    assert logger.name == "test_module"
    assert isinstance(logger, logging.Logger)


def test_get_logger_without_queue_has_no_ws_handler():
    """
    [목적] ws_queue=None 시 WebSocketQueueHandler가 추가되지 않음을 검증
    [유도] ws_queue 조건 분기 강제
    """
    from p1_shared.ops.logger import get_logger, WebSocketQueueHandler

    logger = get_logger("no_ws_test")
    ws_handlers = [h for h in logger.handlers if isinstance(h, WebSocketQueueHandler)]
    assert len(ws_handlers) == 0


def test_websocket_queue_handler_emits_record_to_queue():
    """
    [목적] emit() 호출 시 record가 asyncio.Queue에 삽입됨을 검증
    [유도] queue.put_nowait(record) 구현 강제
    """
    import asyncio
    import logging
    from p1_shared.ops.logger import WebSocketQueueHandler

    queue = asyncio.Queue()
    handler = WebSocketQueueHandler(queue)

    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg="hello", args=(), exc_info=None
    )
    handler.emit(record)

    assert not queue.empty()
    queued = queue.get_nowait()
    assert queued.getMessage() == "hello"


def test_websocket_queue_handler_does_not_raise_when_queue_full():
    """
    [목적] Queue가 가득 찼을 때 emit()이 예외를 발생시키지 않음을 검증
    [유도] QueueFull 예외를 catch하고 silently 무시하는 로직 강제
    """
    import asyncio
    import logging
    from p1_shared.ops.logger import WebSocketQueueHandler

    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait("already_full")  # 용량 1 채움

    handler = WebSocketQueueHandler(queue)
    record = logging.LogRecord(
        name="test", level=logging.WARNING,
        pathname="", lineno=0, msg="overflow", args=(), exc_info=None
    )
    # 예외 없이 통과해야 함
    handler.emit(record)
```

### 4.2 경계값 케이스

```python
def test_retry_with_max_attempts_one_does_not_retry(mocker):
    """
    [목적] max_attempts=1 이면 재시도 없이 즉시 예외 전파
    [유도] 루프 조건이 max_attempts를 정확히 처리함을 검증
    """
    from p1_shared.utils.retry import retry

    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    @retry(max_attempts=1, exceptions=(RuntimeError,))
    def fail_once():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("즉시 실패")

    with pytest.raises(RuntimeError):
        fail_once()

    assert call_count == 1
    mock_sleep.assert_not_called()


def test_get_kr_trading_days_returns_empty_for_weekend_only_range():
    """
    [목적] 주말만 포함된 범위 → 빈 리스트 반환
    [유도] 필터 결과가 0개일 때 빈 리스트 반환 처리
    """
    from p1_shared.utils.date_utils import get_kr_trading_days

    result = get_kr_trading_days(date(2024, 1, 6), date(2024, 1, 7))  # 토·일
    assert result == []
```

### 4.3 예외/오류 처리 케이스

```python
def test_retry_does_not_catch_unlisted_exception(mocker):
    """
    [목적] exceptions 튜플에 없는 예외는 즉시 전파 (재시도 없음)
    [유도] except 절을 지정된 exceptions로만 한정하는 구현 강제
    """
    from p1_shared.utils.retry import retry

    mock_sleep = mocker.patch("time.sleep")

    @retry(max_attempts=3, exceptions=(ValueError,))
    def raise_type_error():
        raise TypeError("이건 재시도 안 함")

    with pytest.raises(TypeError):
        raise_type_error()

    mock_sleep.assert_not_called()


def test_get_kr_trading_days_raises_when_start_after_end():
    """
    [목적] start > end 인 잘못된 범위 입력 시 ValueError 발생
    [유도] 입력 검증 로직 추가 강제
    """
    from p1_shared.utils.date_utils import get_kr_trading_days
    import pytest

    with pytest.raises(ValueError):
        get_kr_trading_days(date(2024, 1, 7), date(2024, 1, 1))
```

### 4.4 통합/연계 케이스

```python
def test_package_is_importable_after_editable_install():
    """
    [목적] p1_shared가 패키지로 import 가능함을 검증
    [유도] pyproject.toml + __init__.py 구조가 올바르게 구성되도록 강제
    """
    import p1_shared
    assert hasattr(p1_shared, "__version__") or True  # 임포트 자체가 성공하면 통과


def test_get_logger_with_queue_adds_ws_handler():
    """
    [목적] ws_queue 제공 시 WebSocketQueueHandler가 logger에 등록됨을 검증
    [유도] 조건부 핸들러 추가 + emit 연결 전체 흐름 구현 강제
    """
    import asyncio
    from p1_shared.ops.logger import get_logger, WebSocketQueueHandler

    queue = asyncio.Queue()
    logger = get_logger("ws_test_logger", ws_queue=queue)

    ws_handlers = [h for h in logger.handlers if isinstance(h, WebSocketQueueHandler)]
    assert len(ws_handlers) == 1
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_db_connection_error_is_catchable_as_exception` | 정상 | DbConnectionError → Exception 상속 |
| 2 | `test_db_operation_error_carries_message` | 정상 | 에러 메시지 보존 |
| 3 | `test_retry_succeeds_on_first_attempt_without_sleep` | 정상 | 1회 성공 시 sleep 미호출 |
| 4 | `test_retry_calls_function_up_to_max_attempts_on_failure` | 정상 | max_attempts 횟수 정확히 호출 |
| 5 | `test_retry_applies_exponential_backoff` | 정상 | sleep 간격 지수 증가 |
| 6 | `test_async_retry_succeeds_on_second_attempt` | 정상 | async 코루틴 재시도 성공 |
| 7 | `test_is_kr_trading_day_returns_true_for_normal_weekday` | 정상 | 평일 True 반환 |
| 8 | `test_is_kr_trading_day_returns_false_for_weekend` | 정상 | 주말 False 반환 |
| 9 | `test_get_kr_trading_days_excludes_weekends_and_returns_sorted` | 정상 | 주말 제외 + 정렬 |
| 10 | `test_last_kr_trading_day_returns_friday_when_reference_is_monday` | 정상 | 월요일 기준 → 직전 금요일 |
| 11 | `test_get_logger_returns_logger_with_name` | 정상 | Logger 인스턴스 + name 일치 |
| 12 | `test_get_logger_without_queue_has_no_ws_handler` | 정상 | ws_queue=None → WS핸들러 없음 |
| 13 | `test_websocket_queue_handler_emits_record_to_queue` | 정상 | emit → queue에 record 삽입 |
| 14 | `test_websocket_queue_handler_does_not_raise_when_queue_full` | 예외 | Queue Full 시 예외 미발생 |
| 15 | `test_retry_with_max_attempts_one_does_not_retry` | 경계값 | max_attempts=1 → 재시도 없음 |
| 16 | `test_get_kr_trading_days_returns_empty_for_weekend_only_range` | 경계값 | 주말 범위 → 빈 리스트 |
| 17 | `test_retry_does_not_catch_unlisted_exception` | 예외 | 미등록 예외 → 즉시 전파 |
| 18 | `test_get_kr_trading_days_raises_when_start_after_end` | 예외 | start>end → ValueError |
| 19 | `test_package_is_importable_after_editable_install` | 통합 | 패키지 import 성공 |
| 20 | `test_get_logger_with_queue_adds_ws_handler` | 통합 | ws_queue 제공 → WS핸들러 등록 |

**총 20개 테스트 — 전체 통과 시 Task-001 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `holidays` 라이브러리 (KR/US 공휴일), `rich` (콘솔 출력), `pytest-asyncio` (비동기 테스트), `pytest-mock` (mocker fixture)
- **pyproject.toml 의존성**:
  ```toml
  [project]
  name = "tdms-shared"
  version = "1.0.0"
  dependencies = [
      "psycopg2-binary>=2.9",
      "requests>=2.32",
      "python-dotenv>=1.1",
      "holidays>=0.46",
      "rich>=13.0",
  ]
  [project.optional-dependencies]
  dev = ["pytest", "pytest-asyncio", "pytest-mock"]
  ```
- **holidays 라이브러리 사용법**: `holidays.KR()`, `holidays.US()` 로 해당 연도 공휴일 집합 생성
- **로거 중복 핸들러 주의**: `get_logger()` 호출 시 동일 name으로 반복 호출하면 핸들러가 중복 등록될 수 있음 → `if not logger.handlers:` 조건 처리 또는 `logger.handlers.clear()` 후 재설정
- **WebSocketQueueHandler 스레드 안전성**: `queue.put_nowait()`는 스레드 안전하나, `asyncio.Queue`는 이벤트 루프에 귀속됨 — 로거가 별도 스레드에서 호출될 경우 `loop.call_soon_threadsafe()` 고려
- **관련 문서**: `docs/p1_shared/p1_shared_PRD.md` §3.6, §3.7, §3.8, §4.1

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 20개 전체 통과 (`cd p1_shared && pytest tests/ -v`)
- [ ] `pip install -e .` 후 `import p1_shared` 성공
- [ ] `docs/p1_shared/p1_shared_pjt_tasks.md`의 T-001 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-001_workthrough.md` 작성
