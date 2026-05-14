# Task-001: 프로젝트 기반 구조 및 DB 인계

> **Sub Project**: p2_kdms
> **PRD 근거**: INFRA (Docker 인계 + StartupValidator + BackupManager), REFACTOR-1(repositories/base.py)
> **작성일**: 2026-05-14
> **의존 Task**: 없음 (Phase 1 최우선)

---

## § 1. 목표

기존 `kdms_db` Docker 볼륨을 단절 없이 인계받아, 기동 시 자동으로 DB 무결성을 검증하는 FastAPI 백엔드 뼈대가 실행된다.

**구현 범위:**
- IN:
  - `docker-compose.yml` (볼륨 `external:true`, `container_name: kdms_timescaledb`)
  - `main.py` (FastAPI 앱 인스턴스, lifespan 등록)
  - `config.py` (pydantic-settings로 `.env` 로딩)
  - `repositories/base.py` (EnvDetector DSN 자동 결정, DbConnectionPool 생성)
  - `lifespan` 내 `StartupValidator` 연동 (DB 5종 검증 → `is_healthy=False` 시 기동 차단)
  - `ops/pre_migration_backup.py` (인계 전 BackupManager 백업 실행 스크립트)
  - `backend.Dockerfile` (기본 이미지 설정)
  - `.env.example` (Layer A + Layer B 변수 템플릿)
- OUT:
  - 실제 데이터 수집 로직 (T-002~T-006)
  - 데이터 조회 API (T-007~T-008)
  - 실제 DB 스키마 DDL (T-001 완료 후 init.sql 별도 확인)

---

## § 2. 구현 대상

### 신규 생성 파일

```
tdms_core/p2_kdms/
├── main.py                          # FastAPI 앱 + lifespan
├── config.py                        # Settings (pydantic-settings)
├── backend.Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── repositories/
│   ├── __init__.py
│   └── base.py                      # 커넥션 풀 팩토리 (EnvDetector 연동)
├── ops/
│   └── pre_migration_backup.py      # 인계 전 백업 실행 스크립트
└── tests/
    └── test_base_repository.py      # 단위 테스트
```

### 핵심 인터페이스

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    .env 파일을 자동으로 로딩하는 설정 클래스.
    Layer A (EnvDetector용)와 Layer B (앱 내부용) 변수를 모두 포함.
    """
    # Layer A — EnvDetector 전용
    tdms_env: str = ""
    dev_hostname: str = ""
    server_hostname: str = ""
    dev_ip: str = ""
    server_ip: str = ""
    dev_kdms_db_user: str = "roid"
    dev_kdms_db_password: str = ""
    dev_kdms_db_port: int = 5432
    dev_kdms_db_name: str = "kdms_db"

    # Layer B — 앱 내부용
    postgres_user: str = ""
    postgres_password: str = ""
    db_pool_min: int = 5
    db_pool_max: int = 20
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()


# repositories/base.py
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
        psycopg2.OperationalError: DB 연결 불가 시
    """
    ...


# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from p1_shared.ops.startup_validator import StartupValidator
from p1_shared.ops.backup_manager import BackupManager

KDMS_EXPECTED_TABLES = [
    "daily_ohlcv", "stock_info", "price_adjustment_factors",
    "financial_statements", "financial_ratios", "daily_market_cap",
    "system_milestones", "minute_target_history",
]
KDMS_MIN_ROW_COUNTS = {"daily_ohlcv": 1_000_000}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 기동 시:
      1. 커넥션 풀 생성 (create_kdms_pool)
      2. StartupValidator로 DB 5종 검증
      3. is_healthy=False 시 RuntimeError → 서비스 기동 차단
    앱 종료 시: 커넥션 풀 정리 (pool.close_all)
    """
    ...
```

---

## § 3. 기존 기능 보존

해당 없음 (신규 프로젝트 최초 Task)

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# tests/test_base_repository.py

def test_create_kdms_pool_on_dev_env_returns_pool(mocker):
    """
    [목적] DEV 환경에서 EnvDetector가 'dev'를 감지하고
           DEV_KDMS_DB_* 변수로 DSN을 구성하여 풀을 반환하는지 검증
    [유도] create_kdms_pool()이 EnvDetector.detect()와 load_env_profile()을
           사용하여 DSN을 동적으로 결정하도록 유도
    """
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="dev"
    )
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.load_env_profile",
        return_value={
            "db_host": "192.168.35.205",
            "db_port": 5432,
            "db_name": "kdms_db",
            "db_user": "roid",
            "db_password": "test_pass",
        }
    )
    mock_pool = mocker.patch("repositories.base.DbConnectionPool")

    pool = create_kdms_pool()

    mock_pool.assert_called_once()
    call_dsn = mock_pool.call_args[1]["dsn"]
    assert "192.168.35.205" in call_dsn
    assert "kdms_db" in call_dsn


def test_create_kdms_pool_on_server_env_returns_pool(mocker):
    """
    [목적] SERVER 환경에서도 올바른 SERVER_KDMS_DB_* 변수로 DSN이 구성되는지 검증
    [유도] 환경별 프로파일 분기 로직 구현을 유도
    """
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="server"
    )
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.load_env_profile",
        return_value={
            "db_host": "192.168.35.97",
            "db_port": 5432,
            "db_name": "kdms_db",
            "db_user": "roid",
            "db_password": "test_pass",
        }
    )
    mock_pool = mocker.patch("repositories.base.DbConnectionPool")

    pool = create_kdms_pool()

    call_dsn = mock_pool.call_args[1]["dsn"]
    assert "192.168.35.97" in call_dsn


def test_settings_loads_layer_a_env_vars(tmp_path, monkeypatch):
    """
    [목적] Settings가 Layer A (EnvDetector용) 변수를 올바르게 로딩하는지 검증
    [유도] Settings 클래스가 DEV_KDMS_DB_* 형태의 변수명을 선언하도록 유도
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEV_KDMS_DB_USER=testuser\n"
        "DEV_KDMS_DB_PORT=5433\n"
        "DEV_KDMS_DB_NAME=test_kdms\n"
        "TDMS_ENV=dev\n"
    )
    monkeypatch.chdir(tmp_path)

    from config import Settings
    s = Settings(_env_file=str(env_file))

    assert s.dev_kdms_db_user == "testuser"
    assert s.dev_kdms_db_port == 5433
    assert s.tdms_env == "dev"


def test_lifespan_startup_calls_validator_and_passes(mocker):
    """
    [목적] lifespan startup 시 StartupValidator.validate()가 호출되고
           is_healthy=True이면 서비스가 정상 기동하는지 검증
    [유도] lifespan 내에서 validator.validate() 호출 및 결과 확인 로직 구현 유도
    """
    from unittest.mock import MagicMock, AsyncMock
    from fastapi.testclient import TestClient

    mock_pool = mocker.patch("main.create_kdms_pool")
    mock_backup = mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app) as client:
        response = client.get("/")
        # StartupValidator.validate가 1회 호출되었음을 확인
        mock_validator.return_value.validate.assert_called_once_with(
            db_name="kdms",
            expected_tables=mocker.ANY,
            min_row_counts=mocker.ANY,
        )
```

### 4.2 경계값 케이스

```python
def test_lifespan_startup_unhealthy_report_raises_runtime_error(mocker):
    """
    [목적] StartupValidator가 is_healthy=False를 반환할 때
           RuntimeError가 발생하여 서비스 기동이 차단되는지 검증
    [유도] is_healthy 체크 후 raise RuntimeError 구현 유도
    """
    import pytest
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient

    mocker.patch("main.create_kdms_pool")
    mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    unhealthy_report = MagicMock()
    unhealthy_report.is_healthy = False
    unhealthy_report.missing_tables = ["daily_ohlcv"]
    mock_validator.return_value.validate.return_value = unhealthy_report

    from main import app
    with pytest.raises(RuntimeError, match="DB 기동 검증 실패"):
        with TestClient(app):
            pass


def test_create_kdms_pool_raises_runtime_error_when_env_unknown(mocker):
    """
    [목적] EnvDetector가 'unknown'을 반환할 때 RuntimeError 발생 검증
    [유도] unknown 환경에서 명확한 에러 메시지와 함께 조기 실패하도록 구현 유도
    """
    import pytest
    mocker.patch(
        "p1_shared.utils.env_detector.EnvDetector.detect",
        return_value="unknown"
    )
    with pytest.raises(RuntimeError, match="환경 감지 실패"):
        create_kdms_pool()
```

### 4.3 예외/오류 처리 케이스

```python
def test_lifespan_shutdown_calls_pool_close_all(mocker):
    """
    [목적] lifespan 종료(shutdown) 시 pool.close_all()이 호출되는지 검증
    [유도] yield 이후 finally 또는 명시적 close_all() 호출 구현 유도
    """
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient

    mock_pool_instance = MagicMock()
    mocker.patch("main.create_kdms_pool", return_value=mock_pool_instance)
    mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app):
        pass  # 컨텍스트 종료 시 shutdown 실행

    mock_pool_instance.close_all.assert_called_once()


def test_backup_manager_called_with_correct_container_name(mocker):
    """
    [목적] BackupManager 초기화 시 container_name이 정확히
           'kdms_timescaledb'로 전달되는지 검증
    [유도] main.py에서 container_name을 하드코딩하지 않고 상수로 관리하도록 유도
    """
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient

    mocker.patch("main.create_kdms_pool")
    mock_backup_cls = mocker.patch("main.BackupManager")
    mock_validator = mocker.patch("main.StartupValidator")

    healthy_report = MagicMock()
    healthy_report.is_healthy = True
    mock_validator.return_value.validate.return_value = healthy_report

    from main import app
    with TestClient(app):
        pass

    call_kwargs = mock_backup_cls.call_args[1]
    assert call_kwargs["container_name"] == "kdms_timescaledb"
    assert call_kwargs["volume_name"] == "kdms_pgdata"
```

### 4.4 통합/연계 케이스

```python
def test_pre_migration_backup_script_creates_dump_file(mocker, tmp_path):
    """
    [목적] ops/pre_migration_backup.py 실행 시 BackupManager.backup()이
           호출되고 tag='pre_p2_migration'이 전달되는지 검증
    [유도] pre_migration_backup.py가 BackupManager를 직접 인스턴스화하고
           backup(tag='pre_p2_migration')을 호출하도록 구현 유도
    """
    mock_backup = mocker.patch("ops.pre_migration_backup.BackupManager")
    mock_backup.return_value.backup.return_value = tmp_path / "checkpoint.dump"

    from ops.pre_migration_backup import run_backup
    result = run_backup()

    mock_backup.return_value.backup.assert_called_once_with(tag="pre_p2_migration")
    assert result is not None
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_create_kdms_pool_on_dev_env_returns_pool` | 정상 | DEV 환경 DSN 구성 및 풀 반환 |
| 2 | `test_create_kdms_pool_on_server_env_returns_pool` | 정상 | SERVER 환경 DSN 구성 |
| 3 | `test_settings_loads_layer_a_env_vars` | 정상 | Layer A 환경변수 로딩 |
| 4 | `test_lifespan_startup_calls_validator_and_passes` | 정상 | lifespan에서 validator 호출 및 정상 기동 |
| 5 | `test_lifespan_startup_unhealthy_report_raises_runtime_error` | 경계값 | is_healthy=False 시 기동 차단 |
| 6 | `test_create_kdms_pool_raises_runtime_error_when_env_unknown` | 예외 | 환경 감지 실패 시 명확한 에러 |
| 7 | `test_lifespan_shutdown_calls_pool_close_all` | 예외 | 종료 시 pool 정리 보장 |
| 8 | `test_backup_manager_called_with_correct_container_name` | 예외 | 컨테이너명 'kdms_timescaledb' 검증 |
| 9 | `test_pre_migration_backup_script_creates_dump_file` | 통합 | 인계 전 백업 스크립트 동작 |

**총 9개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, FastAPI 0.121+, pydantic-settings, psycopg2-binary 2.9.12
- **p1_shared 위키**:
  - `pjt_wiki/p1_wiki/interfaces/env_detector.md` — `detect()`, `load_env_profile()`, `get_db_host()` 시그니처
  - `pjt_wiki/p1_wiki/interfaces/db_connection_pool.md` — DSN 형식: `"postgresql://user:pass@host:port/dbname"`
  - `pjt_wiki/p1_wiki/interfaces/startup_validator.md` — FastAPI lifespan 패턴 코드 참조
  - `pjt_wiki/p1_wiki/interfaces/backup_manager.md` — `backup(tag=)` 사용법
- **환경변수 계층**: PRD §8 참조 — Layer A(EnvDetector 전용)와 Layer B(Docker/앱 내부)를 혼동하지 말 것
- **컨테이너명**: `BackupManager(container_name="kdms_timescaledb")` — docker-compose의 `container_name`과 반드시 일치 (`p1_wiki/errors/p1-err-001`)
- **볼륨 보호**: `docker-compose.yml`에 `kdms_pgdata: external: true` 반드시 설정 — `docker-compose down -v` 시 볼륨 보호
- **DSN 형식**: `"postgresql://{user}:{password}@{host}:{port}/{db_name}"`
- **테스트 Mock 패턴**: `p1_shared` 모듈의 `EnvDetector`는 `mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect")`로 패치. `DbConnectionPool`은 생성 자체를 patch하여 실 DB 불필요.
- **프로젝트 루트**: `tdms_core/p2_kdms/` — p1_shared와 동일 계층

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 9개 전체 통과
- [ ] `docker-compose up` 시 `kdms_timescaledb` 컨테이너가 기존 볼륨에 정상 연결
- [ ] FastAPI 앱 기동 시 StartupValidator 검증 로그 출력 확인
- [ ] `ops/pre_migration_backup.py` 실행 시 `backups/kdms/pre_p2_migration/` 하위에 `.dump` 파일 생성
- [ ] `docs/p2_kdms/p2_kdms_pjt_tasks.md`의 T-001 상태를 `완료`로 업데이트
- [ ] `docs/p2_kdms/tasks/task-001_walkthrough.md` 작성
