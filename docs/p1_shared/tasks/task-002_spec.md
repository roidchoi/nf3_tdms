# Task-002: 환경 감지 모듈 (EnvDetector)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.9 환경 감지 모듈 (`utils/env_detector.py`)
> **작성일**: 2026-05-04
> **의존 Task**: T-001

---

## § 1. 목표

개발PC(WSL2)와 서버PC(WSL2) 양쪽에서 동일한 코드를 실행할 때, 실행 중인 PC가 어느 환경인지 자동으로 감지하고 그에 맞는 `.env` 값(상대방 DB 호스트 등)을 올바르게 반환하는 `EnvDetector` 클래스를 구현한다.

**구현 범위:**
- **IN**:
  - `p1_shared/utils/env_detector.py` — `EnvDetector` 클래스
  - `TDMS_ENV` 명시 → hostname 매칭 → IP 매칭 순서의 3단계 감지 로직
  - `load_env_profile()` — 현재 환경에 맞는 DB 접속 prefix 반환
  - `get_peer_host()` — 동기화 상대 PC의 내부망 IP 반환
  - `tests/test_env_detector.py` — 단위 테스트
- **OUT**:
  - 실제 DB 접속(커넥션 풀) — T-003
  - `pg_hba.conf`, Windows 방화벽 등 인프라 설정 — 운영자 수동 작업
  - SSH 연결 실제 수행 — T-008 (SyncManager)

---

## § 2. 구현 대상

### 신규 생성 파일

- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/env_detector.py` — `EnvDetector` 클래스 구현
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_env_detector.py` — 단위 테스트

### 핵심 인터페이스

```python
# p1_shared/utils/env_detector.py
from typing import Literal

class EnvDetector:
    """
    hostname/IP 기반 실행 환경 자동 감지 및 .env 프로파일 로더.

    감지 우선순위:
      1. 환경변수 TDMS_ENV 명시적 지정 (최우선, 'dev' | 'server')
      2. hostname 매칭 (.env의 DEV_HOSTNAME, SERVER_HOSTNAME과 비교)
      3. IP 주소 매칭 (.env의 DEV_IP, SERVER_IP와 비교)
      4. 감지 실패 시 'unknown' 반환

    Notes:
        - WSL2에서 호스트명은 Windows 호스트명을 따른다.
        - WSL 가상 IP(172.x.x.x)가 아닌 Windows 내부망 IP(192.168.x.x)로 비교한다.
    """

    def detect(self) -> Literal["dev", "server", "unknown"]:
        """
        현재 실행 PC의 환경을 감지하여 반환.

        Returns:
            'dev': 개발PC로 확인됨
            'server': 서버PC로 확인됨
            'unknown': 감지 불가 (경고 로그 출력)
        """
        ...

    def load_env_profile(self) -> dict:
        """
        현재 환경에 맞는 설정 값 dict 반환.

        예: dev 환경이면 → {'env': 'dev', 'self_ip': '192.168.1.10', 'peer_ip': '192.168.1.20'}

        Returns:
            dict with keys: 'env', 'self_ip', 'peer_ip', 'self_hostname', 'peer_hostname'
        Raises:
            RuntimeError: 환경이 'unknown'인 경우
        """
        ...

    def get_peer_host(self) -> str:
        """
        동기화 상대방 PC의 내부망 IP 반환.
        dev → SERVER_IP, server → DEV_IP.

        Returns:
            str: 상대방 IP 주소
        Raises:
            RuntimeError: 환경이 'unknown'인 경우
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **환경 격리 필수**: 모든 테스트는 `monkeypatch` 또는 `mocker.patch`를 사용하여
> 실제 `os.environ`과 `socket.gethostname()`을 오염시키지 않아야 합니다.

### 4.1 정상 동작 케이스

```python
# tests/test_env_detector.py
import pytest
import os

def test_detect_returns_dev_when_tdms_env_is_explicitly_set(monkeypatch):
    """
    [목적] TDMS_ENV=dev가 명시적으로 지정된 경우 최우선 감지됨을 검증
    [유도] detect()가 hostname/IP 조회 전에 TDMS_ENV 환경변수를 먼저 확인하도록 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "dev")
    detector = EnvDetector()
    assert detector.detect() == "dev"


def test_detect_returns_server_when_tdms_env_is_explicitly_set(monkeypatch):
    """
    [목적] TDMS_ENV=server가 명시적으로 지정된 경우 최우선 감지됨을 검증
    [유도] TDMS_ENV 환경변수 처리 로직이 'dev'에 국한되지 않음을 보장
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "server")
    detector = EnvDetector()
    assert detector.detect() == "server"


def test_detect_returns_dev_by_hostname_match(monkeypatch, mocker):
    """
    [목적] TDMS_ENV 미설정 시 hostname이 DEV_HOSTNAME과 일치하면 'dev' 반환
    [유도] TDMS_ENV가 없을 때 hostname을 조회하는 2단계 분기 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    mocker.patch("socket.gethostname", return_value="ROID-DEV")

    detector = EnvDetector()
    assert detector.detect() == "dev"


def test_detect_returns_server_by_hostname_match(monkeypatch, mocker):
    """
    [목적] TDMS_ENV 미설정 시 hostname이 SERVER_HOSTNAME과 일치하면 'server' 반환
    [유도] hostname 매칭이 dev/server 양방향으로 동작함을 보장
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    mocker.patch("socket.gethostname", return_value="ROID-SERVER")

    detector = EnvDetector()
    assert detector.detect() == "server"


def test_detect_returns_dev_by_ip_match(monkeypatch, mocker):
    """
    [목적] hostname 불일치 시 DEV_IP와 현재 내부망 IP가 일치하면 'dev' 반환
    [유도] hostname → IP 순서의 3단계 폴백 로직 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")
    # hostname 불일치, IP 매칭으로 폴백
    mocker.patch("socket.gethostname", return_value="UNKNOWN-HOST")
    mocker.patch(
        "p1_shared.utils.env_detector.get_local_ips",
        return_value=["192.168.1.10", "172.28.0.1"]
    )

    detector = EnvDetector()
    assert detector.detect() == "dev"


def test_get_peer_host_returns_server_ip_when_env_is_dev(monkeypatch):
    """
    [목적] dev 환경에서 get_peer_host()가 SERVER_IP를 반환함을 검증
    [유도] detect() 결과에 따라 peer IP를 조회하는 로직 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "dev")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")

    detector = EnvDetector()
    assert detector.get_peer_host() == "192.168.1.20"


def test_get_peer_host_returns_dev_ip_when_env_is_server(monkeypatch):
    """
    [목적] server 환경에서 get_peer_host()가 DEV_IP를 반환함을 검증
    [유도] dev/server 대칭 반환 로직 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "server")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")

    detector = EnvDetector()
    assert detector.get_peer_host() == "192.168.1.10"


def test_load_env_profile_returns_correct_dict_for_dev(monkeypatch):
    """
    [목적] dev 환경에서 load_env_profile()이 self/peer IP를 올바르게 구성함을 검증
    [유도] detect()와 연동하여 dict를 구성하는 load_env_profile() 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "dev")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")

    detector = EnvDetector()
    profile = detector.load_env_profile()

    assert profile["env"] == "dev"
    assert profile["self_ip"] == "192.168.1.10"
    assert profile["peer_ip"] == "192.168.1.20"
    assert profile["self_hostname"] == "ROID-DEV"
    assert profile["peer_hostname"] == "ROID-SERVER"
```

### 4.2 경계값 케이스

```python
def test_detect_returns_unknown_when_no_env_matches(monkeypatch, mocker):
    """
    [목적] TDMS_ENV 미설정, hostname 불일치, IP 불일치 시 'unknown' 반환
    [유도] 모든 감지 단계 실패 시 graceful fallback(unknown) 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")
    mocker.patch("socket.gethostname", return_value="UNKNOWN-PC")
    mocker.patch(
        "p1_shared.utils.env_detector.get_local_ips",
        return_value=["10.0.0.5"]  # 등록되지 않은 IP
    )

    detector = EnvDetector()
    assert detector.detect() == "unknown"


def test_detect_is_case_insensitive_for_hostname(monkeypatch, mocker):
    """
    [목적] hostname 비교가 대소문자를 무시함을 검증
    [유도] hostname.lower() 정규화 비교 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    mocker.patch("socket.gethostname", return_value="roid-dev")  # 소문자

    detector = EnvDetector()
    assert detector.detect() == "dev"
```

### 4.3 예외/오류 처리 케이스

```python
def test_get_peer_host_raises_when_env_is_unknown(monkeypatch, mocker):
    """
    [목적] 환경이 'unknown'일 때 get_peer_host()가 RuntimeError를 발생시킴을 검증
    [유도] 감지 실패 상태에서 잘못된 IP를 반환하지 않도록 방어 로직 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")
    mocker.patch("socket.gethostname", return_value="UNKNOWN-PC")
    mocker.patch(
        "p1_shared.utils.env_detector.get_local_ips",
        return_value=["10.0.0.99"]
    )

    detector = EnvDetector()
    with pytest.raises(RuntimeError, match="unknown"):
        detector.get_peer_host()


def test_load_env_profile_raises_when_env_is_unknown(monkeypatch, mocker):
    """
    [목적] 환경이 'unknown'일 때 load_env_profile()이 RuntimeError를 발생시킴을 검증
    [유도] unknown 상태에서 잘못된 프로파일 구성을 방지하는 방어 로직 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.delenv("TDMS_ENV", raising=False)
    monkeypatch.setenv("DEV_HOSTNAME", "ROID-DEV")
    monkeypatch.setenv("SERVER_HOSTNAME", "ROID-SERVER")
    monkeypatch.setenv("DEV_IP", "192.168.1.10")
    monkeypatch.setenv("SERVER_IP", "192.168.1.20")
    mocker.patch("socket.gethostname", return_value="UNKNOWN-PC")
    mocker.patch(
        "p1_shared.utils.env_detector.get_local_ips",
        return_value=["10.0.0.99"]
    )

    detector = EnvDetector()
    with pytest.raises(RuntimeError, match="unknown"):
        detector.load_env_profile()


def test_detect_with_invalid_tdms_env_value_returns_unknown(monkeypatch):
    """
    [목적] TDMS_ENV에 'dev'/'server' 외의 값이 입력되면 'unknown'으로 처리됨을 검증
    [유도] TDMS_ENV 값 유효성 검사 로직 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    monkeypatch.setenv("TDMS_ENV", "production")  # 지원하지 않는 값

    detector = EnvDetector()
    assert detector.detect() == "unknown"
```

### 4.4 통합/연계 케이스

```python
def test_env_detector_loads_dotenv_on_init(monkeypatch, tmp_path, mocker):
    """
    [목적] EnvDetector 초기화 시 프로젝트 루트의 .env 파일을 자동으로 로드함을 검증
    [유도] __init__에서 load_dotenv(find_dotenv())를 호출하는 구현 강제
    """
    from p1_shared.utils.env_detector import EnvDetector

    # tmp_path에 임시 .env 생성
    env_file = tmp_path / ".env"
    env_file.write_text("TDMS_ENV=dev\n")

    mocker.patch(
        "p1_shared.utils.env_detector.find_dotenv",
        return_value=str(env_file)
    )
    monkeypatch.delenv("TDMS_ENV", raising=False)

    detector = EnvDetector()
    assert detector.detect() == "dev"


def test_get_local_ips_excludes_loopback_and_wsl_range():
    """
    [목적] get_local_ips()가 루프백(127.x) 및 WSL 가상 IP(172.x)를 제외함을 검증
    [유도] IP 목록 필터링 로직 — 192.168.x.x 내부망만 반환하도록 구현 강제
    """
    from p1_shared.utils.env_detector import get_local_ips

    ips = get_local_ips()
    for ip in ips:
        assert not ip.startswith("127.")
        assert not ip.startswith("172.")
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_detect_returns_dev_when_tdms_env_is_explicitly_set` | 정상 | TDMS_ENV 명시 시 최우선 감지 |
| 2 | `test_detect_returns_server_when_tdms_env_is_explicitly_set` | 정상 | TDMS_ENV=server 최우선 감지 |
| 3 | `test_detect_returns_dev_by_hostname_match` | 정상 | hostname 기반 dev 감지 |
| 4 | `test_detect_returns_server_by_hostname_match` | 정상 | hostname 기반 server 감지 |
| 5 | `test_detect_returns_dev_by_ip_match` | 정상 | IP 기반 dev 폴백 감지 |
| 6 | `test_get_peer_host_returns_server_ip_when_env_is_dev` | 정상 | dev → SERVER_IP 반환 |
| 7 | `test_get_peer_host_returns_dev_ip_when_env_is_server` | 정상 | server → DEV_IP 반환 |
| 8 | `test_load_env_profile_returns_correct_dict_for_dev` | 정상 | dev 프로파일 dict 구조 검증 |
| 9 | `test_detect_returns_unknown_when_no_env_matches` | 경계값 | 모든 감지 실패 시 unknown |
| 10 | `test_detect_is_case_insensitive_for_hostname` | 경계값 | hostname 대소문자 무시 |
| 11 | `test_get_peer_host_raises_when_env_is_unknown` | 예외 | unknown 상태에서 RuntimeError |
| 12 | `test_load_env_profile_raises_when_env_is_unknown` | 예외 | unknown 상태에서 RuntimeError |
| 13 | `test_detect_with_invalid_tdms_env_value_returns_unknown` | 예외 | 잘못된 TDMS_ENV 값 처리 |
| 14 | `test_env_detector_loads_dotenv_on_init` | 통합 | __init__에서 .env 자동 로드 |
| 15 | `test_get_local_ips_excludes_loopback_and_wsl_range` | 통합 | IP 조회 시 WSL 가상 IP 제외 |

**총 15개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, `socket` (내장), `os` (내장), `python-dotenv` (이미 설치됨)
- **관련 문서**:
  - `.env_sample.md` §[p1_shared] 환경 감지 설정 — `DEV_HOSTNAME`, `DEV_IP`, `SERVER_HOSTNAME`, `SERVER_IP` 변수 구조 참조
  - `p1_shared_PRD.md` §3.9 — `EnvDetector` 인터페이스 원본
- **IP 조회 방법**:
  - WSL 가상 IP(`172.x.x.x`)가 아닌 Windows 내부망 IP(`192.168.x.x`)를 얻으려면 `socket.getaddrinfo(socket.gethostname(), None)` 또는 `netifaces` 라이브러리를 사용할 수 있음
  - 단, 외부 라이브러리 추가가 부담스러울 경우 `subprocess`로 `ip addr` 결과를 파싱하는 방법도 가능. `get_local_ips()` 모듈-레벨 헬퍼 함수로 분리하여 테스트에서 mocking 가능하게 만들 것
- **주의사항**:
  - `EnvDetector.__init__()` 에서 `load_dotenv(find_dotenv())`를 호출하여 `.env` 파일 값을 환경변수로 주입해야 함
  - hostname은 WSL2에서도 Windows 호스트명을 `socket.gethostname()`으로 반환하므로 별도 처리 불필요
  - `TDMS_ENV`가 설정되어 있으면 hostname/IP 조회 자체를 건너뛰어 불필요한 시스템 콜을 방지할 것
  - 테스트 환경에서는 `get_local_ips` 함수를 monkeypatch 대상으로 두어 실제 네트워크 조회를 차단할 것

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 15개 전체 통과
- [ ] T-001에서 작성된 기존 테스트 20개 전체 통과 (회귀 없음)
- [ ] `p1_shared_pjt_tasks.md`의 T-002 상태를 `완료`로 업데이트
- [ ] `docs/p1_shared/tasks/task-002_walkthrough.md` 작성
