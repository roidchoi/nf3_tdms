# Task-009: 물리 복구 및 안전장치 구현

> **Sub Project**: p4_manager
> **PRD 근거**: P4-REQ-008 (물리 볼륨 안전 복구 및 오작동 방지)
> **작성일**: 2026-06-10
> **의존 Task**: T-008 (물리 백업 구현)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| StartupValidator 시그니처 | `pjt_wiki/p1_shared_wiki/interfaces/startup_validator.md` | ✅ 확인 |
| BackupService 시그니처 | 위키 미기록 → `tdms_core/p4_manager/services/backup_service.py` 직접 확인 완료 | ⚠️ 직접 확인 |
| docker-compose.yml | 루트 `docker-compose.yml` 및 `tdms_core/p2_kdms/docker-compose.yml` 직접 확인 완료 | ⚠️ 직접 확인 |
| 물리 복구 API 설계 결정 | `pjt_wiki/p4_manager_wiki/decisions.md` (P4DEC-004 물리 차단 결정 내역) | ✅ 확인 |

---

## § 1. 목표

개발 PC 로컬 환경에서 보관된 스냅샷 아카이브(`tar.gz`)를 사용하여 데이터베이스를 안전하게 복구하고, 컨테이너 오케스트레이션 및 복구 직후 데이터 정합성 자가 진단을 수행하는 신뢰성 높은 복구 시스템을 구축한다.

**구현 범위:**
- IN:
  - 백엔드 물리 복구 API (`POST /api/mgr/restore`) 구현
  - 서버 PC 환경(`server`) 진입 시 복구 API 요청 403 Forbidden 차단 및 프론트엔드 UI 비활성화
  - 복구 수행 시 관련 컨테이너 중지/기동 및 권한 교정(Maintenance Mode 오케스트레이션)
  - 복구 후 DB 컨테이너 접속 정상화 대기 및 `StartupValidator`를 연동한 자가 정합성 진단 수행
  - 프론트엔드 복구 모달 내 오작동 방지 이중 컨펌 텍스트 입력창 (`RESTORE LOCAL DB`) 및 백엔드 단의 2차 검증 구현
- OUT:
  - 서버 PC 환경에서의 실제 강제 복구 기능 (원천 차단 대상)
  - pg_dump/pg_restore 기반의 논리 복구 (물리 복구 전용 태스크임)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/tests/services/test_restore_service.py` — 복구 서비스 단위/통합 테스트
- `tdms_core/p4_manager/frontend/src/components/__tests__/RestoreModal.spec.ts` — 프론트엔드 이중 안전장치 검증 컴포넌트 테스트

### 수정 대상 파일
- `tdms_core/p4_manager/services/backup_service.py` — `restore_backup` 메서드 추가 및 오케스트레이션/진단 연동 구현
- `tdms_core/p4_manager/routers/manager.py` — `POST /api/mgr/restore` 라우터 추가 및 환경/이중 안전장치 검증
- `tdms_core/p4_manager/frontend/src/stores/backupStore.ts` — `restoreBackup` API 요청 액션 구현
- `tdms_core/p4_manager/frontend/src/views/BackupView.vue` — 복구 확인 모달 기획 반영 (이중 컨펌 입력창 제공)

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

### 3.1 복구 서비스 메서드 시그니처
```python
# [출처: tdms_core/p4_manager/services/backup_service.py — 직접 확인 후 기능 추가]
# [신규 정의 — 이 Task에서 복구 기능 추가 설계]

from typing import Dict, Any

class BackupService:
    def __init__(self):
        self.env_detector = EnvDetector()

    def get_env(self) -> str:
        """현재 실행 환경 감지 (dev, server, unknown)"""
        return self.env_detector.detect()

    def restore_backup(self, tag: str, filename: str, confirm_text: str) -> Dict[str, Any]:
        """
        개발 PC 로컬 DB를 스냅샷 백업 아카이브로부터 복구합니다.
        
        Args:
            tag: 백업이 저장된 하위 폴더 태그명
            filename: 복구 대상 백업 아카이브 파일명 (.tar.gz)
            confirm_text: 오작동 방지 확인 텍스트 (반드시 'RESTORE LOCAL DB'여야 함)
            
        Returns:
            Dict[str, Any]: 복구 결과 및 StartupValidator 정합성 검증 리포트
            
        Raises:
            PermissionError: 서버 PC 환경에서 호출된 경우
            ValueError: confirm_text가 'RESTORE LOCAL DB'와 일치하지 않는 경우
            FileNotFoundError: 지정된 백업 파일이 존재하지 않는 경우
            RuntimeError: 컨테이너 정지/기동, 압축 해제, 권한 교정, 혹은 DB 대기 타임아웃 발생 시
        """
        ...
```

### 3.2 복구 요청 데이터 모델 (Pydantic)
```python
# [신규 정의 — tdms_core/p4_manager/routers/manager.py에 추가]

from pydantic import BaseModel, Field

class RestoreRequest(BaseModel):
    tag: str = Field(..., description="백업 태그명")
    filename: str = Field(..., description="복구 대상 백업 파일명 (.tar.gz)")
    confirm_text: str = Field(..., description="이중 확인 텍스트 (RESTORE LOCAL DB)")
```

### 3.3 StartupValidator 및 ValidationReport 구조 대조
```python
# [출처: tdms_core/p1_shared/p1_shared/ops/startup_validator.py — 직접 확인]

@dataclass
class ValidationReport:
    db_name: str
    is_connected: bool = False
    missing_tables: list[str] = field(default_factory=list)
    low_row_tables: dict[str, tuple[int, int]] = field(default_factory=dict)
    volume_info: dict = field(default_factory=dict)
    hypertable_ok: bool = True

    @property
    def is_healthy(self) -> bool:
        ...

class StartupValidator:
    def __init__(self, pool: DbConnectionPool, backup_manager: BackupManager | None = None) -> None:
        ...
        
    def validate(
        self,
        db_name: Literal["kdms", "usdms"],
        expected_tables: list[str],
        min_row_counts: dict[str, int]
    ) -> ValidationReport:
        ...
```

---

## § 3a. 기존 기능 보존 (수정 Task에만 작성)

### 보존 인터페이스
- `BackupService.create_backup(tag: str = "manual") -> Dict[str, Any]` — 변경 불가, `routers/manager.py` 및 기존 단위 테스트에서 사용 중
- `BackupService.list_backups() -> List[Dict[str, Any]]` — 변경 불가, `routers/manager.py` 및 기존 단위 테스트에서 사용 중

### 회귀 테스트 케이스
```python
# [Tier 1 — 단위]
def test_create_backup_on_server_env_raises_permission_error_remains_unchanged(mocker):
    """기존의 서버 환경 백업 시도 시 PermissionError 발생 로직이 유지되는지 검증"""
    from tdms_core.p4_manager.services.backup_service import BackupService
    mocker.patch.object(BackupService, "get_env", return_value="server")
    
    service = BackupService()
    import pytest
    with pytest.raises(PermissionError):
        service.create_backup()
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **Tier 안내**:
> - Tier 1 (단위): DB/외부 의존성 없음 — 항상 실행
> - Tier 2 (격리 통합): mocker로 DB/API/Subprocess 대체 — 항상 실행
> - Tier 3 (실제 통합): 실 DB 필요, `@pytest.mark.integration` — `pytest --run-integration`으로만 실행

### 4.1 정상 동작 케이스 (Tier 2 / Tier 3)

```python
# [Tier 2 — 격리 통합]
def test_restore_backup_with_valid_parameters_executes_successfully(mocker):
    """
    [목적] 유효한 파일명, 경로, 이중 컨펌 텍스트가 제공되었을 때 정상적으로 
           컨테이너 중지 -> 압축 해제 -> 권한 교정 -> 컨테이너 기동 -> 검증 연동 흐름이 수행되는지 검증.
    [유도] subprocess.run 모킹, DbConnectionPool 및 StartupValidator를 적절히 모킹하여 
           에러 없이 결과 Dict를 반환하게 구현.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    from pathlib import Path
    
    # 1. 환경 및 파일 모킹
    mocker.patch.object(BackupService, "get_env", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.mkdir")
    
    # 2. subprocess 모킹 및 호출 순서 확인용
    mock_run = mocker.patch("subprocess.run")
    
    # 3. DB 접속 대기 루프 및 StartupValidator 모킹
    mocker.patch("time.sleep") # 대기 시간 스킵
    mocker.patch("psycopg2.connect")
    
    # DbConnectionPool 모킹
    mock_pool = mocker.MagicMock()
    mocker.patch("tdms_core.p4_manager.services.backup_service.DbConnectionPool", return_value=mock_pool)
    
    # StartupValidator 및 ValidationReport 모킹
    mock_report = mocker.MagicMock()
    mock_report.is_healthy = True
    mock_report.is_connected = True
    mock_report.missing_tables = []
    mock_report.low_row_tables = {}
    mock_report.volume_info = {"exists": True}
    mock_report.hypertable_ok = True
    
    mock_validator = mocker.MagicMock()
    mock_validator.validate.return_value = mock_report
    mocker.patch("tdms_core.p4_manager.services.backup_service.StartupValidator", return_value=mock_validator)
    
    service = BackupService()
    result = service.restore_backup(
        tag="manual",
        filename="physical_checkpoint_20260610_120000.tar.gz",
        confirm_text="RESTORE LOCAL DB"
    )
    
    assert result["status"] == "success"
    assert "validation_results" in result
    assert result["validation_results"]["kdms"]["is_healthy"] is True
    
    # subprocess 호출 내역 검증 (stop -> tar -> chown -> start 순)
    calls = [call[0][0] for call in mock_run.call_args_list]
    assert any("stop" in str(cmd) for cmd in calls)
    assert any("tar" in str(cmd) and "-xz" in str(cmd) for cmd in calls)
    assert any("chown" in str(cmd) for cmd in calls)
    assert any("start" in str(cmd) for cmd in calls)
```

### 4.2 경계값 케이스 (Tier 1)

```python
# [Tier 1 — 단위]
def test_restore_backup_with_empty_confirm_text_raises_value_error():
    """
    [목적] confirm_text가 빈 값일 때 즉각 ValueError를 던지는지 검증.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    service = BackupService()
    import pytest
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.restore_backup("manual", "physical_checkpoint_20260610_120000.tar.gz", "")
```

### 4.3 예외/오류 처리 케이스 (Tier 1)

```python
# [Tier 1 — 단위]
def test_restore_backup_on_server_env_raises_permission_error(mocker):
    """
    [목적] 운영 서버PC 환경인 경우 복구를 시도하면 PermissionError를 발생시켜 원천 차단하는지 검증.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    mocker.patch.object(BackupService, "get_env", return_value="server")
    
    service = BackupService()
    import pytest
    with pytest.raises(PermissionError, match="서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다"):
        service.restore_backup("manual", "physical_checkpoint_20260610_120000.tar.gz", "RESTORE LOCAL DB")

# [Tier 1 — 단위]
def test_restore_backup_with_invalid_confirm_text_raises_value_error():
    """
    [목적] confirm_text가 'RESTORE LOCAL DB'와 다르면 ValueError를 던지는지 검증.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    service = BackupService()
    import pytest
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.restore_backup("manual", "physical_checkpoint_20260610_120000.tar.gz", "RESTORE DB")

# [Tier 1 — 단위]
def test_restore_backup_with_non_existent_file_raises_file_not_found_error(mocker):
    """
    [목적] 지정한 백업 아카이브 파일이 존재하지 않는 경우 FileNotFoundError를 던지는지 검증.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    mocker.patch.object(BackupService, "get_env", return_value="dev")
    mocker.patch("pathlib.Path.exists", return_value=False)
    
    service = BackupService()
    import pytest
    with pytest.raises(FileNotFoundError, match="백업 아카이브 파일을 찾을 수 없습니다"):
        service.restore_backup("manual", "non_existent.tar.gz", "RESTORE LOCAL DB")
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
import os
from pathlib import Path

@pytest.mark.integration
def test_restore_backup_with_real_db_and_validation(mocker):
    """
    [목적] 실제 로컬 Docker DB 컨테이너들이 떠 있는 환경에서 임시 백업을 작성하고,
           이를 직접 restore_backup으로 복구한 뒤, StartupValidator 정합성 검증이 
           성공(is_healthy=True)을 보고하는지 실제 End-to-End 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    from tdms_core.p4_manager.services.backup_service import BackupService
    from tdms_core.p4_manager.config import settings
    
    # 1. 실제 백업 서비스 초기화 (실제 실행 환경 감지는 'dev'여야 함)
    service = BackupService()
    assert service.get_env() == "dev", "통합 테스트는 개발 PC(dev) 환경에서만 실행할 수 있습니다."

    # 2. 통합 테스트용 임시 백업 생성
    backup_result = service.create_backup(tag="integration_test")
    filename = backup_result["filename"]
    
    try:
        # 3. 실제 복구 수행 (컨테이너 중지 -> 압축해제 -> 복원 -> 재기동 -> 검증 연동)
        restore_result = service.restore_backup(
            tag="integration_test",
            filename=filename,
            confirm_text="RESTORE LOCAL DB"
        )
        
        # 4. 결과 단언
        assert restore_result["status"] == "success"
        assert "validation_results" in restore_result
        
        kdms_report = restore_result["validation_results"]["kdms"]
        usdms_report = restore_result["validation_results"]["usdms"]
        
        # 실제 데이터가 복원되었고, DB 접속이 이루어지는지 검증
        assert kdms_report["is_connected"] is True
        assert usdms_report["is_connected"] is True
        assert kdms_report["is_healthy"] is True
        assert usdms_report["is_healthy"] is True
        
    finally:
        # 생성된 테스트용 아카이브 정리
        backup_file = Path(settings.BACKUP_BASE_DIR) / "integration_test" / filename
        if backup_file.exists():
            backup_file.unlink()
        backup_dir = backup_file.parent
        if backup_dir.exists() and not any(backup_dir.iterdir()):
            backup_dir.rmdir()
```

### 4.5 프론트엔드 컴포넌트 유닛 테스트 설계 (Vitest)

```typescript
// [출처: tdms_core/p4_manager/frontend/src/components/__tests__/RestoreModal.spec.ts — 신규 작성]
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RestoreModal from '../RestoreModal.vue' // 실제 모달 경로에 맞춰 구현

describe('RestoreModal.vue', () => {
  it('이중 확인 텍스트가 정확히 RESTORE LOCAL DB일 때만 복구 실행 버튼이 활성화된다', async () => {
    const wrapper = mount(RestoreModal, {
      props: {
        isOpen: true,
        backupFilename: 'physical_checkpoint_20260610_120000.tar.gz'
      }
    })

    const input = wrapper.find('input[type="text"]')
    const button = wrapper.find('button.btn-confirm-restore') // 복구 승인 버튼

    // 초기 상태: 비활성화
    expect(button.element.disabled).toBe(true)

    // 잘못된 텍스트 입력 시: 비활성화 유지
    await input.setValue('RESTORE DB')
    expect(button.element.disabled).toBe(true)

    // 정확한 텍스트 입력 시: 활성화
    await input.setValue('RESTORE LOCAL DB')
    expect(button.element.disabled).toBe(false)
  })
})
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_restore_backup_with_valid_parameters_executes_successfully` | Tier 2 | 정상 | 모킹 환경에서 스냅샷 압축 해제, 컨테이너 정지/기동, 검증 연동 흐름 검증 |
| 2 | `test_restore_backup_with_empty_confirm_text_raises_value_error` | Tier 1 | 경계값 | confirm_text가 빈 값인 경우 ValueError 차단 검증 |
| 3 | `test_restore_backup_on_server_env_raises_permission_error` | Tier 1 | 예외 | 운영 서버 PC 환경에서 복구 차단 (403 대응) 검증 |
| 4 | `test_restore_backup_with_invalid_confirm_text_raises_value_error` | Tier 1 | 예외 | 이중 확인 텍스트가 불일치할 때 ValueError 검증 |
| 5 | `test_restore_backup_with_non_existent_file_raises_file_not_found_error` | Tier 1 | 예외 | 백업 파일이 없는 경우 FileNotFoundError 검증 |
| 6 | `test_restore_backup_with_real_db_and_validation` | Tier 3 | 실제 통합 | 실제 로컬 DB 가동 환경에서 복구 및 StartupValidator 자가 진단 정합성 검증 |
| 7 | `test_create_backup_on_server_env_raises_permission_error_remains_unchanged` | Tier 1 | 회귀 | T-008 기존 물리 백업 서버 환경 차단 회귀 방지 검증 |
| 8 | `RestoreModal.spec.ts 이중 확인 활성화 테스트` | 프론트엔드 | UI 단위 | 입력 텍스트에 따른 복구 버튼 활성화/비활성화 검증 |

**총 8개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.
이 섹션은 구현 방법을 지시하지 않으며, 참고용으로만 활용합니다.

- **기술 스택**: Python 3.12, FastAPI, pytest, TypeScript, Vue 3, Vitest
- **위키 참조 링크**:
  - `pjt_wiki/p1_shared_wiki/interfaces/startup_validator.md` — StartupValidator 시그니처 및 리포트 모델 활용
  - `pjt_wiki/p4_manager_wiki/environment.md` — 데이터 및 백업 기본 경로 설정 정보 확인
- **주의사항**:
  - **Docker 중지/기동 시 예외 처리**: 개발 PC의 Docker 데몬 연결 끊김 또는 특정 컨테이너가 이미 중지 상태이더라도 전체 프로세스가 에러로 멈추지 않도록 `docker stop` 명령어 실행 시 `check=False`로 처리하고 예외 로그를 기록해야 합니다.
  - **DB 커넥션 재시도 로직**: DB 컨테이너가 다시 기동된 즉시 uvicorn/fastapi 스레드가 포트에 달라붙으면 `psycopg2.OperationalError`가 발생할 수 있습니다. 복구 서비스 내부에서 `StartupValidator`를 연동하기 전, 최대 30초 동안 매 2초 간격으로 `SELECT 1` 검증 성공 시까지 커넥션 접속을 재시도(Retry)하는 루프를 구성해야 유연하게 통합됩니다.
  - **권한 교정**: 압축 해제 직후TimescaleDB 마운트 데이터 볼륨 디렉토리의 소유자가 root로 꼬여 DB 기동이 중단되는 문제를 예방하기 위해 `sudo chown -R 1000:1000` 권한 교정을 수행해야 합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 실제 통합 테스트 통과
- [ ] 프론트엔드 Vitest 유닛 테스트 전체 통과 (회귀 방지 포함)
- [ ] `p4_manager_pjt_tasks.md`의 T-009 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/tasks/task-009_walkthrough.md` 작성
