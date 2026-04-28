# USDMS 개발 환경 (environment.md)

> **프로젝트**: USDMS (US Data Management System)
> **원본 경로**: `migration_pjt/usdms_origin/`
> **마지막 업데이트**: 2026-04-28

---

## 1. 백엔드 환경

| 항목 | 값 |
|---|---|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| 서버 | Uvicorn (standard) |
| DB 드라이버 | psycopg2-binary, asyncpg |
| 데이터 처리 | pandas, numpy |
| 스케줄러 | APScheduler |
| 환경 관리 | python-dotenv |
| HTTP 클라이언트 | requests, aiohttp |
| HTML 파싱 | beautifulsoup4, lxml |
| 설정 관리 | pydantic-settings |
| 진행 표시 | tqdm |

### 주요 외부 데이터 라이브러리
| 라이브러리 | 용도 |
|---|---|
| yfinance | 메타데이터 보강 (Sector, Industry, MarketCap, Country) |
| SEC EDGAR API | 티커 마스터 + XBRL 재무 데이터 직접 수집 (무료) |

---

## 2. 인프라

| 항목 | 값 |
|---|---|
| DB | TimescaleDB (PostgreSQL) |
| 컨테이너 | Docker + Docker Compose |
| 가상환경 | `usdms_env` (conda) |

### 포트 할당 (KDMS와 공존 설계)
| 포트 | 서비스 |
|---|---|
| 5435 | USDMS Database (PostgreSQL) ← KDMS 5432와 충돌 없음 |
| 8005 | USDMS Backend (FastAPI) ← KDMS 8000과 충돌 없음 |

### Docker 네트워크
- KDMS: `kdms-net`
- USDMS: `usdms_net` (별도 브릿지 네트워크)

---

## 3. 필수 환경 변수 (.env)

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5435
POSTGRES_DB=usdms_db
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# SEC EDGAR (필수)
SEC_USER_AGENT=YourName your@email.com   # SEC 403 차단 방지

# KIS API (선택 - 레거시)
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=xxx
```

---

## 4. 운영 실행 방법

```bash
# 환경 활성화
conda activate usdms_env

# 일일 루틴 실행 (Step 1~6)
python ops/run_daily_routine.py

# 시스템 진단
python ops/run_diagnostics.py

# DB 백업
python ops/run_db_checkpoint.py phase5

# DB 락 긴급 해제
python ops/kill_db_locks.py
```

### Crontab 자동화 (미국 시장 마감 후)
```bash
# 매주 화-토 오전 07:00 실행 (미국 시장 월-금 데이터)
0 7 * * 2-6 /path/to/usdms_env/bin/python /path/to/usdms/ops/run_daily_routine.py >> logs/daily_cron.log 2>&1
```

---

## 5. 알려진 환경 이슈

| 이슈 | 해결법 |
|---|---|
| 8-K 공시만 있는 기간에 Gap Scan 반복 | `Blacklist`로 방어 + 중복 검사 로직으로 무한 루프 방지 |
| DB Lock Contention (Hypertable) | Chunk 단위 수정(1년), App Level Batch Commit, Connection Reset 강제 |
| TimescaleDB pg_restore 시 role 에러 | `role "readonly_analyst" does not exist` — 데이터 복원과 무관, 무시 가능 |
| SEC 403 Forbidden | `SEC_USER_AGENT` 헤더에 실제 연락처 이메일 설정 필수 |

---

## 6. DB 이관 절차 요약

> 상세: `migration_pjt/usdms_origin/docs/USDMS_migration_guide.md`

1. 개발 PC에서 `python ops/run_db_checkpoint.py migration_target` 으로 백업 생성
2. `.dump` 파일을 운영 PC의 `backups/` 폴더로 복사
3. 운영 PC에서 `docker-compose up -d timescaledb`
4. `docker exec -i usdms_db pg_restore -U postgres -d usdms_db -c --if-exists < backups/checkpoint_*.dump`
5. `python ops/run_diagnostics.py` 로 복원 검증
