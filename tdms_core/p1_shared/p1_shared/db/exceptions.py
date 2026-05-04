class DbConnectionError(Exception):
    """DB 접속 실패 (네트워크 등)."""
    pass

class DbOperationError(Exception):
    """쿼리 실행 실패 (중복, 무결성 위반 등)."""
    pass
