# T-006 백업 매니저 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-006 백업 매니저 (`BackupManager`)
- **목표**: Docker 컨테이너 내 TimescaleDB를 `pg_dump -Fc` 포맷으로 백업하고, `pre-data -> data -> post-data` 순서로 강건 복원하는 관리 모듈 구현

## 2. 생성 및 변경된 파일 목록
- **수정**: `docs/p1_shared/p1_shared_pjt_tasks.md` (T-006 상태 업데이트)
- **추가**: `tdms_core/p1_shared/p1_shared/ops/backup_manager.py`
  - `BackupManager` 클래스: 백업(`.dump` 파일 생성), 검증(`pg_restore --list`), 복원(스냅샷 사전 백업 및 섹션 분리 적용) 로직 구현
  - `list_backups()` 및 `cleanup_old()`를 통한 백업 파일 보관 및 만료 파일 삭제 기능 구현
- **추가**: `tdms_core/p1_shared/tests/test_backup_manager.py`
  - Mock 객체(`mocker.patch("subprocess.run")`)를 활용한 17개의 단위 테스트 작성
  - 백업, 검증, 복원, EnvDetector 호환성 등 검증

## 3. 주요 설계 결정사항
1. **섹션 분리 강건 복원**:
   - 기존의 인덱스 및 외래키 순서 오류로 인한 복원 실패를 원천 차단하기 위해 `pre-data`, `data`, `post-data` 섹션을 3회에 걸쳐 순차적으로 복원하도록 `restore()` 메서드를 세밀하게 구현했습니다.
2. **사전 검증(Verify) 자동화**:
   - `pg_dump`로 백업한 파일에 대해 `pg_restore --list`를 통해 헤더 파싱을 검증함으로써 백업 파일의 무결성을 확보했습니다.
3. **볼륨 존재 확인**:
   - 호스트 Docker 볼륨(`/var/lib/docker/volumes/...`) 존재 및 PG_VERSION 파일 확인을 통해, 컨테이너 기동 전에 백업 파일에서 복원해야 하는지 여부를 판단할 수 있도록 기초 유틸리티(`check_volume_exists()`)를 추가했습니다.
4. **로거(logger) Mock 이슈 회피**:
   - `get_logger()` 함수 패치(mocker.spy) 시 이미 import 되어 캐싱된 모듈 때문에 테스트가 실패하는 현상을 방지하기 위해, `import logger as ops_logger` 형태로 로거를 지연 사용하도록 대응했습니다.

## 4. 테스트 결과
- 단위 테스트(T-006): 17개 통과
- `test_connection_integration.py`의 3개 테스트는 타겟 DB 서버(`192.168.35.205`)의 외부 네트워크 이슈(Offline)로 임시 실패(No route to host)했으나, 해당 모듈 코드 자체의 회귀가 아님을 확인했습니다.
- 백업 모듈은 Mock 기반 테스트로 독립적 통과를 완벽히 확보했습니다.

## 5. 다음 Task 관련 참고
- 다음 Task인 `T-007` (StartupValidator)에서는 본 `BackupManager`와 기존 `DbConnectionPool`, `EnvDetector`를 모두 연동하여 무결점 부팅 검증 로직을 결합하게 됩니다.
