# tdms_core/p1_shared/p1_shared/utils/schedule_utils.py
import os
import re
from typing import Tuple, Optional

# 테스트 환경에서 오버라이드하기 위한 전역 파일 경로 변수
ENV_FILE_PATH: Optional[str] = None

def parse_schedule_string(schedule_str: str, default_days: Optional[str] = None) -> Tuple[int, int, Optional[str]]:
    """
    스케줄 설정 문자열([day_of_week:]HH:MM)을 파싱하여 hour, minute, day_of_week을 반환한다.
    
    Args:
        schedule_str: "17:10", "sat:14:00", "wed,sat:07:30" 등의 스케줄 포맷
        default_days: 요일 정보가 없을 경우 적용할 기본 요일 패턴 (예: "mon-fri")
        
    Returns:
        Tuple[hour, minute, day_of_week]
        
    Raises:
        ValueError: 파싱이 불가하거나 시간 형식이 잘못되었을 때 발생
    """
    if not schedule_str:
        raise ValueError("스케줄 문자열이 비어 있습니다.")
        
    cleaned = schedule_str.strip().lower()
    parts = cleaned.split(":")
    
    if len(parts) == 2:
        # HH:MM 형식
        hour_str, minute_str = parts
        day_of_week = default_days
    elif len(parts) == 3:
        # day_of_week:HH:MM 형식
        day_of_week, hour_str, minute_str = parts
    else:
        raise ValueError(f"올바르지 않은 스케줄 형식입니다: {schedule_str}")
        
    try:
        hour = int(hour_str)
        minute = int(minute_str)
    except ValueError as e:
        raise ValueError(f"시간 또는 분 값이 숫자가 아닙니다: {schedule_str}") from e
        
    if not (0 <= hour <= 23):
        raise ValueError(f"시간(hour) 범위를 벗어났습니다 (0-23): {hour}")
        
    if not (0 <= minute <= 59):
        raise ValueError(f"분(minute) 범위를 벗어났습니다 (0-59): {minute}")
        
    return hour, minute, day_of_week

def update_env_value(variable_name: str, value: str) -> None:
    """
    바인드 마운트된 .env 파일의 변수 값을 물리적으로 덮어쓰고, os.environ 캐시를 동기화한다.
    요일 정보 보존 결합 규칙에 따라, 기존 값에 요일 접두사가 있고 새 값에 없으면 접두사를 합쳐서 저장한다.
    
    Args:
        variable_name: .env 내의 타깃 변수명 (예: "SCHEDULE_KDMS_DAILY_UPDATE")
        value: 설정할 새로운 값 (예: "18:00" 또는 "sat:15:30")
    """
    global ENV_FILE_PATH
    env_file_path = ENV_FILE_PATH
    
    if not env_file_path:
        if os.path.exists("/app/.env"):
            env_file_path = "/app/.env"
        else:
            # p1_shared/p1_shared/utils/schedule_utils.py 기준 4단계 위가 root
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
            env_file_path = os.path.join(root_dir, ".env")
            
    if not os.path.exists(env_file_path):
        os.makedirs(os.path.dirname(env_file_path), exist_ok=True)
        with open(env_file_path, "w", encoding="utf-8") as f:
            f.write("")
            
    with open(env_file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    pattern = re.compile(rf"^({variable_name}\s*=\s*)(.*)$", re.MULTILINE)
    match = pattern.search(content)
    
    final_value = value.strip()
    if match:
        old_val = match.group(2).strip()
        # 요일 접두사 보존 결합 메커니즘
        old_parts = old_val.split(":")
        new_parts = final_value.split(":")
        if len(old_parts) == 3 and len(new_parts) == 2:
            # old_val이 "day:HH:MM" 형식이고 new_val이 "HH:MM" 형식인 경우
            day_prefix = old_parts[0].strip()
            final_value = f"{day_prefix}:{final_value}"
            
        new_content = pattern.sub(rf"\g<1>{final_value}", content)
    else:
        # 기존에 선언이 없었다면 끝에 추가
        if content and not content.endswith("\n"):
            new_content = content + f"\n{variable_name}={final_value}\n"
        else:
            new_content = content + f"{variable_name}={final_value}\n"
            
    with open(env_file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    # os.environ 환경 변수 캐시 갱신
    os.environ[variable_name] = final_value
