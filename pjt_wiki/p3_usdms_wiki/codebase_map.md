# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p3_usdms (미국 시장 데이터 백엔드)  
> **마지막 업데이트**: 2026-06-02 (Task-004 완료)  
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

```
tdms_core/p3_usdms/
├── collectors/           # 데이터 수집 레이어 [✅완성]
│   ├── sec_client.py     # SEC EDGAR API 연동용 클라이언트
│   ├── master_sync.py    # 미국 주식 마스터 동기화 오케스트레이터
│   ├── kis_us_client.py  # KIS API 기반 미국 주식 시세 연동 클라이언트
│   ├── price_engine.py   # Ratio 기반 가격 수정계수 계산 엔진
│   ├── market_data_loader.py # 일봉 시세 수집 및 팩터 연동 파이프라인
│   └── financial_parser.py # SEC XBRL facts 수집/정제 및 discrete 분기 재무 데이터 도출
├── engines/              # 비즈니스 연산 엔진 레이어 [✅완성]
│   ├── valuation_calculator.py # PIT 기반 가치평가 비율 산출 (pe, pb, ps, pcr, ev_ebitda)
│   └── metric_calculator.py    # 9대 재무비율 및 3대 YoY 성장률 산출
├── repositories/         # 데이터 접근 레이어 [✅완성]
│   ├── base.py           # DbConnectionPool 및 EnvDetector를 래핑한 기본 레포지토리
│   ├── master_repo.py    # us_ticker_master, us_ticker_history CIK 기반 데이터 I/O
│   ├── price_repo.py     # us_daily_price, us_price_adjustment_factors 데이터 I/O
│   └── valuation_repo.py # us_daily_valuation 및 us_financial_metrics 데이터 I/O
├── routers/              # API 라우팅 레이어 [✅완성]
│   └── data.py           # 마스터 목록, 일일 주가, 수정계수 조회 엔드포인트
├── tests/                # 테스트 스위트 [✅완성]
│   ├── conftest.py       # pytest 픽처 및 DB 풀 정의
│   ├── test_base_infra.py # DB 커넥션 풀 검증
│   ├── test_master_sync.py # 마스터 동기화 검증
│   ├── test_price_collect.py # 일일 시세 수집, 팩터 감지 엔진, API 통합 검증
│   └── test_valuation_metric.py # 가치평가, 재무비율, 대량 550종목 루프 성능 및 적재 통합 검증
├── config.py             # 환경 설정 모듈 [✅완성]
└── main.py               # FastAPI 애플리케이션 진입점 [✅완성]
```

---

## 2. 핵심 데이터 흐름

```
[ SEC EDGAR / yfinance ]
         │
         │ (MasterSync / SECClient / yfinance)
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
```

---

## 3. 모듈별 상태 및 역할

| 모듈/폴더 | 상태 | 핵심 파일 | 역할 요약 |
|---|---|---|---|
| **collectors** | ✅ | `master_sync.py`, `financial_parser.py` | SEC 공시 및 KIS 시세 데이터 동기화, discrete 재무 제표 도출 파이프라인 |
| **engines** | ✅ | `valuation_calculator.py`, `metric_calculator.py` | PIT 기반 가치평가비율 및 YoY 성장률을 포함한 12대 퀀트 재무지표 산출 |
| **repositories** | ✅ | `master_repo.py`, `valuation_repo.py` | 마스터, 시세, 가치평가, 재무비율 대용량 DB 저장 및 최적화 조회 기능 제공 |
| **routers** | ✅ | `data.py` | 외부 퀀트 및 분석 서비스 대상 마스터, 일봉, 수정계수 조회 서비스 제공 |
| **config** | ✅ | `config.py`, `main.py` | FastAPI 기동, DB 커넥션 풀 초기화, 기동 전 Startup Validator 유효성 검증 |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트 | 실행 방법 | 역할 |
|---|---|---|
| `main.py` | `uvicorn main:app --port 8000` | FastAPI Web API Server 기동 |
| `tests/test_master_sync.py` | `pytest tests/test_master_sync.py` | SEC 마스터 데이터 동기화 파이프라인 검증 |
| `tests/test_price_collect.py` | `pytest tests/test_price_collect.py` | KIS 일일 시세, 수정계수 산출 엔진 및 REST API 검증 |
| `tests/test_valuation_metric.py` | `pytest tests/test_valuation_metric.py` | 가치평가/재무비율 연산 단위 및 대량 실 계산 루프 안정성 검증 |

---

## 5. 테스트 현황

| 테스트 파일 | 커버 대상 | 상태 |
|---|---|---|
| `tests/test_base_infra.py` | DbConnectionPool, StartupValidator | ✅ 통과 |
| `tests/test_master_sync.py` | SECClient, MasterRepo, MasterSync | ✅ 통과 |
| `tests/test_price_collect.py` | KisUSClient, PriceEngine, PriceRepo, routers/data.py | ✅ 통과 |
| `tests/test_valuation_metric.py` | ValuationCalculator, MetricCalculator, ValuationRepo | ✅ 통과 |

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