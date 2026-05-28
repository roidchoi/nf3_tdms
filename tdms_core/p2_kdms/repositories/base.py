import os
from p1_shared.utils.env_detector import EnvDetector
from p1_shared.db.connection import DbConnectionPool

def create_kdms_pool() -> DbConnectionPool:
    """
    EnvDetector로 현재 환경(dev/server)을 감지하여
    환경에 맞는 KDMS DB DSN을 자동 구성하고 커넥션 풀을 반환한다.

    Returns:
        DbConnectionPool: 초기화된 커넥션 풀

    Raises:
        RuntimeError: 환경 감지 실패 시 ('unknown')
    """
    detector = EnvDetector()
    env = detector.detect()
    if env == "unknown":
        raise RuntimeError("환경 감지 실패")
    
    # 현재 환경에 맞는 프로파일 로드
    profile = detector.load_env_profile()
    
    # DSN 구성 (profile에 있으면 우선 사용 - 테스트 Mock 대응용)
    # 실제 환경에서는 EnvDetector.load_env_profile이 반환하지 않는 값들을 
    # .env(os.environ)에서 직접 가져옴.
    db_user = profile.get("db_user") or os.environ.get(f"{env.upper()}_KDMS_DB_USER", "roid")
    db_password = profile.get("db_password") or os.environ.get(f"{env.upper()}_KDMS_DB_PASSWORD", "")
    db_host = profile.get("db_host") or detector.get_db_host(env)
    db_port = profile.get("db_port") or os.environ.get(f"{env.upper()}_KDMS_DB_PORT", 5432)
    db_name = profile.get("db_name") or os.environ.get(f"{env.upper()}_KDMS_DB_NAME", "kdms_db")

    dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    return DbConnectionPool(dsn=dsn)
