import os
import socket
import subprocess
from typing import Literal
from dotenv import load_dotenv, find_dotenv

def get_local_ips() -> list[str]:
    """
    현재 시스템의 내부망 IP 목록을 반환한다.
    루프백(127.x.x.x)과 WSL 가상 IP(172.x.x.x)는 제외한다.
    """
    ips = []
    try:
        # ip addr 명령 실행
        result = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                parts = line.split()
                if len(parts) > 1:
                    ip = parts[1].split('/')[0]
                    if not ip.startswith("127.") and not ip.startswith("172."):
                        ips.append(ip)
    except Exception:
        pass
    return ips

class EnvDetector:
    """
    hostname/IP 기반 실행 환경 자동 감지 및 .env 프로파일 로더.

    감지 우선순위:
      1. 환경변수 TDMS_ENV 명시적 지정 (최우선, 'dev' | 'server')
      2. hostname 매칭 (.env의 DEV_HOSTNAME, SERVER_HOSTNAME과 비교)
      3. IP 주소 매칭 (.env의 DEV_IP, SERVER_IP와 비교)
      4. 감지 실패 시 'unknown' 반환
    """

    def __init__(self):
        # .env 파일 값 환경변수로 로드
        load_dotenv(find_dotenv())

    def detect(self) -> Literal["dev", "server", "unknown"]:
        """
        현재 실행 PC의 환경을 감지하여 반환.
        """
        # 1. TDMS_ENV 우선 확인
        tdms_env = os.environ.get("TDMS_ENV", "").strip()
        if tdms_env:
            if tdms_env in ("dev", "server"):
                return tdms_env
            return "unknown"

        # 2. Hostname 매칭
        hostname = socket.gethostname().lower()
        dev_hostname = os.environ.get("DEV_HOSTNAME", "").lower()
        server_hostname = os.environ.get("SERVER_HOSTNAME", "").lower()

        if dev_hostname and hostname == dev_hostname:
            return "dev"
        if server_hostname and hostname == server_hostname:
            return "server"

        # 3. IP 주소 매칭
        local_ips = get_local_ips()
        dev_ip = os.environ.get("DEV_IP", "")
        server_ip = os.environ.get("SERVER_IP", "")

        if dev_ip and dev_ip in local_ips:
            return "dev"
        if server_ip and server_ip in local_ips:
            return "server"

        return "unknown"

    def load_env_profile(self) -> dict:
        """
        현재 환경에 맞는 설정 값 dict 반환.
        """
        env = self.detect()
        if env == "unknown":
            raise RuntimeError("unknown environment")

        dev_ip = os.environ.get("DEV_IP", "")
        server_ip = os.environ.get("SERVER_IP", "")
        dev_hostname = os.environ.get("DEV_HOSTNAME", "")
        server_hostname = os.environ.get("SERVER_HOSTNAME", "")

        if env == "dev":
            self_ip = dev_ip
            peer_ip = server_ip
            self_hostname = dev_hostname
            peer_hostname = server_hostname
        else: # server
            self_ip = server_ip
            peer_ip = dev_ip
            self_hostname = server_hostname
            peer_hostname = dev_hostname

        return {
            "env": env,
            "self_ip": self_ip,
            "peer_ip": peer_ip,
            "self_hostname": self_hostname,
            "peer_hostname": peer_hostname
        }

    def get_peer_host(self) -> str:
        """
        동기화 상대방 PC의 내부망 IP 반환.
        dev → SERVER_IP, server → DEV_IP.
        """
        env = self.detect()
        if env == "unknown":
            raise RuntimeError("unknown environment")
        
        if env == "dev":
            return os.environ.get("SERVER_IP", "")
        else:
            return os.environ.get("DEV_IP", "")

    def get_db_host(self, target: str) -> str:
        """
        특정 시장 또는 환경의 DB에 접속하기 위한 최적의 호스트 주소를 반환한다.
        - 도커 환경: kdms -> kdms_db, usdms -> usdms_db 서비스명을 직접 반환
        - 로컬 WSL2 환경: kdms/usdms에 대해 127.0.0.1 루프백 주소를 반환
        """
        # 1. 도커 컨테이너 환경 판별
        if os.path.exists('/.dockerenv'):
            if target in ("kdms", "dev"):
                return "kdms_db"
            elif target in ("usdms", "server"):
                return "usdms_db"

        # 2. 로컬 WSL2/물리 환경
        if target in ("kdms", "usdms"):
            return "127.0.0.1"

        current_env = self.detect()
        if current_env == target:
            return "127.0.0.1"
        
        return os.environ.get(f"{target.upper()}_IP", "")

    def verify_dev_ip_sync(self, logger=None) -> None:
        """
        [WSL 환경 전용] 윈도우 호스트의 실제 물리 IP와 .env의 DEV_IP가 일치하는지 검증한다.
        DHCP 변경으로 인해 IP가 틀어진 경우 경고 로그를 출력한다.
        에이전트가 이를 인지하고 .env 파일을 수정할 수 있도록 유도한다.
        """
        import platform
        import subprocess

        # WSL 환경인지 확인
        if "microsoft" not in platform.release().lower():
            return

        env = self.detect()
        if env != "dev":
            return

        dev_ip = os.environ.get("DEV_IP", "")
        if not dev_ip:
            return

        try:
            # 윈도우 호스트의 IP 목록 조회
            result = subprocess.run(
                ["powershell.exe", "-Command", "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return
            
            host_ips = [ip.strip() for ip in result.stdout.splitlines() if ip.strip()]
            
            # 127.0.0.1이나 169.254., 172. (WSL) 등 제외한 외부망 IP 추출
            external_ips = [
                ip for ip in host_ips 
                if not ip.startswith("127.") 
                and not ip.startswith("169.254.")
                and not ip.startswith("172.")
            ]

            if external_ips and dev_ip not in external_ips:
                msg = (
                    f"\n⚠️ [네트워크 경고] .env의 DEV_IP({dev_ip})가 윈도우 호스트의 실제 IP와 다릅니다.\n"
                    f"   현재 호스트 외부망 IP 목록: {external_ips}\n"
                    f"   [에이전트 참고용] DB 접속 실패 시, .env 파일의 DEV_IP를 위 목록의 IP 중 하나로 업데이트해야 합니다."
                )
                if logger:
                    logger.warning(msg)
                else:
                    print(msg)

        except Exception as e:
            if logger:
                logger.debug(f"호스트 IP 확인 실패: {e}")
