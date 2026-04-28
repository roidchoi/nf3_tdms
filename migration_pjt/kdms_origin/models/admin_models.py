#
# models/admin_models.py
#
from pydantic import BaseModel, Field
from typing import Dict, Any

class TaskRunRequest(BaseModel):
    """
    PRD 섹션 3.1.1 및 4.1.3을 기반으로 한 태스크 실행 요청 모델
    """
    test_mode: bool = False
    params: Dict[str, Any] = {}

class ScheduleCreateRequest(BaseModel):
    """
    PRD 섹션 3.1.2 및 4.1.3을 기반으로 한 스케줄 생성 요청 모델
    """
    task_id: str = Field(..., description="실행할 태스크 ID (예: daily_update)")
    trigger: str = Field(..., description="트리거 타입 (예: cron, date, interval)")
    config: Dict[str, Any] = Field(
        ..., 
        description="APScheduler 트리거 설정 (예: {'day_of_week': 'mon-fri', 'hour': 16})"
    )

class ScheduleUpdateRequest(BaseModel):
    """
    PRD 섹션 3.1.2 PUT 요청을 기반으로 한 스케줄 업데이트 모델
    (config만 업데이트하는 것으로 단순화)
    """
    config: Dict[str, Any] = Field(
        ...,
        description="APScheduler 트리거 설정 (예: {'hour': 17, 'minute': 0})"
    )