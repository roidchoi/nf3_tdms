import pytest
from datetime import datetime, timezone, timedelta

def test_base_url_returns_real_url_when_is_mock_is_false(tmp_path):
    """
    [목적] is_mock=False 시 실전 투자 URL 반환
    [유도] base_url property가 REAL_URL 상수를 반환하는 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        is_mock=False,
        token_cache_path=str(tmp_path / "kis_token.json"),
    )
    assert "openapi.koreainvestment.com" in core.base_url


def test_base_url_returns_mock_url_when_is_mock_is_true(tmp_path):
    """
    [목적] is_mock=True 시 모의 투자 URL 반환
    [유도] base_url property가 is_mock 플래그를 분기하는 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        is_mock=True,
        token_cache_path=str(tmp_path / "kis_token.json"),
    )
    assert "openapivts.koreainvestment.com" in core.base_url


def test_get_headers_returns_dict_with_required_keys(tmp_path):
    """
    [목적] get_headers()가 Authorization, appkey, appsecret, tr_id를 포함한 dict 반환
    [유도] KIS 표준 헤더 구조 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("Bearer valid_access_token", datetime.now(timezone.utc) + timedelta(hours=12))

    core = KisApiCore(
        app_key="test_key", app_secret="test_secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    headers = core.get_headers(tr_id="FHKST01010100")

    assert "Authorization" in headers
    assert "appkey" in headers
    assert "appsecret" in headers
    assert "tr_id" in headers


def test_get_headers_includes_extra_headers(tmp_path):
    """
    [목적] extra 파라미터로 전달된 항목이 헤더에 병합됨을 검증
    [유도] dict.update(extra) 또는 {**base_headers, **extra} 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("Bearer valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    headers = core.get_headers(tr_id="FHKST01010100", extra={"custtype": "P"})

    assert headers["custtype"] == "P"


def test_request_returns_response_json_on_success(tmp_path, mocker):
    """
    [목적] 정상(200) 응답 시 JSON dict를 반환함을 검증
    [유도] response.json() 결과를 그대로 반환하는 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("Bearer valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"output": [{"stck_prpr": "75000"}]}
    mock_resp.raise_for_status = lambda: None
    mocker.patch("requests.request", return_value=mock_resp)

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    result = core.request("GET", "/uapi/domestic-stock/v1/quotations/inquire-daily-price")

    assert "output" in result


def test_get_headers_issues_new_token_when_cache_is_empty(tmp_path, mocker):
    """
    [목적] 토큰 캐시가 비어있을 때 신규 발급 후 헤더에 포함됨을 검증
    [유도] get_valid_token()이 None이면 issue_new_token()을 호출하는 로직 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore

    # KIS 토큰 발급 API Mock
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "new_kis_token",
        "token_type": "Bearer",
        "access_token_token_expired": "2027-01-01 12:00:00"
    }
    mock_post.return_value.raise_for_status = lambda: None

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(tmp_path / "empty_kis_token.json"),
    )
    headers = core.get_headers(tr_id="FHKST01010100")

    mock_post.assert_called_once()
    assert "Authorization" in headers

def test_request_retries_once_on_401_and_succeeds(tmp_path, mocker):
    """
    [목적] 401 응답 시 토큰 재발급 후 1회 재시도하여 성공함을 검증
    [유도] 401 감지 → 토큰 강제 갱신 → 동일 요청 1회 재실행 로직 구현 강제
    핵심: requests.request가 총 2회 호출되어야 함 (첫 번째 401, 두 번째 200)
    """
    import requests as req
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("old_token", datetime.now(timezone.utc) + timedelta(hours=12))

    # 첫 번째 호출: 401, 두 번째 호출: 200
    resp_401 = mocker.MagicMock()
    resp_401.status_code = 401
    resp_401.raise_for_status.side_effect = req.HTTPError("401")

    resp_200 = mocker.MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"output": "ok"}
    resp_200.raise_for_status = lambda: None

    mock_request = mocker.patch("requests.request", side_effect=[resp_401, resp_200])

    # 토큰 재발급 Mock
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "refreshed_token",
        "token_type": "Bearer",
        "access_token_token_expired": "2027-01-01 12:00:00"
    }
    mock_post.return_value.raise_for_status = lambda: None

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    result = core.request("GET", "/some/path")

    assert mock_request.call_count == 2
    assert result == {"output": "ok"}


def test_two_instances_with_same_cache_path_share_token(tmp_path, mocker):
    """
    [목적] 동일 cache_path를 사용하는 두 인스턴스가 토큰을 공유함을 검증
           (p2_kdms·p3_usdms 간 토큰 공유의 핵심 시나리오)
    [유도] TokenManager가 파일 기반 캐시를 공유하면 두 번째 인스턴스는 재발급하지 않음을 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "shared_kis_token.json"

    # 첫 번째 인스턴스가 토큰 발급 → 캐시 저장
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "shared_access_token",
        "token_type": "Bearer",
        "access_token_token_expired": "2027-01-01 12:00:00"
    }
    mock_post.return_value.raise_for_status = lambda: None

    core1 = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    core1.get_headers(tr_id="FHKST01010100")  # 토큰 발급 + 캐시 저장
    first_call_count = mock_post.call_count  # 1회

    # 두 번째 인스턴스: 동일 캐시 파일 사용 → 재발급 없음
    core2 = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    core2.get_headers(tr_id="FHKST01010100")

    assert mock_post.call_count == first_call_count  # 추가 발급 없음

def test_request_raises_http_error_when_401_persists_after_retry(tmp_path, mocker):
    """
    [목적] 재시도 후에도 401이면 HTTPError가 발생함을 검증
    [유도] 재시도는 1회만 허용하고 그 이후도 실패하면 예외를 재발생시키는 구현 강제
    """
    import requests as req
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("stale_token", datetime.now(timezone.utc) + timedelta(hours=12))

    resp_401 = mocker.MagicMock()
    resp_401.status_code = 401
    resp_401.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

    # 두 번 모두 401 반환 (재발급 후에도 실패)
    mocker.patch("requests.request", return_value=resp_401)

    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "new_token",
        "token_type": "Bearer",
        "access_token_token_expired": "2027-01-01 12:00:00"
    }
    mock_post.return_value.raise_for_status = lambda: None

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    with pytest.raises(req.HTTPError):
        core.request("GET", "/some/path")


def test_request_raises_http_error_on_non_retryable_error(tmp_path, mocker):
    """
    [목적] 404 등 재시도 불가능한 HTTP 오류는 재시도 없이 즉시 HTTPError 전파
    """
    import requests as req
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    resp_404 = mocker.MagicMock()
    resp_404.status_code = 404
    resp_404.raise_for_status.side_effect = req.HTTPError("404 Not Found", response=resp_404)

    mock_request = mocker.patch("requests.request", return_value=resp_404)

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    with pytest.raises(req.HTTPError):
        core.request("GET", "/some/path")

    # 재시도 없이 1회만 호출
    assert mock_request.call_count == 1


def test_request_retries_on_transient_error_using_backoff(tmp_path, mocker):
    """
    [목적] 500 Server Error 발생 시 지수 백오프를 기동하여 최대 3회 재시도(총 4회 호출) 실행 검증
    """
    import requests as req
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    resp_500 = mocker.MagicMock()
    resp_500.status_code = 500
    resp_500.raise_for_status.side_effect = req.HTTPError("500 Server Error", response=resp_500)

    mock_request = mocker.patch("requests.request", return_value=resp_500)
    mock_sleep = mocker.patch("time.sleep") # 테스트 대기 시간 패치로 초고속 완료 보장

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    with pytest.raises(req.HTTPError):
        core.request("GET", "/some/path")

    # 최초 시도 + 3회 재시도 = 총 4회 호출
    assert mock_request.call_count == 4
    assert mock_sleep.call_count == 3


def test_get_headers_raises_runtime_error_when_token_issue_fails(tmp_path, mocker):
    """
    [목적] KIS 토큰 발급 API가 실패하면 RuntimeError 발생
    [유도] 발급 HTTP 오류를 RuntimeError로 변환하는 방어 로직 구현 강제
    """
    from p1_shared.api.kis_api_core import KisApiCore
    import requests as req

    mock_post = mocker.patch("requests.post")
    mock_post.return_value.status_code = 401
    mock_post.return_value.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

    core = KisApiCore(
        app_key="bad_key", app_secret="bad_secret", account_no="00000000-00",
        token_cache_path=str(tmp_path / "empty.json"),
    )
    with pytest.raises(RuntimeError):
        core.get_headers(tr_id="FHKST01010100")
