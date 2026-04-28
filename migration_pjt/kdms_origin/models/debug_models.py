#
# models/debug_models.py
#
"""
API 진단 도구용 Pydantic 모델 정의
"""

from pydantic import BaseModel
from typing import Dict, Any, Optional, List


class MethodInfo(BaseModel):
    """메소드 정보"""
    name: str
    params: List[str]
    defaults: Dict[str, Any] = {}
    description: str = ""


class MethodExecuteRequest(BaseModel):
    """메소드 실행 요청"""
    target: str  # "kis" or "kiwoom"
    method_name: str
    params: Dict[str, Any] = {}
    mock_mode: bool = False  # 모의투자 모드 사용 여부


class ExecutionMetadata(BaseModel):
    """실행 메타데이터"""
    execution_time: float
    result_type: str
    result_length: Optional[int] = None


class ErrorDetail(BaseModel):
    """에러 상세 정보"""
    type: str
    message: str
    traceback: Optional[str] = None
    error_code: Optional[str] = None
    hint: Optional[str] = None


class MethodExecuteResponse(BaseModel):
    """메소드 실행 응답"""
    success: bool
    result: Optional[Any] = None
    metadata: Optional[ExecutionMetadata] = None
    error: Optional[ErrorDetail] = None
    validation_result: Optional[Dict[str, Any]] = None  # 응답 구조 검증 결과
