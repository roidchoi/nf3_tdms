# 개발 환경 (environment.md)

> **Sub Project**: p1_shared
> **마지막 업데이트**: 2026-06-11 (서버 PC 리소스 정리 및 SSH/sudoers 무인화 가이드 수립 완료)

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
| `SCHEDULE_KDMS_DAILY_UPDATE` | 한국 시장 일일 가격 수집 배치 시각 | `17:10` 또는 `15:40` |
| `SCHEDULE_KDMS_FINANCIAL_UPDATE` | 한국 시장 분기 재무 수집 배치 시각 | `sat:14:00` |
| `SCHEDULE_KDMS_BACKFILL_MINUTE` | 한국 시장 분봉 백필 기동 간격 (분) | `10` |
| `SCHEDULE_USDMS_DAILY_ROUTINE` | 미국 시장 일일 루틴 기동 시각 | `wed,sat:07:30` |
| `SCHEDULE_USDMS_WEEKLY_MAINTENANCE` | 미국 시장 주간 백필 및 유지보수 시각 | `sat:09:00` |

---

## 5. Docker 컨테이너 구성 (Static IPs & Subnet)

도커 가상 스위치의 DNS 리졸버 오류를 원천 차단하기 위해, 사용자 정의 브리지 네트워크 `tdms-net`에 정적 서브넷 대역(`172.20.0.0/16`)을 설정하고 컨테이너마다 IP를 고정하여 통신 신뢰성을 극대화했습니다.

| 서비스명 | 컨테이너명 | 가상 IP | 포트 (호스트) | 이미지 / 빌드 소스 |
|---|---|---|---|---|
| `kdms_db` | `kdms_timescaledb` | `172.20.0.3` | `5432:5432` | timescale/timescaledb-ha:pg16 |
| `usdms_db` | `usdms_timescaledb` | `172.20.0.4` | `5433:5432` | timescale/timescaledb-ha:pg16 (digest 고정) |
| `p2_kdms` | `p2_kdms` | `172.20.0.5` | `-(8000)` | tdms_core/p2_kdms/backend.Dockerfile |
| `p3_usdms` | `p3_usdms` | `172.20.0.6` | `-(8005)` | tdms_core/p3_usdms/backend.Dockerfile |
| `p4_backend` | `p4_backend` | `172.20.0.7` | `-(8010)` | tdms_core/p4_manager/backend.Dockerfile |
| `p4_frontend` | `p4_frontend` | `172.20.0.8` | `80:80` | tdms_core/p4_manager/frontend.Dockerfile |

> ⚠️ **주의**: `.env` 물리 마운트(P4DEC-007 핫플러깅 구현)를 보호하기 위해 파일 마운트 `- ./.env:/app/.env` 규격을 그대로 보존합니다.

---

## 6. 알려진 환경 이슈

| 이슈 | 원인 | 해결법 |
|---|---|---|
| WSL2 IP 동적 변경 | DHCP 재할당으로 DEV_IP 불일치 | `EnvDetector.verify_dev_ip_sync()` 호출로 감지 → `.env` 수동 수정 |
| Docker 볼륨 권한(UID mismatch) | 물리 복제 후 UID 불일치 | `PhysicalSyncManager.fix_permissions()` 자동 교정 (1000:1000) |
| USDMS 폴더 탐색기 접근 불가 | Docker가 UID 70으로 폴더 잠금 | `sudo setfacl -R -m u:$USER:rx ./data/usdms_db` |
| SSH sudo 비밀번호 프롬프트 | 자동화 실행 차단 | `sudoers.d/tdms_sync` 1회 설정 (`[[p1_shared_wiki/decisions/dec-001_physical_sync.md]]`) |
| 도커 가상망 DNS/마운트 꼬임 | PC 재부팅 시 가상 DNS 해석 실패 및 볼륨 링크 로딩 지연 | restart 정책 `always`로 상향, 서비스별 `healthcheck` 대기, `env_detector.py` 내 DNS 해석 예외 시 고정 IP 폴백 메커니즘 연동 |
