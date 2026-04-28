# USDMS 코드베이스 맵 (codebase_map.md)

> **프로젝트**: USDMS (US Data Management System)
> **원본 경로**: `migration_pjt/usdms_origin/`
> **원본 저장소**: `https://github.com/roidchoi/nf_03_usdms.git`
> **버전**: 5.0 (Phase 5 - Codebase Cleanup & Document Synchronization)
> **마지막 업데이트**: 2026-04-28

---

## 1. 전체 디렉토리 구조

```
usdms_origin/
├── backend/                              # 핵심 애플리케이션 로직
│   ├── collectors/                       # 데이터 수집/IO 레이어
│   │   ├── master_sync.py               # ✅ [핵심] SEC 티커 동기화 + 노이즈 제거 (MasterSync)
│   │   ├── financial_parser.py          # ✅ [핵심] XBRL 파싱 & 표준화 (FinancialParser)
│   │   ├── market_data_loader.py        # ✅ OHLCV 수집 (반복적 수정 로직)
│   │   ├── sec_client.py               # ✅ SEC EDGAR API 래퍼 (SECClient)
│   │   ├── db_manager.py               # ✅ DB 연결 & 쿼리 관리 [GOD NODE]
│   │   ├── xbrl_mapper.py              # ✅ US-GAAP → 표준 필드 매핑
│   │   ├── master_enricher.py          # ✅ 메타데이터 보강 (Sector, Industry, yfinance)
│   │   ├── price_engine.py             # ✅ 가격 수정 계수 계산기
│   │   ├── kis_api_core.py             # ✅ KIS API 코어 (레거시)
│   │   └── kis_us_wrapper.py           # ✅ KIS 미국 주식 래퍼
│   │
│   ├── engines/                         # 계산 레이어
│   │   ├── valuation_calculator.py      # ✅ [핵심] PIT 기반 PER/PBR/EV-EBITDA 산출
│   │   └── metric_calculator.py         # ✅ ROE/ROA/ROIC 등 재무 비율 산출
│   │
│   ├── auditors/                         # 데이터 무결성 검증
│   │   ├── financial_auditor.py          # ✅ 회계 항등식 검증 (Assets = L + E)
│   │   ├── metric_auditor.py             # ✅ 지표 역산 검증 (ROE 등)
│   │   └── price_auditor.py              # ✅ 수정주가 재현성 검증
│   │
│   ├── routers/
│   │   └── data.py                       # ✅ FastAPI 데이터 조회 엔드포인트
│   │
│   ├── tasks/
│   │   └── valuation_task.py             # ✅ 가치평가 태스크
│   │
│   ├── utils/
│   │   └── blacklist_manager.py          # ✅ 수집 차단 목록 관리 (BlacklistManager)
│   │
│   └── main.py                           # ✅ FastAPI 앱 진입점
│
├── ops/                                  # 운영 진입점 (스크립트)
│   ├── run_daily_routine.py              # ✅ [메인] 일일 오케스트레이터 (Step 1~6)
│   ├── run_diagnostics.py                # ✅ 온디맨드 시스템 헬스체크
│   ├── run_db_checkpoint.py              # ✅ DB 백업 유틸리티
│   ├── kill_db_locks.py                  # ✅ DB 락 긴급 해제
│   ├── run_master_sync_only.py           # ✅ 마스터 동기화 단독 실행
│   ├── apply_schema_update.py            # ✅ 스키마 업데이트 적용
│   ├── cleanup_test_data.py              # ✅ 테스트 데이터 정리
│   ├── test_db_issue.py                  # ✅ DB 이슈 테스트
│   └── run_db_checkpoint.py             # ✅ 체크포인트 생성
│
├── db_init/                              # DB 초기화 스크립트
│   ├── audit_sec_sources.py              # ✅ SEC 소스 감사
│   ├── run_financial_retry.py            # ✅ 재무 데이터 재시도
│   ├── run_historical_backfill.py        # ✅ 과거 이력 백필
│   ├── run_metric_rebuild.py             # ✅ 지표 재구축
│   ├── run_valuation_rebuild.py          # ✅ 가치평가 재구축
│   ├── check_data_integrity.py           # ✅ 데이터 무결성 점검
│   ├── recover_tickers.py                # ✅ 티커 복구
│   ├── rebuild_ticker_master.py          # ✅ 티커 마스터 재구축
│   ├── enrich_major_universe.py          # ✅ 주요 유니버스 보강
│   └── audit_schema.py                   # ✅ 스키마 감사
│
├── tests/                                # 시스템 테스트
│   ├── test_master_logic.py              # ✅ 티커 생명주기 로직 테스트
│   ├── test_master_sync.py               # ✅ 마스터 동기화 검증
│   ├── test_daily_routine_subset.py      # ✅ 일일 루틴 서브셋 테스트
│   ├── draft_integration_test.py         # ✅ 통합 테스트 (드래프트)
│   └── sec_content_verifier.py           # ✅ SEC 콘텐츠 파싱 검증
│
├── docs/                                 # 프로젝트 문서
│   ├── plan_usdms_roadmap.md             # 전체 로드맵 (v4.5)
│   ├── spec_usdms_core_logic.md          # 핵심 로직 명세 (v5.0 As-Built)
│   ├── ds_daily_routine_flow.md          # 일일 루틴 상세 흐름도 (V2.0)
│   ├── USDMS_guide.md                    # AI 어시스턴트 가이드 (v5.0)
│   ├── USDMS_migration_guide.md          # KDMS 운영 PC 이관 가이드
│   ├── session_rules_v1.md               # 개발자 작업 수칙
│   ├── legacy_ref_kdms_guide.md          # KDMS 레거시 참조 가이드
│   └── usdms_health_check_plan.md        # 데이터 정합성 검증 계획 (v3.0)
│
├── check_bl_reasons.py                   # ✅ 블랙리스트 사유 점검
├── docker-compose.yml                    # 멀티 컨테이너 오케스트레이션
└── setup_env.sh                          # 환경 설정 스크립트
```

---

## 2. 일일 루틴 흐름 (run_daily_routine.py — Step 1~6)

```
Step 1: Master Sync (SEC 티커 목록 동기화)
    └→ MasterSync.sync_daily()
Step 2: Market Data Update (시세 수집)
    └→ MarketDataLoader.collect_daily_updates()
Step 3: Financial Data Update (SEC XBRL 재무 파싱)
    └→ FinancialParser.process_filings()
Step 4: Metadata & Price Internal Calculation (내부 지표 갱신)
    └→ us_ticker_master.market_cap, current_price 업데이트
Step 5: Valuation & Metrics (가치평가 산출)
    └→ ValuationCalculator.calculate_and_save()
Step 6: Health Check (이상징후 감지)
    └→ DailyRoutine._detect_anomalies()
```

---

## 3. 수집 대상 선정 기준 (Targeting Logic)

| 조건 | 진입(Entry) | 유지(Retention) |
|---|---|---|
| 시가총액 | >= $5,000만 | >= $3,500만 |
| 주가 | >= $1.00 | >= $0.80 |
| 거래소 | NYSE/NASDAQ/AMEX | 동일 |
| 국가 | United States | 동일 |
| 종목 유형 | EQUITY | 동일 |

---

## 4. 신규 프로젝트(p2_usdms) 구현 시 참고 포인트

- **CIK 중심 관리**: Ticker 대신 SEC CIK(불변 식별자)를 PK로 → [[ref_usdms_wiki/interfaces/cik_centric_identity]]
- **XBRL 파서 그룹화 로직**: `(FY, FP)` 기준 그룹화로 분기 이산값 역산 → [[ref_usdms_wiki/interfaces/financial_parser_logic]]
- **PIT Valuation**: `pandas.merge_asof(direction='backward')` 기반 시점 매칭 → [[ref_usdms_wiki/interfaces/pit_sec_pattern]]
- **블랙리스트 관리**: `SEC_403`, `PARSE_ERROR`, `NO_DATA` 코드 체계 → `backend/utils/blacklist_manager.py`
- **DB 이관 가이드**: KDMS 운영 PC와 공존 가능 (포트 5435/8005 분리) → [[ref_usdms_wiki/decisions/coexistence_with_kdms]]