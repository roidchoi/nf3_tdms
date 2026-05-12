# Task-003: DB 커넥션 풀 (DbConnectionPool)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.4 DB 커넥션 (`db/connection.py`)
> **작성일**: 2026-05-04
> **의존 Task**: T-001

---

## § 1. 목표

`psycopg2.pool.ThreadedConnectionPool`을 래핑하여, `get_cursor()` context manager 패턴으로 커넥션 획득·반환·예외 시 롤백을 자동화하는 `DbConnectionPool` 클래스를 구현한다. p2_kdms·p3_usdms 양쪽 Repo 레이어가 이 단일 클래스를 통해 DB에 접근하는 통일된 표준 패턴을 확립한다.

**구현 범위:**
- **IN**:
  - `p1_shared/db/connection.py` — `DbConnectionPool` 클래스
  - `get_cursor()` context manager (정상 커밋, 예외 rollback, 커넥션 putconn 보장)
  - `autocommit` 모드 지원
  - `close_all()` 풀 종료 메서드
  - `tests/test_connection.py` — 단위 테스트 (psycopg2는 Mock 처리)
  - `tests/test_connection_integration.py` — 통합 테스트 (실 DB 접속 검증)
- **OUT**:
  - 실제 PostgreSQL DB 연결 (단위 테스트에서는 Mock 처리, 통합 테스트에서만 실 DB 사용)
  - `EnvDetector` 연동으로 DSN 자동 구성 — T-002와 조합은 상위 레이어 책임
  - 커넥션 풀 설정값(minconn, maxconn) 최적화 — 운영 설정 문제

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/db/connection.py` — `DbConnectionPool` 클래스 구현
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_connection.py` — 단위 테스트 (Mock 기반)
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_connection_integration.py` — 통합 테스트 (실 DB 기반, `pytest -m integration`으로 분리 실행)

### 핵심 인터페이스

```python
# p1_shared/db/connection.py
from contextlib import contextmanager
from typing import Generator
import psycopg2
import psycopg2.pool
import psycopg2.extensions

class DbConnectionPool:
    """
    psycopg2.pool.ThreadedConnectionPool 래퍼.

    get_cursor()를 context manager로 사용하면 커넥션 획득, 커서 제공,
    커밋(또는 rollback), 커넥션 반환이 자동으로 처리된다.

    Args:
        dsn: PostgreSQL 접속 문자열
             예: "postgresql://user:pass@192.168.1.10:5432/kdms_db"
        min_conn: 풀 최소 커넥션 수 (기본값 5)
        max_conn: 풀 최대 커넥션 수 (기본값 20)
    """

    def __init__(self, dsn: str, min_conn: int = 5, max_conn: int = 20) -> None:
        """
        Raises:
            psycopg2.OperationalError: DSN이 유효하지 않거나 DB에 연결 불가한 경우
        """
        ...

    @contextmanager
    def get_cursor(self, autocommit: bool = False) -> Generator:
        """
        커넥션 풀에서 커넥션을 획득하고 커서를 yield한다.

        - 정상 종료 시: commit() 후 커넥션 반환
        - 예외 발생 시: rollback() 후 커넥션 반환, 예외 재발생
        - autocommit=True 시: 커밋/롤백 없이 커서만 제공

        Usage:
            with pool.get_cursor() as cur:
                cur.execute("SELECT ...")

        Yields:
            psycopg2 cursor 객체

        Raises:
            psycopg2.pool.PoolError: 풀에서 커넥션을 얻지 못한 경우
            Exception: 쿼리 실행 중 발생한 예외 (rollback 후 재발생)
        """
        ...

    def close_all(self) -> None:
        """풀의 모든 커넥션을 닫는다."""
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **DB 격리 필수**: 모든 테스트는 `mocker.patch`로 `psycopg2.pool.ThreadedConnectionPool`을
> Mock 처리하여 실제 DB 접속 없이 동작해야 합니다.

### 4.1 정상 동작 케이스

```python
# tests/test_connection.py
import pytest
from unittest.mock import MagicMock, patch

def test_pool_initializes_with_valid_dsn(mocker):
    """
    [목적] 유효한 DSN으로 DbConnectionPool이 정상 초기화됨을 검증
    [유도] __init__에서 ThreadedConnectionPool을 생성하는 구현 강제
    """
    mock_pool_cls = mocker.patch("psycopg2.pool.ThreadedConnectionPool")

    from p1_shared.db.connection import DbConnectionPool
    pool = DbConnectionPool(dsn="postgresql://user:pass@192.168.1.10:5432/kdms_db")

    mock_pool_cls.assert_called_once_with(
        5, 20, "postgresql://user:pass@192.168.1.10:5432/kdms_db"
    )
    assert pool is not None


def test_get_cursor_yields_cursor_and_commits_on_success(mocker):
    """
    [목적] 정상 실행 시 get_cursor()가 커서를 yield하고 commit()을 호출함을 검증
    [유도] contextmanager 내부에서 conn.commit()이 호출되는 구현 강제
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool
    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pool.get_cursor() as cur:
        assert cur is mock_cursor

    mock_conn.commit.assert_called_once()
    mock_pool_instance.putconn.assert_called_once_with(mock_conn)


def test_get_cursor_rollbacks_on_exception(mocker):
    """
    [목적] 커서 사용 중 예외 발생 시 rollback()이 호출되고 예외가 재발생함을 검증
    [유도] except 블록에서 conn.rollback()을 호출하는 구현 강제
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.db.exceptions import DbOperationError

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pytest.raises(DbOperationError):
        with pool.get_cursor() as cur:
            raise DbOperationError("INSERT 실패")

    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


def test_get_cursor_always_returns_connection_to_pool_even_on_exception(mocker):
    """
    [목적] 예외가 발생해도 putconn()이 반드시 호출됨을 검증 (리소스 누수 방지)
    [유도] finally 블록에서 pool.putconn(conn) 호출 구현 강제
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pytest.raises(RuntimeError):
        with pool.get_cursor() as cur:
            raise RuntimeError("강제 오류")

    # 예외가 발생해도 putconn은 반드시 호출되어야 함
    mock_pool_instance.putconn.assert_called_once_with(mock_conn)


def test_get_cursor_with_autocommit_sets_autocommit_true(mocker):
    """
    [목적] autocommit=True 옵션 시 conn.autocommit이 True로 설정됨을 검증
    [유도] autocommit 분기 처리 구현 강제
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pool.get_cursor(autocommit=True) as cur:
        pass

    assert mock_conn.autocommit is True


def test_get_cursor_with_autocommit_does_not_commit(mocker):
    """
    [목적] autocommit=True 옵션 시 commit()이 호출되지 않음을 검증
    [유도] autocommit 모드에서는 commit()을 건너뛰는 로직 강제
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pool.get_cursor(autocommit=True) as cur:
        pass

    mock_conn.commit.assert_not_called()


def test_close_all_closes_pool(mocker):
    """
    [목적] close_all() 호출 시 내부 풀의 closeall()이 호출됨을 검증
    [유도] close_all()이 _pool.closeall()을 위임 호출하는 구현 강제
    """
    mock_pool_instance = MagicMock()
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")
    pool.close_all()

    mock_pool_instance.closeall.assert_called_once()
```

### 4.2 경계값 케이스

```python
def test_pool_initializes_with_custom_min_max_conn(mocker):
    """
    [목적] min_conn, max_conn 커스텀 값이 ThreadedConnectionPool에 그대로 전달됨을 검증
    [유도] __init__ 파라미터가 그대로 풀 생성자에 전달되는 구현 강제
    """
    mock_pool_cls = mocker.patch("psycopg2.pool.ThreadedConnectionPool")

    from p1_shared.db.connection import DbConnectionPool
    DbConnectionPool(dsn="postgresql://dummy", min_conn=2, max_conn=10)

    mock_pool_cls.assert_called_once_with(2, 10, "postgresql://dummy")


def test_get_cursor_can_be_used_multiple_times_sequentially(mocker):
    """
    [목적] get_cursor()를 순차적으로 여러 번 호출해도 각 호출마다 커넥션을 올바르게 반환함을 검증
    [유도] 단일 사용 후 커넥션 상태가 다음 호출에 영향을 주지 않는 격리된 구현 강제
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pool.get_cursor() as cur1:
        pass
    with pool.get_cursor() as cur2:
        pass

    # 두 번 호출되었으므로 getconn, putconn 각 2회 호출
    assert mock_pool_instance.getconn.call_count == 2
    assert mock_pool_instance.putconn.call_count == 2
```

### 4.3 예외/오류 처리 케이스

```python
def test_pool_raises_on_invalid_dsn(mocker):
    """
    [목적] 유효하지 않은 DSN으로 초기화 시 psycopg2.OperationalError가 발생함을 검증
    [유도] __init__에서 예외를 catch하지 않고 그대로 전파하는 구현 강제
    """
    import psycopg2
    mocker.patch(
        "psycopg2.pool.ThreadedConnectionPool",
        side_effect=psycopg2.OperationalError("연결 실패")
    )

    from p1_shared.db.connection import DbConnectionPool

    with pytest.raises(psycopg2.OperationalError):
        DbConnectionPool(dsn="postgresql://invalid-host:9999/nodb")


def test_get_cursor_raises_pool_error_when_pool_exhausted(mocker):
    """
    [목적] 풀이 고갈된 경우(PoolError) 예외가 그대로 전파됨을 검증
    [유도] getconn()에서 발생하는 PoolError를 catch하지 않는 구현 강제
    """
    import psycopg2.pool

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.side_effect = psycopg2.pool.PoolError("풀 고갈")
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pytest.raises(psycopg2.pool.PoolError):
        with pool.get_cursor() as cur:
            pass


def test_get_cursor_rollbacks_and_reraises_on_any_exception_type(mocker):
    """
    [목적] DbOperationError 외 임의의 예외에도 rollback 후 재발생함을 검증
    [유도] except 절이 Exception을 범용으로 처리하는 구현 강제
    """
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_instance = MagicMock()
    mock_pool_instance.getconn.return_value = mock_conn
    mocker.patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool_instance)

    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn="postgresql://dummy")

    with pytest.raises(KeyError):
        with pool.get_cursor() as cur:
            raise KeyError("예상치 못한 오류")

    mock_conn.rollback.assert_called_once()
```

### 4.4 통합 테스트 케이스 (실 DB 접속)

> **실행 조건**: 아래 테스트는 실제 DB가 접속 가능한 환경에서만 실행합니다.
> `pytest -m integration` 으로 단위 테스트와 분리하여 실행하세요.
>
> **개발PC 기준 사전 준비**: `kdms_timescaledb` 및 `usdms_db` Docker 컨테이너가 실행 중이어야 합니다.
> (`docker ps`로 `Up` 상태 확인)
>
> **서버PC DB**: 개발PC와 동일한 내부망(192.168.35.0/24) 내에서 서버PC가 켜져 있으면 별도 준비 없이 접속 가능합니다.

```python
# tests/test_connection_integration.py
import pytest
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

DEV_IP = os.getenv("DEV_IP", "192.168.35.205")
SERVER_IP = os.getenv("SERVER_IP", "192.168.35.97")

DEV_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{DEV_IP}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
DEV_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{DEV_IP}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)
SERVER_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{SERVER_IP}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
SERVER_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{SERVER_IP}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)


@pytest.mark.integration
def test_pool_connects_to_dev_kdms_db():
    """
    [목적] 개발PC KDMS DB(192.168.35.205:5432)에 실제 접속 가능함을 검증
    [유도] DbConnectionPool이 실 DSN으로 psycopg2 풀을 정상 생성하는 구현 강제
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_dev_usdms_db():
    """
    [목적] 개발PC USDMS DB(192.168.35.205:5435)에 실제 접속 가능함을 검증
    [유도] 포트가 다른 DB에도 동일한 DbConnectionPool 클래스가 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_USDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_server_kdms_db():
    """
    [목적] 서버PC KDMS DB(192.168.35.97:5432)에 내부망으로 실제 접속 가능함을 검증
    [유도] localhost 대신 내부망 IP 기반 접속이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=SERVER_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_connects_to_server_usdms_db():
    """
    [목적] 서버PC USDMS DB(192.168.35.97:5435)에 내부망으로 실제 접속 가능함을 검증
    [유도] 서버PC의 두 번째 DB 포트(5435)도 내부망 접속이 가능함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=SERVER_USDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
    pool.close_all()

    assert result[0] == 1


@pytest.mark.integration
def test_pool_execute_select_and_fetch_from_dev_kdms():
    """
    [목적] 개발PC KDMS DB에서 실제 테이블 조회가 가능함을 검증
    [유도] cursor.execute + fetchone/fetchall 흐름이 실 DB에서 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    with pool.get_cursor() as cur:
        cur.execute("SELECT current_database(), current_user")
        db_name, db_user = cur.fetchone()
    pool.close_all()

    assert db_name == os.getenv("DEV_KDMS_DB_NAME", "kdms_db")
```

### 테스트 케이스 요약

#### 단위 테스트 (Mock 기반)

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_pool_initializes_with_valid_dsn` | 정상 | 유효한 DSN으로 풀 초기화 |
| 2 | `test_get_cursor_yields_cursor_and_commits_on_success` | 정상 | 정상 종료 시 commit + putconn |
| 3 | `test_get_cursor_rollbacks_on_exception` | 정상 | 예외 발생 시 rollback 호출 |
| 4 | `test_get_cursor_always_returns_connection_to_pool_even_on_exception` | 정상 | 예외 시에도 putconn 보장 (finally) |
| 5 | `test_get_cursor_with_autocommit_sets_autocommit_true` | 정상 | autocommit=True 시 속성 설정 |
| 6 | `test_get_cursor_with_autocommit_does_not_commit` | 정상 | autocommit 모드에서 commit 생략 |
| 7 | `test_close_all_closes_pool` | 정상 | close_all() → pool.closeall() 위임 |
| 8 | `test_pool_initializes_with_custom_min_max_conn` | 경계값 | 커스텀 min/max 값 전달 |
| 9 | `test_get_cursor_can_be_used_multiple_times_sequentially` | 경계값 | 순차 다중 호출 시 커넥션 격리 |
| 10 | `test_pool_raises_on_invalid_dsn` | 예외 | 잘못된 DSN → OperationalError 전파 |
| 11 | `test_get_cursor_raises_pool_error_when_pool_exhausted` | 예외 | 풀 고갈 → PoolError 전파 |
| 12 | `test_get_cursor_rollbacks_and_reraises_on_any_exception_type` | 예외 | 임의 예외에도 rollback 후 재발생 |

#### 통합 테스트 (실 DB 기반, `pytest -m integration`)

| # | 테스트명 | 검증 내용 |
|---|---|---|
| 13 | `test_pool_connects_to_dev_kdms_db` | 개발PC KDMS 실 접속 |
| 14 | `test_pool_connects_to_dev_usdms_db` | 개발PC USDMS 실 접속 |
| 15 | `test_pool_connects_to_server_kdms_db` | 서버PC KDMS 내부망 실 접속 |
| 16 | `test_pool_connects_to_server_usdms_db` | 서버PC USDMS 내부망 실 접속 |
| 17 | `test_pool_execute_select_and_fetch_from_dev_kdms` | 실 DB 쿼리 실행 및 결과 검증 |

**단위 테스트 12개 + 통합 테스트 5개 = 총 17개 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `psycopg2-binary>=2.9` (이미 `requirements.txt`에 포함)
- **통합 테스트 실행 방법**:
  ```bash
  # 단위 테스트만 실행 (DB 불필요)
  conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/test_connection.py -v

  # 통합 테스트 실행 (Docker 컨테이너 및 서버PC 실행 중이어야 함)
  conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/test_connection_integration.py -v -m integration

  # 전체 실행
  conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/ -v
  ```
- **pytest.ini / pyproject.toml에 마커 등록 필요**:
  ```toml
  [tool.pytest.ini_options]
  markers = ["integration: 실 DB 접속이 필요한 통합 테스트"]
  ```
- **관련 문서**: `p1_shared_PRD.md` §3.4 — `DbConnectionPool` 인터페이스 원본 및 사용 패턴
- **주의사항**:
  - `get_cursor()`는 `contextlib.contextmanager` 데코레이터를 사용하여 구현할 것
  - `conn.cursor()`도 context manager이므로 `with conn.cursor() as cur: yield cur` 패턴 사용
  - `finally` 블록에서 `self._pool.putconn(conn)`을 호출해야 예외 여부와 무관하게 커넥션이 반환됨
  - `autocommit` 모드일 때는 `conn.autocommit = True` 설정 후 commit/rollback을 건너뜀
  - `close_all()`은 `self._pool.closeall()`을 단순 위임하면 충분
- **DSN 형식 참고**:
  ```
  postgresql://user:password@192.168.1.10:5432/kdms_db
  ```
  또는 keyword 형식:
  ```
  "host=192.168.1.10 port=5432 dbname=kdms_db user=kdms_user password=secret"
  ```

---

## § 6. 완료 기준

- [ ] § 4의 단위 테스트 케이스 12개 전체 통과
- [ ] § 4의 통합 테스트 케이스 5개 전체 통과 (개발PC + 서버PC DB 실접속 확인)
- [ ] 기존 T-001(20개) + T-002(15개) 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-003 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-003_walkthrough.md` 작성
