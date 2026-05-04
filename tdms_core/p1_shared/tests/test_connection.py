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
