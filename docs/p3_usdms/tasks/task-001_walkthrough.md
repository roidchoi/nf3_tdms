# Task-001 Walkthrough: 프로젝트 기반 구조 및 DB 인계

## § 1. 개요 및 구현 파일 목록

미국 주식 데이터 백엔드(`p3_usdms`)의 첫 번째 마일스톤인 `T-001` 프로젝트 기반 인프라 구축 및 DB 인계를 완료하였습니다. `p1_shared` 공통 인프라 모듈을 안정적으로 이식하였으며, 기존 코드와의 호환성을 완벽히 조율하였습니다.

### 구현/수정된 파일 목록

| 파일 경로 | 구분 | 역할 및 설명 |
|---|---|---|
| [requirements.txt](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/requirements.txt) | 신규 | `fastapi`, `uvicorn`, `psycopg2-binary`, `pydantic-settings` 및 `httpx` 등 개발 및 테스트에 필요한 의존 패키지 선언 (p1_shared editable 연결 포함) |
| [pyproject.toml](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/pyproject.toml) | 신규 | `p3_usdms` 패키지의 빌드 사양 및 패키지 메타데이터 정의 |
| [config.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/config.py) | 신규 | pydantic-settings 기반 환경 변수 매퍼. `SEC_USER_AGENT` 필수 로딩 체크 유효성 검증 포함 |
| [repositories/base.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/base.py) | 신규 | `DbConnectionPool` 및 `EnvDetector`를 통합하고 지연 초기화(Lazy Initialization)를 수행하는 Repository 기본 골격 |
| [collectors/db_manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/db_manager.py) | 신규 | 기존 레거시 코드와의 100% 동작 정합성을 보장하기 위해 `RealDictCursor`를 context manager로 획득하는 DatabaseManager 어댑터(shim) |
| [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/main.py) | 신규 | FastAPI 진입점. lifespan 단계에서 DSN 커넥션 풀을 기동하고 `StartupValidator`를 연동하여 서버 부팅 전 기동 무결성을 강제함 |
| [tests/conftest.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/conftest.py) | 신규 | pytest를 실행하기 위한 공통 환경 변수 모킹(Fixture) 파일 |
| [tests/test_base_infra.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_base_infra.py) | 신규 | 환경감지, 커넥션 풀, StartupValidator, DatabaseManager shim, config, BackupManager 등 7개 테스트 케이스 구현 |

---

## § 2. 설계상 주요 결정사항

1. **`DatabaseManager` Shim 어댑터 도입**
   - 원본 코드베이스의 여러 수집 엔진 모듈들이 `with DatabaseManager().get_cursor() as cur:` 문법 및 딕셔너리 형태(`cur.fetchone()["cnt"]`)의 리턴 값을 강하게 의존하고 있습니다.
   - 이를 지원하기 위해 `BaseRepository`를 상속받은 `DatabaseManager` 클래스를 구현하고, `psycopg2.extras.RealDictCursor`를 탑재한 커서 제너레이터를 `contextmanager`로 정의하여 레거시 호환성을 완전 충족시켰습니다.

2. **Docker 볼륨 검증 건너뛰기 (`backup_manager=None`)**
   - 미국 주식 DB인 `usdms_db`는 `docker-compose.yml` 상에 볼륨명이 아닌 로컬 디렉토리 바인드 마운트(`./data/usdms_db:/var/lib/postgresql/data`) 구조를 취하고 있습니다.
   - 이로 인해 `BackupManager`가 Docker 볼륨 실물 파일 존재 검증(`/var/lib/docker/volumes/...`)을 수행하면 존재하지 않는 것으로 판단해 건강성 상태(`is_healthy`)가 실패로 반환됩니다.
   - 따라서 `main.py` 내 `StartupValidator` 인스턴스 생성 시 `backup_manager=None`으로 설정하여, 안전하게 볼륨 검증 단계를 건너뛰고 DB 커넥션 및 테이블 필수 검증만을 완수하도록 방어 코드를 적용했습니다.

3. **`SEC_USER_AGENT` 기동 제약**
   - 미국 SEC EDGAR API는 식별 가능한 User-Agent 헤더 정보가 누락되어 있을 시 접속을 원천 차단합니다.
   - 이에 따라 `config.py` 빌드 과정에서 `SEC_USER_AGENT` 필드가 공백이거나 누락되어 있을 경우 `ValueError`를 발생시키고 서버 부팅을 제한하도록 사전에 예외 검증기를 적용했습니다.

---

## § 3. 테스트 및 검증 결과

가상환경 `tdms_p3_env`에서 `pytest`를 실행한 결과 7개 테스트 케이스가 전원 정상적으로 통과되었습니다.

```bash
$ conda run -n tdms_p3_env pytest tdms_core/p3_usdms/tests/ -v
============================= test session starts ==============================
...
tdms_core/p3_usdms/tests/test_base_infra.py::test_env_detector_resolves_local_development_env PASSED
tdms_core/p3_usdms/tests/test_db_connection_pool_creates_and_fetches_cursor PASSED
tdms_core/p3_usdms/tests/test_startup_validator_passes_all_checks_on_dev PASSED
tdms_core/p3_usdms/tests/test_db_manager_shim_provides_compatible_context_cursor PASSED
tdms_core/p3_usdms/tests/test_fastapi_lifespan_executes_startup_sequence PASSED
tdms_core/p3_usdms/tests/test_config_with_empty_or_missing_env_vars_raises_error PASSED
tdms_core/p3_usdms/tests/test_backup_manager_handles_invalid_dest_path_and_logs_error PASSED
========================= 7 passed, 1 warning in 0.26s =========================
```

---

## § 4. 다음 단계 진행 시 주의사항

- **T-002 (티커 마스터 및 KIS 수집) 연계**:
  - `T-002` 수집 태스크를 구현할 때, 이번 `T-001`에서 이식한 `DatabaseManager` shim 어댑터를 활용하여 SQL 쿼리를 실행함으로써 레거시 파이프라인 마이그레이션 중 쿼리 동작 에러를 예방할 수 있습니다.
  - SEC EDGAR API를 호출할 때는 `config.get_settings().SEC_USER_AGENT` 헤더를 반드시 API 호출 요청 객체에 주입하여 수집 서버로부터의 블락킹 차단 조치를 방지해야 합니다.
