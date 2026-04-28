# KDMS 개발 환경 (environment.md)

> **프로젝트**: KDMS (Korea Data Management System)
> **원본 경로**: `migration_pjt/kdms_origin/`
> **마지막 업데이트**: 2026-04-28

---

## 1. 백엔드 환경

| 항목 | 값 |
|---|---|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI 0.121.1 |
| 서버 | Uvicorn 0.38.0 (ASGI, async) |
| DB 드라이버 | psycopg2-binary 2.9.11 |
| 데이터 처리 | pandas 2.3.3, numpy 1.26.4, pyarrow 22.0.0 |
| 스케줄러 | APScheduler 3.11.0 (AsyncIOScheduler) |
| 테스트 | pytest 8.4.2 |
| 환경 관리 | python-dotenv 1.1.1 |
| HTTP 클라이언트 | requests 2.32.5 |
| 로깅 | rich 14.2.0 |

### 주요 외부 데이터 라이브러리
| 라이브러리 | 버전 | 용도 |
|---|---|---|
| finance-datareader | >=0.9.80 | 주식 데이터 보조 수집 |
| pykrx | (requirements 미명시) | KRX 시총 데이터 수집 (Phase 8) |

---

## 2. 프론트엔드 환경

| 항목 | 값 |
|---|---|
| 프레임워크 | Vue 3.5.22 |
| 언어 | TypeScript 5.9 |
| 빌드 도구 | Vite 7.1.11 |
| 상태 관리 | Pinia 3.0.3 |
| 라우팅 | Vue Router 4.6.3 |
| HTTP 클라이언트 | Axios 1.13.2 (180s timeout) |
| 차트 | Chart.js 4.5.1 + vue-chartjs 5.3.3 |
| 린팅 | ESLint 9.37.0 |
| 포매팅 | Prettier 3.6.2 |
| Node 버전 | 20.19+ or 22.12+ |

---

## 3. 인프라

| 항목 | 값 |
|---|---|
| DB | TimescaleDB (PostgreSQL 16) |
| 컨테이너 | Docker + Docker Compose |
| 웹서버 | Nginx 1.25 (리버스 프록시 + 정적 파일) |
| Docker 네트워크 | `kdms-net` (bridge) |

### 포트 할당
| 포트 | 서비스 |
|---|---|
| 80 | Frontend (Nginx) |
| 8000 | Backend (FastAPI) [내부] |
| 5432 | Database (PostgreSQL) |

---

## 4. 필수 환경 변수 (.env)

```bash
# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=kdms_db
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# API Credentials
KIWOOM_APP_KEY=xxx
KIWOOM_APP_SECRET=xxx
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=xxx
```

> **주의**: `.env`는 절대 git에 커밋하지 않습니다 (`.gitignore` 등록됨)

---

## 5. 로컬 개발 실행 방법

```bash
# 1. DB 시작
docker-compose up db -d

# 2. 백엔드 실행 (hot reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 3. 프론트엔드 실행
cd frontend && npm install && npm run dev
# Dev server: http://localhost:5173
# API proxy: /api/* → http://127.0.0.1:8000
```

---

## 6. 알려진 환경 이슈

| 이슈 | 해결법 |
|---|---|
| `AsyncIOScheduler` vs `BackgroundScheduler` | 반드시 `AsyncIOScheduler` 사용 (FastAPI event loop와 호환) |
| TimescaleDB 커넥션 풀 고갈 | `ThreadedConnectionPool(min=5, max=20)` 파라미터 조정 |
| pykrx 비동기 미지원 | 별도 스레드에서 동기 호출 처리 |
