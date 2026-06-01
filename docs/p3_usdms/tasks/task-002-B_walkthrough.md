# Walkthrough - USDMS KIS Price Pipeline Integration (T-002-B)

## 1. 구현 개요
본 태스크에서는 한국투자증권(KIS) 미국 주식 API를 기반으로 한 일일 가격(OHLCV) 및 가격 수정계수(Adjustment Factors) 연동 파이프라인(`T-002-B`)을 구현하고 검증을 완료하였습니다.

- **`KisUSClient`**: KIS 해외 주식 일봉 시세 API(`HHDFS76240000`)를 통해 지정된 기간의 주식 정보 수집. 종목 검색 시 거래소 자동 탐색(`NAS`, `NYS`, `AMS`) 및 하이픈 티커(예: `BRK-B` -> `BRK/B`) KIS 호환 자동 변환을 포함합니다.
- **`PriceEngine`**: 수정주가와 원본주가의 비율($Ratio = Adj\ Close / Close$) 변화를 계산하고, 전일 대비 변동이 $10^{-5}$ 이상 발생한 권리락/주식분할 등 이벤트를 자동 감지하여 수정계수($Factor = Ratio_{t-1} / Ratio_t$)를 역산 후 데이터베이스에 적재합니다.
- **`PriceRepo`**: TimescaleDB Hypertable인 `us_daily_price` 및 `us_price_adjustment_factors`에 대해 `execute_values` 기반 벌크 업서트를 처리하여 I/O 부하를 최적화합니다.
- **FastAPI GET Endpoints**:
  - `/api/data/price/daily`: 특정 종목(CIK)의 일일 주가(Raw)를 기간 필터링하여 조회합니다.
  - `/api/data/price/factors`: 특정 종목(CIK)의 수정계수 변경 내역을 시간순으로 조회합니다.

---

## 2. 구현된 파일 목록

| 모듈 분류 | 파일 경로 | 주요 역할 |
|---|---|---|
| **Repository** | [price_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/price_repo.py) | 일일 가격 및 수정계수 DB I/O (TimescaleDB 최적화) |
| **API Client** | [kis_us_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/kis_us_client.py) | `KisApiCore` 상속, KIS 해외주식 일봉 및 거래소 탐색 래핑 |
| **Engine** | [price_engine.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/price_engine.py) | $1e-5$ 임계값 기반 주식분할/배당 수정계수 역산 연산기 |
| **Loader** | [market_data_loader.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/collectors/market_data_loader.py) | 데이터 수집 및 수정계수 연산을 조율하는 오케스트레이터 |
| **Router** | [data.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/data.py) | `/price/daily` 및 `/price/factors` REST API 구현 |
| **Test Suite** | [test_price_collect.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_price_collect.py) | Tier 1 ~ 3 TDD 테스트 및 API 단위 테스트 |

---

## 3. 테스트 검증 결과

### 3.1 단위 및 API 모의 테스트 (Tier 1 & 2)
```bash
conda run -n tdms_p3_env pytest tests/test_price_collect.py -v -m "not integration"
```
```text
tests/test_price_collect.py::test_price_engine_detects_split_event_and_calculates_factor PASSED [ 20%]
tests/test_price_collect.py::test_price_engine_ignores_missing_columns PASSED [ 40%]
tests/test_price_collect.py::test_market_data_loader_saves_data_and_triggers_price_engine PASSED [ 60%]
tests/test_price_collect.py::test_get_daily_prices_endpoint PASSED       [ 80%]
tests/test_price_collect.py::test_get_price_factors_endpoint PASSED      [100%]
================= 5 passed, 1 deselected, 2 warnings in 0.89s ==================
```

### 3.2 데이터베이스 실제 통합 테스트 (Tier 3)
로컬에 구동 중인 PostgreSQL 인스턴스에 실제로 커넥션 풀을 맺어 `us_daily_price`에 삽입하고 정상적으로 조회되는지 검증하였습니다.
```bash
conda run -n tdms_p3_env pytest tests/test_price_collect.py -v --run-integration
```
```text
tests/test_price_collect.py::test_price_engine_detects_split_event_and_calculates_factor PASSED [ 16%]
tests/test_price_collect.py::test_price_engine_ignores_missing_columns PASSED [ 33%]
tests/test_price_collect.py::test_market_data_loader_saves_data_and_triggers_price_engine PASSED [ 50%]
tests/test_price_collect.py::test_price_pipeline_stores_to_real_db PASSED [ 66%]
tests/test_price_collect.py::test_get_daily_prices_endpoint PASSED       [ 83%]
tests/test_price_collect.py::test_get_price_factors_endpoint PASSED      [100%]
======================== 6 passed, 2 warnings in 2.70s =========================
```

---

## 4. 로컬 터미널 시연 실행 가이드

실제 KIS API 및 DB 환경이 완전히 구성되어 있는 상황에서 수집 파이프라인의 실 시연을 진행하고자 하신다면 다음 한 줄짜리 python 코드를 실행할 수 있습니다.

```bash
# 1. KIS API 자격증명 및 DB 호스트 등을 미리 환경 변수로 주입
export KIS_APP_KEY="YOUR_KIS_APP_KEY"
export KIS_APP_SECRET="YOUR_KIS_APP_SECRET"
export KIS_ACCOUNT_NO="YOUR_KIS_ACCOUNT_NO"

# 2. AAPL(Apple)의 일봉 데이터(최근 15일 범위) 수집 시연
conda run -n tdms_p3_env env PYTHONPATH=/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core python -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from p3_usdms.collectors.market_data_loader import MarketDataLoader
loader = MarketDataLoader()
print('>>> AAPL 종목에 대한 시세 수집 및 수정계수 연산을 시연합니다...')
success = loader.process_ticker(cik='0000320193', ticker='AAPL', start_date='2026-05-15', end_date='2026-06-01')
print('>>> 시연 완료! 수집 성공 여부:', success)
"
```
