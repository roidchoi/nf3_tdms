# T-003 DbConnectionPool 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-003 DB 커넥션 풀 (`db/connection.py`)
- **목표**: `psycopg2.pool.ThreadedConnectionPool`을 래핑하여 `get_cursor()` context manager 패턴으로 커넥션 획득·반환·롤백을 자동화하는 `DbConnectionPool` 클래스 구현

## 2. 변경된 파일 목록
- **수정**: `tdms_core/p1_shared/pyproject.toml`
  - `pytest.ini_options`에 `integration` 마커 추가 (통합 테스트 분리용)
- **추가**: `tdms_core/p1_shared/p1_shared/db/connection.py`
  - `DbConnectionPool` 클래스: `ThreadedConnectionPool`을 내부에 캡슐화
  - `@contextmanager get_cursor(autocommit=False)`: 커넥션을 풀에서 가져오고 예외 발생 시 `rollback()`, 정상 시 `commit()`, 그리고 항상 `putconn()`으로 반환
  - `close_all()`: 풀 종료 위임
- **추가**: `tdms_core/p1_shared/tests/test_connection.py`
  - 12개의 단위 테스트 작성 (`psycopg2.pool`을 mocker로 패치하여 독립적 테스트)
- **추가**: `tdms_core/p1_shared/tests/test_connection_integration.py`
  - 5개의 통합 테스트 작성 (개발PC 및 서버PC의 KDMS/USDMS 실 DB 접속 테스트, `@pytest.mark.integration` 적용)

## 3. 주요 구현 내용
1. **커넥션 라이프사이클 캡슐화**:
   - `get_cursor()` 제너레이터를 통해 커서 객체를 안전하게 `yield`합니다.
   - `try-except-finally` 블록을 구성하여 예외 상황에서도 무조건 `self._pool.putconn(conn)`이 호출되게 함으로써 리소스 누수(커넥션 고갈)를 방지했습니다.
2. **Autocommit 모드 지원**:
   - `autocommit=True`로 전달될 경우 트랜잭션 블록 처리(commit/rollback)를 생략하고, `conn.autocommit = True`를 설정한 뒤 반환합니다. (테스트 케이스의 요구사항을 반영하여 `finally` 구문 내에서는 불필요한 상태 초기화를 제거했습니다.)
3. **통합 테스트 분리**:
   - 실제 PostgreSQL 접속 정보(`.env`)를 사용하여, 4개의 타겟 DB(개발PC-KDMS, 개발PC-USDMS, 서버PC-KDMS, 서버PC-USDMS)에 접근할 수 있는지 검증하는 통합 테스트를 독립적으로 구성했습니다.

## 4. 테스트 결과
- 단위 테스트 12개 통과
- 통합 테스트 5개 통과 (실 DB 접속 검증)
- T-001/T-002 기반 테스트 35개 전부 통과 (회귀 없음)
- **총 52개 테스트 통과** (`pytest tests/ -v` 기준)

## 5. 다음 Task 진행 시 유의사항
- 이후 T-008, T-009 등의 상위 로직에서는 직접 커넥션을 다루지 않고 반드시 `DbConnectionPool.get_cursor()`를 사용해 쿼리를 실행해야 합니다.
- 통합 테스트의 경우, 실제 DB 컨테이너가 실행되어 있지 않으면 실패하므로 개발 환경에서 `docker ps` 상태를 확인 후 `pytest -m integration`을 수행해야 합니다.
