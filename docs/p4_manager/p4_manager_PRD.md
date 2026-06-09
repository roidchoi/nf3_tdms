# p4_manager PRD — 통합 관리 레이어

> **버전**: v1.0 | **작성일**: 2026-04-28
> **참조 원본**: `migration_pjt/kdms_origin/frontend/` (KDMS Vue3 SPA)
> **상위 PRD**: `docs/parent/tdms_PRD.md`
> **의존 시스템**: `p2_kdms` (REST API), `p3_usdms` (REST API)

---

## 1. 목적 및 범위

p4_manager는 p2_kdms와 p3_usdms를 **하나의 화면에서 통합 모니터링·제어**하는 관리 레이어다.

### 핵심 목표
1. 두 시스템(KR/US)의 수집 상태를 단일 대시보드에서 실시간 확인
2. 태스크 수동 실행, 스케줄 관리, 헬스체크를 통합 UI에서 제공
3. DB 백업·복구 절차를 UI로 관리 (안전 운영의 핵심)
4. KDMS 원본 Vue3 프론트엔드 구조를 기반으로 US 시스템을 통합 확장

### 범위 제외
- 직접적인 데이터 수집 로직 없음 (p1, p2에 위임)
- p1·p2 DB에 직접 접근하지 않음 (**REST API 전용** 연결)

---

## 2. 시스템 연결 구조

```
p4_manager
├── Frontend (Vue3 SPA, Port 80)
│   └── Nginx → /api/kr/* → p2_kdms:8000
│               /api/us/* → p3_usdms:8005
│               /api/mgr/* → p4 Backend:8010
│
└── Backend (FastAPI, Port 8010)
    ├── /api/mgr/backup   → BackupManager (p1_shared)
    ├── /api/mgr/status   → p2, p3 헬스 집계
    └── /ws/logs/kr|us    → p2/p3 WebSocket 프록시
```

### API 라우팅 원칙
- **`/api/kr/`** → p2_kdms 엔드포인트로 프록시
- **`/api/us/`** → p3_usdms 엔드포인트로 프록시
- **`/api/mgr/`** → p4 자체 백엔드 (백업/복구/통합 상태)
- Frontend에서 시장 접두사만 바꾸면 동일 API 구조 재사용 가능

---

## 3. 기능 요구사항

### 3.1 통합 대시보드

#### F-01: 시스템 상태 개요
- KR(p1) / US(p2) 각각의 수집 상태를 카드로 표시
- 표시 항목: 마지막 수집 시각, 마지막 성공/실패 태스크, 데이터 최신성
- 자동 폴링: 30초 간격 (`/api/kr/admin/tasks/status`, `/api/us/admin/tasks/status`)

#### F-02: 태스크 상태 모니터링
- KR/US 탭 분리 또는 시장별 컬러 구분 (KR: 파란색, US: 빨간색)
- 각 태스크(일일 루틴, 재무 업데이트, 백필 등)의 상태(대기/실행중/완료/실패) 표시
- 실패 태스크: 에러 메시지 툴팁 표시

#### F-03: 수동 태스크 실행
- 각 태스크 카드에 "즉시 실행" 버튼 제공
- 실행 요청: `POST /api/kr/admin/tasks/{task_id}/run`
- 실행 중 버튼 비활성화 + 스피너 표시

---

### 3.2 실시간 로그 터미널

#### F-04: WebSocket 로그 스트리밍
- 화면 하단 또는 별도 탭에 터미널 스타일 로그 패널
- KR/US 탭 전환으로 각 시스템 로그 분리 표시
- 연결: `/ws/logs/kr` (→ p2_kdms WebSocket 프록시 중계), `/ws/logs/us` (→ p3_usdms WebSocket 프록시 중계)
- 백엔드(`proxy_ws.py`)에서 각 타깃 백엔드의 WebSocket을 안전하게 수용하고 프론트엔드로 중계(Proxy)하는 비동기 프록시 터널링 보장
- 로그 레벨별 색상 구분: INFO(흰색), WARNING(노란색), ERROR(빨간색)
- 성능 및 메모리 관리를 위해 KR/US 각각 독립된 로그 버퍼(최대 500줄)를 유지하며, 초과 시 상단부터 제거

---

### 3.3 스케줄 관리

#### F-05: 스케줄 조회 및 수정
- KR/US 스케줄 목록을 시장별 탭으로 표시
- 각 스케줄: Job ID, 실행 주기, 다음 실행 예정 시각, 활성화 상태
- 수정 모달: 실행 시각 변경, 활성화/비활성화 토글
- 요청: `GET/PUT /api/kr/admin/schedules`, `GET/PUT /api/us/admin/schedules`

---

### 3.4 헬스 모니터링

#### F-06: 데이터 신선도 확인
- 각 주요 테이블(OHLCV, 재무, 가치평가 등)의 최신 데이터 날짜 표시
- 기준 날짜 대비 지연 일수 시각화 (신호등: 녹색/노랑/빨강)
- 요청: `GET /api/kr/health/freshness`, `GET /api/us/health/freshness`

#### F-07: 갭 탐지
- 날짜 범위 입력 → 수집 갭이 있는 날짜 목록 조회
- KR/US 각각 조회 가능
- 갭 날짜 목록을 캘린더 또는 테이블로 표시

#### F-08: 마일스톤 관리 (KR 전용, p1 기능)
- `system_milestones` 테이블 기반 이정표 타임라인 표시
- 신규 마일스톤 생성 모달 제공

#### F-09: 블랙리스트 조회 (US 전용, p3 기능)
- `us_collection_blacklist` 현황 테이블 표시
- 차단 사유 코드별 건수 집계
- 개별 CIK 차단 해제 버튼 제공 및 해제 API 연동 (`POST /api/us/admin/blacklist/release` 프록시 호출)

---

### 3.5 데이터 익스플로러

#### F-10: 테이블 미리보기
- KR/US 탭 전환 후 테이블명 선택 → 최근 100건 미리보기
- 요청: `GET /api/kr/data/preview/{table}`, `GET /api/us/data/preview/{table}`
- 컬럼명, 타입, 샘플 값 표시

---

### 3.6 백업·복구 관리 (p4 자체 기능)

#### F-11: 백업 실행
- "KR 백업", "US 백업", "전체 백업" 버튼 제공
- 백업 태그 입력 후 실행 → 비동기 Background Tasks 상태 모니터링 및 로딩/진행률 표시
- 요청: `POST /api/mgr/backup` → `p1_shared/BackupManager` 래퍼 비동기 실행

#### F-12: 백업 이력 조회
- 최근 N개 백업 파일 목록 (생성일시, 태그, 파일 크기, 검증 상태)
- 각 백업 항목에 "검증" 버튼 (dump 파일의 PostgreSQL 헤더 파싱을 통해 유효 dump인지 검증)
- 요청: `POST /api/mgr/backup/verify`

#### F-13: 복구 실행
- 백업 파일 선택 → 복구 대상(KR/US) 선택 → 확인 다이얼로그 → 복구 실행
- **안전장치**: 복구 실행 직전 실수로 인한 데이터 손실을 막기 위해 **최신 시점의 자동 백업 강제 생성 옵션** 제공
- 복구 완료 직후 자동으로 데이터 무결성 진단(`run_diagnostics`)을 실행하여 결과를 사용자에게 화면으로 즉시 표출
- 요청: `POST /api/mgr/restore`

---

### 3.7 DB 물리 동기화 (p1_shared 기능)

#### F-14: DB 물리 동기화 실행
- "서버 → 개발PC (Pull)" 및 "개발PC → 서버 (Push)" 물리 동기화 트리거
- 대상 데이터베이스(KDMS / USDMS) 선택 가능
- 실행 시 경고 팝업 표출 (양 컴퓨터의 DB 컨테이너가 복제 기간 동안 일시 정지됨을 안내)
- 요청: `POST /api/mgr/sync` -> `p1_shared/PhysicalSyncManager` 실행

#### F-15: 동기화 로그 중계 및 정밀 감사 결과 표출
- 동기화 진행 중 백그라운드 태스크의 터미널 표준 출력 로그를 실시간 터미널 컴포넌트로 스트리밍
- 물리 동기화 완료 후, p1_shared 내 감사 엔진(`audit_fast`, `audit_deep`, `audit_usdms`)을 자동 실행하여 테이블 레코드 수 및 무결성 대조 결과를 화면에 리포팅
- 요청: `GET /api/mgr/sync/status`, `POST /api/mgr/sync/audit`

---

## 4. UI 구조 (Pages & Components)

### 4.1 페이지 라우팅

| 경로 | 페이지 | 설명 |
|---|---|---|
| `/` | DashboardView | 통합 시스템 상태 + 태스크 현황 |
| `/logs` | LogView | 실시간 로그 터미널 |
| `/schedules` | ScheduleView | KR/US 스케줄 관리 |
| `/health` | HealthView | 신선도/갭/마일스톤/블랙리스트 |
| `/explorer` | ExplorerView | 데이터 테이블 미리보기 |
| `/backup` | BackupView | 백업·복구 관리 |

### 4.2 핵심 컴포넌트

```
components/
├── layout/
│   ├── AppHeader.vue          # 상단 네비게이션 + 시스템 상태 인디케이터
│   ├── AppSidebar.vue         # 메뉴 사이드바
│   └── MarketTab.vue          # KR/US 탭 전환 (공통)
│
├── dashboard/
│   ├── SystemStatusCard.vue   # KR/US 시스템 상태 카드
│   ├── TaskStatusCard.vue     # 태스크 상태 카드 + 즉시 실행 버튼
│   └── LogTerminal.vue        # WebSocket 로그 터미널
│
├── health/
│   ├── FreshnessPanel.vue     # 데이터 신선도 신호등
│   ├── GapInspector.vue       # 갭 탐지 조회
│   ├── MilestoneTimeline.vue  # 마일스톤 타임라인 (KR)
│   └── BlacklistPanel.vue     # 블랙리스트 현황 (US)
│
├── schedule/
│   └── ScheduleModal.vue      # 스케줄 수정 모달
│
└── backup/
    ├── BackupControl.vue      # 백업 실행 컨트롤
    ├── BackupHistoryTable.vue # 백업 이력 테이블
    ├── RestoreModal.vue       # 복구 확인 다이얼로그
    └── SyncControl.vue        # 물리 동기화 제어 및 감사결과 표출 (F-14, F-15)
```

### 4.3 Pinia 스토어

| 스토어 | 관리 상태 |
|---|---|
| `systemStore` | KR/US 시스템 연결 상태(ONLINE/OFFLINE), 공통 활성 시장 상태(kr/us) 관리 |
| `taskStore` | 시장 접두사별(`kr`/`us`) 독립된 태스크 목록 및 진행 상태 관리 |
| `scheduleStore` | 시장 접두사별 스케줄 정보, 활성화 및 수정 상태 모달 관리 |
| `healthStore` | 신선도, 갭(공통), KR 마일스톤 타임라인, US 수집 블랙리스트 분리 관리 |
| `backupStore` | 백업 이력 목록, 생성/검증/복구 비동기 상태 관리 |
| `syncStore` | DB 물리 동기화 이력, 실행 상태, 실시간 감사 결과 관리 |
| `logStore` | WebSocket 로그 버퍼 (`kr`/`us` 별도 500줄 버퍼 관리 및 자동 해제) |

---

## 5. 백엔드 설계 (p4 자체 Backend)

p4 백엔드는 **백업·복구·통합 상태 집계** 전용이다. 데이터 수집 로직 없음.

### 5.1 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/mgr/status` | p2, p3 헬스 집계 (양측 `/health/freshness` 비동기 호출 및 집계) |
| POST | `/api/mgr/backup` | DB 백업 실행 (`BackupManager` 비동기 래핑 실행) |
| GET | `/api/mgr/backup/list` | 백업 이력 목록 |
| POST | `/api/mgr/backup/verify` | 특정 백업 파일 검증 (PostgreSQL dump 헤더 파싱) |
| POST | `/api/mgr/restore` | DB 복구 실행 (안전장치 토큰 및 사전 백업 필수 확인) |
| POST | `/api/mgr/sync` | DB 물리 동기화 실행 (`PhysicalSyncManager`) |
| GET | `/api/mgr/sync/status` | 동기화 진행 상태 및 최근 감사 결과 반환 |
| WS | `/ws/logs/kr` | `p2_kdms` WebSocket 로그 수용 및 프론트엔드 중계 프록시 |
| WS | `/ws/logs/us` | `p3_usdms` WebSocket 로그 수용 및 프론트엔드 중계 프록시 |

### 5.2 Nginx 리버스 프록시 설정

```nginx
server {
    listen 80;

    # p4 Frontend (정적 파일)
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # p4 자체 백엔드
    location /api/mgr/ {
        proxy_pass http://p4_backend:8010;
    }

    # p2_kdms 프록시
    location /api/kr/ {
        proxy_pass http://p2_kdms:8000/api/;
    }

    # p3_usdms 프록시
    location /api/us/ {
        proxy_pass http://p3_usdms:8005/api/;
    }

    # WebSocket 프록시
    location /ws/ {
        proxy_pass http://p4_backend:8010;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 6. 기술 스택

### 프론트엔드
| 항목 | 값 | 비고 |
|---|---|---|
| 프레임워크 | Vue 3.5+ | Composition API |
| 언어 | TypeScript 5.9+ | |
| 빌드 도구 | Vite 7+ | |
| 상태 관리 | Pinia 3+ | |
| 라우팅 | Vue Router 4+ | |
| HTTP | Axios 1.13+ | 180s timeout |
| 차트 | Chart.js 4+ + vue-chartjs | 신선도, 갭 시각화 |
| Node | 20.19+ / 22.12+ | |

### 백엔드
| 항목 | 값 |
|---|---|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| ASGI | Uvicorn |
| HTTP 클라이언트 | httpx (비동기, p1/p2 API 호출용) |
| 설정 관리 | pydantic-settings |

### 인프라
| 항목 | 값 |
|---|---|
| 웹서버 | Nginx 1.25 (리버스 프록시 + 정적 파일) |
| 컨테이너 | Docker + Compose |
| 네트워크 | `tdms-net` (p2, p3, p4 공유 브릿지) |

---

## 7. 환경 변수 (.env)

```bash
# p2_kdms 연결
P2_KDMS_URL=http://p2_kdms:8000

# p3_usdms 연결
P3_USDMS_URL=http://p3_usdms:8005

# p4 자체 백엔드
P4_PORT=8010

# 백업 경로
BACKUP_BASE_DIR=/app/backups
BACKUP_RETENTION_DAILY=30
BACKUP_RETENTION_WEEKLY=12

# 폴링 간격 (초)
TASK_POLL_INTERVAL=30

# ── DB 물리 동기화 설정 (p1_shared 연동) ───────────────────────────────────
DEV_IP=192.168.35.233
SERVER_IP=192.168.35.176
SSH_USER=roid2
SSH_KEY_PATH=~/.ssh/tdms_sync_rsa

# ── 공통 스케줄링 일정 (.env 중앙화 관리) ──────────────────────────────────
# 한국 시장 (KDMS) 스케줄
SCHEDULE_KDMS_DAILY_UPDATE=17:10
SCHEDULE_KDMS_FINANCIAL_UPDATE=sat:14:00
SCHEDULE_KDMS_BACKFILL_MINUTE=sat:16:00

# 미국 시장 (USDMS) 스케줄
SCHEDULE_USDMS_DAILY_ROUTINE=wed,sat:07:30
```

---

## 8. Docker 구성

```yaml
services:
  p4_backend:
    build:
      context: .
      dockerfile: backend.Dockerfile
    ports:
      - "8010:8010"
    volumes:
      - ./backups:/app/backups    # 백업 파일 공유
      - ./logs:/app/logs
    environment:
      P2_KDMS_URL: http://p2_kdms:8000
      P3_USDMS_URL: http://p3_usdms:8005
    networks:
      - tdms-net

  p4_frontend:
    build:
      context: ./frontend
      dockerfile: frontend.Dockerfile
    ports:
      - "80:80"
    depends_on:
      - p4_backend
    networks:
      - tdms-net

networks:
  tdms-net:
    external: true               # p2, p3와 공유 네트워크
```

> **네트워크 공유 원칙**: p2, p3, p4가 동일 `tdms-net`에 속해야 Nginx 프록시가 컨테이너명으로 라우팅 가능하다.

---

## 9. 프로젝트 디렉토리 구조 (목표)

```
p4_manager/
├── backend/
│   ├── main.py                # FastAPI 앱
│   ├── config.py
│   ├── routers/
│   │   ├── manager.py         # /api/mgr/* (백업/복구/통합상태)
│   │   └── proxy_ws.py        # /ws/logs/* WebSocket 프록시
│   └── services/
│       ├── backup_service.py  # shared/BackupManager 래퍼
│       └── status_service.py  # p1, p2 상태 집계
│
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── stores/            # systemStore, taskStore, etc.
│   │   ├── views/             # Dashboard, Log, Schedule, Health, Explorer, Backup
│   │   └── components/        # layout, dashboard, health, schedule, backup
│   ├── vite.config.ts
│   └── package.json
│
├── nginx/
│   └── nginx.conf             # 리버스 프록시 설정
│
├── docker-compose.yml
├── backend.Dockerfile
├── frontend.Dockerfile
└── .env.example
```

---

## 10. 구현 단계 (Phase)

### Phase 1 — 기본 연결 및 대시보드
- [ ] Docker 네트워크 `tdms-net` 구성 (p1, p2 공유)
- [ ] Nginx 리버스 프록시 설정 (`/api/kr/`, `/api/us/`, `/api/mgr/`)
- [ ] 통합 대시보드 (F-01): 시스템 상태 카드 + 폴링
- [ ] 태스크 모니터링 (F-02) + 수동 실행 (F-03)

### Phase 2 — 로그 및 스케줄
- [ ] WebSocket 로그 터미널 (F-04): KR/US 탭 분리
- [ ] 스케줄 관리 (F-05): 조회 + 수정 모달

### Phase 3 — 헬스 및 데이터 익스플로러
- [ ] 신선도 확인 (F-06), 갭 탐지 (F-07)
- [ ] 마일스톤 관리 (F-08, KR), 블랙리스트 조회 (F-09, US)
- [ ] 데이터 익스플로러 (F-10)

### Phase 4 — 백업·복구 및 동기화 인프라
- [ ] 백업 실행 (F-11) + 이력 조회 (F-12)
- [ ] 복구 실행 (F-13) + 복구 후 자동 진단 연동
- [ ] DB 물리 동기화 기능 (F-14, F-15) 및 UI 추가
- [ ] `.env` 스케줄러 중앙 제어 및 kdms/usdms 연동 작업

---

## 11. 알려진 이슈 및 주의사항

| 이슈 | 내용 | 대응 |
|---|---|---|
| 네트워크 격리 | p2, p3, p4가 다른 Compose 파일로 실행될 경우 컨테이너명 라우팅 불가 | `tdms-net` 외부 네트워크(`external: true`)로 설정하여 격리 환경 통신 보장 |
| WebSocket 프록시 | Nginx WS 프록시 및 FastAPI ASGI 환경에서 중계 시 핸드셰이크 유실 발생 가능 | `proxy_set_header Upgrade $http_upgrade` 설정 및 `proxy_ws.py`에서 비동기 연결 타임아웃/재연결 예외처리 구현 |
| 백업 경로 공유 | p4 백업 서비스가 p2/p3 DB 볼륨에 직접 접근 불가 | `/app/backups` 볼륨을 p2/p3/p4 컨테이너 간 동일 호스트 디렉토리로 바인드 마운트 공유 |
| 복구 안전 장치 | 복구 실행 시 전체 데이터 덮어쓰기로 인한 영구 유실 우려 | 더블 컨펌 다이얼로그 배치 + 복구 명령 수신 즉시 백엔드에서 강제 사전 스냅샷 백업 실행 |
| p2/p3 미실행 시 | 특정 백엔드가 오프라인일 때 p4 전체 대시보드 렌더링 마비 가능 | `status_service.py`에서 `httpx` 비동기 호출 시 Timeout(최대 3초) 예외 처리 후 해당 채널만 `OFFLINE`으로 표시하여 오류 전파 차단 |
| 동기화 중 컨테이너 중지 | 물리 동기화(`PhysicalSyncManager`) 실행 시 양 컴퓨터의 DB 컨테이너가 복제 단계에서 강제 중지됨 | 동기화 실행 전 로컬/원격 경고 팝업을 띄우고, 완료 직후 `StartupValidator`가 컨테이너 정상 가동 및 테이블 검증을 완료할 때까지 화면에 진행 로딩 표시 적용 |

---

*p2_kdms 상세: `docs/p2_kdms/p2_kdms_PRD.md`*
*p3_usdms 상세: `docs/p3_usdms/p3_usdms_PRD.md`*
*공통 모듈: `docs/p1_shared/p1_shared_PRD.md` (미작성)*
