# Interface: PhysicalSyncManager (db_sync.py)

> **파일**: `tdms_core/p1_shared/p1_shared/ops/db_sync.py`
> **Task**: T-008 (T-009 통합 흡수)
> **Graphify God Node**: 20 edges
> **관련**: `[[p1_shared_wiki/interfaces/env_detector.md]]`, `[[p1_shared_wiki/decisions/dec-001_physical_sync.md]]`

---

## 데이터클래스 및 클래스 시그니처

```python
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
    def __init__(self, config: SyncConfig) -> None: ...

    def preflight_check(self) -> bool:
        """SSH 접속 및 대상 디렉토리 유효성 검사. 실패 시 False 반환."""

    def stop_containers(self) -> None:
        """로컬 및 원격 DB 컨테이너 중지 (Maintenance Mode 진입)."""

    def start_containers(self) -> None:
        """로컬 및 원격 DB 컨테이너 재기동."""

    def transfer_data(self) -> bool:
        """tar + SSH 파이프라인으로 물리 데이터 전송. Safe 2-Step 방식."""

    def fix_permissions(self) -> None:
        """대상 디렉토리 권한 교정 (chown 1000:1000)."""

    def execute(self) -> bool:
        """5단계 파이프라인 전체 실행: preflight → stop → transfer → fix → start"""
```

---

## 실행 방법 (CLI)

```bash
# Pull: 서버의 최신 데이터를 개발PC로 복제
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction pull

# Push: 개발PC 데이터를 서버로 복제
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction push

# 확인 없이 자동화 실행
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction pull --yes
```

---

## 핵심 물리 전송 명령 (Pull 기준)

```bash
# tar + SSH 파이프 — 중간 파일 생성 없이 실시간 전송
ssh -i {key} {user}@{server_ip} \
  "sudo tar -czf - -C /path/to/data/{db_name}_db ." \
  | sudo tar -xzf - -C ./data/{db_name}_db
```

---

## 5단계 파이프라인

| 단계 | 메서드 | 설명 |
|---|---|---|
| 1. Preflight | `preflight_check()` | SSH 접속 검증 (`echo SSH_OK`) |
| 2. Stop | `stop_containers()` | 양측 DB 컨테이너 중지 |
| 3. Transfer | `transfer_data()` | tar + SSH 파이프 물리 전송 |
| 4. Permission | `fix_permissions()` | `chown 1000:1000` 권한 교정 |
| 5. Start | `start_containers()` | 양측 컨테이너 재기동 |

---

## sudo 무인화 (자동화 필수 설정)

```bash
# 개발PC & 서버PC 양쪽에서 1회 실행
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/tar, /usr/bin/rm, /usr/bin/chown, /usr/bin/docker" \
  | sudo tee /etc/sudoers.d/tdms_sync
```

---

## 감사 도구 (동기화 후 검증)

```bash
# 빠른 통계 비교 (락 없음, 1초 내)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_fast

# 정밀 무결성 검증 (행 수 정확 카운트 + PK/Index + 첫/끝 행)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_deep

# USDMS 전용 (10개 테이블 전수 대조)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_usdms
```
