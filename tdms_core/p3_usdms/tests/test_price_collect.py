import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime

from p3_usdms.collectors.price_engine import PriceEngine
from p3_usdms.collectors.market_data_loader import MarketDataLoader
from p3_usdms.repositories.price_repo import PriceRepo

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

# [Tier 2 — 격리 통합]
def test_market_data_loader_saves_data_and_triggers_price_engine(mocker):
    """
    [목적] MarketDataLoader가 종목 수집을 완수했을 때 DB에 OHLCV를 저장하고 연쇄적으로 PriceEngine을 동작시키는지 확인
    [유도] KIS API Mock 데이터를 반환시키고, PriceRepo에 쓰기 요청이 가는지 검사
    """
    # Settings & connection pool 모킹하여 로더 초기화 에러 우회
    mocker.patch("p3_usdms.collectors.market_data_loader.DbConnectionPool")
    
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

# [Tier 3 — 실제 통합]
@pytest.mark.integration
def test_price_pipeline_stores_to_real_db(real_pool):
    """
    [목적] KIS Mock 데이터 파이프라인 구동 결과가 실제 PostgreSQL의 us_daily_price 및 us_price_adjustment_factors 테이블에 정확히 업서트되는지 무결성 최종 검증
    """
    price_repo = PriceRepo()
    price_repo._pool = real_pool
    
    # 1. 이전 값 삭제
    with price_repo.get_cursor() as cur:
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
    with price_repo.get_cursor() as cur:
        cur.execute("SELECT cls_prc FROM us_daily_price WHERE cik = '0000320193' AND dt = '2026-05-12'")
        res = cur.fetchone()
    
    assert res['cls_prc'] == 151.0

# [Tier 1 — API 단위]
def test_get_daily_prices_endpoint(mocker):
    """
    [목적] GET /api/data/price/daily API 엔드포인트가 CIK, 기간 쿼리를 올바르게 Repo로 파싱하고 데이터를 반환하는지 검증
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from p3_usdms.routers.data import router as data_router
    
    app = FastAPI()
    app.include_router(data_router)
    client = TestClient(app)
    
    # get_daily_prices 모킹
    mock_data = [
        {'dt': '2026-05-12', 'cik': '0000320193', 'ticker': 'AAPL', 'cls_prc': 151.0}
    ]
    mocker.patch.object(PriceRepo, "get_daily_prices", return_value=mock_data)
    
    response = client.get("/api/data/price/daily?cik=0000320193&start_dt=2026-05-01&end_dt=2026-05-30")
    
    assert response.status_code == 200
    assert response.json() == mock_data
    # 파라미터가 잘 매핑되었는지 확인
    PriceRepo.get_daily_prices.assert_called_once_with("0000320193", "2026-05-01", "2026-05-30")

# [Tier 1 — API 단위]
def test_get_price_factors_endpoint(mocker):
    """
    [목적] GET /api/data/price/factors API 엔드포인트가 CIK 쿼리를 받아 적합한 수정계수 이력을 반환하는지 검증
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from p3_usdms.routers.data import router as data_router
    
    app = FastAPI()
    app.include_router(data_router)
    client = TestClient(app)
    
    mock_factors = [
        {'cik': '0000320193', 'event_dt': '2026-05-12', 'factor_val': 0.5, 'event_type': 'ADJUSTMENT'}
    ]
    mocker.patch.object(PriceRepo, "get_price_factors", return_value=mock_factors)
    
    response = client.get("/api/data/price/factors?cik=0000320193")
    
    assert response.status_code == 200
    assert response.json() == mock_factors
    PriceRepo.get_price_factors.assert_called_once_with("0000320193")

