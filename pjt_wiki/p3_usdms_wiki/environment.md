# Sub Project 개발/운영 환경 (environment.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-04  
> **타입**: Type E (배경/환경 지식)  
> **공통 환경**: `parent_wiki/environment.md` 참조 (중복 기재 금지)

---

## 1. 가상환경

- **환경명**: `tdms_p3_env`
- **생성 방법**: `conda create -n tdms_p3_env python=3.12 -y`
- **활성화**: `conda activate tdms_p3_env`
- **requirements**: `tdms_core/p3_usdms/requirements.txt`

---

## 2. 주요 패키지 버전

> 실제 설치 버전 기재. 범위 표기 금지. (`pip show {패키지}`로 확인)

| 패키지 | 버전 | 용도 |
|---|---|---|
| fastapi | 0.110.0 | REST API 웹 서빙 및 라우터 |
| uvicorn | 0.28.0 | ASGI 웹 서버 실행 |
| psycopg2-binary | 2.9.9 | PostgreSQL DB 드라이버 및 DSN 커넥션 |
| requests | 2.31.0 | SEC EDGAR API 동기 호출 |
| yfinance | 0.2.38 | Yahoo Finance 메타데이터 보강 조회 |
| pandas | 2.2.0 | 가격 및 재무 데이터 가공 및 연산 |
| apscheduler | 3.10.4 | 일일 루틴 및 주간 백필 백그라운드 크론 스케줄링 |

---

## 3. 데이터 소스 및 외부 의존성

| 소스 | 접근 방법 | 갱신 주기 | 제약/한도 |
|---|---|---|---|
| SEC EDGAR | HTTPS REST (JSON) | 일일 마스터 동기화 및 공시 사실 수집 | 초당 최대 10회 호출 제한 (User-Agent 필수 설정) |
| KIS API | HTTPS REST (OAuth2) | 매일 일봉 시세 동기화 | 초당 호출 제한 및 OAuth 토큰 만료 주기 관리 |
| yfinance | API (HTTP) | 주간 미보강 메타데이터 수집 | 무차별 호출 시 IP 차단(Ban) 위협 (조회 간 1초 지연 슬립 필수) |

---

## 4. 설정 파일 및 환경변수

| 파일 | 경로 | git 포함 | 주요 내용 |
|---|---|---|---|
| `.env` | `tdms_core/p3_usdms/.env` | ❌ | `TDMS_ENV`, `SEC_USER_AGENT` <br> `DEV_USDMS_DB_HOST`/`PORT`/`NAME`/`USER`/`PASSWORD` <br> `SERVER_USDMS_DB_HOST`/`PORT`/`NAME`/`USER`/`PASSWORD` |
| `pyproject.toml` | `tdms_core/p3_usdms/pyproject.toml` | ✅ | 패키지 메타데이터 및 빌드 설정 |

---

## 5. DB/파일 저장 위치

| 종류 | 경로 | git 포함 | 비고 |
|---|---|---|---|
| TimescaleDB | `localhost:5433` (dev) / `server-ip:5433` | ❌ | TimescaleDB 데이터베이스 인스턴스 |
| 실행 리포트 | `tdms_core/p3_usdms/logs/` | ❌ | 일일 루틴 및 주간 백필 오케스트레이터의 결과 JSON 로그 |

---

## 6. 알려진 환경 이슈

| 이슈 | 발생 조건 | 해결법 |
|---|---|---|
| yfinance IP Block | 지연(sleep) 없이 대량 메타데이터 보강을 단시간 내 호출할 때 | `MasterEnricher` 내부에서 각 타겟당 1초의 Cooldown Sleep 강제 적용 및 차단 시 블랙리스트 자동 편입 |
| SEC User Agent Block | `SEC_USER_AGENT` 환경변수 누락 또는 비정상 포맷 지정 시 | `config.py` Startup 검증을 통해 구동 차단, 실 메일 주소를 포함하도록 규격 강제 |
| WSL2 바인드 마운트 동기화 유실 | WSL2 환경에서 도커 바인드 마운트 볼륨의 IO 정체 현상 발생 시 | DB 기동 시 StartupValidator를 통한 커넥션 및 스키마 실재 여부 조기 스캔 검증 수행 |