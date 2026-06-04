# Interface: EnvDetector

> **파일**: `tdms_core/p1_shared/p1_shared/utils/env_detector.py`
> **Task**: T-002
> **Graphify God Node**: 97 edges (1위 — 전체 그래프의 최고 허브)
> **관련**: `[[p1_shared_wiki/interfaces/db_connection_pool.md]]`, `[[p1_shared_wiki/interfaces/physical_sync_manager.md]]`

---

## 클래스/함수 시그니처

```python
def get_local_ips() -> list[str]:
    """
    현재 시스템의 내부망 IP 목록을 반환한다.
    루프백(127.x.x.x)과 WSL 가상 IP(172.x.x.x)는 제외한다.
    """

class EnvDetector:
    """
    hostname/IP 기반 실행 환경 자동 감지 및 .env 프로파일 로더.

    감지 우선순위:
      1. 환경변수 TDMS_ENV 명시적 지정 (최우선, 'dev' | 'server')
      2. hostname 매칭 (.env의 DEV_HOSTNAME, SERVER_HOSTNAME과 비교)
      3. IP 주소 매칭 (.env의 DEV_IP, SERVER_IP와 비교)
      4. 감지 실패 시 'unknown' 반환
    """

    def __init__(self) -> None:
        """__init__에서 load_dotenv(find_dotenv()) 호출"""

    def detect(self) -> Literal["dev", "server", "unknown"]:
        """현재 실행 PC의 환경을 감지하여 반환"""

    def load_env_profile(self) -> dict:
        """현재 환경에 맞는 설정 값 dict 반환"""

    def get_db_host(self, db_name: Literal["kdms", "usdms"]) -> str:
        """
        특정 환경의 DB에 접속하기 위한 최적의 호스트 주소를 반환한다.
        자기 자신에게 접속하는 경우(WSL -> Host) 127.0.0.1 반환
        """

    def get_peer_host(self) -> str:
        """
        동기화 상대방 PC의 내부망 IP 반환.
        dev → SERVER_IP, server → DEV_IP
        """

    def verify_dev_ip_sync(self) -> bool:
        """
        [WSL 환경 전용] 윈도우 호스트의 실제 물리 IP와 .env의 DEV_IP가
        일치하는지 검증한다. DHCP 변경으로 인해 IP가 바뀌었을 때 감지용.
        """
```

---

## 사용 패턴

```python
from p1_shared.utils.env_detector import EnvDetector

detector = EnvDetector()
env = detector.detect()  # "dev" | "server" | "unknown"

# DB 접속 호스트 자동 결정
host = detector.get_db_host("kdms")

# 동기화 대상 IP 자동 결정
peer = detector.get_peer_host()

# WSL2 IP 변경 감지
if not detector.verify_dev_ip_sync():
    print("⚠️ DEV_IP가 .env와 불일치. 수동 수정 필요.")
```

---

## 감지 로직 (코드 레벨)

```python
# 1. TDMS_ENV 환경변수 우선 확인
tdms_env = os.environ.get("TDMS_ENV", "").strip()
if tdms_env in ("dev", "server"):
    return tdms_env

# 2. Hostname 매칭
hostname = socket.gethostname().lower()
if hostname == dev_hostname: return "dev"
if hostname == server_hostname: return "server"

# 3. IP 주소 매칭 (get_local_ips() 사용)
local_ips = get_local_ips()
if dev_ip in local_ips: return "dev"
if server_ip in local_ips: return "server"

return "unknown"
```

---

## 주의사항

- **WSL2 IP 불안정**: DHCP 재할당으로 DEV_IP가 바뀔 수 있음 → `verify_dev_ip_sync()` 주기적 호출 권장
- **루프백 vs 내부망**: WSL → Host DB 접속 시 `127.0.0.1` 반환, WSL → 원격 서버 접속 시 실제 IP 반환
- **`ip addr` 의존**: `get_local_ips()`는 Linux `ip` 명령에 의존. WSL2 환경에서만 테스트됨
