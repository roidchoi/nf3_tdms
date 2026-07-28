# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p2_kdms (한국 시장 데이터 백엔드)
> **마지막 업데이트**: 2026-07-27 (시가총액 2017~2019 자체 연산 쿼리 오류 해결 및 수급 백필 CLI 지식화 완료)
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

```
tdms_core/p2_kdms/
├── collectors/                  # 외부 API 클라이언트 레이어  ✅
│   ├── kis_kr_client.py         # KIS REST API KR 래퍼 (OHLCV + 재무 + 마스터, BC/MF/ELW 비주식성 특수 상품 필터링 내장)
│   ├── kiwoom_client.py         # Kiwoom REST API 분봉 수집
│   ├── pub_data_client.py       # pykrx 기반 시가총액 수집
│   ├── factor_calculator.py     # 수정계수(Price Factor) 역산 계산기
│   ├── target_selector.py       # 분봉 수집 대상 종목 선정 (거래대금 기준 Top-N)
│   └── utils.py                 # 수집 공통 유틸 (데이터 변환 등)
├── repositories/                # DB 접근 레이어  ✅
│   ├── base.py                  # create_kdms_pool() — EnvDetector 기반 DSN 자동 구성
│   ├── ohlcv_repo.py            # OhlcvRepo — 일봉/수정주가/분봉 CRUD (God Node #1)
│   ├── financial_repo.py        # FinancialRepo — PIT 재무제표/비율 CRUD (God Node #3)
│   ├── market_cap_repo.py       # MarketCapRepo — 시가총액 UPSERT/갭탐지 (God Node #4)
│   ├── master_repo.py           # MasterRepo — stock_info 활성종목 조회 (God Node #5)
│   └── factor_repo.py           # FactorRepo — price_adjustment_factors CRUD (God Node #7)
├── routers/                     # FastAPI 라우터  ✅
│   ├── data.py                  # /api/data/* 조회 엔드포인트 (수정주가, PIT 재무, 팩터)
│   └── admin.py                 # /api/v1/admin/* 관리 엔드포인트 (태스크 트리거, 상태 조회)
├── tasks/                       # 배치/스케줄 태스크  ✅
│   ├── daily_task.py            # DailyTask — 일일 OHLCV + 시총 + 팩터 갱신 파이프라인
│   ├── financial_task.py        # 분기 PIT 재무제표 수집 및 비교 태스크
│   └── backfill_task.py         # 분봉 백필 파이프라인 (DatabaseManager 내장)
├── ops/                         # 운영 스크립트  ✅
│   ├── backfill_daily_cap.py    # 공공데이터포털 API 연동 과거 5개년 시가총액 백필 스크립트
│   ├── backfill_daily_ohlcv_amt.py # 일봉 거래대금(amt) 백필 스크립트
│   ├── backfill_minute_ohlcv.py # 과거 분봉 데이터 백필 스크립트
│   ├── backfill_pipeline.py     # 코퍼레이트 액션 의심 종목 탐지 + 백필 실행
│   ├── check_db.py              # DB 테이블/행수 헬스체크
│   ├── cleanup_database.py      # 불필요 데이터 정리
│   ├── fix_ohlcv_amt_from_kis.py # KIS API 대조 일봉 거래대금(amt) 정정 스크립트
│   ├── pre_migration_backup.py  # 마이그레이션 전 백업 실행 (BackupManager 연동)
│   ├── rebuild_factors_from_kis.py # KIS API 기반 수정계수 일괄 재구축 스크립트
│   ├── rebuild_minute_targets.py # 거래대금 기준 분봉 수집 타겟 종목 재구축 스크립트
│   ├── run_financial_manual.py  # 수동 재무 업데이트 기동 스크립트
│   ├── run_monthly_backfill.py  # 월 단위 분봉 백필 범위 슬라이싱 실행기
│   └── verify_nulls.py          # DB 테이블 내 Null 값 검증 스크립트
├── tests/                       # 테스트  ✅
│   ├── conftest.py              # mock_lifespan — FastAPI lifespan 오프라인 모킹
│   ├── test_backfill_task.py
│   ├── test_base_repository.py
│   ├── test_blacklist.py
│   ├── test_daily_task.py
│   ├── test_data_api_t007.py
│   ├── test_factor_calculator.py
│   ├── test_factor_endpoints.py
│   ├── test_factor_repo.py
│   ├── test_financial_endpoints.py
│   ├── test_financial_repo.py
│   ├── test_financial_task.py
│   ├── test_health_t008.py
│   ├── test_kis_kr_client.py
│   ├── test_logs_ws_t008.py
│   ├── test_market_cap_scheduler.py
│   ├── test_master_repo.py
│   ├── test_ohlcv_repo.py
│   ├── test_ohlcv_repo_adjusted.py
│   └── test_range_backfill_t010.py
├── main.py                      # FastAPI 앱, lifespan, APScheduler 등록
├── config.py                    # Settings (pydantic-settings, Layer A/B 분리)
├── pyproject.toml               # 패키지 메타데이터 (editable install)
├── requirements.txt             # 의존성 (p1_shared editable 포함)
├── backend.Dockerfile
└── docker-compose.yml           # TimescaleDB (kdms_timescaledb, port 5432)
```

---

## 2. 핵심 데이터 흐름

```
[KIS REST API / Kiwoom REST API / pykrx (KRX)]
      │ KisKrClient / KiwoomClient / PubDataClient
      ▼
[tasks/daily_task.py — DailyTask]
  ├── OHLCV 수집 → OhlcvRepo.upsert_daily_ohlcv()
  ├── 팩터 계산 → FactorCalculator.calculate_factors() → FactorRepo.bulk_upsert_factors()
  ├── 수정주가 갱신 → OhlcvRepo.refresh_adjusted_ohlcv_batch() (SQL CTE 누적곱)
  ├── 시가총액 → PubDataClient.get_market_cap_by_date() → MarketCapRepo.upsert_daily_market_cap()
  └── 분봉 수집 → KiwoomClient.get_minute_chart() → OhlcvRepo.upsert_minute_ohlcv()

[tasks/financial_task.py]
      │ KisKrClient.fetch_financial_data() × 7종
      ▼ _compare_financial_data() → 변경 감지 시
  FinancialRepo.insert_statements() / insert_ratios()

[tasks/backfill_task.py]
      │ DatabaseManager(내부 DB 접근) + KiwoomClient
      ▼ _detect_missing_and_partial_days() → _execute_backfill_jobs()

[FastAPI — routers/data.py]
      ├── GET /api/data/stocks             → MasterRepo.get_all_active_stocks()
      ├── GET /api/data/factors/{stk_cd}   → FactorRepo.get_factors_for_stock()
      ├── GET /api/data/ohlcv/daily/adjusted → On-the-fly 수정주가 계산
      ├── GET /api/data/ohlcv/adjusted/{stk_cd} → OhlcvRepo.get_adjusted_ohlcv_direct()
      └── GET /api/data/financials          → FinancialRepo.get_statements_as_of() + get_ratios_as_of()

[FastAPI — routers/admin.py]
      ├── GET  /api/v1/admin/status         → job_statuses 반환
      └── POST /api/v1/admin/run_task       → APScheduler를 통해 배치 즉시 실행
```

---

## 3. 모듈별 상태 및 역할

| 모듈/폴더 | 상태 | 핵심 파일 | 역할 요약 |
|---|---|---|---|
| `main.py` | ✅ | FastAPI lifespan | DB풀 생성, StartupValidator, APScheduler 크론 등록 |
| `config.py` | ✅ | Settings | pydantic-settings 기반 Layer A(EnvDetector용)/Layer B(앱 내부) 이중 구조 |
| `repositories/base.py` | ✅ | create_kdms_pool() | EnvDetector로 dev/server 환경 감지 후 DSN 자동 구성 |
| `repositories/ohlcv_repo.py` | ✅ | OhlcvRepo | 일봉/수정주가(On-the-fly + 물리)/분봉/팩터역산용 DataFrame 반환 |
| `repositories/financial_repo.py` | ✅ | FinancialRepo | PIT 재무제표/비율 INSERT + as_of 기준 버전 선택 (DISTINCT ON) |
| `repositories/market_cap_repo.py` | ✅ | MarketCapRepo | daily_market_cap UPSERT, 갭 날짜 탐지 |
| `repositories/master_repo.py` | ✅ | MasterRepo | stock_info 활성 종목 조회 |
| `repositories/factor_repo.py` | ✅ | FactorRepo | price_adjustment_factors CRUD (bulk upsert, delete, list) |
| `collectors/kis_kr_client.py` | ✅ | KisKrClient | KIS API KR 래퍼: 일봉/마스터/재무 7종 수집 |
| `collectors/kiwoom_client.py` | ✅ | KiwoomClient | Kiwoom REST: 분봉 차트 수집 (페이지네이션) |
| `collectors/pub_data_client.py` | ✅ | PubDataClient | pykrx 기반 시가총액 수집 |
| `collectors/factor_calculator.py` | ✅ | FactorCalculator | Raw/Adj 비율 기반 수정계수 역산 (ZeroDivision 처리) |
| `collectors/target_selector.py` | ✅ | TargetSelector | 거래대금 기준 분봉 수집 대상 Top-N 선정 |
| `tasks/daily_task.py` | ✅ | DailyTask | 평일 17:00 KST 크론: OHLCV → 팩터 → 수정주가 → 시총(1000억주 컷오프/9경 초과 bigint 방어 필터) → 분봉 |
| `tasks/financial_task.py` | ✅ | run_financial_update() | 매일 19:00 KST 크론: PIT 재무데이터 변경 감지 및 수집 (KST 시간대 보정 완료) |
| `tasks/backfill_task.py` | ✅ | run_backfill_minute_data() | 분봉 갭 탐지 및 백필 (수동 트리거, KST 시간대 보정 완료) |
| `routers/data.py` | ✅ | data router | /api/data/* 데이터 조회 API |
| `routers/admin.py` | ✅ | admin router | /api/v1/admin/* 배치 수동 트리거 및 상태 조회 |
| `ops/backfill_pipeline.py` | ✅ | run_backfill() | 코퍼레이트 액션 의심 종목 탐지 + 일봉 팩터 백필 |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트/명령 | 실행 방법 | 역할 |
|---|---|---|
| `main.py` (FastAPI 서버) | `uvicorn main:app --reload --port 8000` | API 서버 기동, 스케줄러 시작 |
| `ops/check_db.py` | `conda run -n tdms_p2_env python -m ops.check_db` | DB 헬스체크 |
| `ops/run_monthly_backfill.py` | `conda run -n tdms_p2_env python -m ops.run_monthly_backfill` | 월간 분봉 백필 |
| `scripts/backfill_investor_trade_by_year.py` | `conda run -n tdms_p2_env python scripts/backfill_investor_trade_by_year.py --start-year 2024 --end-year 2025 --skip-existing` | 연도별 투자자 매매동향(수급) 백필 스크립트 |
| Admin API POST | `POST /api/v1/admin/run_task {"task_name": "daily_update"}` | 배치 태스크 즉시 실행 |

---

## 5. 테스트 현황

| 테스트 파일 | 커버 대상 | 상태 |
|---|---|---|
| `test_daily_task.py` | DailyTask 파이프라인 흐름 | ✅ |
| `test_backfill_task.py` | 백필 갭탐지 + KiwoomClient | ✅ |
| `test_financial_task.py` | PIT 재무 수집 + 비교 | ✅ |
| `test_market_cap_scheduler.py` | 시총 스케줄러 전체 통합 | ✅ |
| `test_kis_kr_client.py` | KisKrClient API 호출 | ✅ |
| `test_factor_calculator.py` | 수정계수 역산 (액면분할 등) | ✅ |
| `test_factor_repo.py` | FactorRepo CRUD | ✅ |
| `test_financial_repo.py` | FinancialRepo PIT 조회 | ✅ |
| `test_financial_endpoints.py` | /api/data/financials 엔드포인트 | ✅ |
| `test_factor_endpoints.py` | /api/data/factors, ohlcv/adjusted | ✅ |
| `test_base_repository.py` | create_kdms_pool() 환경별 DSN | ✅ |
| `test_ohlcv_repo.py` | OhlcvRepo CRUD | ✅ |
| `test_ohlcv_repo_adjusted.py` | 수정주가 물리테이블 직접 조회 | ✅ |
| `test_master_repo.py` | MasterRepo 활성종목 조회 | ✅ |

---

## 6. 변경 이력 요약

| Task | 주요 변경 내용 |
|---|---|
| 초기화 | 폴더 구조 골격 생성 (Task 계획 기반) |
| T-001~T-002 | infrastructure + master/ohlcv 레포 구현 |
| T-003 | FactorCalculator + FactorRepo + 수정주가 API |
| T-004 | FinancialRepo PIT + /api/data/financials |
| T-005 | KiwoomClient + TargetSelector + backfill_task |
| T-006~T-008 | 시가총액 수집 파이프라인 + MarketCapRepo + DailyTask 통합 |
| 2026-05-26 | Graphify 기반 초기 지식화 (위키 codebase_map 전면 작성) |
| 2026-05-28 | KIS 마스터 데이터 오차 대응을 위한 시가총액 bigint 오버플로우 방어 패치 적용 |
| T-011 | 스케줄링 환경 변수 외부화 및 API 개정 작업 완료, KIS 마스터 비주식 특수 상품(BC/MF/EW) 제외 필터 적용 |
| T-105 (2026-06-16) | 재무 업데이트 및 분봉 백필 태스크 기동/완료 상태 기록 시 KST 시간대(+09:00) 처리 및 isoformat() 적용 |
| 2026-07-27 | 시가총액 2017~2019년 자체 연산 쿼리 스키마/오버플로우 오류 해결(err-008), 2017-01-02 일봉 수집 단위 표준화 정제 완수, 수급 백필 CLI 스크립트 작성 및 위키 지식화 |