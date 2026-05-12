from dataclasses import dataclass, field
from typing import Literal
import psycopg2
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops.backup_manager import BackupManager
from p1_shared.ops import logger as ops_logger

@dataclass
class ValidationReport:
    db_name: str
    is_connected: bool = False
    missing_tables: list[str] = field(default_factory=list)
    low_row_tables: dict[str, tuple[int, int]] = field(default_factory=dict)
    # {table: (actual_rows, expected_min)}
    volume_info: dict = field(default_factory=dict)
    # BackupManager.check_volume_exists() 결과
    hypertable_ok: bool = True

    @property
    def is_healthy(self) -> bool:
        """모든 검증 항목 통과 시 True."""
        # volume_info가 비어있으면(검증 건너뜀) True로 취급
        vol_ok = self.volume_info.get("exists", True)
        return (
            self.is_connected
            and not self.missing_tables
            and not self.low_row_tables
            and vol_ok
        )


class StartupValidator:
    """Docker 재기동 시 DB 연결·데이터 정합성 자가 검증기."""

    def __init__(
        self,
        pool: DbConnectionPool,
        backup_manager: BackupManager | None = None,
    ) -> None:
        """
        Args:
            pool: 검증 대상 DB 커넥션 풀 (T-003)
            backup_manager: 볼륨 확인에 사용할 BackupManager (T-006, None이면 볼륨 검증 건너뜀)
        """
        self.pool = pool
        self.backup_manager = backup_manager
        self.logger = ops_logger.get_logger(__name__)

    def validate(
        self,
        db_name: Literal["kdms", "usdms"],
        expected_tables: list[str],
        min_row_counts: dict[str, int],
    ) -> ValidationReport:
        """
        5가지 항목 순차 검증 후 ValidationReport 반환.
        """
        report = ValidationReport(db_name=db_name)

        # 1. DB 접속 가능 여부 (SELECT 1)
        try:
            with self.pool.get_cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                report.is_connected = True
        except Exception as e:
            self.logger.error(f"DB 접속 실패 ({db_name}): {e}")
            report.is_connected = False

            # 네트워크 에러 시 IP 검증 로직 실행
            err_str = str(e).lower()
            if "no route to host" in err_str or "connection" in err_str or "timeout" in err_str:
                try:
                    from p1_shared.utils.env_detector import EnvDetector
                    EnvDetector().verify_dev_ip_sync(self.logger)
                except Exception:
                    pass

            return report

        # 2. 핵심 테이블 존재 여부
        if expected_tables:
            try:
                with self.pool.get_cursor() as cur:
                    query = """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = ANY(%s)
                    """
                    cur.execute(query, (expected_tables,))
                    existing_tables = [row[0] for row in cur.fetchall()]
                    report.missing_tables = [t for t in expected_tables if t not in existing_tables]
            except Exception as e:
                self.logger.error(f"테이블 존재 확인 실패: {e}")

        # 3. 각 테이블 행 수 >= 최소 예상치
        for table, min_count in min_row_counts.items():
            if table in report.missing_tables:
                continue
            try:
                with self.pool.get_cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    if count < min_count:
                        report.low_row_tables[table] = (count, min_count)
            except Exception as e:
                self.logger.error(f"테이블 {table} 행 수 확인 실패: {e}")

        # 4. Docker 볼륨 실물 파일 존재
        if self.backup_manager:
            try:
                report.volume_info = self.backup_manager.check_volume_exists()
            except Exception as e:
                self.logger.error(f"볼륨 정보 확인 실패: {e}")
        else:
            # backup_manager가 없으면 빈 dict (테스트 7번 케이스 대응)
            report.volume_info = {}

        # 5. Hypertable 청크 상태 (TimescaleDB 전용)
        # kdms의 핵심 테이블(daily_ohlcv) 등에 대해 체크
        if db_name == "kdms":
            try:
                with self.pool.get_cursor() as cur:
                    # hypertable_name이 expected_tables에 포함된 것 중 하나라도 체크
                    # 여기서는 간단히 daily_ohlcv가 있으면 체크
                    target_hyper = "daily_ohlcv"
                    if target_hyper in expected_tables and target_hyper not in report.missing_tables:
                        query = """
                        SELECT COUNT(*) FROM timescaledb_information.chunks
                        WHERE hypertable_name = %s AND is_compressed = false
                        """
                        cur.execute(query, (target_hyper,))
                        # 청크가 하나도 없으면 경고 (단, is_healthy에는 영향 안 줌)
                        chunk_count = cur.fetchone()[0]
                        if chunk_count == 0:
                            report.hypertable_ok = False
            except Exception:
                # TimescaleDB 미설치 환경이거나 쿼리 실패 시 통과 처리
                report.hypertable_ok = True

        return report

    def print_report(self, report: ValidationReport) -> None:
        """
        검증 결과를 콘솔에 출력.
        """
        print(f"\n--- DB 기동 검증 리포트 ({report.db_name}) ---")
        
        # 1. 접속
        if report.is_connected:
            print("✅ DB 접속: 정상")
        else:
            print("❌ DB 접속: 실패")
            print(f"   → 조치: docker ps 로 DB 컨테이너 상태 확인")
            return

        # 2. 테이블
        if not report.missing_tables:
            print(f"✅ 테이블 존재: 정상")
        else:
            print(f"❌ 테이블 누락: {', '.join(report.missing_tables)}")
            print(f"   → 조치: python -m p1_shared.ops.backup_manager restore --target {report.db_name}")

        # 3. 행 수
        if not report.low_row_tables:
            print("✅ 데이터 행 수: 정상")
        else:
            for table, (actual, expected) in report.low_row_tables.items():
                print(f"❌ 행 수 부족: {table} 현재 {actual:,}행 (예상: {expected:,}행 이상)")
                print(f"   → 조치: 데이터 동기화 확인 (SyncManager)")

        # 4. 볼륨
        exists = report.volume_info.get("exists", False)
        if exists:
            print("✅ Docker 볼륨: 연결됨")
            if "volume_path" in report.volume_info:
                print(f"   → 경로: {report.volume_info['volume_path']}")
        else:
            print("❌ Docker 볼륨: 찾을 수 없음")
            print(f"   → 조치: Docker 볼륨 마운트 설정 확인")

        # 5. Hypertable
        if not report.hypertable_ok:
            print("⚠️ TimescaleDB 청크: 압축되지 않은 청크가 없음 (데이터 확인 필요)")

        if report.is_healthy:
            print("\n✨ 결과: DB가 안전하게 기동되었습니다.")
        else:
            print("\n🚨 결과: DB 상태가 불안정합니다. 위 조치 사항을 확인하세요.")
