# tdms_core/p4_manager/services/backup_service.py
import os
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from p1_shared.utils.env_detector import EnvDetector
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops.startup_validator import StartupValidator
from tdms_core.p4_manager.config import settings

logger = logging.getLogger("p4_manager.backup_service")

# 무결성 검증을 위한 상수 정의
KDMS_EXPECTED_TABLES = [
    "daily_ohlcv", "stock_info", "price_adjustment_factors",
    "financial_statements", "financial_ratios", "daily_market_cap",
    "system_milestones", "minute_target_history",
]
KDMS_MIN_ROW_COUNTS = {"daily_ohlcv": 1_000_000}

USDMS_EXPECTED_TABLES = [
    "us_ticker_master", "us_daily_price", "us_daily_valuation", "us_financial_facts",
    "us_financial_metrics", "us_price_adjustment_factors", "us_share_history",
    "us_standard_financials", "us_ticker_history", "us_collection_blacklist"
]
USDMS_MIN_ROW_COUNTS = {
    "us_daily_price": 100_000
}

class BackupService:
    def __init__(self):
        self.env_detector = EnvDetector()

    def get_env(self) -> str:
        """현재 실행 환경 감지 (dev, server, unknown)"""
        return self.env_detector.detect()

    def create_backup(self, market: str, tag: str = "manual") -> Dict[str, Any]:
        """
        개발 PC 로컬 DB의 물리적 스냅샷 백업(tar.gz)을 생성합니다. (시장별 격리)
        서버 환경에서는 실행을 차단(PermissionError)합니다.
        """
        if market not in ["kdms", "usdms"]:
            raise ValueError("market은 'kdms' 또는 'usdms' 여야 합니다.")

        env = self.get_env()
        if env == "server":
            raise PermissionError(
                "서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다. "
                "백업은 개발 PC의 수시 Pull 동기화를 이용하십시오."
            )

        # 백업 대상 검증
        data_dir = Path(settings.data_path)
        db_path = data_dir / f"{market}_db"

        if not db_path.exists():
            raise FileNotFoundError(
                f"백업 대상 데이터 디렉토리가 존재하지 않습니다: {db_path}"
            )

        # 백업 경로 생성 (backups/{market}/{tag}/)
        base_dir = Path(settings.BACKUP_BASE_DIR)
        target_dir = base_dir / market / tag
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"physical_checkpoint_{market}_{timestamp}.tar.gz"
        backup_file_path = target_dir / filename

        # sudo 권한 자동 판단 래퍼 기법 적용
        import shutil
        has_sudo = shutil.which("sudo") is not None
        is_root = os.geteuid() == 0

        cmd = []
        if has_sudo and not is_root:
            cmd.append("sudo")
        
        # tar -czf {backup_file_path} -C {settings.data_path} {market}_db
        cmd += ["tar", "-czf", str(backup_file_path), "-C", str(data_dir), f"{market}_db"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"물리 백업 압축 생성 중 오류 발생: {e.stderr}")

        if not backup_file_path.exists():
            raise RuntimeError("백업 파일이 생성되었으나 디스크 상에 존재하지 않습니다.")

        size_bytes = backup_file_path.stat().st_size

        return {
            "status": "success",
            "message": f"{market.upper()} physical snapshot backup created successfully",
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
            
            # backups/{market}/{tag}/filename.tar.gz 파싱
            parent = filepath.parent
            grandparent = parent.parent
            
            tag = parent.name if parent != base_dir else "default"
            market = grandparent.name if grandparent != base_dir else "unknown"
            
            # 파일명 형식: physical_checkpoint_{market}_YYYYMMDD_HHMMSS.tar.gz
            created_at_str = None
            prefix = f"physical_checkpoint_{market}_"
            if filename.startswith(prefix) and filename.endswith(".tar.gz"):
                try:
                    ts_part = filename.replace(prefix, "").replace(".tar.gz", "")
                    # YYYYMMDD_HHMMSS 파싱
                    dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                    created_at_str = dt.isoformat()
                except ValueError:
                    pass

            if not created_at_str:
                # 하위 호환성 또는 파싱 실패 시 mtime 사용
                created_at_str = datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()

            size_bytes = filepath.stat().st_size
            verified = size_bytes > 0

            backups.append({
                "path": str(filepath),
                "filename": filename,
                "market": market,
                "tag": tag,
                "created_at": created_at_str,
                "size_bytes": size_bytes,
                "verified": verified
            })

        # 최근 생성일시 역순 정렬
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def restore_backup(self, market: str, tag: str, filename: str, confirm_text: str) -> Dict[str, Any]:
        """
        개발 PC 로컬 DB를 시장별 스냅샷 백업 아카이브로부터 복구합니다.
        """
        if market not in ["kdms", "usdms"]:
            raise ValueError("market은 'kdms' 또는 'usdms' 여야 합니다.")

        env = self.get_env()
        if env == "server":
            raise PermissionError(
                "서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다. "
                "백업은 개발 PC의 수시 Pull 동기화를 이용하십시오."
            )

        if confirm_text != "RESTORE LOCAL DB":
            raise ValueError("이중 확인 텍스트가 일치하지 않습니다. ('RESTORE LOCAL DB'를 정확히 입력해야 합니다.)")

        # backups/{market}/{tag}/{filename}
        backup_file_path = Path(settings.BACKUP_BASE_DIR) / market / tag / filename
        if not backup_file_path.exists():
            raise FileNotFoundError(f"백업 아카이브 파일을 찾을 수 없습니다: {backup_file_path}")

        # 1. Maintenance Mode: 시장별 관련 컨테이너만 정지
        if market == "kdms":
            containers_to_stop = ["p2_kdms", "kdms_backend", "kdms_timescaledb"]
        else:
            containers_to_stop = ["p3_usdms", "usdms_backend", "usdms_timescaledb"]

        for container in containers_to_stop:
            try:
                subprocess.run(["docker", "stop", container], capture_output=True, text=True, check=False)
            except Exception as e:
                logger.warning(f"컨테이너 {container} 중지 시도 중 오류 발생(무시됨): {e}")

        # 2. 압축 해제 및 복원
        data_dir = Path(settings.data_path)
        
        # sudo 권한 자동 판단 래퍼 기법 적용
        import shutil
        has_sudo = shutil.which("sudo") is not None
        is_root = os.geteuid() == 0

        cmd = []
        if has_sudo and not is_root:
            cmd.append("sudo")
        cmd += ["tar", "-xzf", str(backup_file_path), "-C", str(data_dir)]

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"물리 백업 압축 해제 중 오류 발생: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"복구 데이터 복원 중 예외 발생: {e}")

        # 3. 소유권 교정 (root 소유물 방지) - 단독 시장 데이터 디렉토리만 수행
        db_path = data_dir / f"{market}_db"
        if db_path.exists():
            try:
                cmd_chown = []
                if has_sudo and not is_root:
                    cmd_chown.append("sudo")
                cmd_chown += ["chown", "-R", "1000:1000", str(db_path)]
                subprocess.run(cmd_chown, capture_output=True, text=True, check=False)
            except Exception as e:
                logger.warning(f"{market}_db 권한 교정 중 오류 발생(무시됨): {e}")

        # 4. 컨테이너 재기동 (대상 시장 DB만 기동)
        db_container = f"{market}_timescaledb"
        try:
            subprocess.run(["docker", "start", db_container], capture_output=True, text=True, check=True)
        except Exception as e:
            raise RuntimeError(f"컨테이너 {db_container} 기동 실패: {e}")

        # 5. DB 연결 상태 대기 및 무결성 진단 (최대 30초) - 해당 시장만 대상
        profile = self.env_detector.load_env_profile()
        
        db_user = profile.get("db_user") or os.environ.get(f"{env.upper()}_{market.upper()}_DB_USER", "postgres" if market == "usdms" else "roid")
        db_password = profile.get("db_password") or os.environ.get(f"{env.upper()}_{market.upper()}_DB_PASSWORD", "")
        db_host = self.env_detector.get_db_host(market)
        db_port = profile.get("db_port") or os.environ.get(f"{env.upper()}_{market.upper()}_DB_PORT", 5433 if market == "usdms" else 5432)
        db_name_val = profile.get("db_name") or os.environ.get(f"{env.upper()}_{market.upper()}_DB_NAME", f"{market}_db")
        dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name_val}"

        # 대기 루프
        start_time = time.time()
        db_ok = False
        
        while time.time() - start_time < 30:
            try:
                pool = DbConnectionPool(dsn=dsn)
                with pool.get_cursor() as cur:
                    cur.execute("SELECT 1")
                    db_ok = True
                pool.close_all()
            except Exception:
                pass
            
            if db_ok:
                break
            time.sleep(2)

        if not db_ok:
            logger.warning(f"{market.upper()} DB 기동 완료 대기 시간 초과(DB가 아직 접속 불가능합니다).")

        # 6. StartupValidator를 이용한 최종 자가 진단 - 해당 시장만 검증
        validation_results = {}
        pool = DbConnectionPool(dsn=dsn)
        try:
            validator = StartupValidator(pool, backup_manager=None)
            expected_tables = KDMS_EXPECTED_TABLES if market == "kdms" else USDMS_EXPECTED_TABLES
            min_row_counts = KDMS_MIN_ROW_COUNTS if market == "kdms" else USDMS_MIN_ROW_COUNTS
            
            report = validator.validate(
                db_name=market,
                expected_tables=expected_tables,
                min_row_counts=min_row_counts
            )
            validation_results[market] = {
                "is_healthy": report.is_healthy,
                "is_connected": report.is_connected,
                "missing_tables": report.missing_tables,
                "low_row_tables": {k: {"actual": v[0], "expected": v[1]} for k, v in report.low_row_tables.items()},
                "hypertable_ok": report.hypertable_ok
            }
        finally:
            pool.close_all()

        # 백엔드 컨테이너들 재기동 (해당 시장 계열만)
        if market == "kdms":
            backends_to_start = ["p2_kdms", "kdms_backend"]
        else:
            backends_to_start = ["p3_usdms", "usdms_backend"]
            
        for container in backends_to_start:
            if container in containers_to_stop:
                try:
                    subprocess.run(["docker", "start", container], capture_output=True, text=True, check=False)
                except Exception as e:
                    logger.warning(f"백엔드 {container} 기동 실패(무시됨): {e}")

        return {
            "status": "success",
            "message": f"{market.upper()} physical restore and validation completed successfully",
            "validation_results": validation_results
        }

backup_service = BackupService()
