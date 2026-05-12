import argparse
import subprocess
import os
import sys
from dataclasses import dataclass
from typing import Literal
from dotenv import load_dotenv

from p1_shared.utils.env_detector import EnvDetector
from p1_shared.ops.logger import get_logger

logger = get_logger("db_sync")

@dataclass
class SyncConfig:
    db_name: Literal["kdms", "usdms"]
    direction: Literal["pull", "push"]
    source_ip: str
    target_ip: str
    ssh_user: str
    ssh_key_path: str
    data_path: str

class PhysicalSyncManager:
    def __init__(self, config: SyncConfig):
        self.config = config

    def _run_local(self, cmd: str) -> subprocess.CompletedProcess:
        """로컬 셸 명령어 실행"""
        logger.debug(f"Local exec: {cmd}")
        return subprocess.run(cmd, shell=True, capture_output=True, text=True)

    def _run_remote(self, host: str, cmd: str) -> subprocess.CompletedProcess:
        """원격 SSH 명령어 실행"""
        ssh_cmd = (
            f"ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no "
            f"{self.config.ssh_user}@{host} \"{cmd}\""
        )
        logger.debug(f"Remote exec ({host}): {cmd}")
        return subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)

    def preflight_check(self) -> bool:
        logger.info("1. Preflight 점검 중...")
        # SSH 접속 테스트 (대상 또는 소스가 원격인 경우)
        remote_host = self.config.target_ip if self.config.direction == "push" else self.config.source_ip
        res = self._run_remote(remote_host, "echo SSH_OK")
        if "SSH_OK" not in res.stdout:
            logger.error(f"SSH 접속 실패: {res.stderr}")
            return False
        logger.info("   - SSH 접속 정상")
        return True

    def stop_containers(self) -> None:
        logger.info("2. 컨테이너 중지 (Maintenance Mode)")
        svc_name = f"{self.config.db_name}_db"
        cmd = f"cd /home/{self.config.ssh_user}/pjt/nf3/01_nf3_tdms && docker compose stop {svc_name}"
        
        # 로컬 중지
        logger.info("   - 로컬 DB 중지 중...")
        self._run_local(cmd)
        
        # 원격 중지
        remote_host = self.config.target_ip if self.config.direction == "push" else self.config.source_ip
        logger.info(f"   - 원격({remote_host}) DB 중지 중...")
        self._run_remote(remote_host, cmd)

    def start_containers(self) -> None:
        logger.info("5. 컨테이너 재기동")
        svc_name = f"{self.config.db_name}_db"
        cmd = f"cd /home/{self.config.ssh_user}/pjt/nf3/01_nf3_tdms && docker compose start {svc_name}"
        
        logger.info("   - 로컬 DB 기동 중...")
        self._run_local(cmd)
        
        remote_host = self.config.target_ip if self.config.direction == "push" else self.config.source_ip
        logger.info(f"   - 원격({remote_host}) DB 기동 중...")
        self._run_remote(remote_host, cmd)

    def transfer_data(self) -> bool:
        logger.info("3. 물리 데이터 전송 시작 (tar + SSH Pipeline)")
        
        db_path = f"{self.config.data_path}/{self.config.db_name}_db"
        
        if self.config.direction == "pull":
            # 서버 -> 로컬
            logger.info("   - 서버 데이터를 로컬로 가져옵니다 (Pull)...")
            cmd = (
                f"ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no "
                f"{self.config.ssh_user}@{self.config.source_ip} "
                f"\"sudo tar -czf - -C {db_path} .\" | sudo tar -xzf - -C {db_path}"
            )
        else:
            # 로컬 -> 서버
            logger.info("   - 로컬 데이터를 서버로 밀어넣습니다 (Push)...")
            cmd = (
                f"sudo tar -czf - -C {db_path} . | "
                f"ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no "
                f"{self.config.ssh_user}@{self.config.target_ip} "
                f"\"sudo tar -xzf - -C {db_path}\""
            )

        logger.debug(f"Transfer cmd: {cmd}")
        res = self._run_local(cmd)
        if res.returncode != 0:
            logger.error(f"데이터 전송 실패: {res.stderr}")
            return False
            
        logger.info("   - 전송 완료")
        return True

    def fix_permissions(self) -> None:
        logger.info("4. 수신 측 폴더 권한 교정")
        db_path = f"{self.config.data_path}/{self.config.db_name}_db"
        
        if self.config.direction == "pull":
            # 로컬 수신이므로 로컬 권한 교정
            cmd = f"sudo chown -R 1000:1000 {db_path}"
            self._run_local(cmd)
        else:
            # 서버 수신이므로 원격 권한 교정
            cmd = f"sudo chown -R 1000:1000 {db_path}"
            self._run_remote(self.config.target_ip, cmd)

    def execute(self) -> bool:
        if not self.preflight_check():
            return False
            
        try:
            self.stop_containers()
            if not self.transfer_data():
                return False
            self.fix_permissions()
        finally:
            self.start_containers()
            
        logger.info(f"✅ [{self.config.db_name}] 물리적 동기화 완료!")
        return True


def main():
    parser = argparse.ArgumentParser(description="물리적 DB 동기화 파이프라인")
    parser.add_argument("--db", required=True, choices=["kdms", "usdms"], help="대상 DB 이름")
    parser.add_argument("--direction", required=True, choices=["pull", "push"], help="동기화 방향 (pull: 서버->로컬, push: 로컬->서버)")
    parser.add_argument("--yes", action="store_true", help="사용자 확인 생략")
    args = parser.parse_args()

    load_dotenv()
    
    if not args.yes:
        ans = input(f"⚠️ [경고] {args.db} DB를 {args.direction} 방향으로 덮어씁니다. 계속하시겠습니까? (yes 입력): ")
        if ans.lower() != "yes":
            print("작업을 취소합니다.")
            sys.exit(0)

    env = EnvDetector()
    is_dev = env.detect() == "dev"
    peer_ip = env.get_peer_host()
    
    local_ip = os.getenv("DEV_IP") if is_dev else os.getenv("SERVER_IP")
    
    source_ip = peer_ip if args.direction == "pull" else local_ip
    target_ip = local_ip if args.direction == "pull" else peer_ip

    config = SyncConfig(
        db_name=args.db,
        direction=args.direction,
        source_ip=source_ip,
        target_ip=target_ip,
        ssh_user=os.getenv("SSH_USER", "roid2"),
        ssh_key_path=os.getenv("SSH_KEY_PATH", "~/.ssh/tdms_sync_rsa"),
        data_path=f"/home/{os.getenv('SSH_USER', 'roid2')}/pjt/nf3/01_nf3_tdms/data"
    )

    manager = PhysicalSyncManager(config)
    success = manager.execute()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
