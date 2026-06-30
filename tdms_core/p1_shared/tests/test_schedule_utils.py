# tdms_core/p1_shared/tests/test_schedule_utils.py
import pytest
import os
from p1_shared.utils.schedule_utils import parse_schedule_string, update_env_value

def test_parse_schedule_string_with_only_time():
    """
    [목적] 요일 정보가 없는 HH:MM 포맷 파싱 검증
    [유도] parse_schedule_string("17:10", "mon-fri") -> (17, 10, "mon-fri")
    """
    hour, minute, day_of_week = parse_schedule_string("17:10", default_days="mon-fri")
    assert hour == 17
    assert minute == 10
    assert day_of_week == "mon-fri"

def test_parse_schedule_string_with_day_prefix():
    """
    [목적] 요일 접두사가 존재하는 day_of_week:HH:MM 포맷 파싱 검증
    [유도] parse_schedule_string("sat:14:00") -> (14, 0, "sat")
    """
    hour, minute, day_of_week = parse_schedule_string("sat:14:00")
    assert hour == 14
    assert minute == 0
    assert day_of_week == "sat"

def test_parse_schedule_string_boundary_values():
    """
    [목적] 시간과 분의 최대 경계값(23:59) 파싱 검증
    """
    hour, minute, day_of_week = parse_schedule_string("23:59")
    assert hour == 23
    assert minute == 59

def test_parse_schedule_string_invalid_format_raises_value_error():
    """
    [목적] 올바르지 않은 스케줄 패턴 문자열 입력 시 ValueError 발생
    """
    with pytest.raises(ValueError):
        parse_schedule_string("invalid_format")
        
    with pytest.raises(ValueError):
        parse_schedule_string("25:00")  # 범위를 벗어난 시간
        
    with pytest.raises(ValueError):
        parse_schedule_string("12:60")  # 범위를 벗어난 분

def test_update_env_value_writes_correctly_and_refreshes_cache(tmp_path, mocker):
    """
    [목적] 지정된 환경 변수의 값이 .env 파일에 실시간 덮어쓰기되는지 검증
    """
    temp_env = tmp_path / ".env"
    temp_env.write_text("SCHEDULE_KDMS_DAILY_UPDATE=17:10\n", encoding="utf-8")
    
    import p1_shared.utils.schedule_utils as su
    mocker.patch.object(su, "ENV_FILE_PATH", str(temp_env))
    
    update_env_value("SCHEDULE_KDMS_DAILY_UPDATE", "18:00")
    
    updated_content = temp_env.read_text(encoding="utf-8")
    assert "SCHEDULE_KDMS_DAILY_UPDATE=18:00" in updated_content
    assert os.environ.get("SCHEDULE_KDMS_DAILY_UPDATE") == "18:00"

def test_reschedule_combines_existing_day_prefix_with_new_time(tmp_path, mocker):
    """
    [목적] 기존 요일 접두사가 존재할 경우, 요일을 보존한 채 시간만 업데이트하는 결합 로직 검증
    """
    temp_env = tmp_path / ".env"
    temp_env.write_text("SCHEDULE_USDMS_DAILY_ROUTINE=wed,sat:07:30\n", encoding="utf-8")
    
    import p1_shared.utils.schedule_utils as su
    mocker.patch.object(su, "ENV_FILE_PATH", str(temp_env))
    
    update_env_value("SCHEDULE_USDMS_DAILY_ROUTINE", "09:00")
    
    updated_content = temp_env.read_text(encoding="utf-8")
    assert "SCHEDULE_USDMS_DAILY_ROUTINE=wed,sat:09:00" in updated_content
    assert os.environ.get("SCHEDULE_USDMS_DAILY_ROUTINE") == "wed,sat:09:00"

