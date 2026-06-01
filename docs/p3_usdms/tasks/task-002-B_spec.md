# Task-002-B: 일봉 OHLCV + 수정계수 + 가격 API (KIS)

> **Sub Project**: p3_usdms
> **PRD 근거**: F-02 (일봉 OHLCV 수집), F-03 (수정주가 계산 엔진), API-데이터
> **작성일**: 2026-06-01
> **의존 Task**: T-002-A (티커 마스터 수집 코어)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| KIS API 설정 변수 | `tdms_core/p3_usdms/config.py` | ⚠️ 직접 확인 |
| KisApiCore 인터페이스 | `tdms_core/p1_shared/p1_shared/api/kis_api_core.py` | ⚠️ 직접 확인 |
| DB Connection Pool | `pjt_wiki/p1_shared_wiki/interfaces/db_connection_pool.md` | ✅ 확인 |
| USDMS DB 스키마 | `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/db_schema.md` | ✅ 확인 |
| KisUSREST & PriceEngine | `migration_pjt/usdms_origin/backend/collectors/` | ⚠️ 직접 확인 |
| PriceRepo | 신규 설계 | 🆕 신규 |

---

## § 1. 목표

한국투자증권(KIS) 미국 주식 API를 활용하여 일봉 OHLCV 데이터를 수집 및 저장하고, 원본 대비 수정주가 비율의 변화를 수학적으로 추적하여 가격 수정계수(Adjustment Factors)를 산출하는 파이프라인을 구축합니다. 또한 이를 조회할 수 있는 레포지토리와 REST API를 함께 완성합니다.

**구현 범위:**
- **IN**:
  - `KisUSClient`: `p1_shared.api.KisApiCore`를 상속하여 구현하며, KIS 해외주식 일봉 API를 페이지네이션 및 토큰 캐싱을 거쳐 래핑.
  - `PriceEngine`: Ratio 방식(Ratio = Adj Close / Raw Close)을 활용해 전일비 $10^{-5}$ 이상의 변화가 발생한 시점에 권리락/주식분할 등 수정계수 이벤트(`us_price_adjustment_factors`) 자동 검출 및 산출.
  - `MarketDataLoader`: Active 타겟팅된 주식들을 대상으로 일봉 OHLCV를 배치/일일 수집하고 DB 적재 및 수정계수 연산을 유기적으로 유도.
  - `PriceRepo`: `us_daily_price` 및 `us_price_adjustment_factors`에 대한 CRUD 접근 인터페이스 제공.
  - `/api/data/price/daily`, `/api/data/price/factors` API 엔드포인트 구현.
- **OUT**:
  - SEC EDGAR 기반 마스터 동기화 및 yfinance Enrichment (T-002-A)
  - 재무 데이터 XBRL 파싱 엔진 (T-003)

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/collectors/kis_us_client.py` — KIS 미국 주식 API 클라이언트 (상속 기반 리팩토링)
- `tdms_core/p3_usdms/collectors/market_data_loader.py` — 일봉 OHLCV 수집 파이프라인
- `tdms_core/p3_usdms/collectors/price_engine.py` — 수정계수 계산 엔진
- `tdms_core/p3_usdms/repositories/price_repo.py` — 일일 가격 및 수정계수 DB 레포지토리
- `tdms_core/p3_usdms/tests/test_price_collect.py` — T-002-B 검증용 테스트 코드

### 수정 대상 파일
- `tdms_core/p3_usdms/routers/data.py` — `/price/daily` 및 `/price/factors` 엔드포인트 추가 구현

---

## § 3. 핵심 인터페이스

### 3.1 KisUSClient
```python
# [출처: p1_shared.api.KisApiCore를 상속하여 리팩토링 구현]
from p1_shared.api.kis_api_core import KisApiCore
import pandas as pd

class KisUSClient(KisApiCore):
    """
    한국투자증권 미국 주식 REST API 래퍼.
    super().request()는 dict를 반환하므로, 기존 .json() 호출을 배제하도록 리팩토링.
    """
    TR_ID_DAILY = 'HHDFS76240000'
    URL_DAILY = '/uapi/overseas-price/v1/quotations/dailyprice'
    EXCHANGE_CANDIDATES = ['NAS', 'NYS', 'AMS']

    def __init__(self, app_key: str, app_secret: str, account_no: str, is_mock: bool = False):
        super().__init__(app_key, app_secret, account_no, is_mock=is_mock)

    def _fetch_chunk(self, ticker: str, exchange: str, base_date: str, mod_yn: str) -> list[dict]:
        """
        1회 데이터 요청(최대 100건).
        BRK-B 처럼 하이픈이 들어간 티커는 KIS API 호환을 위해 슬래시(/)로 변경(BRK/B).
        """
        formatted_ticker = ticker.replace('-', '/')
        params = {
            'AUTH': '',
            'EXCD': exchange,
            'SYMB': formatted_ticker,
            'GUBN': '0',
            'BYMD': base_date,
            'MODP': mod_yn,  # '0': Raw Close, '1': Adj Close
            'KEYB': ''
        }
        # p1_shared.api.KisApiCore.request API 활용
        res = self.request('GET', self.URL_DAILY, params=params, tr_id=self.TR_ID_DAILY)
        return res.get('output2', [])
```

### 3.2 PriceEngine
```python
# [출처: migration_pjt/usdms_origin/backend/collectors/price_engine.py 직접 확인 후 리팩토링]
class PriceEngine:
    def __init__(self, price_repo: Any) -> None:
        self.price_repo = price_repo

    def calculate_factors_from_ratio(self, cik: str, df: pd.DataFrame) -> None:
        """
        수정주가 비율 변동(Ratio = Adj Close / Close)을 추적하여 수정계수 산출 및 DB 적재.
        Formula: Factor = Ratio_t-1 / Ratio_t
        변화 감지 입계치: delta >= 1e-5
        """
        ...
```

### 3.3 PriceRepo
```python
# [신규 정의 — T-002-B에서 설계]
from p3_usdms.repositories.base import BaseRepository

class PriceRepo(BaseRepository):
    def insert_daily_price(self, records: list[dict]) -> None:
        """
        us_daily_price 테이블에 일봉 시세를 bulk insert (ON CONFLICT (dt, cik) DO UPDATE).
        """
        ...

    def upsert_price_factors(self, records: list[dict]) -> None:
        """
        us_price_adjustment_factors 테이블에 수정 계수를 upsert.
        """
        ...

    def get_daily_prices(self, cik: str, start_dt: str, end_dt: str) -> list[dict]:
        """특정 기간의 일일 주가(Raw)를 조회"""
        ...

    def get_price_factors(self, cik: str) -> list[dict]:
        """특정 종목의 전체 수정계수 이력을 조회"""
        ...
```

---

## § 4. 테스트 케이스

### 4.1 정상 동작 케이스 (Tier 1 & Tier 2)

```python
# [Tier 1 — 단위]
def test_price_engine_detects_split_event_and_calculates_factor():
    """
    [목적] Adj Close와 Close의 비율 변동이 발생했을 때 PriceEngine이 이를 감지하고 올바른 팩터 비율을 생성하는지 검증
    [유도] Split 발생 전/후의 DataFrame 모의 데이터를 입력하여 1:2 액션에 대응하는 0.5 팩터 생성을 확인
    """
    # 2:1 주식 분할 예시 (이전 Ratio = 0.5, 당일 Ratio = 1.0)
    data = {
        'Close': [100.0, 100.0, 50.0],
        'Adj Close': [50.0, 50.0, 50.0]
    }
    dates = pd.to_datetime(['2026-05-10', '2026-05-11', '2026-05-12'])
    df = pd.DataFrame(data, index=dates)
    
    mock_repo = MagicMock()
    engine = PriceEngine(mock_repo)
    engine.calculate_factors_from_ratio("0000320193", df)
    
    # upsert_price_factors 가 정상 호출되었는지와 계산된 Factor 확인
    assert mock_repo.upsert_price_factors.called
    factors = mock_repo.upsert_price_factors.call_args[0][0]
    assert len(factors) == 1
    assert factors[0]['factor_val'] == 0.5
    assert factors[0]['event_dt'] == dates[2].date()

# [Tier 2 — 격리 통합]
def test_market_data_loader_saves_data_and_triggers_price_engine(mocker):
    """
    [목적] MarketDataLoader가 종목 수집을 완수했을 때 DB에 OHLCV를 저장하고 연쇄적으로 PriceEngine을 동작시키는지 확인
    [유도] KIS API Mock 데이터를 반환시키고, PriceRepo에 쓰기 요청이 가는지 검사
    """
    loader = MarketDataLoader()
    
    # Mock KIS Client
    mock_df = pd.DataFrame({
        'Open': [10.0], 'High': [11.0], 'Low': [9.0], 'Close': [10.0], 'Adj Close': [10.0], 'Volume': [1000]
    }, index=pd.to_datetime(['2026-05-12']))
    mocker.patch.object(loader.kis, "get_ohlcv", return_value=mock_df)
    
    # Mock Repositories / Engines
    mock_price_repo = mocker.patch.object(loader, "price_repo")
    mock_engine = mocker.patch.object(loader, "price_engine")
    
    # Act
    loader.process_ticker("0000320193", "AAPL")
    
    # Assert
    assert mock_price_repo.insert_daily_price.called
    assert mock_engine.calculate_factors_from_ratio.called
```

### 4.2 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_price_engine_ignores_missing_columns():
    """
    [목적] 시세 DataFrame에 Close 또는 Adj Close가 없더라도 예외를 터뜨리지 않고 안전하게 로깅 후 리턴하는지 검증
    [유도] 비어 있거나 컬럼이 유실된 데이터를 넣었을 때 에러 없이 함수가 종료되는지 테스트
    """
    mock_repo = MagicMock()
    engine = PriceEngine(mock_repo)
    df_invalid = pd.DataFrame({'Open': [10.0]})
    
    # 예외가 던져지지 않고 리턴되는지 확인
    engine.calculate_factors_from_ratio("0000320193", df_invalid)
    assert not mock_repo.upsert_price_factors.called
```

### 4.3 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합]
@pytest.mark.integration
def test_price_pipeline_stores_to_real_db(real_pool):
    """
    [목적] KIS Mock 데이터 파이프라인 구동 결과가 실제 PostgreSQL의 us_daily_price 및 us_price_adjustment_factors 테이블에 정확히 업서트되는지 무결성 최종 검증
    """
    price_repo = PriceRepo()
    price_repo._pool = real_pool
    
    # 1. 이전 값 삭제
    with real_pool.get_cursor() as cur:
        cur.execute("DELETE FROM us_daily_price WHERE cik = '0000320193'")
        
    # 2. 임의의 가격 데이터 물리 적재
    price_repo.insert_daily_price([
        {
            'dt': '2026-05-12', 'cik': '0000320193', 'ticker': 'AAPL',
            'open_prc': 150.0, 'high_prc': 155.0, 'low_prc': 149.0, 'cls_prc': 151.0,
            'vol': 500000, 'amt': 0.0
        }
    ])
    
    # 3. 물리 데이터 확인
    with real_pool.get_cursor() as cur:
        cur.execute("SELECT cls_prc FROM us_daily_price WHERE cik = '0000320193' AND dt = '2026-05-12'")
        res = cur.fetchone()
    
    assert res['cls_prc'] == 151.0
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_price_engine_detects_split_event_and_calculates_factor` | Tier 1 | 정상 | 2:1 액션에 대응하는 0.5 팩터 생성 검증 |
| 2 | `test_market_data_loader_saves_data_and_triggers_price_engine` | Tier 2 | 정상 | 수집 시 DB 물리 쓰기 호출 연동 및 엔진 작동 확인 |
| 3 | `test_price_engine_ignores_missing_columns` | Tier 1 | 예외 | 컬럼 유실 시 비정상 중단 없음 검증 |
| 4 | `test_price_pipeline_stores_to_real_db` | Tier 3 | 실제 통합 | 실 PostgreSQL 테이블 물리 적재 및 트랜잭션 정상 검증 |

**총 4개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **Hypertable 최적화**:
  - `us_daily_price`는 Hypertable로 동작하므로 대량의 INSERT가 빈번합니다. 레포지토리 단에서는 `execute_values` 혹은 `execute_batch`를 활용하여 속도를 최적화하고 데드락을 예방해야 합니다.
- **Ratio 계산의 안전 분모(Safe Division)**:
  - 주식 분할이나 특정 변동성으로 인해 Raw Close가 0이 발생하는 경우가 있을 수 있습니다. `Close`가 0일 때 `NaN` 처리하여 `ZeroDivisionError`가 유발되지 않도록 수학 안전망을 유지하십시오.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 1~3 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 통합 테스트 통과
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 T-002-B 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-002-B_walkthrough.md` 작성
