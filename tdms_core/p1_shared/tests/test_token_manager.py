import pytest
from datetime import datetime, timezone, timedelta

def test_get_valid_token_returns_token_when_cache_is_valid(tmp_path):
    """
    [목적] 유효한 캐시 파일이 있을 때 토큰 문자열 반환
    [유도] JSON 파일 읽기 + 만료 시각 비교 로직 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("valid_token_abc", expires_at)

    result = tm.get_valid_token()
    assert result == "valid_token_abc"


def test_get_valid_token_returns_none_when_cache_file_not_exists(tmp_path):
    """
    [목적] 캐시 파일이 없을 때 None 반환 (예외 발생 금지)
    [유도] FileNotFoundError를 catch하고 None을 반환하는 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "nonexistent_token.json"
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")

    result = tm.get_valid_token()
    assert result is None


def test_save_token_creates_json_file_with_correct_structure(tmp_path):
    """
    [목적] save_token() 호출 시 JSON 파일이 올바른 구조로 생성됨을 검증
    [유도] JSON 파일에 'token'과 'expires_at' 필드를 저장하는 구현 강제
    """
    import json
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    expires_at = datetime(2026, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("my_token", expires_at)

    data = json.loads(cache_file.read_text())
    assert data["token"] == "my_token"
    assert "expires_at" in data


def test_save_token_creates_parent_directories_automatically(tmp_path):
    """
    [목적] 캐시 파일의 부모 디렉토리가 없어도 자동 생성됨을 검증
    [유도] Path.mkdir(parents=True, exist_ok=True) 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "subdir" / "deep" / "token.json"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("my_token", expires_at)

    assert cache_file.exists()


def test_is_valid_returns_true_when_token_has_enough_time_left(tmp_path):
    """
    [목적] 만료까지 5분 이상 남은 경우 is_valid()가 True 반환
    [유도] (expires_at - now) > timedelta(minutes=5) 조건 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("still_valid", expires_at)

    assert tm.is_valid() is True


def test_is_valid_returns_false_when_no_cache_file(tmp_path):
    """
    [목적] 캐시 파일이 없으면 is_valid()가 False 반환
    [유도] 파일 없음 → False 반환 분기 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "missing.json"
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")

    assert tm.is_valid() is False


def test_get_valid_token_returns_none_when_token_is_expired(tmp_path):
    """
    [목적] 만료된 토큰이 캐시에 있으면 None 반환
    [유도] 만료 시각 비교 후 만료된 경우 None 반환 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("expired_token", expired_at)

    result = tm.get_valid_token()
    assert result is None


def test_is_valid_returns_false_within_5_minutes_of_expiry(tmp_path):
    """
    [목적] 만료 4분 전 토큰은 is_valid()가 False 반환 (조기 만료 처리)
    [유도] 5분 버퍼 로직 — (expires_at - now) <= timedelta(minutes=5) 구현 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    # 만료까지 4분 남음 (5분 버퍼 내)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=4)
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")
    tm.save_token("almost_expired", expires_at)

    assert tm.is_valid() is False


def test_get_valid_token_returns_none_when_cache_file_is_corrupted(tmp_path):
    """
    [목적] 캐시 파일이 손상(invalid JSON)된 경우 예외 없이 None 반환
    [유도] json.JSONDecodeError를 catch하고 None 반환하는 방어 로직 강제
    """
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "token.json"
    cache_file.write_text("THIS IS NOT VALID JSON {{{{")
    tm = TokenManager(cache_path=str(cache_file), token_type="kiwoom")

    result = tm.get_valid_token()
    assert result is None
