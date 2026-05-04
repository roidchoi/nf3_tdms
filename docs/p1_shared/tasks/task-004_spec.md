# Task-004: 토큰 매니저 + Kiwoom API 코어

> **Sub Project**: p1_shared
> **PRD 근거**: §3.2 Kiwoom API 코어, §3.3 토큰 매니저
> **작성일**: 2026-05-04
> **의존 Task**: T-001

---

## § 1. 목표

파일 기반 API 토큰 캐시를 담당하는 `TokenManager`와, 이를 활용하여 Kiwoom REST API에 인증된 요청을 보내는 `KiwoomApiCore`를 구현한다. 원본(`kdms_origin/collectors/kiwoom_rest.py`)의 400줄 단일 파일을 `TokenManager`와 `KiwoomApiCore`로 분리하여 재사용성과 테스트 가능성을 확보한다.

**구현 범위:**
- **IN**:
  - `p1_shared/api/token_manager.py` — `TokenManager` 클래스 (파일 기반 캐시, 만료 5분 전 처리)
  - `p1_shared/api/kiwoom_api_core.py` — `KiwoomApiCore` 클래스 (`TokenManager` 연동, `get_headers()`, `request()`)
  - `p1_shared/api/__init__.py` — 서브패키지 초기화
  - `tests/test_token_manager.py` — `TokenManager` 단위 테스트
  - `tests/test_kiwoom_api_core.py` — `KiwoomApiCore` 단위 테스트 (HTTP는 Mock 처리)
- **OUT**:
  - KIS API 코어 (`KisApiCore`) — T-005
  - 실제 Kiwoom API 서버 호출 (단위 테스트에서는 Mock 처리)
  - 토큰 발급 로직 내부 구현 (`issue_new_token`은 `KiwoomApiCore` 책임이므로 `TokenManager`는 저장·조회만 담당)

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/api/__init__.py` — 서브패키지 초기화
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/api/token_manager.py` — `TokenManager` 구현
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/api/kiwoom_api_core.py` — `KiwoomApiCore` 구현
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_token_manager.py` — `TokenManager` 단위 테스트
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_kiwoom_api_core.py` — `KiwoomApiCore` 단위 테스트

### 핵심 인터페이스

```python
# p1_shared/api/token_manager.py
from datetime import datetime
from pathlib import Path

class TokenManager:
    """
    파일 기반 API 토큰 캐시 관리자.
    토큰을 JSON 파일로 저장하고, 만료 여부를 판단하여 반환한다.

    Args:
        cache_path: 토큰 캐시 파일 경로 (예: "~/.cache/tdms/kiwoom_token.json")
        token_type: 토큰 종류 식별자 (예: "kiwoom", "kis") — 로깅 및 오류 메시지용
    """

    def __init__(self, cache_path: str, token_type: str) -> None: ...

    def get_valid_token(self) -> str | None:
        """
        유효한 토큰 반환. 캐시 파일이 없거나 만료 시 None 반환.

        Returns:
            str: 유효한 토큰 문자열
            None: 캐시 없음 또는 만료됨
        """
        ...

    def save_token(self, token: str, expires_at: datetime) -> None:
        """
        토큰과 만료 시각을 JSON 파일로 저장.
        부모 디렉토리가 없으면 자동 생성(mkdir -p).

        Args:
            token: 저장할 토큰 문자열
            expires_at: 토큰 만료 datetime (timezone-aware 권장)
        """
        ...

    def is_valid(self) -> bool:
        """
        현재 캐시된 토큰의 유효성 확인.
        만료 시각 5분 전을 만료로 처리(조기 갱신 버퍼).

        Returns:
            True: 토큰 유효 (만료까지 5분 초과 남음)
            False: 캐시 없음, 파싱 실패, 또는 5분 이내 만료
        """
        ...


# p1_shared/api/kiwoom_api_core.py
import requests

class KiwoomApiCore:
    """
    Kiwoom REST API 클라이언트 (한국 시장 전용).
    TokenManager를 통해 토큰 캐시를 관리하며, 요청 시 자동으로 유효한 헤더를 구성한다.

    Args:
        app_key: Kiwoom Open API 앱 키
        app_secret: Kiwoom Open API 앱 시크릿
        token_cache_path: 토큰 캐시 파일 경로 (기본값: "~/.cache/tdms/kiwoom_token.json")
    """

    BASE_URL = "https://openapi.kiwoom.com"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        token_cache_path: str = "~/.cache/tdms/kiwoom_token.json",
    ) -> None: ...

    def get_headers(self) -> dict:
        """
        유효한 토큰이 포함된 요청 헤더 반환.
        토큰이 없거나 만료 시 자동으로 신규 발급 후 캐시 저장.

        Returns:
            dict: Authorization 헤더를 포함한 요청 헤더
        Raises:
            RuntimeError: 토큰 발급 실패 시
        """
        ...

    def request(
        self,
        method: str,
        path: str,
        params: dict = {},
    ) -> dict:
        """
        Kiwoom API 요청 실행.

        Args:
            method: HTTP 메서드 ("GET", "POST" 등)
            path: API 경로 (예: "/api/dostk/stkinfo")
            params: 쿼리 파라미터 또는 요청 바디

        Returns:
            dict: API 응답 JSON
        Raises:
            requests.HTTPError: 4xx/5xx 응답 시
            RuntimeError: 토큰 발급 실패 시
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **외부 격리 필수**: 모든 테스트는 실제 Kiwoom API 서버 및 파일시스템에 의존하지 않아야 합니다.
> `tmp_path` fixture로 캐시 파일 격리, `mocker.patch`로 HTTP 요청을 Mock 처리하세요.

### 4.1 정상 동작 케이스 — TokenManager

```python
# tests/test_token_manager.py
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
```

### 4.2 경계값 케이스 — TokenManager

```python
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
```

### 4.3 정상 동작 케이스 — KiwoomApiCore

```python
# tests/test_kiwoom_api_core.py
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
    from datetime import timezone, timedelta
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
    from datetime import timezone, timedelta
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
```

### 4.4 예외/오류 처리 케이스

```python
def test_request_raises_http_error_on_4xx_response(tmp_path, mocker):
    """
    [목적] API가 4xx 응답 시 HTTPError가 발생함을 검증
    [유도] response.raise_for_status() 호출 구현 강제
    """
    import requests as req
    from p1_shared.api.kiwoom_api_core import KiwoomApiCore
    from datetime import timezone, timedelta
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
```

### 테스트 케이스 요약

#### TokenManager (`test_token_manager.py`)

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_get_valid_token_returns_token_when_cache_is_valid` | 정상 | 유효 캐시에서 토큰 반환 |
| 2 | `test_get_valid_token_returns_none_when_cache_file_not_exists` | 정상 | 캐시 없음 → None 반환 |
| 3 | `test_save_token_creates_json_file_with_correct_structure` | 정상 | JSON 파일 구조 검증 |
| 4 | `test_save_token_creates_parent_directories_automatically` | 정상 | 부모 디렉토리 자동 생성 |
| 5 | `test_is_valid_returns_true_when_token_has_enough_time_left` | 정상 | 유효 기간 충분 → True |
| 6 | `test_is_valid_returns_false_when_no_cache_file` | 정상 | 캐시 없음 → False |
| 7 | `test_get_valid_token_returns_none_when_token_is_expired` | 경계값 | 만료 토큰 → None |
| 8 | `test_is_valid_returns_false_within_5_minutes_of_expiry` | 경계값 | 만료 4분 전 → False (5분 버퍼) |
| 9 | `test_get_valid_token_returns_none_when_cache_file_is_corrupted` | 예외 | JSON 손상 → None (예외 없음) |

#### KiwoomApiCore (`test_kiwoom_api_core.py`)

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 10 | `test_kiwoom_api_core_initializes_with_credentials` | 정상 | 정상 초기화 |
| 11 | `test_get_headers_returns_dict_with_authorization` | 정상 | 유효 캐시 시 Authorization 헤더 포함 |
| 12 | `test_get_headers_issues_new_token_when_cache_is_empty` | 정상 | 캐시 없을 때 신규 발급 후 헤더 구성 |
| 13 | `test_request_calls_http_method_with_correct_url` | 정상 | 올바른 URL로 HTTP 요청 |
| 14 | `test_request_raises_http_error_on_4xx_response` | 예외 | 4xx 응답 → HTTPError 전파 |
| 15 | `test_get_headers_raises_runtime_error_when_token_issue_fails` | 예외 | 토큰 발급 실패 → RuntimeError |

**총 15개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `requests>=2.32`, `python-dotenv>=1.1` (모두 이미 설치됨)
- **관련 문서**: `p1_shared_PRD.md` §3.2, §3.3 — `KiwoomApiCore`, `TokenManager` 인터페이스 원본
- **Kiwoom 토큰 발급 API 참고** (원본 `kdms_origin/collectors/kiwoom_rest.py` 참조):
  - 엔드포인트: `POST https://openapi.kiwoom.com/oauth2/token`
  - 요청 바디: `{"grant_type": "client_credentials", "appkey": ..., "secretkey": ...}`
  - 응답 필드: `token` (토큰 문자열), `expires_dt` (만료일시, `"YYYYMMDDHHMMSS"` 형식)
- **만료 시각 파싱**:
  - Kiwoom `expires_dt` 형식: `"20260501120000"` → `datetime.strptime(..., "%Y%m%d%H%M%S")`
  - JSON 저장 시에는 ISO8601 형식(`isoformat()`)으로 변환하여 저장 권장
- **주의사항**:
  - `TokenManager`는 토큰 발급(HTTP 호출)을 하지 않음. 저장(`save_token`)과 조회(`get_valid_token`, `is_valid`)만 담당
  - `KiwoomApiCore.get_headers()`에서 `TokenManager.get_valid_token()` 결과가 `None`이면 신규 발급 후 `save_token()` 호출
  - `tmp_path` fixture를 캐시 파일 격리에 활용하면 테스트 간 상태 오염 없음

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 15개 전체 통과
- [ ] 기존 T-001(20개) + T-002(15개) + T-003(12개) 테스트 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-004 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-004_walkthrough.md` 작성
