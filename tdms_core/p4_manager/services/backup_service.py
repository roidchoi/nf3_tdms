# tdms_core/p4_manager/services/backup_service.py
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from p1_shared.utils.env_detector import EnvDetector
from tdms_core.p4_manager.config import settings

class BackupService:
    def __init__(self):
        self.env_detector = EnvDetector()

    def get_env(self) -> str:
        """현재 실행 환경 감지 (dev, server, unknown)"""
        return self.env_detector.detect()

    def create_backup(self, tag: str = "manual") -> Dict[str, Any]:
        """
        개발 PC 로컬 DB의 물리적 스냅샷 백업(tar.gz)을 생성합니다.
        서버 환경에서는 실행을 차단(PermissionError)합니다.
        """
        env = self.get_env()
        if env == "server":
            raise PermissionError(
                "서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다. "
                "백업은 개발 PC의 수시 Pull 동기화를 이용하십시오."
            )

        # 백업 대상 검증
        data_dir = Path(settings.data_path)
        kdms_db_path = data_dir / "kdms_db"
        usdms_db_path = data_dir / "usdms_db"

        # 압축할 디렉토리가 하나라도 존재해야 진행
        if not kdms_db_path.exists() and not usdms_db_path.exists():
            raise FileNotFoundError(
                f"백업 대상 데이터 디렉토리가 존재하지 않습니다: {data_dir}"
            )

        # 백업 경로 생성
        base_dir = Path(settings.BACKUP_BASE_DIR)
        target_dir = base_dir / tag
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"physical_checkpoint_{timestamp}.tar.gz"
        backup_file_path = target_dir / filename

        # 압축 대상 폴더 목록 구성
        targets = []
        if kdms_db_path.exists():
            targets.append("kdms_db")
        if usdms_db_path.exists():
            targets.append("usdms_db")

        # tar -czf {backup_file_path} -C {settings.data_path} kdms_db usdms_db ...
        cmd = ["tar", "-czf", str(backup_file_path), "-C", str(data_dir)] + targets
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"물리 백업 압축 생성 중 오류 발생: {e.stderr}")

        if not backup_file_path.exists():
            raise RuntimeError("백업 파일이 생성되었으나 디스크 상에 존재하지 않습니다.")

        size_bytes = backup_file_path.stat().st_size

        return {
            "status": "success",
            "message": "Physical snapshot backup created successfully",
            "path": str(backup_file_path),
            "filename": filename,
            "size_bytes": size_bytes
        }

    def list_backups(self) -> List[Dict[str, Any]]:
        """보관된 물리 백업 스냅샷 목록을 조회합니다."""
        base_dir = Path(settings.BACKUP_BASE_DIR)
        if not base_dir.exists():
            return []

        backups = []
        # backups/**/*.tar.gz 검색
        for filepath in base_dir.rglob("*.tar.gz"):
            if not filepath.is_file():
                continue
            
            filename = filepath.name
            # 태그는 부모 폴더명으로 매핑 (예: backups/{tag}/filename.tar.gz)
            tag = filepath.parent.name if filepath.parent != base_dir else "default"
            
            # 파일명 형식: physical_checkpoint_YYYYMMDD_HHMMSS.tar.gz
            created_at_str = None
            if filename.startswith("physical_checkpoint_") and len(filename) >= 36:
                try:
                    ts_part = filename.replace("physical_checkpoint_", "").replace(".tar.gz", "")
                    # YYYYMMDD_HHMMSS 파싱
                    dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                    created_at_str = dt.isoformat()
                except ValueError:
                    pass

            if not created_at_str:
                # 파싱 실패 시 파일 시스템 생성 일시 사용
                created_at_str = datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()

            size_bytes = filepath.stat().st_size
            # 실물이 존재하고 파일 크기가 0보다 크면 임시 유효(verified) 처리
            verified = size_bytes > 0

            backups.append({
                "path": str(filepath),
                "filename": filename,
                "tag": tag,
                "created_at": created_at_str,
                "size_bytes": size_bytes,
                "verified": verified
            })

        # 최근 생성일시 역순 정렬
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

backup_service = BackupService()
