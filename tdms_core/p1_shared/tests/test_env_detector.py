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
