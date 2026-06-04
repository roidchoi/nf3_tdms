# 개발 환경 (environment.md)

> **Sub Project**: p1_shared
> **마지막 업데이트**: 2026-05-14 (T-008 완료)

---

## 1. Conda 가상환경

| 항목 | 값 |
|---|---|
| **환경명** | `tdms_p1_env` |
| **Python** | 3.12 |
| **관리 도구** | Miniforge (Conda) + uv pip install |
| **활성화** | `conda activate tdms_p1_env` |
| **비대화형 실행** | `conda run -n tdms_p1_env python -m ...` |

> ⚠️ **필수 규칙**: 에이전트 자동 실행 시 `conda activate` 대신 반드시 `conda run -n tdms_p1_env <명령>` 사용. 비대화형 셸에서 activate가 동작하지 않음.

---

## 2. 설치된 패키지 (실제 버전)

| 패키지 | 버전 | 용도 |
|---|---|---|
| `psycopg2-binary` | 2.9.12 | PostgreSQL/TimescaleDB 연결 |
| `requests` | 2.33.1 | KIS/Kiwoom REST API 호출 |
| `python-dotenv` | 1.2.2 | .env 파일 로드 |
| `pytest` | 9.0.3 | 테스트 실행 |
| `pytest-mock` | 3.15.1 | Mock/Spy 기반 단위 테스트 |

---

## 3. Editable Install (서브프로젝트 연동)

`p1_shared`는 `editable install`로 배포되어 서브프로젝트에서 `from p1_shared.xxx import ...` 방식으로 참조된다.

```bash
# 각 서브프로젝트 환경에서 1회 실행
conda run -n tdms_p1_env uv pip install -e tdms_core/p1_shared/
```

---

## 4. 환경 설정 파일 (.env)

루트에 위치한 `.env` 파일로 환경별 접속 정보 관리. **Git 커밋 절대 금지**.

| 변수 | 설명 | 예시 |
|---|---|---|
| `TDMS_ENV` | 명시적 환경 지정 (최우선) | `dev` 또는 `server` |
| `DEV_HOSTNAME` | 개발PC 호스트명 | `ROID-PC` |
| `SERVER_HOSTNAME` | 서버PC 호스트명 | `EDM-LAB-MD02` |
| `DEV_IP` | 개발PC 내부망 IP | `192.168.35.205` |
| `SERVER_IP` | 서버PC 내부망 IP | `192.168.35.97` |
| `DEV_KDMS_DB_USER` | KDMS DB 사용자 | `roid` |
| `DEV_KDMS_DB_PASSWORD` | KDMS DB 비밀번호 | (비공개) |
| `DEV_KDMS_DB_PORT` | KDMS DB 포트 | `5432` |
| `DEV_KDMS_DB_NAME` | KDMS DB 이름 | `kdms_db` |
| `DEV_USDMS_DB_PORT` | USDMS DB 포트 | `5435` |
| `SSH_KEY_PATH` | SSH 개인키 경로 | `~/.ssh/tdms_sync_rsa` |

---

## 5. Docker 컨테이너 구성

| 컨테이너명 | DB | 포트 | 이미지 |
|---|---|---|---|
| `kdms_timescaledb` | kdms_db | 5432 | TimescaleDB 2.14.2 + PG16 |
| `usdms_db` | usdms_db | 5435 | TimescaleDB (별도 환경) |

> ⚠️ TimescaleDB 버전 불일치 주의: 개발PC 2.14.2, 과거 서버PC에서 2.15.0 불일치 발생 → **이미지 Digest 고정으로 해결** (`[[p1_shared_wiki/decisions/dec-001_physical_sync.md]]`)

---

## 6. 알려진 환경 이슈

| 이슈 | 원인 | 해결법 |
|---|---|---|
| WSL2 IP 동적 변경 | DHCP 재할당으로 DEV_IP 불일치 | `EnvDetector.verify_dev_ip_sync()` 호출로 감지 → `.env` 수동 수정 |
| Docker 볼륨 권한(UID mismatch) | 물리 복제 후 UID 불일치 | `PhysicalSyncManager.fix_permissions()` 자동 교정 (1000:1000) |
| USDMS 폴더 탐색기 접근 불가 | Docker가 UID 70으로 폴더 잠금 | `sudo setfacl -R -m u:$USER:rx ./data/usdms_db` |
| SSH sudo 비밀번호 프롬프트 | 자동화 실행 차단 | `sudoers.d/tdms_sync` 1회 설정 (`[[p1_shared_wiki/decisions/dec-001_physical_sync.md]]`) |
