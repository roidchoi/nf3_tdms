# tdms_core/p4_manager/services/sync_service.py
import os
import sys
import socket
import logging
import asyncio
import subprocess
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Literal, List
from threading import Thread

import httpx
from pydantic import BaseModel, Field

from p1_shared.utils.env_detector import EnvDetector, get_local_ips
from p1_shared.ops.db_sync import PhysicalSyncManager, SyncConfig
from tdms_core.p4_manager.config import settings

# 스레드 안전한 실시간 로그 버퍼 및 상태 저장용 클래스 변수
_sync_state = {
    "status": "IDLE",
    "logs": [],
    "error_message": ""
}

# 테스트 모킹을 위한 전역 env 파일 경로 오버라이드 변수
ENV_FILE_PATH = None

class SyncLogCaptureHandler(logging.Handler):
    """db_sync 로거의 출력을 가로채 상태 딕셔너리에 추가하는 로그 핸들러"""
    def emit(self, record):
        log_entry = self.format(record)
        _sync_state["logs"].append(log_entry)

class SyncService:
    def __init__(self) -> None:
        self.env_detector = EnvDetector()

    def get_sync_status(self) -> Dict[str, Any]:
        """
        현재 진행 중인 백그라운드 동기화 상태 및 로그 버퍼 반환.
        """
        return {
            "status": _sync_state["status"],
            "logs": list(_sync_state["logs"]),
            "error_message": _sync_state["error_message"]
        }

    def run_sync_task(self, market: Literal["kdms", "usdms"], direction: Literal["pull", "push"], confirm_text: str) -> Dict[str, Any]:
        """
        물리 동기화 트리거 및 사전 검증.
        1. confirm_text 매치 검증 (PULL FROM SERVER / PUSH TO SERVER)
        2. env 감지 (server 환경에서 push 수신 쓰기 행위 차단 -> 403)
        3. 로컬 및 원격지 sudo -n true 검증 -> 실패 시 무인화 가이드 예외(412) 반환
        4. 비동기 백그라운드 스레드로 PhysicalSyncManager 구동
        """
        # 1. 컨펌 텍스트 검증
        if direction == "pull" and confirm_text != "PULL FROM SERVER":
            raise ValueError("이중 확인 텍스트가 일치하지 않습니다. 'PULL FROM SERVER'를 입력하십시오.")
        elif direction == "push" and confirm_text != "PUSH TO SERVER":
            raise ValueError("이중 확인 텍스트가 일치하지 않습니다. 'PUSH TO SERVER'를 입력하십시오.")
        elif direction not in ["pull", "push"]:
            raise ValueError("올바르지 않은 동기화 방향입니다.")

        # 2. 서버 환경 쓰기 행위 차단 (PermissionError)
        current_env = self.env_detector.detect()
        if current_env == "server" and direction == "push":
            raise PermissionError("서버 PC는 로컬 동기화 수신 쓰기 동작을 허용하지 않습니다. (403 Forbidden)")

        # 3. sudo 무인화 설정 검증
        # 로컬 sudo 검사
        local_sudo_check = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True)
        if local_sudo_check.returncode != 0:
            raise RuntimeError(
                "로컬 서버에서 비밀번호 없이 sudo 명령을 실행할 수 없습니다. "
                "아래 명령을 개발PC 터미널에 등록해 주십시오 (412 Precondition Failed):\n"
                'echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/tar, /usr/bin/rm, /usr/bin/chown, /usr/bin/docker" | sudo tee /etc/sudoers.d/tdms_sync'
            )

        # 원격지 sudo 검사
        peer_ip = self.env_detector.get_peer_host()
        profile = self.env_detector.load_env_profile()
        ssh_user = profile.get("ssh_user", "roid2")
        ssh_key = profile.get("ssh_key_path", "~/.ssh/tdms_sync_rsa")

        # SSH key 경로 정규화 (예: ~ 처리)
        ssh_key_expanded = os.path.expanduser(ssh_key)

        ssh_cmd = [
            "ssh", "-i", ssh_key_expanded, "-o", "StrictHostKeyChecking=no",
            f"{ssh_user}@{peer_ip}", "sudo -n true"
        ]
        remote_sudo_check = subprocess.run(ssh_cmd, capture_output=True, text=True)
        if remote_sudo_check.returncode != 0:
            raise RuntimeError(
                f"원격지({peer_ip})에서 비밀번호 없이 sudo 명령을 실행할 수 없습니다. "
                "아래 명령을 원격 서버 터미널에 등록해 주십시오 (412 Precondition Failed):\n"
                'echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/tar, /usr/bin/rm, /usr/bin/chown, /usr/bin/docker" | sudo tee /etc/sudoers.d/tdms_sync'
            )

        # 4. 백그라운드 태스크 기동
        if _sync_state["status"] == "RUNNING":
            raise RuntimeError("이미 동기화 태스크가 실행 중입니다.")

        # 상태 초기화
        _sync_state["status"] = "RUNNING"
        _sync_state["logs"] = []
        _sync_state["error_message"] = ""

        # 백그라운드 스레드 생성 및 실행
        thread = Thread(target=self._execute_sync_in_background, args=(market, direction, peer_ip, ssh_user, ssh_key_expanded))
        thread.daemon = True
        thread.start()

        return {
            "status": "success",
            "message": f"{market.upper()} physical sync task started in background"
        }

    def _execute_sync_in_background(self, market: str, direction: str, peer_ip: str, ssh_user: str, ssh_key: str):
        """백그라운드 스레드에서 PhysicalSyncManager 구동"""
        # 로그 캡처 핸들러 등록
        logger = logging.getLogger("db_sync")
        handler = SyncLogCaptureHandler()
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        try:
            logger.info(f"동기화 기동 준비: market={market}, direction={direction}, peer_ip={peer_ip}")
            
            source_ip = peer_ip if direction == "pull" else "127.0.0.1"
            target_ip = "127.0.0.1" if direction == "pull" else peer_ip

            config = SyncConfig(
                db_name=market,
                direction=direction,
                source_ip=source_ip,
                target_ip=target_ip,
                ssh_user=ssh_user,
                ssh_key_path=ssh_key,
                data_path=settings.data_path
            )

            manager = PhysicalSyncManager(config)
            
            # 파이프라인 수행
            if not manager.preflight_check():
                raise RuntimeError("Preflight 점검에 실패하였습니다. SSH 연결 또는 원격지 경로를 확인하세요.")
            
            manager.stop_containers()
            
            if not manager.transfer_data():
                raise RuntimeError("물리 데이터 전송 파이프라인 가동에 실패하였습니다.")
                
            manager.fix_permissions()
            manager.start_containers()

            logger.info("동기화 전체 파이프라인이 성공적으로 완료되었습니다.")
            _sync_state["status"] = "SUCCESS"

        except Exception as e:
            logger.error(f"동기화 중 에러 발생: {str(e)}")
            _sync_state["status"] = "ERROR"
            _sync_state["error_message"] = str(e)
        finally:
            # 핸들러 해제
            logger.removeHandler(handler)

    def get_audit_report(self, market: Literal["kdms", "usdms"]) -> Dict[str, Any]:
        """
        동기화 완료 후 audit_deep 또는 audit_usdms 스크립트를 비동기로 기동하여 데이터를 JSON으로 정규화 파싱.
        """
        # conda 가상환경에서 실행
        script = "audit_usdms" if market == "usdms" else "audit_deep"
        cmd = ["conda", "run", "-n", "tdms_p1_env", "python", "-m", f"p1_shared.ops.auditors.{script}"]
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode != 0:
                return {"status": "error", "message": f"Audit execution failed: {res.stderr}"}
            
            # 정밀 감사 도구는 표준 출력에 마크다운이나 요약 정보를 인쇄하므로 
            # 이를 간단하게 구조화된 딕셔너리로 추출하거나 텍스트 통째로 반환합니다.
            return {
                "status": "success",
                "market": market,
                "audit_type": script,
                "raw_output": res.stdout
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def detect_server_ip(self) -> Dict[str, Any]:
        """
        개발 PC 단에서 서버 IP 불일치 시 서버 IP 추적.
        1. SERVER_HOSTNAME 로드 후 powershell.exe 호출 우회 DNS 리졸브 시도
        2. 실패 시, 개발 PC IP 대역 (C클래스 .1 ~ .254) 비동기 포트 스캔 (Port 8000/80)
        3. /api/mgr/env API를 던져 {"env": "server"}를 응답하는 IP 색출
        """
        server_hostname = os.environ.get("SERVER_HOSTNAME", "").strip()
        
        # 1. DNS 리졸브 시도 (Powershell 우회)
        if server_hostname:
            try:
                cmd = ["powershell.exe", "-Command", f"[System.Net.Dns]::GetHostAddresses('{server_hostname}') | Select-Object -ExpandProperty IPAddressToString"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    resolved_ips = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                    for ip in resolved_ips:
                        # 통신 테스트를 거쳐 유효성 검증
                        test_res = self.test_connection(ip, port=8000)
                        if test_res["connected"]:
                            return {"server_ip": ip, "method": "dns"}
            except Exception:
                pass  # 리졸브 및 통신 검사 실패 시 스캔으로 폴백

        # 2. 비동기 사설 C클래스 포트 스캔
        try:
            local_ips = get_local_ips()
            if not local_ips:
                # 로컬 IP를 획득할 수 없을 시 default 대역 스캔
                local_ips = ["192.168.35.1"]
            
            base_ip = local_ips[0]
            # 192.168.35.x 구조로 분할
            ip_parts = base_ip.split(".")
            if len(ip_parts) == 4:
                subnet_prefix = ".".join(ip_parts[:3])
                
                # asyncio 루프 구동
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    server_ip = loop.run_until_complete(self._async_scan_subnet(subnet_prefix))
                    if server_ip:
                        return {"server_ip": server_ip, "method": "scan"}
                finally:
                    loop.close()
        except Exception:
            pass

        return {"server_ip": None, "method": "failed"}

    async def _async_scan_subnet(self, subnet_prefix: str) -> str:
        """비동기 병렬 포트 스캔으로 서버 PC 탐색"""
        tasks = []
        for i in range(1, 255):
            ip = f"{subnet_prefix}.{i}"
            tasks.append(self._check_single_ip_is_server(ip))
        
        results = await asyncio.gather(*tasks)
        for ip in results:
            if ip:
                return ip
        return None

    async def _check_single_ip_is_server(self, ip: str) -> str:
        """특정 IP의 8000 포트 연결 및 /api/mgr/env 검증 수행"""
        try:
            # 1. TCP 커넥션 테스트 (타임아웃 200ms)
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 8000),
                timeout=0.2
            )
            writer.close()
            await writer.wait_closed()
            
            # 2. HTTP GET /api/mgr/env 호출
            async with httpx.AsyncClient(timeout=0.5) as client:
                resp = await client.get(f"http://{ip}:8000/api/mgr/env")
                if resp.status_code == 200 and resp.json().get("env") == "server":
                    return ip
        except Exception:
            pass
        return None

    def sync_ip_in_env(self, target: Literal["dev", "server"], new_ip: str) -> Dict[str, Any]:
        """
        .env 파일을 정규표현식으로 로드하여 DEV_IP 또는 SERVER_IP 값을 new_ip로 갱신 적용.
        """
        global ENV_FILE_PATH
        env_file_path = ENV_FILE_PATH
        if not env_file_path:
            env_file_path = getattr(settings, "env_file_path", None)
        if not env_file_path:
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            env_file_path = str(root_dir / ".env")

        env_path = Path(env_file_path)
        if not env_path.exists():
            # 테스트 상 임시 파일 자동 생성
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.touch()

        content = env_path.read_text(encoding="utf-8")
        var_name = "DEV_IP" if target == "dev" else "SERVER_IP"
        pattern = re.compile(rf"^({var_name}\s*=\s*)(.*)$", re.MULTILINE)
        
        if pattern.search(content):
            new_content = pattern.sub(rf"\g<1>{new_ip}", content)
        else:
            new_content = content + f"\n{var_name}={new_ip}\n"
            
        env_path.write_text(new_content, encoding="utf-8")
        
        # 시스템 메모리 캐시 갱신 및 env detector 재조정
        os.environ[var_name] = new_ip
        self.env_detector = EnvDetector()

        return {
            "status": "success",
            "message": f"Successfully updated {var_name} to {new_ip} in .env file"
        }

    def test_connection(self, ip: str, port: int) -> Dict[str, Any]:
        """
        수동 입력된 IP 및 포트에 대해 TCP 소켓 검사 및 SSH 가용 테스트 수행.
        """
        # IP 형식 사전 검증
        try:
            socket.inet_aton(ip)
        except socket.error:
            return {"connected": False, "message": "Invalid IP format"}

        try:
            with socket.create_connection((ip, port), timeout=1.0):
                pass
            return {"connected": True, "message": "Connection Success"}
        except Exception as e:
            return {"connected": False, "message": f"Socket connection failed: {str(e)}"}
