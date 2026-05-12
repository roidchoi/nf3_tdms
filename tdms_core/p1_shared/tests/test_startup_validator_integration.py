import pytest
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

from p1_shared.utils.env_detector import EnvDetector

detector = EnvDetector()
DEV_HOST = detector.get_db_host("dev")
SERVER_HOST = detector.get_db_host("server")

DEV_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{DEV_HOST}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
DEV_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{DEV_HOST}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)
SERVER_KDMS_DSN = (
    f"postgresql://{os.getenv('DEV_KDMS_DB_USER')}:{os.getenv('DEV_KDMS_DB_PASSWORD')}"
    f"@{SERVER_HOST}:{os.getenv('DEV_KDMS_DB_PORT', 5432)}/{os.getenv('DEV_KDMS_DB_NAME')}"
)
SERVER_USDMS_DSN = (
    f"postgresql://{os.getenv('DEV_USDMS_DB_USER')}:{os.getenv('DEV_USDMS_DB_PASSWORD')}"
    f"@{SERVER_HOST}:{os.getenv('DEV_USDMS_DB_PORT', 5435)}/{os.getenv('DEV_USDMS_DB_NAME')}"
)


@pytest.mark.integration
def test_validator_is_connected_with_dev_kdms_real_db():
    """
    [목적] 개발PC KDMS 실 DB에 StartupValidator가 정상 접속하고 is_connected=True를 반환함을 검증
    [유도] DbConnectionPool + StartupValidator 연동이 실 DB에서 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_dev_usdms_real_db():
    """
    [목적] 개발PC USDMS 실 DB에 StartupValidator가 정상 접속하고 is_connected=True를 반환함을 검증
    [유도] 포트가 다른 DB(5435)에도 동일한 패턴이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_USDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="usdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_server_kdms_real_db():
    """
    [목적] 서버PC KDMS 실 DB에 내부망으로 접속하고 is_connected=True를 반환함을 검증
    [유도] localhost 대신 192.168.35.97 내부망 IP 기반 접속이 동작함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=SERVER_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_is_connected_with_server_usdms_real_db():
    """
    [목적] 서버PC USDMS 실 DB에 내부망으로 접속하고 is_connected=True를 반환함을 검증
    [유도] 서버PC 두 번째 DB 포트(5435)도 내부망 접속이 가능함을 보장
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=SERVER_USDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="usdms", expected_tables=[], min_row_counts={})
    pool.close_all()

    assert report.is_connected is True


@pytest.mark.integration
def test_validator_detect_real_tables_in_dev_kdms():
    """
    [목적] 개발PC KDMS 실 DB에서 테이블 존재 여부 확인이 동작함을 검증
    [유도] information_schema 쿼리가 실 DB에서 정상 실행됨을 보장.
           존재하지 않는 테이블 지정 시 missing_tables에 포함되어야 함
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["nonexistent_table_xyz"],
        min_row_counts={},
    )
    pool.close_all()

    assert report.is_connected is True
    assert "nonexistent_table_xyz" in report.missing_tables


@pytest.mark.integration
def test_validator_print_report_runs_without_error_on_real_db(capsys):
    """
    [목적] 실 DB 검증 결과를 print_report()로 출력할 때 예외 없이 완료됨을 검증
    [유도] validate() 실행 후 print_report() 호출해도 crash가 없는 구현 유도
    """
    from p1_shared.db.connection import DbConnectionPool
    from p1_shared.ops.startup_validator import StartupValidator

    pool = DbConnectionPool(dsn=DEV_KDMS_DSN, min_conn=1, max_conn=3)
    validator = StartupValidator(pool=pool)
    report = validator.validate(db_name="kdms", expected_tables=[], min_row_counts={})
    validator.print_report(report)  # 예외 발생 없이 완료되어야 함
    pool.close_all()

    captured = capsys.readouterr()
    assert len(captured.out) > 0
