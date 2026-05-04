import pytest
from p1_shared.db.exceptions import DbConnectionError, DbOperationError

def test_db_connection_error_is_catchable_as_exception():
    with pytest.raises(Exception):
        raise DbConnectionError("연결 실패")

def test_db_operation_error_carries_message():
    err = DbOperationError("INSERT 실패")
    assert "INSERT 실패" in str(err)
