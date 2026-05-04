import pytest

def test_kiwoom_api_core_initializes_with_credentials(tmp_path):
    """
    [목적] app_key, app_secret, token_cache_path로 정상 초기화됨을 검증
    [유도] __init__에서 TokenManager를 생성하는 구현 강제
    """
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore

    core = KiwoomApiCore(
        app_key="test_key",
        app_secret="test_secret",
        token_cache_path=str(tmp_path / "kiwoom_token.json"),
    )
    assert core is not None


def test_get_headers_returns_dict_with_authorization(tmp_path, mocker):
    """
    [목적] get_headers()가 Authorization 키를 포함한 dict를 반환함을 검증
    [유도] 유효한 토큰을 헤더에 삽입하는 구현 강제
    """
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore
    from datetime import datetime, timezone, timedelta
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kiwoom_token.json"
    # 캐시에 유효한 토큰 미리 저장
    tm = TokenManager(str(cache_file), "kiwoom")
    tm.save_token("Bearer test_access_token", datetime.now(timezone.utc) + timedelta(hours=12))

    core = KiwoomApiCore(
        app_key="test_key",
        app_secret="test_secret",
        token_cache_path=str(cache_file),
    )
    headers = core.get_headers()

    assert "Authorization" in headers


def test_get_headers_issues_new_token_when_cache_is_empty(tmp_path, mocker):
    """
    [목적] 캐시가 비어있을 때 신규 토큰 발급 후 헤더에 포함됨을 검증
    [유도] get_valid_token()이 None이면 issue_new_token()을 호출하는 로직 강제
    """
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore

    # 토큰 발급 HTTP 요청 Mock
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "new_issued_token",
        "expires_in": 86400  # Kiwoom은 expires_in을 초 단위로 주거나, 명세에 따르면 "expires_dt"를 줄 수 있음. 명세에 따름.
    }
    # 명세에 따라 "token", "expires_dt" 반환
    mock_post.return_value.json.return_value = {
        "access_token": "new_issued_token", # Spec says token or access_token, wait, let me look at spec: "응답 필드: token (토큰 문자열), expires_dt (만료일시, "YYYYMMDDHHMMSS" 형식)"
    }
    mock_post.return_value.json.return_value = {
        "token": "new_issued_token",
        "expires_dt": "20270101120000"  # Kiwoom 응답 형식
    }

    core = KiwoomApiCore(
        app_key="test_key",
        app_secret="test_secret",
        token_cache_path=str(tmp_path / "empty_token.json"),
    )
    headers = core.get_headers()

    mock_post.assert_called_once()
    assert "Authorization" in headers


def test_request_calls_http_method_with_correct_url(tmp_path, mocker):
    """
    [목적] request()가 올바른 URL로 HTTP 요청을 보냄을 검증
    [유도] BASE_URL + path로 URL을 조합하는 구현 강제
    """
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore
    from datetime import datetime, timezone, timedelta
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kiwoom_token.json"
    tm = TokenManager(str(cache_file), "kiwoom")
    tm.save_token("valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    mock_request = mocker.patch("requests.request")
    mock_request.return_value.status_code = 200
    mock_request.return_value.json.return_value = {"data": []}
    mock_request.return_value.raise_for_status = lambda: None

    core = KiwoomApiCore(
        app_key="test_key",
        app_secret="test_secret",
        token_cache_path=str(cache_file),
    )
    result = core.request("GET", "/api/dostk/stkinfo", params={"stk_cd": "005930"})

    called_url = mock_request.call_args[0][1]
    assert "/api/dostk/stkinfo" in called_url
    assert isinstance(result, dict)


def test_request_raises_http_error_on_4xx_response(tmp_path, mocker):
    """
    [목적] API가 4xx 응답 시 HTTPError가 발생함을 검증
    [유도] response.raise_for_status() 호출 구현 강제
    """
    import requests as req
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore
    from datetime import datetime, timezone, timedelta
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kiwoom_token.json"
    tm = TokenManager(str(cache_file), "kiwoom")
    tm.save_token("valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    mock_request = mocker.patch("requests.request")
    mock_response = mocker.MagicMock()
    mock_response.raise_for_status.side_effect = req.HTTPError("400 Bad Request")
    mock_request.return_value = mock_response

    core = KiwoomApiCore(
        app_key="test_key",
        app_secret="test_secret",
        token_cache_path=str(cache_file),
    )
    with pytest.raises(req.HTTPError):
        core.request("GET", "/api/dostk/stkinfo")


def test_get_headers_raises_runtime_error_when_token_issue_fails(tmp_path, mocker):
    """
    [목적] 토큰 발급 API 실패 시 RuntimeError가 발생함을 검증
    [유도] 발급 HTTP 응답 실패를 catch하고 RuntimeError로 변환하는 구현 강제
    """
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore
    import requests as req

    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 401
    mock_post.return_value.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

    core = KiwoomApiCore(
        app_key="bad_key",
        app_secret="bad_secret",
        token_cache_path=str(tmp_path / "empty.json"),
    )
    with pytest.raises(RuntimeError):
        core.get_headers()
