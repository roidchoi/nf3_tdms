# Task-001: 프로젝트 기반 구조 및 DB 인계

> **Sub Project**: p3_usdms
> **PRD 근거**: INFRA (Docker 인계 + StartupValidator + BackupManager)
> **작성일**: 2026-05-28
> **의존 Task**: 없음

---

## § 1. 목표

USDMS v5.0 레거시 코드 이식을 위한 FastAPI 개발 스켈레톤과 p1_shared 공통 모듈에 기반한 안정적인 인프라 환경을 완성한다. Docker를 통해 기존 `usdms_timescaledb`를 안전하게 마운트하고, 서비스 기동 전 백업 및 환경/DB 정밀 검증(`StartupValidator`)을 수행하며, 기존 코드들의 호환성을 위해 `db_manager.py`에 대한 shim(어댑터)을 제공한다.

**구현 범위:**
- **IN**:
  - `tdms_core/p3_usdms/` 개발 환경 뼈대 구성 (FastAPI, config)
  - `docker-compose.yml` (`external: true` 볼륨 설정 또는 bind-mount 보호) 및 `backend.Dockerfile`
  - `repositories/base.py` (`DbConnectionPool`, `EnvDetector` 통합)
  - `StartupValidator` 및 `BackupManager` 연동 로직
  - 레거시 코드 동작 유지를 위한 `db_manager.py` 호환용 shim 구현
  - `tests/` 단위 테스트 구성 및 7개 검증 케이스 통과
- **OUT**:
  - 구체적인 수집 엔진(`MasterSync`, `FinancialParser` 등) 및 스케줄러 구현 (T-002, T-005 진행 예정)
  - 데이터 조회 및 관리 API 엔드포인트 구현 (T-006, T-007 진행 예정)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/config.py` — 환경 변수 및 공통 설정 로더 (Pydantic Settings 기반 또는 python-dotenv 연동)
- `tdms_core/p3_usdms/main.py` — FastAPI 애플리케이션 진입점 및 lifespan 제어
- `tdms_core/p3_usdms/repositories/__init__.py`
- `tdms_core/p3_usdms/repositories/base.py` — DB Pool 및 환경 감지 기반 리포지토리 베이스
- `tdms_core/p3_usdms/collectors/__init__.py`
- `tdms_core/p3_usdms/collectors/db_manager.py` — 레거시 `DatabaseManager` 호환용 shim 어댑터
- `tdms_core/p3_usdms/tests/conftest.py` — pytest 피스처 및 환경 설정
- `tdms_core/p3_usdms/tests/test_base_infra.py` — 인프라 및 기반 로직 통합 테스트

### 수정 대상 파일 (해당 시)
- 없음 (신규 폴더 내 골격 구축)

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

```python
# tdms_core/p3_usdms/repositories/base.py
from p1_shared.db.connection import DbConnectionPool
from p1_shared.utils.env_detector import EnvDetector

class BaseRepository:
    """모든 Repository가 상속받는 기본 클래스"""
    
    # 클래스 수준에서 단일 커넥션 풀을 공유하여 유지
    _pool: DbConnectionPool = None
    _env: EnvDetector = None

    def __init__(self):
        """커넥션 풀 및 환경 감지 인스턴스 지연 초기화"""
        ...

    def get_connection(self):
        """커넥션 풀에서 커넥션을 직접 획득 (레거시 지원용)"""
        ...

    def get_cursor(self, autocommit: bool = False):
        """커넥션 풀에서 context manager로 동작하는 커서 획득"""
        ...

# tdms_core/p3_usdms/collectors/db_manager.py
from tdms_core.p3_usdms.repositories.base import BaseRepository

class DatabaseManager(BaseRepository):
    """
    레거시 코드와의 100% 호환성을 유지하기 위한 Shim 어댑터.
    기존의 db_manager.py API 구조를 유지하면서 내부적으로는 DbConnectionPool을 활용함.
    """
    def __init__(self):
        super().__init__()

    def get_cursor(self):
        """
        기존 db_manager.py와 동일하게 context manager로 동작하는 커서 객체를 반환.
        with DatabaseManager().get_cursor() as cur: 형식 지원.
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

#### 1) `test_env_detector_resolves_local_development_env`
- **목적**: WSL/Ubuntu 로컬 개발 환경에서 `EnvDetector`가 개발(dev) 혹은 로컬(local) 환경을 정상 식별하는지 검증.
- **유도**: `EnvDetector` 인스턴스 생성 및 환경 탐지 결과 반환값 확인.

#### 2) `test_db_connection_pool_creates_and_fetches_cursor`
- **목적**: `BaseRepository`가 통합된 `DbConnectionPool`을 정상 초기화하고 데이터베이스 커서를 성공적으로 반환하는지 검증.
- **유도**: `get_connection()` 및 커서 획득 후 `SELECT 1;` 쿼리 정상 작동 여부 단언.

#### 3) `test_startup_validator_passes_all_checks_on_dev`
- **목적**: `StartupValidator`가 현재 로컬 환경에서 요구하는 DSN, 필수 툴체인(uv/conda 등), 가상환경, 필수 시스템 변수 검증을 통과하는지 검증.
- **유도**: `StartupValidator.validate()` 호출 시 예외 없이 `True` 반환 확인 (볼륨 정보가 없는 환경이더라도 `volume_info` 검증 우회 처리가 반영되어야 함).

#### 4) `test_db_manager_shim_provides_compatible_context_cursor`
- **목적**: 레거시 코드가 `DatabaseManager().get_cursor()`를 사용할 때 `with` 구문 및 딕셔너리 기반 반환값(`RealDictCursor` 호환)이 정상 작동하는지 검증.
- **유도**: shim이 제공하는 커서로 테스트 쿼리를 수행하고 결과 데이터에 딕셔너리 형태로 접근할 수 있는지 검증.

#### 5) `test_fastapi_lifespan_executes_startup_sequence`
- **목적**: FastAPI 서비스가 구동(lifespan)될 때 `StartupValidator` 검증 및 `DbConnectionPool` 기동 로직이 자동으로 실행되는지 검증.
- **유도**: FastAPI `TestClient`로 서버 테스트 인스턴스 셋업 및 lifespan 성공 확인.

---

### 4.2 경계값 케이스

#### 6) `test_config_with_empty_or_missing_env_vars_raises_error`
- **목적**: 필수 환경 변수(`SEC_USER_AGENT` 등)가 제공되지 않았을 때 시스템 기동이 거부되고 적절한 예외가 발생하는지 확인.
- **유도**: 환경 변수가 누락된 상태에서 `config.py` 로드 혹은 `StartupValidator` 구동 시 `ValueError`가 발생하도록 유도.

---

### 4.3 예외/오류 처리 케이스

#### 7) `test_backup_manager_handles_invalid_dest_path_and_logs_error`
- **목적**: `BackupManager`가 데이터베이스 스냅샷 백업 실행 중 잘못된 경로 등으로 실패했을 때 프로세스를 크래시 시키지 않고 적절한 오류 로깅 및 실패 반환을 하는지 검증.
- **유도**: 임의의 존재하지 않는 무효한 타겟 경로를 전달하여 백업 실행 시 실패 코드 반환 및 예외 핸들링 여부 단언.

---

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_env_detector_resolves_local_development_env` | 정상 | WSL 2(Ubuntu) 환경 및 개발 DSN 결정 검증 |
| 2 | `test_db_connection_pool_creates_and_fetches_cursor` | 정상 | `DbConnectionPool` 기반 DSN 자동 연동 및 쿼리 테스트 |
| 3 | `test_startup_validator_passes_all_checks_on_dev` | 정상 | `StartupValidator` 필수 검증 단계 통과 여부 검증 |
| 4 | `test_db_manager_shim_provides_compatible_context_cursor` | 정상 | `DatabaseManager` shim 어댑터의 레거시 호환 및 작동성 검증 |
| 5 | `test_fastapi_lifespan_executes_startup_sequence` | 정상 | FastAPI lifespan 실행 시 검증 장치 연동 및 구동성 확인 |
| 6 | `test_config_with_empty_or_missing_env_vars_raises_error` | 경계 | 필수 키(`SEC_USER_AGENT`) 누락 시 동작 제한 및 예외 발생 |
| 7 | `test_backup_manager_handles_invalid_dest_path_and_logs_error` | 예외 | 백업 중 대상 경로 오류 또는 장애 발생 시 복구 및 핸들링 |

**총 7개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, Conda 가상환경 (`tdms_p1_env`), FastAPI, PostgreSQL (`psycopg2`), `p1_shared` 공통 모듈
- **관련 문서**:
  - `docs/parent/tdms_PRD.md` — § 2. 통합 아키텍처 및 공통 기준
  - `pjt_wiki/p1_shared_wiki/interfaces/startup_validator.md` — 기동 유효성 검증
  - `pjt_wiki/p1_shared_wiki/interfaces/backup_manager.md` — DB 백업 관리 인터페이스
- **주의사항**:
  - **DB 커넥션 정보**: `p1_shared` 동기화가 완료된 실물 DB인 `usdms_timescaledb` 컨테이너(포트 `5433`, 데이터베이스명 `usdms_db`)를 향하도록 환경 변수를 설계합니다.
  - **Docker Compose**: `docker-compose.yml` 에서 `usdms_db` 서비스의 컨테이너명이 `usdms_timescaledb` 로 선언되어 있으므로, `.env` 상의 `USDMS_CONTAINER_NAME` 역시 이와 일치하는 `usdms_timescaledb` 로 사용되어야 합니다.
  - **SEC User-Agent**: 미국 SEC API 호출 제한을 회피하기 위해 `SEC_USER_AGENT` 환경변수를 필수적으로 설정하고 애플리케이션 초기화 단계에서 유효성을 확인하도록 합니다.
  - **IP 변경(DHCP) 및 환경 자동감지 완화 정책**:
    - PC 재부팅 등으로 호스트의 실제 물리 IP가 변경되어도 `EnvDetector`는 `socket.gethostname()` (호스트명) 매칭을 최우선으로 사용하여 `dev` / `server` 환경을 정상 식별합니다.
    - 실제 IP와 `.env`에 정의된 `DEV_IP`가 불일치할 시 `verify_dev_ip_sync()`를 통해 경고 로그를 출력하므로, 기동 시 해당 로그가 콘솔과 시스템 로그에 올바르게 반영되는지 유의해야 합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 7개 전체 통과
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 Task-001 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-001_walkthrough.md` 작성
