# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)  
> **마지막 업데이트**: 2026-06-16 (로깅 및 실행 중 상태 유실 장애 해결 반영 완료)  
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

```
tdms_core/p3_usdms/
├── collectors/           # 데이터 수집 레이어 [✅완성]
│   ├── sec_client.py     # SEC EDGAR API 연동용 클라이언트
│   ├── master_sync.py    # 미국 주식 마스터 동기화 오케스트레이터
│   ├── master_enricher.py # yfinance 기반 메타데이터 보강 및 ADR 필터링 수집기
│   ├── kis_us_client.py  # KIS API 기반 미국 주식 시세 연동 클라이언트
│   ├── price_engine.py   # Ratio 기반 가격 수정계수 계산 엔진
│   ├── market_data_loader.py # 일봉 시세 수집 및 팩터 연동 파이프라인
│   └── financial_parser.py # SEC XBRL facts 수집/정제 및 discrete 분기 재무 데이터 도출
├── engines/              # 비즈니스 연산 엔진 레이어 [✅완성]
│   ├── valuation_calculator.py # PIT 기반 가치평가 비율 산출 (pe, pb, ps, pcr, ev_ebitda)
│   └── metric_calculator.py    # 9대 재무비율 및 3대 YoY 성장률 산출
├── auditors/             # 데이터 무결성 검증 레이어 [✅완성] [NEW]
│   ├── financial_auditor.py # 회계 항등식, 핵심 Null값, 공시이격 이격 검사 엔진
│   ├── metric_auditor.py    # ROE 역산, 가치평가 아웃라이어 검사 엔진
│   ├── price_auditor.py     # KIS 종가 대조 및 수정계수 재현 검증 엔진
├── repositories/         # 데이터 접근 레이어 [✅완성]
│   ├── base.py           # DbConnectionPool 및 EnvDetector를 래핑한 기본 레포지토리
│   ├── master_repo.py    # us_ticker_master, us_ticker_history CIK 기반 데이터 I/O
│   ├── price_repo.py     # us_daily_price, us_price_adjustment_factors 데이터 I/O
│   ├── valuation_repo.py # us_daily_valuation 및 us_financial_metrics 데이터 I/O
│   └── blacklist_repo.py # us_collection_blacklist 데이터 I/O
├── routers/              # API 라우팅 레이어 [✅완성]
│   ├── data.py           # 마스터 목록, 일일 주가, 수정계수 조회 엔드포인트
│   ├── health.py         # 데이터 최신성(Freshness), 갭(Gaps), 블랙리스트 헬스 엔드포인트 [NEW]
│   └── admin.py          # 일일 루틴 수동 실행, 스케줄링 관리 및 실시간 로그 스트리밍 엔드포인트 [NEW]
├── tasks/                # 자동화 태스크 레이어 [✅완성]
│   └── daily_routine.py  # 5단계 일일 루틴 및 주간 백필 스케줄러 제어기 (KST 기반 target_date 처리 및 동적 FileHandler 바인딩 내장)
├── ops/                  # 시스템 운영 및 진단 스크립트 레이어 [✅완성] [NEW]
│   └── run_diagnostics.py # 3종 감사 및 최신성 판정을 일괄 실행하는 CLI 진단 스크립트
├── utils/                # 유틸리티 레이어 [✅완성]
│   └── blacklist_manager.py # 일시적/영구적 에러의 이원화 격리 처리 및 쿨다운 해제 비즈니스 논리 제어
├── tests/                # 테스트 스위트 [✅완성]
│   ├── conftest.py       # pytest 픽처 및 DB 풀 정의
│   ├── test_base_infra.py # DB 커넥션 풀 검증
│   ├── test_master_sync.py # 마스터 동기화 검증
│   ├── test_master_enricher.py # 메타데이터 보강 필터 및 실패 누적 검증
│   ├── test_price_collect.py # 일일 시세 수집, 팩터 감지 엔진, API 통합 검증
│   ├── test_financial_collect.py # SEC XBRL 파싱 및 분기 재무제표 수집 검증
│   ├── test_valuation_metric.py # 가치평가, 재무비율, 대량 550종목 루프 성능 및 적재 통합 검증
│   ├── test_blacklist.py # 블랙리스트 매니저 임계치 도달 및 자동 해제 검증
│   ├── test_daily_routine.py # 일일 파이프라인 E2E, 이상치 격리 및 수동 API 락 검증
│   ├── test_health_auditors.py # 헬스 API 및 3종 Auditors 모킹 단위/통합 테스트 [NEW]
│   └── test_holiday_sync.py # 미국 영업일 판별, DailyRoutine 스킵 및 캘린더 동기화 검증 [NEW]
├── config.py             # 환경 설정 모듈 [✅완성]
└── main.py               # FastAPI 애플리케이션 진입점 [✅완성]
```

---

## 2. 핵심 데이터 흐름

```
[ SEC EDGAR / yfinance ]
         │
         │ (MasterSync / SECClient / MasterEnricher)
         ▼
[ us_ticker_master / us_ticker_history ] 
         │
         │ (MarketDataLoader / KisUSClient) -> 일봉 OHLCV (Raw & Adjusted)
         ▼
[ us_daily_price ] (Hypertable)
         │
         │ (PriceEngine) -> Ratio(Adj / Close) 추적 및 1e-5 임계치 변화 감지
         ▼
[ us_price_adjustment_factors ] (수정계수 적재)

───────────────────────────────────────────────────────

[ us_daily_price ] ──┐
[ us_standard_financials ] ──┼─► [ ValuationCalculator ] ──► [ us_daily_valuation ] (일별 가치평가 적재)
[ us_share_history ] ──┘

[ us_standard_financials ] ──► [ MetricCalculator ] ──► [ us_financial_metrics ] (재무비율/YoY성장률 적재)

───────────────────────────────────────────────────────

[ 수집/연산 장애 감지 ] ──► [ BlacklistManager ] ──► [ us_collection_blacklist ]
                                                            │ (daily_routine 차단 필터링)
                                                            ▼
                                                     [ 수집 대상 제외 ]
```

---

## 3. 모듈별 상태 및 역할

| 모듈/폴더 | 상태 | 핵심 파일 | 역할 요약 |
|---|---|---|---|
| **collectors** | ✅ | `master_sync.py`, `master_enricher.py` | SEC 공시 동기화, yfinance 기반 메타데이터 보강 및 ADR 차단 수집기 |
| **engines** | ✅ | `valuation_calculator.py`, `metric_calculator.py` | PIT 기반 가치평가비율 및 YoY 성장률을 포함한 12대 퀀트 재무지표 산출 |
| **repositories** | ✅ | `master_repo.py`, `valuation_repo.py`, `blacklist_repo.py` | 마스터, 시세, 가치평가, 블랙리스트 대용량 DB 저장 및 최적화 조회 기능 제공 |
| **routers** | ✅ | `data.py`, `admin.py` | 외부 퀀트 및 분석 서비스 대상 시세 조회 및 수동 태스크 기동 API 제공 |
| **tasks** | ✅ | `daily_routine.py` | 5단계 일일 루틴 및 주간 자동 해제/보강 백필 스케줄러 오케스트레이션 |
| **utils** | ✅ | `blacklist_manager.py` | 일시적/영구적 에러의 이원화 격리 처리 및 쿨다운 해제 비즈니스 논리 제어 |
| **config** | ✅ | `config.py`, `main.py` | FastAPI 기동, DB 커넥션 풀 초기화, Startup Validator 및 APScheduler 연동 |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트 | 실행 방법 | 역할 |
|---|---|---|
| `main.py` | `uvicorn main:app --port 8000` | FastAPI Web API Server 기동 및 APScheduler 스케줄러 백그라운드 구동 |
| `tests/test_daily_routine.py` | `pytest tests/test_daily_routine.py` | 일일 파이프라인 E2E 통합 및 이상치 격리, 수동 Lock API 통합 검증 |

---

## 5. 테스트 현황

| 테스트 파일 | 커버 대상 | 상태 |
|---|---|---|
| `tests/test_base_infra.py` | DbConnectionPool, StartupValidator | ✅ 통과 |
| `tests/test_master_sync.py` | SECClient, MasterRepo, MasterSync | ✅ 통과 |
| `tests/test_master_enricher.py` | MasterEnricher, yfinance 연동 | ✅ 통과 |
| `tests/test_price_collect.py` | KisUSClient, PriceEngine, PriceRepo, routers/data.py | ✅ 통과 |
| `tests/test_financial_collect.py` | FinancialParser, FinancialRepo | ✅ 통과 |
| `tests/test_valuation_metric.py` | ValuationCalculator, MetricCalculator, ValuationRepo | ✅ 통과 |
| `tests/test_blacklist.py` | BlacklistManager, BlacklistRepo | ✅ 통과 |
| `tests/test_daily_routine.py` | DailyRoutine, routers/admin.py | ✅ 통과 |
| `tests/test_health_auditors.py` | routers/health.py, routers/admin.py (WebSocket / schedules / status), Auditors 3종 | ✅ 통과 [NEW] |
| `tests/test_holiday_sync.py` | is_us_trading_day, DailyRoutine 휴장 스킵, sync_trading_calendar | ✅ 통과 [NEW] |

---

## 6. 가비지 현황

> 이 섹션이 비어있는 것이 정상.

| 파일/폴더 | 생성 Task | 삭제 사유 |
|---|---|---|
| — | — | — |

---

## 7. 변경 이력 요약

| Task | 주요 변경 내용 |
|---|---|
| Task-초기화 | 초기 구조 생성 |
| Task-002-A | SEC EDGAR & yfinance 마스터 동기화 파이프라인 및 SCD Type 2 구축 |
| Task-002-B | KIS API 연동 일일 주가 수집, PriceEngine 기반 수정계수 역산 및 REST API 구축 |
| Task-003 | SEC facts 파싱 정규화 매퍼(XBRLMapper), 분기 discrete 재무제표 구축 및 주식수 수집기 이식 |
| Task-004 | PIT 기반 가치비율(5대 지표) 및 9대 재무비율/3대 YoY 성장률 엔진 구현, 550종목 실 데이터 벌크 캐싱 대용량 최적화 검증 완료 |
| Task-005 | Blacklist Repo/Manager 구축, MasterEnricher(ADR 필터링), DailyRoutine 5단계 자동화 스케줄러 및 이상치 격리(Quarantine), 수동 실행 Lock API 및 자가 치유형 갭 복구 엔진 최적화 완료 |
| Task-007 | 헬스체크 API(Freshness/Gaps/Blacklist), 어드민 스케줄 제어 및 WebSocket 로그 스트리밍, 재무/지표/수정주가 감사 엔진 3종 이식 및 CLI 진단 도구 완료 |
| Task-008 | DatabaseManager 레거시 완전 제거, 수집 임계 기준 및 스케줄 시간 외부화, 미국 휴장 판단 및 trading_calendar 테이블 자동 동기화 구축 완료 |
| T-011 | 스케줄 변수명 일원화(SCHEDULE_USDMS_*) 및 주간 유지보수 스케줄 외부화, API 개정에 따른 .env 실시간 갱신 및 reschedule 보존 처리 적용 |
| T-105 (2026-06-16) | logging.basicConfig 기본값 누락에 따른 로깅 중단 복구, /tasks/status API 내 실행 중 플래그 동적 오버라이드 구현 |