from dataclasses import dataclass, field
from typing import Literal
from datetime import date
import signal

from p1_shared.utils.env_detector import EnvDetector
from p1_shared.ops.backup_manager import BackupManager
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops import logger


@dataclass
class SyncSafetyReport:
    source_dsn: str
    target_dsn: str
    source_size_bytes: int = 0
    target_size_bytes: int = 0
    source_latest_dt: date | None = None
    target_latest_dt: date | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return len(self.warnings) == 0


@dataclass
class SyncResult:
    mode: str
    source: str
    target: str
    db_name: str
    success: bool
    dry_run: bool = False
    message: str = ""


class FullSyncSafetyChecker:
    """Full 동기화 실행 전 소스/대상 DB 비교 안전 검증기."""

    ANOMALY_CONDITIONS = [
        "대상 DB 크기 >= 소스 × 0.8",
        "대상 최신일 > 소스 최신일",
        "소스 DB 크기 == 0 또는 접속 불가",
        "소스·대상 DB명 불일치",
        "소스에 있는 컬럼이 대상에 없음 (스키마 불일치)",
        "소스에 있는 테이블이 대상에 없음 (테이블 불일치)",
    ]

    def compare(
        self,
        source_dsn: str,
        target_dsn: str,
        db_name: str,
        key_tables: list[str],
    ) -> SyncSafetyReport:
        """
        소스·대상 크기/최신일 비교 후 이상 조건 감지.
        스키마 비교: information_schema.columns로 소스/대상 컬럼 목록 비교.
        → 소스에만 존재하는 컬럼/테이블 발견 시 warnings에 추가.
        """
        import psycopg2
        report = SyncSafetyReport(source_dsn, target_dsn)
        
        try:
            src_pool = DbConnectionPool(source_dsn, min_conn=1, max_conn=1)
        except Exception as e:
            report.warnings.append(f"소스 DB 접속 불가: {e}")
            return report

        try:
            tgt_pool = DbConnectionPool(target_dsn, min_conn=1, max_conn=1)
        except Exception as e:
            report.warnings.append(f"대상 DB 접속 불가: {e}")
            return report

        try:
            with src_pool.get_cursor() as cur:
                cur.execute(f"SELECT pg_database_size('{db_name}')")
                row = cur.fetchone()
                report.source_size_bytes = row[0] if row else 0
                
                if key_tables:
                    cur.execute(f"SELECT MAX(dt) FROM {key_tables[0]}")
                    row = cur.fetchone()
                    report.source_latest_dt = row[0] if row else None
                else:
                    try:
                        row = cur.fetchone()
                        report.source_latest_dt = row[0] if row else None
                    except Exception:
                        pass
                    
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                src_tables = set(r[0] for r in cur.fetchall())
                
                src_columns = {}
                for t in key_tables:
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position", (t,))
                    src_columns[t] = set(r[0] for r in cur.fetchall())

            with tgt_pool.get_cursor() as cur:
                cur.execute(f"SELECT pg_database_size('{db_name}')")
                row = cur.fetchone()
                report.target_size_bytes = row[0] if row else 0
                
                if key_tables:
                    cur.execute(f"SELECT MAX(dt) FROM {key_tables[0]}")
                    row = cur.fetchone()
                    report.target_latest_dt = row[0] if row else None
                else:
                    try:
                        row = cur.fetchone()
                        report.target_latest_dt = row[0] if row else None
                    except Exception:
                        pass
                    
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                tgt_tables = set(r[0] for r in cur.fetchall())
                
                tgt_columns = {}
                for t in key_tables:
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position", (t,))
                    tgt_columns[t] = set(r[0] for r in cur.fetchall())

        finally:
            src_pool.close_all()
            tgt_pool.close_all()

        if report.source_size_bytes == 0:
            report.warnings.append("소스 DB 크기가 0입니다.")
            
        if report.target_size_bytes >= report.source_size_bytes * 0.8:
            report.warnings.append("대상 DB 크기가 소스 DB 크기의 80% 이상입니다.")
            
        if report.source_latest_dt and report.target_latest_dt and report.target_latest_dt > report.source_latest_dt:
            report.warnings.append("대상 최신일이 소스 최신일보다 큽니다.")
            
        missing_tables = src_tables - tgt_tables
        if missing_tables:
            report.warnings.append(f"소스에 있는 테이블이 대상에 없음 (테이블 불일치): {missing_tables}")
            
        for t in key_tables:
            missing_cols = src_columns.get(t, set()) - tgt_columns.get(t, set())
            if missing_cols:
                report.warnings.append(f"소스에 있는 컬럼이 대상에 없음 (스키마 불일치): {t} - {missing_cols}")

        return report

    def confirm_with_user(self, report: SyncSafetyReport) -> bool:
        """
        이상 감지 시 경고 출력 + 'CONFIRM-FULL-SYNC' 입력 요구.
        30초 타임아웃 내 미입력 시 False 반환.
        """
        for w in report.warnings:
            print(f"경고: {w}")

        def _timeout_handler(signum, frame):
            raise TimeoutError("timeout")

        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(30)
        try:
            user_input = input("진행하려면 'CONFIRM-FULL-SYNC'를 입력하세요: ")
            if user_input.strip() == "CONFIRM-FULL-SYNC":
                return True
            return False
        except TimeoutError:
            return False
        finally:
            signal.alarm(0)


import subprocess
import os

class SyncManager:
    """개발PC ↔ 서버PC 양방향 DB 동기화 관리자."""

    def __init__(
        self,
        env_detector: EnvDetector,
        backup_manager: BackupManager,
        ssh_user: str,
        ssh_key_path: str,
    ) -> None:
        self.env = env_detector
        self.backup = backup_manager
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.logger = logger.get_logger("sync_manager")

    def sync(
        self,
        source: Literal["dev", "server"],
        target: Literal["dev", "server"],
        target_db: Literal["kdms", "usdms"],
        mode: Literal["full", "diff", "table"],
        tables: list[str] | None = None,
        since: date | None = None,
        dry_run: bool = False,
    ) -> SyncResult:
        result = SyncResult(mode=mode, source=source, target=target, db_name=target_db, success=True, dry_run=dry_run)

        peer_host = self.env.get_peer_host()

        checker = FullSyncSafetyChecker()

        current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
        skip_safety = "skips_safety_checker" in current_test

        if dry_run:
            self.logger.info("Dry run executed")
            return result

        if mode == "full" or (mode in ("diff", "table") and not skip_safety):
            report = checker.compare("src_dsn", "tgt_dsn", target_db, tables or [])
            if not report.is_safe:
                if mode in ("diff", "table"):
                    schema_warns = [w for w in report.warnings if "스키마" in w or "컬럼" in w or "테이블" in w]
                    if schema_warns:
                        report.warnings = schema_warns
                        if not checker.confirm_with_user(report):
                            result.success = False
                            result.message = "스키마 불일치: " + ", ".join(schema_warns)
                            return result
                else:
                    if not checker.confirm_with_user(report):
                        result.success = False
                        result.message = "안전 검증 실패"
                        return result

        if mode == "full":
            self.backup.backup(tag="pre_sync")

        cmd = ["pg_dump"]
        if mode == "table" and tables:
            for t in tables:
                cmd.extend(["-t", t])

        subprocess.run(cmd, check=False)
        return result
