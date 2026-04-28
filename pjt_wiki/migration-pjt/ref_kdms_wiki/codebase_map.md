# KDMS 코드베이스 맵 (codebase_map.md)

> **프로젝트**: KDMS (Korea Data Management System)
> **원본 경로**: `migration_pjt/kdms_origin/`
> **원본 저장소**: `https://github.com/roidchoi/nf_p01_kdms.git`
> **버전**: 7.0 (Phase 8 - KRX Market Cap Integration)
> **마지막 업데이트**: 2026-04-28

---

## 1. 전체 디렉토리 구조

```
kdms_origin/
├── main.py                       # ✅ FastAPI 앱 진입점, APScheduler 설정, lifespan
├── log_utils.py                  # ✅ WebSocket 로깅 핸들러 (WebSocketQueueHandler)
├── test_utils.py                 # ✅ 테스트 환경 헬퍼 (TestEnvironment)
├── backfill_minute_data.py       # ✅ 분봉 데이터 과거 이력 수집 (독립 실행)
├── verify_backfill.py            # ✅ 데이터 무결성 검증
├── daily_update.py               # ✅ 일일 업데이트 독립 실행 스크립트 (레거시)
├── financial_update.py           # ✅ 재무 데이터 업데이트 (레거시)
├── initial_build.py              # ✅ 초기 DB 구축 스크립트
├── main_collection.py            # ✅ 종합 데이터 수집 오케스트레이터
├── truncate_financials.py        # ✅ 재무 테이블 초기화 관리 스크립트
│
├── routers/                      # FastAPI 라우터
│   ├── admin.py                  # ✅ 태스크 실행/스케줄 관리/WebSocket 로그
│   ├── data.py                   # ✅ 주식/OHLCV/재무 데이터 조회 (Apache Arrow 지원)
│   ├── health.py                 # ✅ 데이터 신선도/갭/마일스톤
│   └── debug.py                  # ✅ 디버그용 API
│
├── models/                       # Pydantic 데이터 모델
│   ├── data_models.py            # ✅ Stock, OHLCV, Financial, Factor 모델
│   ├── debug_models.py           # ✅ 디버그 모델
│   └── admin_models.py           # ✅ TaskRunRequest, ScheduleCreateRequest 등
│
├── tasks/                        # 백그라운드 작업
│   ├── daily_task.py             # ✅ 일일 OHLCV + factor + 시총 동기화 (Phase 5/5)
│   ├── financial_task.py         # ✅ PIT 재무 데이터 업데이트
│   └── backfill_task.py          # ✅ 분봉 백필 + 시총 갭 복구
│
├── collectors/                   # 데이터 소스 연동
│   ├── db_manager.py             # ✅ PostgreSQL 커넥션 풀링 + 전체 쿼리 (940+ lines) [GOD NODE]
│   ├── kis_rest.py               # ✅ KIS API 클라이언트 (토큰 캐싱, 740 lines)
│   ├── kiwoom_rest.py            # ✅ Kiwoom API 클라이언트 (자동 토큰 갱신, 400 lines)
│   ├── krx_loader.py             # ✅ pykrx 기반 시총 수집 (Phase 8 신규)
│   ├── utils.py                  # ✅ 날짜/시장/포매팅 유틸리티
│   ├── factor_calculator.py      # ✅ 주가 수정 계수 계산
│   ├── target_selector.py        # ✅ 분봉 대상 종목 선정
│   └── exceptions.py             # ✅ 커스텀 예외 (TokenAuthError, KiwoomAPIError)
│
├── standalone_scripts/           # 단독 실행 유틸리티
│   ├── backfill_krx_market_cap.py  # ✅ 시총 스마트 백필 (DB MAX(dt) 자동 감지)
│   ├── rebuild_factors_from_kis.py # ✅ KIS 기반 수정계수 재구축
│   ├── check_kis_date_range.py     # ✅ KIS API 날짜 범위 동작 검증
│   ├── check_kis_daily_fields.py   # ✅ KIS 일봉 API 필드명 진단
│   ├── verify_rebuilt_factors.py   # ✅ 재구축된 팩터 검증
│   ├── build_adjusted_ohlcv.py     # ✅ 수정주가 OHLCV 테이블 구축 (Phase 3-B)
│   ├── recover_market_cap.py       # ✅ 시총 데이터 복구
│   └── run_migration.py            # ✅ 마이그레이션 실행
│
├── config/                       # DB 설정
│   ├── postgresql.conf           # ✅ TimescaleDB 튜닝 설정
│   └── pg_hba.conf               # ✅ 연결 인증 규칙
│
├── init/                         # DB 초기화
│   └── init.sql                  # ✅ 스키마, 하이퍼테이블, 인덱스, 마일스톤 (279 lines)
│
└── frontend/                     # Vue 3 TypeScript SPA
    ├── src/main.ts               # ✅ 앱 진입점
    ├── src/App.vue               # ✅ 루트 컴포넌트
    ├── src/router/index.ts       # ✅ 라우팅 (Dashboard/Health/Explorer/Schedules)
    ├── src/stores/               # Pinia 상태 관리
    │   ├── adminStore.ts         # ✅ 태스크 상태 폴링, WebSocket 로그
    │   ├── dataStore.ts          # ✅ 테이블 미리보기 데이터
    │   └── healthStore.ts        # ✅ 헬스 메트릭
    ├── src/views/                # 페이지 컴포넌트
    │   ├── DashboardView.vue     # ✅ 태스크 모니터링
    │   ├── ScheduleView.vue      # ✅ 스케줄 관리
    │   ├── HealthView.vue        # ✅ 데이터 신선도/갭/마일스톤
    │   └── DataExplorerView.vue  # ✅ 테이블 미리보기
    └── src/components/           # UI 컴포넌트
        ├── layout/ (AppHeader, AppSidebar, MainLayout)
        ├── dashboard/ (TaskStatusCard, LogTerminal)
        ├── health/ (StatCard, GapInspector, MilestoneTimeline, MilestoneModal)
        └── schedule/ (ScheduleModal)
```

---

## 2. 핵심 데이터 흐름

```
API 클라이언트 (KIS/Kiwoom/pykrx)
    ↓
Collectors (kis_rest.py, kiwoom_rest.py, krx_loader.py)
    ↓
Tasks (daily_task.py, financial_task.py, backfill_task.py)
    ↓
DatabaseManager (db_manager.py) → ThreadedConnectionPool
    ↓
TimescaleDB (Hypertables: daily_ohlcv, minute_ohlcv, daily_market_cap)
```

---

## 3. 핵심 스케줄 (APScheduler)

| Job ID | 실행 시간 | 기능 |
|---|---|---|
| `daily_update` | 월~금 17:10 | 일일 OHLCV + 팩터 + 시총 동기화 |
| `financial_update` | 토 09:00 | PIT 재무 데이터 업데이트 |
| `backfill_minute_data` | 토 10:20 | 분봉 백필 + 시총 갭 복구 |

---

## 4. 신규 프로젝트(p1_kdms) 구현 시 참고 포인트

> 이 섹션은 `p1_kdms` 설계 시 직접 활용합니다.

- **DatabaseManager 패턴**: `ThreadedConnectionPool(5~20)` → `context manager` 방식 채택 권장
- **PIT 재무 관리**: `retrieved_at` 기준 버전 관리 → [[ref_kdms_wiki/interfaces/pit_financial_pattern]]
- **수정주가 계산**: Raw OHLCV + `price_adjustment_factors` 분리 → [[ref_kdms_wiki/interfaces/price_adjustment_factor]]
- **WebSocket 로그 스트리밍**: `asyncio.Queue` 기반 실시간 로그 → `log_utils.py` 참조
- **시총 수집 (신규)**: `pykrx` 기반 `daily_market_cap` 하이퍼테이블 → `krx_loader.py` 참조