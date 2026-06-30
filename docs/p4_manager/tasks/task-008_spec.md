# Task-008: DB 백업 실행 및 이력 관리 (개발 PC 백업 허브 모델)

> **Sub Project**: p4_manager (통합 관리 레이어)  
> **PRD 근거**: F-11 (물리 스냅샷 백업 실행 - 개발 전용), F-12 (백업 스냅샷 이력 조회 - 개발 전용), F-16 (환경 식별 및 오제어 차단 안전장치 - 공통)  
> **작성일**: 2026-06-10  
> **의존 Task**: T-007 (데이터 익스플로러 테이블 동적 미리보기)  

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.  
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.  

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| 환경 감지 모듈 | `pjt_wiki/p1_shared_wiki/codebase_map.md` -> `p1_shared.utils.env_detector` | ✅ 확인 |
| 물리 동기화 파이프라인 | `pjt_wiki/p1_shared_wiki/codebase_map.md` -> `p1_shared.ops.db_sync` | ✅ 확인 |
| 기존 API 라우팅 규격 | `pjt_wiki/p4_manager_wiki/interfaces/api_routing_map.md` | ✅ 확인 |
| P4 설정 변수 규격 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| 신규 백업 서비스 설계 | 이 Task에서 최초 설계 | 🆕 신규 |
| 신규 환경 정보 조회 API | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

개발 PC 환경에서 대용량 TimescaleDB의 무결성 손실 위험을 원천 방어하기 위해, `pg_dump`를 배제하고 **로컬 물리 데이터 디렉토리의 tar.gz 압축을 통한 물리 스냅샷 백업 서비스**를 구현합니다. 

이때 동일 빌드본이 올라가는 서버 PC(운영계)와의 조작 혼선 및 오제어를 물리적·논리적으로 차단하기 위해, **API 레벨의 서버 측 백업 생성 거절(403 Forbidden)**, **UI 레벨의 상단 환경 시각화 배지**, 그리고 **서버 PC 모드 시 백업 생성 버튼 비활성화**를 강건하게 결합합니다.

**구현 범위:**
- **IN**:
  - `p4_backend` 설정(`config.py`)에 백업 보관 폴더 및 보관 기한 환경변수 정의.
  - `p4_backend`에 환경 프로파일 정보 조회 API (`GET /api/mgr/env`) 추가.
  - `p4_backend`에 개발 PC 전용 물리 스냅샷 백업 생성 API (`POST /api/mgr/backup`) 추가. (서버 PC 감지 시 API에서 403 Forbidden 기각 처리)
  - `p4_backend`에 물리 스냅샷 이력 조회 API (`GET /api/mgr/backup/list`) 추가.
  - `p4_frontend` 글로벌 헤더(`AppHeader.vue`)에 실시간 접속 환경 식별 배지 추가 (개발: 녹색 배지, 서버: 적색 점멸 배지).
  - `p4_frontend` 백업 뷰(`BackupView.vue`)에서 서버 PC로 접속한 경우 스냅샷 생성 컨트롤 비활성화/숨김 처리 및 가이드라인 배너 표출.
- **OUT**:
  - 스냅샷을 이용한 로컬 복구 기능 (T-009로 위임).
  - 개발 PC ↔ 서버 PC 간 물리 동기화(Pull/Push) 파이프라인 및 감사 연동 (T-010으로 위임).

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/services/backup_service.py` — 개발 PC의 물리 데이터 폴더 압축 및 스냅샷 보관 관리를 담당하는 서비스 모듈
- `tdms_core/p4_manager/tests/test_backup.py` — 백업 및 환경 식별 API 검증을 위한 pytest 단위/격리 테스트 파일
- `tdms_core/p4_manager/frontend/src/stores/backupStore.ts` — 백업 스냅샷 이력 및 생성 비동기 상태를 보관하는 Pinia 스토어
- `tdms_core/p4_manager/frontend/src/views/BackupView.vue` — 스냅샷 생성 컨트롤(개발 전용), 백업 이력 테이블, 그리고 서버 PC 전용 안내 배너를 포함한 백업 화면
- `tdms_core/p4_manager/frontend/src/tests/BackupView.spec.ts` — 환경 인디케이터 배지 상태 및 서버 PC 환경 시 버튼 비활성화 동작을 검증하는 Vitest 컴포넌트 테스트

### 수정 대상 파일
- `tdms_core/p4_manager/config.py` — 백업 관련 환경변수(`BACKUP_BASE_DIR` 등) 및 호스트 데이터 마운트 경로 설정 추가
- `tdms_core/p4_manager/routers/manager.py` — `/env`, `/backup`, `/backup/list` 엔드포인트 라우트 핸들러 추가
- `tdms_core/p4_manager/frontend/src/components/layout/AppHeader.vue` — 접속 환경 유형(개발 PC / 서버 PC)을 시각적으로 상시 식별하게 해 주는 글로벌 헤더 배지 UI 추가

---

## § 3. 핵심 인터페이스

### 3.1. 환경 정보 조회 API (`GET /api/mgr/env`)
* **[신규 정의 — 구현 Agent가 아래 시그니처로 생성]**
* **역할**: `EnvDetector`를 활용해 판별된 현재 백엔드의 운영 환경 프로파일을 반환합니다.
* **반환 구조 (JSON)**:
```json
{
  "env": "dev" // "dev" | "server" | "unknown"
}
```

### 3.2. 물리 백업 실행 API (`POST /api/mgr/backup`)
* **[신규 정의 — 구현 Agent가 아래 시그니처로 생성]**
* **역할**: 개발 PC의 로컬 DB 물리 데이터를 압축하여 백업 파일로 보관합니다. (서버 PC에서는 즉시 기각)
* **입력 매개변수**:
  - `tag` (Query, Optional): 백업 식별용 태그 (기본값 `"manual"`)
* **반환 구조 (개발 PC에서 정상 백업 완료 시 - 200 OK)**:
```json
{
  "status": "success",
  "message": "Physical snapshot backup created successfully",
  "path": "/app/backups/manual/physical_checkpoint_20260610_113000.tar.gz",
  "filename": "physical_checkpoint_20260610_113000.tar.gz",
  "size_bytes": 12058044316
}
```
* **반환 구조 (서버 PC에서 호출 시 차단 - 403 Forbidden)**:
```json
{
  "status": "error",
  "message": "서버 PC는 로컬 스냅샷 백업 및 복구를 지원하지 않습니다. 백업은 개발 PC의 수시 Pull 동기화를 이용하십시오."
}
```

### 3.3. 백업 스냅샷 이력 조회 API (`GET /api/mgr/backup/list`)
* **[신규 정의 — 구현 Agent가 아래 시그니처로 생성]**
* **역할**: `BACKUP_BASE_DIR` 내에 보관된 `.tar.gz` 물리 스냅샷 아카이브 목록을 반환합니다.
* **반환 구조 (JSON)**:
```json
[
  {
    "path": "/app/backups/manual/physical_checkpoint_20260610_113000.tar.gz",
    "filename": "physical_checkpoint_20260610_113000.tar.gz",
    "tag": "manual",
    "created_at": "2026-06-10T11:30:00",
    "size_bytes": 12058044316,
    "verified": true
  }
]
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤, 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1. 환경 식별 및 백업 차단 정책 케이스 (Tier 2)

```python
# [Tier 2 — 격리 통합]
def test_get_env_returns_correct_profile_for_dev(mocker):
    """
    [목적] /api/mgr/env API 호출 시 EnvDetector가 감지한 'dev' 환경 프로파일을 정상 리턴하는지 검증
    [유도] EnvDetector.detect()가 "dev"를 반환할 때 {"env": "dev"}를 JSON으로 응답하게 유도
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    response = client.get("/api/mgr/env")
    assert response.status_code == 200
    assert response.json()["env"] == "dev"

# [Tier 2 — 격리 통합]
def test_post_backup_on_server_raises_403_forbidden(mocker):
    """
    [목적] 서버 PC 환경에서 백업 API 호출 시, I/O 및 오제어 차단을 위해 403 Forbidden과 경고 문구가 리턴되는지 검증
    [유도] EnvDetector.detect()가 "server"를 리턴할 시 403 HTTP 예외를 발생시키고 지정된 에러 메시지를 넘기도록 유도
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="server")
    response = client.post("/api/mgr/backup?tag=manual")
    assert response.status_code == 403
    assert "서버 PC는 로컬 스냅샷 백업" in response.json()["detail"]
```

### 4.2. 개발 PC 물리 백업 생성 및 목록 조회 케이스 (Tier 2)

```python
# [Tier 2 — 격리 통합]
def test_post_backup_on_dev_success(mocker, tmp_path):
    """
    [목적] 개발 PC 환경에서 백업 API를 트리거했을 때, 실제로 물리 디렉토리를 압축하여 스냅샷 파일을 보관소에 생성하는지 검증
    [유도] 
      - EnvDetector.detect() -> "dev" 모킹
      - config의 BACKUP_BASE_DIR를 임시 tmp_path로 세팅
      - subprocess.run을 모킹하여 tar 압축이 성공적으로 실행(returncode=0)되었음을 흉내 내며, 테스트 내에서 스냅샷 파일 실물을 생성
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    
    # 임시 백업 보관 디렉토리 생성 및 설정 오버라이드
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    mocker.patch("tdms_core.p4_manager.config.settings.BACKUP_BASE_DIR", str(backup_dir))
    mocker.patch("tdms_core.p4_manager.config.settings.data_path", str(tmp_path / "data"))
    
    # 임시 소스 데이터 폴더 생성
    (tmp_path / "data" / "kdms_db").mkdir(parents=True)
    (tmp_path / "data" / "usdms_db").mkdir(parents=True)

    # tar 명령 실행 시 실제 파일이 생성되는 것처럼 mock 처리
    def mock_tar_exec(*args, **kwargs):
        # 실제 검증용 더미 백업 파일 떨구기
        manual_dir = backup_dir / "manual"
        manual_dir.mkdir(exist_ok=True)
        dummy_file = manual_dir / "physical_checkpoint_20260610_113000.tar.gz"
        dummy_file.write_bytes(b"dummy_tar_content")
        
        # subprocess.run의 성공 응답 리턴
        mock_process = mocker.Mock()
        mock_process.returncode = 0
        return mock_process

    mocker.patch("subprocess.run", side_effect=mock_tar_exec)

    # API 실행
    response = client.post("/api/mgr/backup?tag=manual")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert "physical_checkpoint_" in res_data["filename"]
    assert (backup_dir / "manual" / res_data["filename"]).exists()

# [Tier 2 — 격리 통합]
def test_get_backup_list_success(mocker, tmp_path):
    """
    [목적] 로컬 스냅샷 디렉토리에 존재하는 tar.gz 파일 목록을 파싱하여 생성일시 및 용량 정보를 담은 이력 리스트를 반환하는지 검증
    [유도] 지정된 디렉토리의 파일들을 rglob하여 BackupInfo 규격의 JSON 배열로 올바르게 변환하게 유도
    """
    backup_dir = tmp_path / "backups"
    manual_dir = backup_dir / "manual"
    manual_dir.mkdir(parents=True)
    
    # 더미 백업 파일 생성
    dummy_file = manual_dir / "physical_checkpoint_20260610_113000.tar.gz"
    dummy_file.write_bytes(b"dummy_tar_content")
    
    mocker.patch("tdms_core.p4_manager.config.settings.BACKUP_BASE_DIR", str(backup_dir))
    
    response = client.get("/api/mgr/backup/list")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "physical_checkpoint_20260610_113000.tar.gz"
    assert data[0]["tag"] == "manual"
    assert data[0]["size_bytes"] == len(b"dummy_tar_content")
    assert data[0]["verified"] is True
```

### 4.3. 실제 통합 및 물리 아카이브 검증 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
from pathlib import Path

@pytest.mark.integration
def test_real_physical_backup_generation_on_dev():
    """
    [목적] 모킹 없이 실제 개발 PC(WSL2) 환경에서 로컬 DB 볼륨 디렉토리를 압축하여 physical_checkpoint_*.tar.gz가 정상 빌드되는지 실물 검증
    [실행 조건] 개발 PC 기동 및 호스트 데이터 경로 마운트 환경 필요. `pytest --run-integration`으로 실행.
    """
    # 1. 백업 실행 API 기동
    response = client.post("/api/mgr/backup?tag=integration_test")
    
    # 서버 PC에서 돌렸을 경우를 대비해 분기 단언
    env_resp = client.get("/api/mgr/env")
    current_env = env_resp.json()["env"]
    
    if current_env == "server":
        assert response.status_code == 403
    else:
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "success"
        
        # 2. 실제 파일 존재 및 크기가 0 초과인지 검증
        backup_file_path = Path(res_data["path"])
        assert backup_file_path.exists()
        assert backup_file_path.stat().st_size > 0
        
        # 3. 이력 목록 조회 API 연동 확인
        list_resp = client.get("/api/mgr/backup/list")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert any(b["filename"] == res_data["filename"] for b in list_data)
        
        # 4. 생성된 실물 테스트 파일 제거 (클린업)
        if backup_file_path.exists():
            backup_file_path.unlink()
```

---

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_get_env_returns_correct_profile_for_dev` | Tier 2 | 정상 | 환경 조회 시 EnvDetector 기반 프로파일 반환 검증 |
| 2 | `test_post_backup_on_server_raises_403_forbidden` | Tier 2 | 예외 | 서버 PC 접속 시 백업 API 요청을 403 Forbidden 기각 처리하는지 검증 |
| 3 | `test_post_backup_on_dev_success` | Tier 2 | 정상 | 개발 PC에서 물리 데이터 디렉토리를 압축하여 스냅샷을 보관소에 떨구는지 검증 |
| 4 | `test_get_backup_list_success` | Tier 2 | 정상 | 보관소 하위의 `.tar.gz` 이력을 추출하여 정상 리스트업하는지 검증 |
| 5 | `test_real_physical_backup_generation_on_dev` | Tier 3 | 실제 통합 | 모킹 없는 실환경 연동 하에서 물리 스냅샷 빌드 및 파일 생성 상태 전수 검증 |

**총 5개 테스트 — 전체 통과 시 Task 완료**  
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다. 이 섹션은 구현 방법을 지시하지 않으며, 참고용으로만 활용합니다.

### 5.1. 인프라 전제 조건 (호스트 데이터 디렉토리 마운트)
* **배경**: `p4_backend` 컨테이너 내부에서 개발 PC의 물리 DB 데이터 디렉토리에 접근해 압축해야 합니다.
* **조치**: `tdms_core/p4_manager/docker-compose.yml` 내 `p4_backend` 서비스 정의부에 아래 볼륨 마운트가 명시적으로 잡혀 있는지 확인하거나 수정하여 주입해야 합니다.
  ```yaml
  volumes:
    - ./backups:/app/backups   # 백업본 아카이브용
    - ../../data:/app/data     # 호스트의 kdms_db, usdms_db 실물 데이터 디렉토리
  ```
* **백업 대상 타겟**: `/app/data/kdms_db` 및 `/app/data/usdms_db`를 통째로 타겟팅하여 `tar -czf`로 묶어냅니다.

### 5.2. config.py 설정 변수
* `config.py`의 `Settings` 클래스에 아래 변수들을 기본값과 함께 정의하고, 이들은 `.env`에서 정의된 경우 오버라이딩될 수 있도록 Pydantic Settings 규격에 맞춰 결합합니다.
  ```python
  BACKUP_BASE_DIR: str = "/app/backups"
  data_path: str = "/app/data"
  ```

### 5.3. 프론트엔드 UI/UX 혼선 방지 설계 가이드
* **상단 배지 (AppHeader.vue)**: 
  * `axios.get("/api/mgr/env")`를 호출하여 수신된 `env` 값에 따라 헤더 중앙 배지의 색상 및 텍스트를 바인딩합니다.
  * `dev` 일 경우 녹색 `[🟢 개발 PC - 백업 허브 모드]` 렌더링.
  * `server` 일 경우 적색 점멸 CSS 애니메이션이 들어간 `[⚠️ 운영 서버 PC - 데이터 적재 모드]` 렌더링.
* **백업 뷰 버튼 비활성화 (BackupView.vue)**:
  * 백업 화면 마운트 시 `backupStore`에 정의된 `env`를 가져와서, `env === 'server'`인 경우 "스냅샷 백업 생성" 버튼 엘리먼트에 `:disabled="true"`를 부여하고, 마우스를 오버하면 차단 사유 가이드가 툴팁으로 뜨도록 제어합니다.
  * 또한 화면 최상단에 "본 환경은 운영 서버 PC이므로 로컬 백업 기능이 차단되어 있습니다. 백업 이력 조회만 가능하며 생성은 개발 PC에서만 허용됩니다." 배너 경고창을 배치합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 프론트엔드 Vitest 컴포넌트 테스트(`BackupView.spec.ts`) 전체 통과
- [ ] `p4_manager_pjt_tasks.md`의 T-008 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/tasks/task-008_walkthrough.md` 작성
