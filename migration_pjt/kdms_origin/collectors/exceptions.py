#
# collectors/exceptions.py
#
"""
Collectors 공통 예외 클래스 정의
"""

from typing import Optional


class KiwoomAPIError(Exception):
    """
    키움증권 API 응답 에러 (일반)

    API가 return_code != 0을 반환했을 때 발생.
    재시도가 가능한 일반적인 에러.
    """
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class TokenAuthError(Exception):
    """
    토큰 인증 치명적 에러 (복구 불가)

    토큰 강제 갱신 및 재시도를 수행했음에도 인증이 실패한 경우 발생.
    이 예외가 발생하면 작업을 즉시 중단(Fail-Fast)해야 함.

    발생 시나리오:
    - API 키가 만료됨
    - 토큰 발급 서버 장애
    - 토큰 갱신 후에도 계속 인증 실패
    - 실전/모의 계정 설정 오류
    """
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error
