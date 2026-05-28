# Sub Project 개발/운영 환경 (environment.md)

> **Sub Project**: p2_kdms (한국 시장 데이터 백엔드)
> **마지막 업데이트**: 2026-05-28
> **타입**: Type E (배경/환경 지식)
> **공통 환경**: `parent_wiki/environment.md` 참조 (중복 기재 금지)

---

## 1. 가상환경

- **환경명**: `tdms_p2_env`
- **생성 방법**: `conda create -n tdms_p2_env python=3.12`
- **활성화**: `conda activate tdms_p2_env`
- **requirements**: `tdms_core/p2_kdms/requirements.txt`

---

## 2. 주요 패키지 버전

> 실제 설치 버전 기재. 범위 표기 금지. (`pip show {패키지}`로 확인)

| 패키지 | 버전 | 용도 |
|---|---|---|
| `fastapi` | >= 0.121.0 | REST API 프레임워크 |
| `pydantic-settings` | 최신 | .env 기반 Settings 클래스 |
| `psycopg2-binary` | 2.9.12 | PostgreSQL 드라이버 |
| `uvicorn` | 최신 | ASGI 서버 |
| `apscheduler` | 3.11.0 | 크론 기반 배치 스케줄러 |
| `pandas` | 최신 | FactorCalculator DataFrame 처리 |
| `lxml` | 최신 | XML/HTML 파싱 |
| `httpx` | 최신 | FastAPI TestClient |
| `pytest` | 최신 | 테스트 프레임워크 |
| `pytest-mock` | 최신 | Mock 지원 |
| `p1_shared` | editable (`-e ../p1_shared`) | 공통 모듈 |

---

## 3. 데이터 소스 및 외부 의존성

| 소스 | 접근 방법 | 갱신 주기 | 제약/한도 |
|---|---|---|---|
| KIS OpenAPI (한국투자증권) | REST API (Bearer Token) | 일 1회 (평일 17:00) | 초당 호출 제한 있음 (실전 0.08s, 모의 0.4s 지연 적용) |
| Kiwoom REST API | REST API (Bearer Token) | 분봉 백필 시 | 호출 제한 있음 (0.25s 기본 지연 적용) |
| pykrx / KRX | 공개 API | 일 1회 (시총) | 비인증, 안정성 제한 |

---

## 4. 설정 파일 및 환경변수

| 파일 | 경로 | git 포함 | 주요 내용 |
|---|---|---|---|
| `.env` | `tdms_core/p2_kdms/.env` | ❌ | DB 접속 정보, EnvDetector 변수 |
| `.env.example` | `tdms_core/p2_kdms/.env.example` | ✅ | 변수 목록 템플릿 |

**필수 환경변수 (Layer A — EnvDetector)**

| 변수 | 예시 | 설명 |
|---|---|---|
| `TDMS_ENV` | `dev` | 환경 식별자 |
| `DEV_HOSTNAME` | `roid-dev` | 개발PC 호스트명 |
| `SERVER_HOSTNAME` | `roid-server` | 서버 호스트명 |
| `DEV_IP` | `192.168.x.x` | 개발PC IP |
| `SERVER_IP` | `192.168.x.x` | 서버 IP |

**필수 환경변수 (Layer B — DB 접속)**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DEV_KDMS_DB_PASSWORD` | — | 개발 DB 비밀번호 |
| `SERVER_KDMS_DB_PASSWORD` | — | 서버 DB 비밀번호 |
| `DEV_KDMS_DB_PORT` | `5432` | 개발 DB 포트 |
| `SERVER_KDMS_DB_PORT` | `5432` | 서버 DB 포트 |

---

## 5. DB/인프라 저장 위치

| 종류 | 경로/설정 | 비고 |
|---|---|---|
| TimescaleDB | Docker: `kdms_timescaledb`, Port `5432` | `kdms_pgdata` 볼륨 (external: true) |
| 백업 파일 | `backups/kdms/` | `.env` 외부 경로 사용 금지 |
| FastAPI 포트 | `8000` | docker-compose 포트 매핑 |

---

## 6. 알려진 환경 이슈

> 해결법 또는 회피법이 있는 것만 등록.

| 이슈 | 발생 조건 | 해결법 |
|---|---|---|
| EnvDetector "unknown" 감지 실패 | `.env`에 TDMS_ENV/DEV_HOSTNAME 미설정 | `.env.example` 참조하여 변수 채우기 |
| FastAPI lifespan DB 검증 실패 | DB 미기동 또는 테이블 누락 | `check_db.py` 수동 실행으로 상태 확인 |
| conftest mock_lifespan 미적용 | pytest fixtures 미등록 | `tests/conftest.py`의 `autouse=True` fixture 확인 |
| KIS API 403 Forbidden 차단 | API 호출 딜레이 제어 누락 | `KisApiCore`에 안전 마진 스로틀 딜레이 도입 (`[[dec-004_kis_api_throttling_strategy.md]]` 참조) |
| 시가총액 bigint 오버플로우 롤백 | 비주식 상품 주식수 파싱 오차 | `daily_task.py` 수집 시 1,000억 주 초과 및 9경 초과값 `0` 보정 |