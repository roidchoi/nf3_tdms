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
