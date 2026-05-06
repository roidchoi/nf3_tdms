# Task-005: KIS API 코어 (KisApiCore)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.1 KIS API 코어 (`api/kis_api_core.py`)
> **작성일**: 2026-05-04
> **의존 Task**: T-004

---

## § 1. 목표

p2_kdms·p3_usdms 양쪽에 각각 중복 구현된 KIS REST API 클라이언트를 `KisApiCore`로 통합한다. `TokenManager`(T-004)를 통해 토큰 캐시 파일을 공유함으로써 중복 발급을 방지하고, `is_mock` 플래그로 실전/모의 투자 URL을 자동 선택한다. `401` 응답 시 토큰 자동 갱신 후 1회 재시도하는 방어 로직도 포함한다.

**구현 범위:**
- **IN**:
  - `p1_shared/api/kis_api_core.py` — `KisApiCore` 기반 클래스
  - `base_url` property (실전/모의 URL 자동 선택)
  - `get_headers(tr_id, extra)` — 유효 토큰 포함 헤더 반환
  - `request(method, path, params, body)` — 401 시 자동 갱신 + 1회 재시도
  - `tests/test_kis_api_core.py` — 단위 테스트 (HTTP Mock 처리)
- **OUT**:
  - `KisKrClient`, `KisUsClient` 서브클래스 — p2_kdms, p3_usdms 각 Task
  - 실제 KIS API 서버 호출 (단위 테스트에서는 Mock 처리)
  - KIS 토큰 발급 세부 로직 — KIS OAuth2 사양에 따라 구현하되, 이 Task의 핵심 관심사는 캐시 공유 및 재시도 패턴

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/api/kis_api_core.py` — `KisApiCore` 구현
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_kis_api_core.py` — 단위 테스트

### 핵심 인터페이스

```python
# p1_shared/api/kis_api_core.py
import requests
from p1_shared.api.token_manager import TokenManager

class KisApiCore:
    """
    KIS REST API 클라이언트 기반 클래스.

    p2_kdms·p3_usdms가 동일 token_cache_path를 사용하면
    토큰 캐시 파일을 공유하여 중복 발급을 방지한다.

    Args:
        app_key: KIS Open API 앱 키 (KIS_APP_KEY)
        app_secret: KIS Open API 앱 시크릿 (KIS_APP_SECRET)
        account_no: 계좌번호 (헤더 구성에 사용)
        is_mock: True이면 모의 투자 URL, False이면 실전 투자 URL
        token_cache_path: 토큰 캐시 파일 경로
    """

    REAL_URL = "https://openapi.koreainvestment.com:9443"
    MOCK_URL = "https://openapivts.koreainvestment.com:29443"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_mock: bool = False,
        token_cache_path: str = "~/.cache/tdms/kis_token.json",
    ) -> None: ...

    @property
    def base_url(self) -> str:
        """
        is_mock 플래그에 따라 실전/모의 투자 URL 반환.

        Returns:
            REAL_URL (is_mock=False) 또는 MOCK_URL (is_mock=True)
        """
        ...

    def get_headers(self, tr_id: str, extra: dict = {}) -> dict:
        """
        유효한 토큰이 포함된 KIS 요청 헤더 반환.
        토큰 만료 시 자동 갱신 후 헤더 구성.

        Args:
            tr_id: KIS 거래 ID (예: "FHKST01010100")
            extra: 추가 헤더 항목 (선택)

        Returns:
            dict: Authorization, appkey, appsecret, tr_id 등을 포함한 헤더
        Raises:
            RuntimeError: 토큰 발급 실패 시
        """
        ...

    def request(
        self,
        method: str,
        path: str,
        params: dict = {},
        body: dict = {},
    ) -> dict:
        """
        KIS API 요청 실행. 401 응답 시 토큰 자동 갱신 후 1회 재시도.

        Args:
            method: HTTP 메서드 ("GET", "POST" 등)
            path: API 경로 (예: "/uapi/domestic-stock/v1/quotations/inquire-daily-price")
            params: 쿼리 파라미터
            body: 요청 바디 (POST 전용)

        Returns:
            dict: API 응답 JSON

        Raises:
            requests.HTTPError: 401 이외의 4xx/5xx 응답 또는 재시도 후에도 401인 경우
            RuntimeError: 토큰 발급 실패 시
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **외부 격리 필수**: 모든 테스트는 실제 KIS API 서버 호출 없이 동작해야 합니다.
> `tmp_path`로 캐시 파일 격리, `mocker.patch("requests.request")`로 HTTP 요청을 Mock 처리하세요.

### 4.1 정상 동작 케이스

```python
# tests/test_kis_api_core.py
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
```

### 4.2 경계값 케이스

```python
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
```

### 4.3 예외/오류 처리 케이스

```python
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


def test_request_raises_http_error_on_non_401_error(tmp_path, mocker):
    """
    [목적] 500 등 401이 아닌 HTTP 오류는 재시도 없이 즉시 HTTPError 전파
    [유도] 401 조건을 명시적으로 분기하여 다른 오류는 바로 raise하는 구현 강제
    """
    import requests as req
    from p1_shared.api.kis_api_core import KisApiCore
    from p1_shared.api.token_manager import TokenManager

    cache_file = tmp_path / "kis_token.json"
    tm = TokenManager(str(cache_file), "kis")
    tm.save_token("valid_token", datetime.now(timezone.utc) + timedelta(hours=12))

    resp_500 = mocker.MagicMock()
    resp_500.status_code = 500
    resp_500.raise_for_status.side_effect = req.HTTPError("500 Server Error")

    mock_request = mocker.patch("requests.request", return_value=resp_500)

    core = KisApiCore(
        app_key="key", app_secret="secret", account_no="12345678-01",
        token_cache_path=str(cache_file),
    )
    with pytest.raises(req.HTTPError):
        core.request("GET", "/some/path")

    # 재시도 없이 1회만 호출
    assert mock_request.call_count == 1


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
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_base_url_returns_real_url_when_is_mock_is_false` | 정상 | is_mock=False → 실전 URL |
| 2 | `test_base_url_returns_mock_url_when_is_mock_is_true` | 정상 | is_mock=True → 모의 URL |
| 3 | `test_get_headers_returns_dict_with_required_keys` | 정상 | Authorization 등 필수 헤더 포함 |
| 4 | `test_get_headers_includes_extra_headers` | 정상 | extra 헤더 병합 |
| 5 | `test_request_returns_response_json_on_success` | 정상 | 200 응답 → JSON dict 반환 |
| 6 | `test_get_headers_issues_new_token_when_cache_is_empty` | 정상 | 캐시 없을 때 신규 발급 |
| 7 | `test_request_retries_once_on_401_and_succeeds` | 경계값 | 401 → 갱신 → 재시도 성공 (2회 호출) |
| 8 | `test_two_instances_with_same_cache_path_share_token` | 경계값 | 동일 캐시 경로 → 토큰 공유 (p2·p3 공유 핵심 시나리오) |
| 9 | `test_request_raises_http_error_when_401_persists_after_retry` | 예외 | 재시도 후에도 401 → HTTPError |
| 10 | `test_request_raises_http_error_on_non_401_error` | 예외 | 500 등 → 재시도 없이 즉시 HTTPError |
| 11 | `test_get_headers_raises_runtime_error_when_token_issue_fails` | 예외 | 토큰 발급 실패 → RuntimeError |

**총 11개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `requests>=2.32` (이미 설치됨), `p1_shared.api.token_manager.TokenManager` (T-004 완료)
- **관련 문서**: `p1_shared_PRD.md` §3.1 — `KisApiCore` 인터페이스 및 토큰 캐시 공유 흐름
- **KIS 토큰 발급 API 참고**:
  - 엔드포인트: `POST {base_url}/oauth2/tokenP`
  - 요청 바디: `{"grant_type": "client_credentials", "appkey": ..., "appsecret": ...}`
  - 응답 필드: `access_token`, `token_type`, `access_token_token_expired` (`"YYYY-MM-DD HH:MM:SS"` 형식)
- **만료 시각 파싱**: `datetime.strptime(expires_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)`
- **401 재시도 패턴 구현 가이드**:
  ```python
  try:
      response = requests.request(...)
      response.raise_for_status()
  except requests.HTTPError as e:
      if response.status_code == 401:
          self._refresh_token()  # 강제 재발급 후 캐시 갱신
          response = requests.request(...)  # 1회 재시도
          response.raise_for_status()  # 재시도 후에도 실패하면 raise
      else:
          raise
  ```
- **토큰 캐시 공유 핵심**: `token_cache_path`가 동일한 파일 경로면 `TokenManager`가 파일을 공유 → p2_kdms와 p3_usdms가 서로 다른 프로세스에서 실행되더라도 파일 기반 캐시로 중복 발급 방지 가능
- **주의사항**: `get_headers()`에서 `TokenManager.get_valid_token()` 결과가 `None`이면 `issue_new_token()` 내부 메서드를 호출하여 발급 후 `save_token()` 저장. 발급 실패 시 `RuntimeError`로 변환.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 11개 전체 통과
- [ ] 기존 T-001(20개) + T-002(15개) + T-003(12개) + T-004(15개) 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-005 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-005_walkthrough.md` 작성
