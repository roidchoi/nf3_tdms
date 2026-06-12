# Task-010: DB 물리 동기화 연동 및 감사 리포팅

> **Sub Project**: p4_manager
> **PRD 근거**: F-14, F-15, F-16
> **작성일**: 2026-06-11
> **의존 Task**: T-009

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p1_shared_wiki/environment.md` | ✅ 확인 |
| PhysicalSyncManager 시그니처 | `pjt_wiki/p1_shared_wiki/interfaces/physical_sync_manager.md` | ✅ 확인 |
| EnvDetector 시그니처 | `pjt_wiki/p1_shared_wiki/interfaces/env_detector.md` | ✅ 확인 |
| p4_manager 백업 서비스 구조 | `tdms_core/p4_manager/services/backup_service.py` 직접 확인 완료 | ⚠️ 직접 확인 |
| p4_manager 라우터 구조 | `tdms_core/p4_manager/routers/manager.py` 직접 확인 완료 | ⚠️ 직접 확인 |
| WSL2 네트워크 우회 DNS 리졸브 | 이 Task에서 최초 설계 | 🆕 신규 |
| 사설 IP 대역 비동기 자동 탐색 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

개발 PC와 서버 PC 간의 대용량 TimescaleDB 물리적 동기화(Pull/Push)를 안전하게 처리할 수 있는 백엔드 API 파이프라인 및 정밀 감사(Audit) 결과를 렌더링하기 위한 데이터 계약을 구축합니다. 
특히 API 비대화형 환경에서 발생하는 `sudo` 비밀번호 대기(Hang)를 원천 예방하고, DHCP 환경 하에서 WSL2 네트워크 스택의 DNS 제약(mDNS 리졸브 한계)을 윈도우 호스트 Powershell 우회 기법으로 타개하며, 수동/자동 IP 추적 및 갱신 API를 통해 운영 편의성과 안전성을 극대화합니다.

**구현 범위:**
- **IN**:
  1. `routers/manager.py` 내 동기화 및 IP 갱신/탐색용 REST API 엔드포인트 구현:
     - `POST /api/mgr/sync`: 물리 동기화 실행 (백그라운드 태스크)
     - `GET /api/mgr/sync/status`: 동기화 진행 상황 및 실시간 터미널 출력(최근 로그) 조회
     - `GET /api/mgr/network/detect-server`: 서버 PC IP 자동 탐색 (Powershell 리졸브 + C클래스 포트 스캔)
     - `POST /api/mgr/network/sync-ip`: .env 파일 내 DEV_IP 또는 SERVER_IP 갱신
     - `POST /api/mgr/network/test-connection`: 수동 IP 연결성 및 SSH 사전 검증
  2. `services/sync_service.py` 신규 구현:
     - `PhysicalSyncManager`를 구동하기 위한 `SyncConfig` 동적 생성 및 5단계 오케스트레이션 수행.
     - `sudo -n true` 명령을 로컬/원격지에 대해 실행하여 비밀번호 없는 권한 획득 여부를 사전 검증.
     - WSL2 가상 환경에서 `SERVER_HOSTNAME` 해석 실패를 우회하기 위해 `powershell.exe` 서브프로세스를 기동하여 윈도우 호스트 측 DNS에 쿼리하는 특화 리졸버 내장.
     - 비동기 `asyncio` TCP 소켓 통신을 이용해 C클래스 사설망 전체 대역에 대해 `/api/mgr/env`로 `"env": "server"`를 탐색하는 Auto-Discovery 탐색 모듈 구축.
     - 물리 동기화 완료 후 `audit_deep` 또는 `audit_usdms` 감사 도구를 비동기 호출하고, 결과를 가공하여 JSON 형태로 보존 및 반환.
  3. `tests/test_sync_service.py` 신규 구현:
     - TDD에 기초한 Tier 1 단위 테스트 및 Tier 2 격리 통합 테스트 케이스 작성.
- **OUT**:
  - `PhysicalSyncManager` 내부의 데이터 전송 및 압축 알고리즘의 자체 개정 (기존 p1_shared 기능 그대로 사용).
  - 프론트엔드 UI/UX 소스 작성 (Vue 3 컴포넌트 마크업 및 스타일링은 별도 프론트엔드 Task로 위임).

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/services/sync_service.py` — 동기화 오케스트레이션, IP 탐색 및 .env 갱신 서비스
- `tdms_core/p4_manager/tests/test_sync_service.py` — 비동기 탐색, sudo 예외 및 동기화 흐름 단위/격리 통합 테스트

### 수정 대상 파일
- `tdms_core/p4_manager/routers/manager.py` — 신규 동기화 제어 및 네트워크 갱신 API 노출
- `tdms_core/p4_manager/config.py` — (필요 시) 동기화용 백업 경로 및 설정 매핑 보완

---

## § 3. 핵심 인터페이스

### 1) SyncRequest 및 API DTO 규격
```python
# [신규 정의 — 이 Task에서 최초 설계]
from pydantic import BaseModel, Field
from typing import Literal

class SyncRequest(BaseModel):
    market: Literal["kdms", "usdms"] = Field(..., description="대상 시장")
    direction: Literal["pull", "push"] = Field(..., description="동기화 방향")
    confirm_text: str = Field(..., description="이중 컨펌 입력값 (PULL FROM SERVER 또는 PUSH TO SERVER)")

class SyncIPRequest(BaseModel):
    target: Literal["dev", "server"] = Field(..., description="갱신 대상 변수")
    ip: str = Field(..., description="새로운 IP 주소")

class ConnectionTestRequest(BaseModel):
    ip: str = Field(..., description="연결성 검증 대상 IP 주소")
    port: int = Field(8000, description="백엔드 포트 번호")
```

### 2) SyncService 인터페이스
```python
# [신규 정의 — 이 Task에서 최초 설계]
from typing import Dict, Any, Literal

class SyncService:
    def __init__(self) -> None:
        """EnvDetector 로드 및 Uvicorn/FastAPI 백그라운드 태스크 연동 준비"""
        ...

    def get_sync_status(self) -> Dict[str, Any]:
        """
        현재 진행 중인 백그라운드 동기화 상태 및 로그 버퍼 반환.
        Returns:
            {"status": "IDLE"|"RUNNING"|"SUCCESS"|"ERROR", "logs": [...], "error_message": str}
        """
        ...

    def run_sync_task(self, market: Literal["kdms", "usdms"], direction: Literal["pull", "push"], confirm_text: str) -> Dict[str, Any]:
        """
        물리 동기화 트리거 및 사전 검증.
        1. confirm_text 매치 검증 (PULL FROM SERVER / PUSH TO SERVER)
        2. env 감지 (server 환경에서 push 수신 쓰기 행위 차단 -> 403)
        3. 로컬 및 원격지 sudo -n true 검증 -> 실패 시 무인화 가이드 예외(412) 반환
        4. 비동기 백그라운드 스레드로 PhysicalSyncManager 구동
        Raises:
            ValueError: confirm_text 오류 시
            PermissionError: 운영서버 쓰기 시도(403) 시
            RuntimeError: sudo 검증 실패(412) 시
        """
        ...

    def get_audit_report(self, market: Literal["kdms", "usdms"]) -> Dict[str, Any]:
        """
        동기화 완료 후 audit_deep 또는 audit_usdms 스크립트를 비동기로 기동하여 데이터를 JSON으로 정규화 파싱.
        Returns:
            감사 정합성 통계 리포트 딕셔너리
        """
        ...

    def detect_server_ip(self) -> Dict[str, Any]:
        """
        개발 PC 단에서 서버 IP 불일치 시 서버 IP 추적.
        1. SERVER_HOSTNAME 로드 후 powershell.exe 호출 우회 DNS 리졸브 시도
        2. 실패 시, 개발 PC IP 대역 (C클래스 .1 ~ .254) 비동기 포트 스캔 (Port 8000/80)
        3. /api/mgr/env API를 던져 {"env": "server"}를 응답하는 IP 색출
        Returns:
            {"server_ip": str | None, "method": "dns"|"scan"|"failed"}
        """
        ...

    def sync_ip_in_env(self, target: Literal["dev", "server"], new_ip: str) -> Dict[str, Any]:
        """
        .env 파일을 정규표현식으로 로드하여 DEV_IP 또는 SERVER_IP 값을 new_ip로 갱신 적용.
        """
        ...

    def test_connection(self, ip: str, port: int) -> Dict[str, Any]:
        """
        수동 입력된 IP 및 포트에 대해 TCP 소켓 검사 및 SSH 가용(preflight 수준) 테스트 수행.
        """
        ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **Tier 안내**:
> - Tier 1 (단위): DB/외부 의존성 없음 — 항상 실행
> - Tier 2 (격리 통합): mocker로 DB/API/Subprocess 대체 — 항상 실행
> - Tier 3 (실제 통합): 실 DB 및 원격 SSH 연결 필요, `@pytest.mark.integration` — `pytest --run-integration`으로만 실행

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위]
def test_sync_task_with_invalid_confirm_text_raises_value_error():
    """
    [목적] 잘못된 confirm_text 입력 시 즉각 ValueError를 발생시켜 동작을 원천 차단하는지 검증.
    [유도] confirm_text와 direction 매칭 조건 검사 수행 및 예외 처리 유도.
    """
    service = SyncService()
    import pytest
    with pytest.raises(ValueError, match="이중 확인 텍스트가 일치하지 않습니다"):
        service.run_sync_task(market="kdms", direction="pull", confirm_text="WRONG TEXT")
```

```python
# [Tier 2 — 격리 통합]
def test_sync_task_on_server_with_push_direction_raises_permission_error(mocker):
    """
    [목적] 운영 서버 PC(server)에서 Push(쓰기 수신) 명령이 유입될 때 403 Forbidden 오류에 해당하는 PermissionError를 발생시키는지 검증.
    [유도] EnvDetector.detect()가 'server'를 반환할 때 direction이 'push'이면 PermissionError를 일으키는 차단 로직 유도.
    """
    service = SyncService()
    mocker.patch.object(service.env_detector, "detect", return_value="server")
    
    import pytest
    with pytest.raises(PermissionError, match="서버 PC는 로컬 동기화 수신 쓰기 동작을 허용하지 않습니다"):
        service.run_sync_task(market="kdms", direction="push", confirm_text="PUSH TO SERVER")
```

```python
# [Tier 2 — 격리 통합]
def test_sync_sudo_verification_failure_raises_runtime_error(mocker):
    """
    [목적] sudo -n true 검사 결과 비밀번호를 요구하는 상황(Status != 0)일 때, 412 오류용 RuntimeError 및 가이드라인 문구를 적절히 반환하는지 검증.
    [유도] subprocess.run의 returncode가 1인 모의 상황을 설정하여 예외 분기 구현 유도.
    """
    service = SyncService()
    # sudo -n true 검증이 실패하는 Mocking
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "sudo: a password is required"

    import pytest
    with pytest.raises(RuntimeError) as exc_info:
        service.run_sync_task(market="kdms", direction="pull", confirm_text="PULL FROM SERVER")
    
    assert "NOPASSWD" in str(exc_info.value)  # 무인화 명령어 가이드 포함 여부 검증
```

```python
# [Tier 2 — 격리 통합]
def test_detect_server_ip_via_powershell_dns_resolver(mocker):
    """
    [목적] WSL2 환경에서 SERVER_HOSTNAME을 받아 powershell.exe DNS 리졸버 호출 결과로 올바른 IP 주소를 리팩토링 및 획득하는지 검증.
    [유도] subprocess.run의 powershell.exe 호출 모의를 진행하여 표준 출력 파싱 성공 유도.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": "EDM-LAB-MD02"})
    
    # powershell.exe 결과 모의
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "192.168.35.176\n"
    
    # TCP 통신 검사 모의
    mocker.patch.object(service, "test_connection", return_value={"connected": True})

    res = service.detect_server_ip()
    assert res["server_ip"] == "192.168.35.176"
    assert res["method"] == "dns"
```

```python
# [Tier 2 — 격리 통합]
def test_detect_server_ip_via_async_port_scanning(mocker):
    """
    [목적] DNS 리졸브 실패 시, 로컬 IP 서브넷 대역을 훑는 비동기 포트 스캔을 수행하여 서버 PC를 정확히 색출해내는지 검증.
    [유도] asyncio TCP 커넥션과 HTTP 요청을 모킹하여 스캔 성공 처리 구현 유도.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": ""})
    
    # 개발 PC IP 모킹
    mocker.patch("p1_shared.utils.env_detector.get_local_ips", return_value=["192.168.35.105"])
    
    # 192.168.35.176 만 서버로 식별되도록 비동기 Mocking
    async def mock_scan_ips(*args, **kwargs):
        return "192.168.35.176"
        
    mocker.patch.object(service, "_async_scan_subnet", side_effect=mock_scan_ips)

    res = service.detect_server_ip()
    assert res["server_ip"] == "192.168.35.176"
    assert res["method"] == "scan"
```

```python
# [Tier 2 — 격리 통합]
def test_update_ip_in_env_file_modifies_dev_or_server_ip(tmp_path, mocker):
    """
    [목적] 특정 IP 갱신 API 호출 시 .env 파일 내의 타깃 IP 변수(DEV_IP 또는 SERVER_IP)만 정확하게 수정 보존하는지 검증.
    [유도] 임시 경로에 .env를 생성하고 정규표현식 매칭을 거쳐 갱신 로직을 관통시키는 흐름 유도.
    """
    service = SyncService()
    env_content = "DEV_IP=192.168.35.10\nSERVER_IP=192.168.35.20\n"
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)
    
    mocker.patch("tdms_core.p4_manager.config.settings.env_file_path", str(env_file))
    
    service.sync_ip_in_env(target="server", new_ip="192.168.35.176")
    
    updated_content = env_file.read_text()
    assert "SERVER_IP=192.168.35.176" in updated_content
    assert "DEV_IP=192.168.35.10" in updated_content  # 기존 다른 변수 유지 보존
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
def test_test_connection_with_invalid_ip_format_returns_error():
    """
    [목적] 잘못된 형식의 IP(예: 문자열 "abc") 입력 시 에러 객체를 즉시 안전 반환하는지 검증.
    """
    service = SyncService()
    res = service.test_connection(ip="abc", port=8000)
    assert res["connected"] is False
    assert "invalid" in res["message"].lower()
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 2 — 격리 통합]
def test_detect_server_ip_returns_failed_when_no_server_found(mocker):
    """
    [목적] DNS 및 대역 스캔까지 전부 실패하여 서버 PC를 탐색할 수 없을 때, 에러 크래시 없이 안전한 실패 규격을 반환하는지 검증.
    """
    service = SyncService()
    mocker.patch.dict("os.environ", {"SERVER_HOSTNAME": ""})
    mocker.patch("p1_shared.utils.env_detector.get_local_ips", return_value=["192.168.35.105"])
    
    async def mock_scan_ips_failed(*args, **kwargs):
        return None
    mocker.patch.object(service, "_async_scan_subnet", side_effect=mock_scan_ips_failed)

    res = service.detect_server_ip()
    assert res["server_ip"] is None
    assert res["method"] == "failed"
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest

@pytest.mark.integration
def test_physical_sync_preflight_check_against_real_target():
    """
    [목적] 실제 .env에 정의된 서버 및 개발 PC 설정을 가지고 PhysicalSyncManager의 preflight_check가 성공하는지 검증.
    [실행 조건] SSH 키 등록 완료 및 네트워크가 정상 연결된 상태에서 작동.
    """
    from p1_shared.ops.db_sync import PhysicalSyncManager, SyncConfig
    from p1_shared.utils.env_detector import EnvDetector
    
    detector = EnvDetector()
    profile = detector.load_env_profile()
    
    config = SyncConfig(
        db_name="kdms",
        direction="pull",
        source_ip=detector.get_peer_host(),
        target_ip="127.0.0.1",
        ssh_user=profile.get("ssh_user"),
        ssh_key_path=profile.get("ssh_key_path"),
        data_path=profile.get("data_path")
    )
    
    manager = PhysicalSyncManager(config)
    # 실제 preflight_check 성공 검증
    assert manager.preflight_check() is True
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_sync_task_with_invalid_confirm_text_raises_value_error` | Tier 1 | 예외 | 잘못된 컨펌 텍스트 입력 차단 |
| 2 | `test_sync_task_on_server_with_push_direction_raises_permission_error` | Tier 2 | 예외 | 운영 서버 PC에서 쓰기/수신 행위(Push) 403 거절 |
| 3 | `test_sync_sudo_verification_failure_raises_runtime_error` | Tier 2 | 예외 | 패스워드를 요구하는 sudo 환경 시 412 오류 및 무인화 가이드 반환 |
| 4 | `test_detect_server_ip_via_powershell_dns_resolver` | Tier 2 | 정상 | WSL2 환경에서 powershell.exe 호출을 통한 서버 DNS 리졸브 성공 |
| 5 | `test_detect_server_ip_via_async_port_scanning` | Tier 2 | 정상 | DNS 실패 시 C클래스 사설망 비동기 TCP 대역 스캔 성공 |
| 6 | `test_update_ip_in_env_file_modifies_dev_or_server_ip` | Tier 2 | 정상 | .env 파일 내 타깃 IP의 안전한 파싱 갱신 적용 |
| 7 | `test_test_connection_with_invalid_ip_format_returns_error` | Tier 1 | 경계값 | 잘못된 IP 형식 입력 시 에러 안전 반환 및 크래시 예방 |
| 8 | `test_detect_server_ip_returns_failed_when_no_server_found` | Tier 2 | 예외 | 서버 PC 탐색 실패 시 규격화된 null 반환 |
| 9 | `test_physical_sync_preflight_check_against_real_target` | Tier 3 | 실제 통합 | 실제 로컬/원격지 SSH 터널링 활성화 검증 |

**총 9개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

- **기술 스택**:
  - Python 3.12 (Conda 가상환경 `tdms_p1_env` 및 `p4_manager` 가상환경)
  - FastAPI, Pydantic, asyncio, subprocess, socket
- **위키 참조 링크**:
  - `pjt_wiki/p1_shared_wiki/interfaces/physical_sync_manager.md`
  - `pjt_wiki/p1_shared_wiki/interfaces/env_detector.md`
- **주의사항**:
  - **WSL2 한계 해결**: 리눅스 내부의 `socket.gethostbyname`을 절대 사용하지 말고, `powershell.exe` 서브프로세스를 기동하여 윈도우 네이티브 DNS를 호출하도록 구현해야 합니다.
  - **비동기 스캔 성능**: 254개 IP 대역을 순차 탐색하면 API 타임아웃이 발생하므로, `asyncio.gather` 및 `asyncio.open_connection(timeout=0.2)` 등을 활용해 전체 탐색을 3초 이내에 완료해야 합니다.
  - **비대화형 SSH**: `db_sync.py` 내 `subprocess` 호출 시 `sudo -n`을 통과하더라도 SSH 연결 시 호스트 키 확인 대기(`StrictHostKeyChecking`)가 걸릴 수 있으므로 `ssh -o StrictHostKeyChecking=no`가 설정되어 있는지 사전에 확인하십시오.

---

## § 6. 완료 기준

- [x] § 4의 단위 및 격리 통합 테스트(1~8번) 전체 통과 (`pytest tdms_core/p4_manager/tests/test_sync_service.py`)
- [x] `pytest --run-integration` 실행 시 9번 Tier 3 테스트 통과
- [x] `p4_manager_pjt_tasks.md` 내 `T-010` 상태를 `완료`로 업데이트
- [x] `docs/p4_manager/tasks/task-010_walkthrough.md` 결과 정리 문서 작성
