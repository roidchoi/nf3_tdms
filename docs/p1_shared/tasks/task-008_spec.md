# Task-008: 물리적 DB 동기화 파이프라인 (Physical Sync Automation)

> **Sub Project**: p1_shared
> **PRD 근거**: §3.10 DB 동기화 매니저 (`ops/db_sync.py`)
> **작성일**: 2026-05-12 (논리적 동기화에서 물리적 동기화로 전면 개편)
> **의존 Task**: T-002 (EnvDetector), T-006 (BackupManager)

---

## § 1. 목표

개발PC ↔ 서버PC 간의 대용량 시계열 데이터베이스(TimescaleDB)를 100% 무결성으로 동기화하기 위한 **완전 자동화 물리 동기화(Stop-and-Copy) 도구**를 구현한다.

과거 `pg_dump`/`pg_restore` 기반의 논리적 동기화가 가진 한계(메모리 부족, 타임아웃, 익스텐션 충돌)를 극복하기 위해, **바인드 마운트된 데이터 폴더 자체를 SSH 파이프라인으로 전송(Binary Sync)**하는 방식을 채택한다. (Task-009 실행 절차를 이 도구 하나로 통합 흡수)

**구현 범위:**
- **IN**:
  - `p1_shared/ops/db_sync.py` — 메인 파이프라인 제어 (Preflight -> Stop -> Copy -> Permission -> Start)
  - `tests/test_db_sync.py` — SSH 명령어 생성 및 컨테이너 제어 흐름 단위 테스트
- **OUT**:
  - 기존 논리적 동기화 코드 및 `SyncManager`, `FullSyncSafetyChecker` 모듈 폐기
  - `task-009_spec.md` (수동 인계 절차서 폐기 및 통합)

---

## § 2. 구현 대상

### 신규 생성 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/db_sync.py`
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/tests/test_db_sync.py`

### 핵심 아키텍처 및 파이프라인

단일 스크립트 실행 시 5단계 자동화 수행:

1. **Safety & Preflight**: SSH 접속 검증, 소스/대상 DB 환경 확인
2. **Maintenance Mode (Stop)**: 데이터 쓰기 원천 차단을 위해 양측 PC의 앱(backend/frontend) 및 DB 컨테이너 중지
3. **Physical Binary Transfer**: `tar + SSH Pipe`를 통한 바인드 마운트 데이터 실시간 압축 전송/해제
4. **Permission Fix**: 수신 측 PC에서 폴더 권한 교정 (`chown 1000:1000`)
5. **Resume**: 양측 PC 컨테이너 재기동

---

## § 3. 핵심 인터페이스 (`db_sync.py`)

```python
import argparse
from dataclasses import dataclass
from typing import Literal
from p1_shared.utils.env_detector import EnvDetector
from p1_shared.ops.logger import get_logger

logger = get_logger("db_sync")

@dataclass
class SyncConfig:
    db_name: Literal["kdms", "usdms"]
    direction: Literal["pull", "push"]
    source_ip: str
    target_ip: str
    ssh_user: str
    ssh_key_path: str
    data_path: str

class PhysicalSyncManager:
    def __init__(self, config: SyncConfig):
        self.config = config

    def preflight_check(self) -> bool:
        """SSH 접속 및 대상 디렉토리 유효성 검사"""
        ...

    def stop_containers(self, target_host: str, is_local: bool) -> None:
        """대상 호스트의 App 및 DB 컨테이너 중지"""
        ...

    def start_containers(self, target_host: str, is_local: bool) -> None:
        """대상 호스트의 컨테이너 재기동"""
        ...

    def transfer_data(self) -> None:
        """tar + ssh 파이프라인을 통한 물리 데이터 전송"""
        ...

    def fix_permissions(self) -> None:
        """대상 디렉토리의 UID/GID를 1000:1000으로 교정"""
        ...

    def execute(self) -> bool:
        """5단계 파이프라인 전체 실행"""
        ...
```

---

## § 4. 테스트 케이스 설계 (`test_db_sync.py`)

*실제 데이터 파괴를 막기 위해 subprocess.run을 전면 Mocking하여 명령어 생성 및 파이프라인 호출 순서를 검증한다.*

1. **`test_preflight_check_validates_ssh`**: SSH 접속 실패 시 False 반환.
2. **`test_stop_containers_generates_correct_commands`**: 로컬 및 원격 중지 명령어(`docker compose stop`) 생성 검증.
3. **`test_transfer_data_pipeline_commands`**: `push` 및 `pull` 방향에 따른 `tar + ssh` 파이프라인 문자열 정확도 검증.
4. **`test_fix_permissions_executes_sudo_chown`**: 데이터 수신 측에 대한 권한 교정 명령어 생성 검증.
5. **`test_execute_pipeline_order`**: `preflight -> stop -> transfer -> fix -> start` 순서 호출 검증.

---

## § 5. 구현 참고사항

*   **물리 전송 핵심 명령어 (Pull 기준 예시)**:
    ```bash
    ssh -i {key} {user}@{server_ip} "sudo tar -czf - -C /path/to/data/{db_name}_db ." | sudo tar -xzf - -C ./data/{db_name}_db
    ```
    *(주의: 폴더 내의 숨김파일 및 전체 구조 유지를 위해 `.` 사용, 양측 모두 sudo 또는 root 권한 접근 고려)*
*   **컨테이너 제어**: `docker compose stop usdms_db`, `docker compose stop 01_usdms-backend` (또는 전체 `docker compose stop` 후 타겟팅 기동)
*   프로젝트 루트 경로는 절대경로를 하드코딩하지 않고 `.env`나 실행 위치를 기반으로 탐색.

---

## § 6. 완료 기준

- [ ] `ops/db_sync.py` 파이프라인 전면 구현
- [ ] `test_db_sync.py` 단위 테스트 전체 통과 (Mocking 기반)
- [ ] (선택) `run_command`로 Dry Run 수준의 명령어 덤프 확인
- [ ] `docs/p1_shared/tasks/task-008_walkthrough.md` 작성
