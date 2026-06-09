# Sub Project 개발/운영 환경 (environment.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-09  
> **타입**: Type E (배경/환경 지식)  
> **공통 환경**: `parent_wiki/environment.md` 참조 (중복 기재 금지)

---

## 1. 가상환경

- **환경명**: `tdms_p4_env`
- **생성 방법**: `conda create -n tdms_p4_env python=3.12 -y`
- **활성화**: `conda activate tdms_p4_env`
- **requirements**: `tdms_core/p4_manager/requirements.txt`
- **editable install**: `conda run -n tdms_p4_env uv pip install -e .`

---

## 2. 주요 패키지 버전

> 실제 설치 버전 기재. 범위 표기 금지. (`pip show {패키지}`로 확인)

| 패키지 | 버전 | 용도 |
|---|---|---|
| fastapi | 0.136.3 | REST API 웹 서비스 구축 및 헬스 체크 엔드포인트 |
| uvicorn | 0.49.0 | ASGI 웹 서버 실행 |
| psycopg2-binary | 2.9.12 | PostgreSQL DB 연결 드라이버 |
| requests | 2.34.2 | 동기 HTTP 요청 및 외부/로컬 테스트 호출 |
| pydantic-settings | 2.14.1 | 환경 변수 및 설정 데이터 인스턴스 검증 관리 |
| httpx | 0.28.1 | 비동기 HTTP 호출 및 백엔드 간 비동기 폴링 |
| pandas | 3.0.3 | 갭 체크 및 통계 등 테이블 지표 분석 연산 |
| pytest | 9.0.3 | TDD 단위/격리/통합 테스트 프레임워크 |

---

## 3. 데이터 소스 및 외부 의존성

| 소스 | 접근 방법 | 갱신 주기 | 제약/한도 |
|---|---|---|---|
| p2_kdms (백엔드) | HTTP API (포트 8000) | 실시간 (프록시 라우팅) | Nginx `/api/kr/` 리버스 프록시 연동 |
| p3_usdms (백엔드) | HTTP API (포트 8005) | 실시간 (프록시 라우팅) | Nginx `/api/us/` 리버스 프록시 연동 |
| p4_backend (백엔드) | HTTP API (포트 8010) | 실시간 (프록시 라우팅) | Nginx `/api/mgr/` 리버스 프록시 연동 |
| WebSocket logs | WS 프로토콜 | 실시간 (중계 프록시) | Nginx `/ws/logs/kr`, `/ws/logs/us` 중계 |

---

## 4. 설정 파일 및 환경변수

| 파일 | 경로 | git 포함 | 주요 내용 |
|---|---|---|---|
| `.dockerignore` | `.dockerignore` | ✅ | 빌드 시 `data/`, `backups/`, `docs/`, `pjt_wiki/` 등의 배제 목록 관리 |
| `nginx.conf` | `tdms_core/p4_manager/nginx/nginx.conf` | ✅ | Nginx 리버스 프록시, 리졸버, rewrite 룰 및 WS 중계 설정 |
| `docker-compose.yml` | `tdms_core/p4_manager/docker-compose.yml` | ✅ | `p4_backend` 및 `p4_frontend`(Nginx 포트 80) 멀티 컨테이너 구성 및 외부 네트워크 `tdms-net` 지정 |
| `.env` | `.env` (루트) | ❌ | 공통 환경변수 (`SCHEDULE_KDMS_*`, `SCHEDULE_USDMS_*` 등) 로드 |

---

## 5. DB/파일 저장 위치

| 종류 | 경로 | git 포함 | 비고 |
|---|---|---|---|
| 없음 | - | - | p4_manager는 상태를 유지하지 않는 무상태(Stateless) 아키텍처로 구현됨 |

---

## 6. 알려진 환경 이슈

> 해결법 또는 회피법이 있는 것만 등록. 해결된 이슈는 Lint 시 제거.

| 이슈 | 발생 조건 | 해결법 |
|---|---|---|
| **Upstream 호스트 미조인으로 인한 Nginx 기동 불가** | Nginx 컨테이너 부팅 시, 연동 백엔드 컨테이너(`p2_kdms`, `p3_usdms`)가 가동 전이거나 도커 DNS에 등록되지 않은 경우 Nginx가 `upstream host not found` 에러로 크래시 발생 | `nginx.conf` 내에 도커 내장 DNS(`resolver 127.0.0.11 valid=10s;`)를 정의하고, `set $variable host;` 구문과 `rewrite ^... break;`를 적용하여 런타임에 동적으로 대상을 Resolve하도록 구성합니다.<br>*(주의: `set` 지시어는 `rewrite ... break;`보다 먼저 수행되도록 배치되어야 함)* |