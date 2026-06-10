# Sub Project 개발/운영 환경 (environment.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-10 (T-008 완료)  
> **타입**: Type E (배경/환경 지식)  
> **공통 환경**: `parent_wiki/environment.md` 참조 (중복 기재 금지)

---

## 1. 가상환경
- **환경명**: `tdms_p4_env`
- **생성 방법**: `conda create -n tdms_p4_env python=3.12 -y`
- **활성화**: `conda activate tdms_p4_env`
- **requirements**: `tdms_core/p4_manager/requirements.txt` (API 모킹용 `respx`, 실시간 중계용 `websockets` 추가됨)
- **editable install**: `conda run -n tdms_p4_env uv pip install -e .`
- **프론트엔드 빌드 환경**: Node.js `v20` (Docker Build: `node:20-alpine`) / Package Manager: `npm`

---

## 2. 주요 패키지 버전

> 실제 설치 버전 기재. 범위 표기 금지. (`pip show {패키지}` 또는 `npm list {패키지}`로 확인)

### Backend Packages
| 패키지 | 버전 | 용도 |
|---|---|---|
| fastapi | 0.136.3 | REST API 웹 서비스 구축 및 헬스 체크 엔드포인트 |
| uvicorn | 0.49.0 | ASGI 웹 서버 실행 |
| psycopg2-binary | 2.9.12 | PostgreSQL DB 연결 드라이버 |
| requests | 2.34.2 | 동기 HTTP 요청 및 외부/로컬 테스트 호출 |
| pydantic-settings | 2.14.1 | 환경 변수 및 설정 데이터 인스턴스 검증 관리 |
| httpx | 0.28.1 | 비동기 HTTP 호출 및 백엔드 간 비동기 폴링 |
| pandas | 3.0.3 | 갭 체크 및 통계 등 테이블 지표 분석 연산 |
| websockets | 12.0 | 비동기 WebSocket 업스트림 연결 클라이언트 라이브러리 |
| pytest | 9.0.3 | TDD 단위/격리/통합 테스트 프레임워크 |
| respx | 0.23.1 | HTTP API 모킹 테스트 및 격리 검증용 툴 |

### Frontend Packages
| 패키지 | 버전 | 용도 |
|---|---|---|
| vue | 3.5.34 | 웹 UI 프레임워크 |
| axios | 1.7.9 | 백엔드 API와의 비동기 HTTP 통신 클라이언트 |
| pinia | 2.3.1 | 통합 상태 보관용 스토어 라이브러리 |
| vue-router | 4.5.0 | 단일 페이지 어플리케이션(SPA) 라우팅 |
| vite | 8.0.12 | 개발 서버 기동 및 프로덕션 번들러 |
| typescript | 6.0.2 | 타입 안정성 보장 및 린팅 컴파일러 |
| vitest | 3.0.5 | 프론트엔드 유닛 TDD 테스트 러너 |
| @vue/test-utils | 2.4.6 | Vue 컴포넌트 마운팅 및 돔 테스트 헬퍼 |
| jsdom | 26.0.0 | Vitest 구동용 가상 브라우저 Dom 환경 |

---

## 3. 데이터 소스 및 외부 의존성

| 소스 | 접근 방법 | 갱신 주기 | 제약/한도 |
|---|---|---|---|
| p2_kdms (백엔드) | HTTP API (포트 8000) | 실시간 (프록시 라우팅) | Nginx `/api/kr/` 리버스 프록시 연동 |
| p3_usdms (백엔드) | HTTP API (포트 8005) | 실시간 (프록시 라우팅) | Nginx `/api/us/` 리버스 프록시 연동 |
| p4_backend (백엔드) | HTTP API (포트 8010) | 실시간 (프록시 라우팅) | Nginx `/api/mgr/` 리버스 프록시 연동 |
| WebSocket logs | WS 프로토콜 | 실시간 (중계 프록시) | Nginx `/ws/logs/kr` 및 `us`를 P4 백엔드 `/api/mgr/ws/logs/*` 중계 경로로 대리 위임 |



---

## 4. 설정 파일 및 환경변수

| 파일 | 경로 | git 포함 | 주요 내용 |
|---|---|---|---|
| `.dockerignore` | `.dockerignore` | ✅ | 빌드 시 `data/`, `backups/`, `docs/`, `pjt_wiki/` 등의 배제 목록 관리 |
| `nginx.conf` | `tdms_core/p4_manager/nginx/nginx.conf` | ✅ | Nginx 리버스 프록시, 리졸버, rewrite 룰 및 WS 중계 설정 |
| `docker-compose.yml` | `tdms_core/p4_manager/docker-compose.yml` | ✅ | `p4_backend` 및 `p4_frontend`(Nginx 포트 80) 멀티 컨테이너 구성 및 외부 네트워크 `tdms-net` 지정 |
| `package.json` | `tdms_core/p4_manager/frontend/package.json` | ✅ | 프론트엔드 의존성 및 실행 스크립트(`build`, `test`) 정의 |
| `tsconfig.app.json` | `tdms_core/p4_manager/frontend/tsconfig.app.json` | ✅ | TypeScript 에일리어스(`@/*`) 및 컴파일 타겟 지시 규칙 정의 |
| `vite.config.ts` | `tdms_core/p4_manager/frontend/vite.config.ts` | ✅ | Vitest `jsdom` 환경 및 paths 별칭 resolve 규칙 매핑 |
| `.env` | `.env` (루트) | ❌ | 공통 환경변수 (`SCHEDULE_KDMS_*`, `SCHEDULE_USDMS_*` 등) 및 DB 물리 경로(`data_path` = `"/app/data"`), 백업 보관 경로(`BACKUP_BASE_DIR` = `"/app/backups"`) 로드 |

---

## 5. DB/파일 저장 위치

| 종류 | 경로 | git 포함 | 비고 |
|---|---|---|---|
| DB 백업 아카이브 | `/app/backups/` | ❌ | 백업 실행(POST `/backup`) 시 생성되는 `tar.gz` 백업 아카이브가 저장되는 물리 경로 |
| TimescaleDB 볼륨 | `/app/data/` | ❌ | 백업 대상이 되는 실물 데이터 볼륨 마운트 경로 (kdms_db, usdms_db 수록) |

---

## 6. 알려진 환경 이슈

> 해결법 또는 회피법이 있는 것만 등록. 해결된 이슈는 Lint 시 제거.

| 이슈 | 발생 조건 | 해결법 |
|---|---|---|
| **Upstream 호스트 미조인으로 인한 Nginx 기동 불가** | Nginx 컨테이너 부팅 시, 연동 백엔드 컨테이너(`p2_kdms`, `p3_usdms`)가 가동 전이거나 도커 DNS에 등록되지 않은 경우 Nginx가 `upstream host not found` 에러로 크래시 발생 | `nginx.conf` 내에 도커 내장 DNS(`resolver 127.0.0.11 valid=10s;`)를 정의하고, `set $variable host;` 구문과 `rewrite ^... break;`를 적용하여 런타임에 동적으로 대상을 Resolve하도록 구성합니다.<br>*(주의: `set` 지시어는 `rewrite ... break;`보다 먼저 수행되도록 배치되어야 함)* |
| **도커 백엔드 기동 시 모듈 임포트 실패 (P4ERR-001)** | `p4_backend` 컨테이너 기동 시 상위 `tdms_core` 패키지를 찾지 못해 `ModuleNotFoundError: No module named 'tdms_core'` 에러가 나면서 무한 재기동 루프에 빠짐 | `backend.Dockerfile` 내부에 환경 변수 `ENV PYTHONPATH="/app"`을 설정하여 파이썬 런타임이 패키지 루트를 항상 찾을 수 있도록 보완합니다. |
| **TypeScript 6.0 빌드 시 tsconfig.json 내 baseUrl 감쇄 에러 (TS5101)** | `tsconfig.app.json` 내에 구식 `"baseUrl": "."` 설정이 남아 있는 경우 컴파일 시 `error TS5101` 빌드 에러 발생 | 현대적 TypeScript 에일리어스 해석법에 따라 `"baseUrl": "."` 속성을 완전히 제거하고 `"paths"`의 상대적 경로 매핑(`"@/*": ["./src/*"]`) 정보만 기재하여 컴파일러가 config 파일 폴더를 기준으로 resolve하게 설계합니다. |
| **TypeScript 빌드 시 미사용 변수 에러 (TS6133)** | `tsconfig.app.json` 내에 `"noUnusedLocals": true` 옵션이 켜져 있는 상태에서 테스트 코드(예: `DashboardView.spec.ts`)에서 임포트한 `vi` 등의 라이브러리 객체를 사용하지 않으면 `TS6133` 에러와 함께 빌드가 차단됨 | 소스 코드 상에서 실제 호출되지 않는 미사용 변수 및 라이브러리 임포트 구문을 완전히 제거하여 정적 분석 빌드가 통과되도록 보완합니다. |