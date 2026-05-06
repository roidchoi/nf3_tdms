# T-007 DB 기동 검증기 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-007 DB 기동 검증기 (`StartupValidator`)
- **목표**: Docker 재기동 시 DB의 물리적 볼륨 마운트 상태와 논리적 데이터(테이블, 행 수, 청크) 무결성을 검증하고 실패 시 조치 방법을 안내하는 모듈 구현

## 2. 생성 및 변경된 파일 목록
- **수정**: `docs/p1_shared/p1_shared_pjt_tasks.md` (T-007 상태 업데이트)
- **수정**: `tdms_core/p1_shared/p1_shared/utils/env_detector.py`
  - `get_db_host(target_env)` 메서드 추가: WSL 환경에서 호스트 물리 IP 접근 제약을 회피하기 위해 "자기 자신" 접속 시 `127.0.0.1`로 자동 우회하는 로직 구현
- **추가**: `tdms_core/p1_shared/p1_shared/ops/startup_validator.py`
  - `ValidationReport` dataclass: 검증 결과를 구조화하여 저장하고 `is_healthy` 프로퍼티로 최종 상태 판별
  - `StartupValidator` 클래스: `DbConnectionPool`(T-003)과 `BackupManager`(T-006)를 주입받아 5단계 검증 수행
- **추가**: `tdms_core/p1_shared/tests/test_startup_validator.py` (단위 테스트 14개)
- **추가**: `tdms_core/p1_shared/tests/test_startup_validator_integration.py` (통합 테스트 6개)
- **수정**: `tdms_core/p1_shared/tests/test_connection_integration.py` (Smart Host 연동 수정)

## 3. 주요 설계 결정사항 및 트러블슈팅 가이드
1. **WSL 네트워크 이슈 해결 (Smart Host)**:
   - WSL에서 호스트의 물리 IP(`192.168.35.201`)로의 라우팅이 차단되는 현상 및 IP 변동에 대응하기 위해, `EnvDetector`가 실행 환경을 판단하여 로컬 DB 접속 시에는 `127.0.0.1`을 사용하도록 자동화했습니다.
   - **[트러블슈팅 가이드] 통합 테스트 실패 시 IP 확인 방법**:
     만약 `No route to host` 에러가 다시 발생한다면 윈도우 PC의 IP(DHCP)가 변경되었을 수 있습니다.
     1. PowerShell에서 `Get-NetIPAddress -AddressFamily IPv4` 명령어로 현재 `Wi-Fi` 또는 `이더넷`의 IP를 확인합니다.
     2. 확인된 IP가 `.env` 파일의 `DEV_IP`와 다르다면, `.env`의 값을 현재 IP로 수정합니다.
2. **검증 순서 및 단계적 탈출**:
   - DB 접속 실패 시 이후 검증을 중단하여 불필요한 에러 로그를 방지했습니다.
3. **볼륨 검증 결합**:
   - T-006의 `BackupManager`와 연동하여 물리 볼륨 파일 존재 여부를 체크합니다.
4. **FastAPI 연동성**:
   - `is_healthy` 프로퍼티를 통해 FastAPI `lifespan`에서 즉시 사용 가능한 구조를 갖추었습니다.


## 4. 테스트 결과
- **단위 테스트**: 14개 전체 통과
- **통합 테스트**: 개발 PC(`192.168.35.201` → `127.0.0.1`) 및 서버 PC(`192.168.35.97`) 모두 접속 성공 확인
- **전체 회귀 테스트**: T-001 ~ T-007 총 **115개 테스트 전체 통과 (100% Green)**.

## 5. 다음 Task 관련 참고
- T-008 (SyncManager)에서는 본 검증기의 리포트를 활용하여 데이터가 임계치 미만일 경우 전체 동기화(`rsync`)를 실행하는 안전 장치(`FullSyncSafetyChecker`)를 구현할 예정입니다.
