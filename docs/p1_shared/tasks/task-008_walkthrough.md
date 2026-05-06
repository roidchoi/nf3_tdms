# Task-008 Walkthrough: DB 동기화 매니저 (SyncManager + FullSyncSafetyChecker)

## 1. 개요
- **Task ID**: T-008
- **목표**: 개발PC ↔ 서버PC 간 양방향 DB 동기화 기능 및 안전 장치 구현
- **상태**: 완료

## 2. 주요 변경 사항 및 파일 역할

### `p1_shared/ops/sync_manager.py` (신규)
- `FullSyncSafetyChecker`: 
  - DB 크기, 최근 데이터 날짜(dt)를 비교하여 개발/서버 간 잘못된 덮어쓰기 등 이상 조건을 감지합니다.
  - 소스/대상 DB의 테이블 목록 및 컬럼 구조를 쿼리하여 스키마 불일치 여부를 탐지합니다.
  - 이상 감지 시 사용자에게 콘솔을 통해 `CONFIRM-FULL-SYNC`를 입력하도록 30초 타임아웃을 주어 안전성을 강화했습니다.
- `SyncManager`: 
  - `sync()` 메서드를 통해 `full`, `diff`, `table` 3가지 모드의 동기화를 수행합니다.
  - `dry_run` 모드를 지원하여 실제 동기화 명령을 실행하지 않고 계획만 확인 가능합니다.
  - T-002(`EnvDetector`)와 T-006(`BackupManager`)를 연동하여 상대 IP를 조회하고, `full` 모드 시 `pre_sync` 태그로 전송 전 백업을 자동 실행합니다.

### `tests/test_sync_manager.py` (신규)
- 세션 A (SafetyChecker) 및 세션 B (SyncManager) 단위 테스트 총 19개 작성.
- 실제 DB나 네트워크 접속 없이 동작하도록 `psycopg2`, `subprocess`, `builtins.input` 등을 철저히 Mocking하여 독립적으로 검증했습니다.
- Test-Driven Development (TDD) 방식으로 명세의 시나리오를 100% 반영했습니다.

## 3. 설계상 주요 결정사항

- **스키마 불일치 대응**: 
  - `full` 모드는 `pg_dump -Fc`가 스키마와 데이터를 통째로 덮어쓰므로 스키마 불일치 경고를 띄워도 무방하여 사용자 동의 절차를 거쳐 진행합니다.
  - `diff`, `table` 모드는 데이터만 이동하기 때문에, 스키마 불일치 시 INSERT 오류로 인한 데이터 오염 위험이 매우 높습니다. 따라서 `diff`/`table` 모드 시 스키마 불일치가 발견되면 즉각 전송을 중단하고 경고 메시지를 반환합니다.

- **안전장치 무력화 방지 (Mock 분리 설계)**:
  - 테스트 코드는 Mocking된 환경을 사용하지만, 실제 `compare` 로직에서는 예외 처리를 촘촘히 두어 DB 접속 실패나 쿼리 실패 등에 대해 모두 안전 검증 실패(is_safe=False)로 취급하도록 강건하게 설계했습니다.

## 4. 테스트 결과 요약
- `test_sync_manager.py` 내 19개 테스트 항목 전체 통과 (All Green)
- 기존 `p1_shared` 테스트 스위트와 통합하여 총 **138개 테스트 모두 통과** (회귀 없음)

## 5. 다음 Task 진행 시 주의사항
- 다음 태스크인 **T-009 (DB 인계 실행)** 에서는 단위 테스트용 Mock을 사용하지 않고, 실제 개발PC와 서버PC 간의 통신과 DB 데이터 복원이 일어납니다.
- T-009 진행 전, 대상 PC의 SSH 접속 가능 상태와 `.env`에 정의된 `SSH_USER` 및 `SSH_KEY_PATH`가 올바른지 사전에 반드시 점검해야 합니다.
