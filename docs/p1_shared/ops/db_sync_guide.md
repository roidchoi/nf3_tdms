# 물리적 DB 동기화 도구 (db_sync.py) 사용 가이드

본 문서는 개발PC(Local)와 서버PC(Remote) 간에 대용량 시계열 데이터베이스(TimescaleDB)를 100% 무결성으로 양방향 동기화하기 위한 `db_sync.py` 스크립트의 사용법과 원리를 안내합니다.

## 1. 개요 및 원리

`db_sync.py`는 기존의 `pg_dump` 기반 논리적 동기화가 가진 메모리 및 타임아웃 한계를 극복하기 위해 만들어진 **'물리적 스톱-앤-카피(Stop-and-Copy)'** 자동화 스크립트입니다.

### ⚙️ 동작 메커니즘 (5단계 파이프라인)
1.  **Preflight 점검**: 네트워크 및 SSH 접속 상태를 확인합니다.
2.  **Maintenance Mode**: 데이터 오염을 막기 위해 양측 PC의 DB 및 어플리케이션 컨테이너를 안전하게 중지(Stop)합니다.
3.  **SSH Pipeline 전송**: 대상 폴더(`data/kdms_db` 등)의 데이터를 실시간 `tar` 압축하여 중간 파일 생성 없이 SSH 파이프를 통해 상대방 PC에 직접 꽂아 넣습니다.
4.  **권한 교정**: 리눅스 사용자(UID) 충돌 방지를 위해, 데이터를 받은 PC의 폴더 권한을 호스트 유저(`1000:1000`)에 맞게 자동 교정(`chown`)합니다.
5.  **재기동**: 모든 전송이 완료되면 중지했던 컨테이너들을 즉시 재기동합니다.

---

## 2. 사용 방법

> **⚠️ 주의사항**
> 동기화(Pull/Push) 작업은 대상 PC의 데이터를 완전히 덮어쓰는(Overwrite) 파괴적인 작업입니다. 방향을 헷갈리지 않도록 주의하십시오.

동기화 스크립트는 **프로젝트 루트**에서 다음 명령어로 실행합니다.

### ⬇️ 서버의 최신 데이터를 개발PC로 가져올 때 (Pull)
서버에 적재된 최신 데이터를 로컬로 당겨와 개발 환경을 최신화합니다.

```bash
# KDMS (한국 주식) 가져오기
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction pull

# USDMS (미국 주식) 가져오기
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction pull
```

### ⬆️ 개발PC의 데이터를 서버로 밀어넣을 때 (Push)
초기 구축 등 로컬에서 깎은 데이터를 서버로 이식할 때 사용합니다.

```bash
# KDMS (한국 주식) 서버로 보내기
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction push

# USDMS (미국 주식) 서버로 보내기
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction push
```

*(실행 시 `yes`를 입력하라는 프롬프트가 나옵니다. 자동화 스크립트에 통합할 경우 `--yes` 플래그를 추가하여 생략할 수 있습니다.)*

---

## 3. 동기화 후 점검 방법 (Audit)

동기화가 완료된 후, 개발PC와 서버PC 간의 데이터가 100% 일치하는지 확인하려면 `p1_shared/ops/auditors/` 패키지에 준비된 검증 스크립트를 사용하십시오. 
스크립트는 자동으로 `.env`의 접속 정보를 읽어 로컬과 원격 DB 양쪽을 동시에 조회 및 대조합니다.

### 🚀 빠른 테이블 통계 비교 (KDMS)
`pg_class` 시스템 테이블을 이용해 락(Lock) 없이 1초 만에 양측 DB의 테이블 로우 수(추정치)와 컬럼 수를 비교합니다. 동기화 직후 일차적인 확인 용도로 적합합니다.
```bash
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_fast
```

### 🔍 정밀 데이터 무결성 검증 (KDMS)
로우 수를 정확하게 카운팅하고, Primary Key와 Index 구조의 일치 여부, 그리고 각 테이블의 첫 데이터와 마지막 데이터(최신일 등)를 뽑아내어 완벽히 동일한지 정밀 검사합니다.
```bash
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_deep
```

### 🇺🇸 미국 주식 전용 데이터 건수 검증 (USDMS)
미국 주식(USDMS)의 10개 핵심 테이블에 대해 양측 DB의 정확한 데이터 건수를 전수 대조합니다.
```bash
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_usdms
```

---

## 4. 자주 묻는 질문 (FAQ)

### Q. 동기화 후 윈도우 탐색기에서 `data/usdms_db` 폴더 접근이 안 됩니다.
이것은 에러가 아니라 Docker의 보안 메커니즘이 정상 작동하는 것입니다.
*   **이유**: `usdms_db` 컨테이너 내부는 보안상 UID `70(postgres)` 사용자를 사용합니다. 컨테이너가 켜질 때 폴더 주인을 `70`으로 바꾸고 접근을 차단(`700`)하기 때문에, 호스트 사용자(UID 1000)인 윈도우 탐색기가 거부당하는 것입니다.
*   **해결책**: 굳이 탐색기로 보고 싶으시다면 터미널에서 다음 ACL 명령으로 읽기 권한을 부여하세요.
    ```bash
    sudo setfacl -R -m u:$USER:rx ./data/usdms_db
    sudo setfacl -R -d -m u:$USER:rx ./data/usdms_db
    ```

### Q. `pg_dump` 백업과 무엇이 다른가요?
`pg_dump`는 데이터를 텍스트/바이너리 포맷으로 "논리적"으로 재해석하여 뽑아냅니다. 덩치가 큰(수십 GB) DB에서는 메모리가 터지거나 복원 시 제약 조건(FK)에 걸리기 쉽습니다. 반면 본 도구는 디스크에 저장된 **실제 데이터 블록 파일 자체를 통째로 복제**하므로 100% 무결성을 보장하며 훨씬 빠릅니다.

### Q. 스크립트 실행 중 에러가 나면 어떻게 복구하나요?
물리적 복제가 실패했을 경우(네트워크 단절 등), 해당 폴더(`data/kdms_db`)의 데이터가 불완전해져 컨테이너가 켜지지 않을 수 있습니다. 이때는 스크립트 실행 전 스케줄러가 남겨둔 `.dump` 백업 파일을 통해 수동 복원(`BackupManager` 활용)을 진행해야 합니다.
