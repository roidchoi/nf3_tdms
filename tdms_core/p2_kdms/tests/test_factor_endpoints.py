# tests/test_factor_endpoints.py

import pytest
from datetime import date
from fastapi.testclient import TestClient
from main import app

# mock_repo들을 오버라이드하기 위한 종속성 함수 mock 등록
from routers.data import get_factor_repo, get_ohlcv_repo


def test_endpoint_get_factors_returns_list(mocker):
    """
    [목적] GET /api/data/factors/{stk_cd} 가 특정 종목의 수정계수 리스트를 반환하는지 검증.
    """
    mock_factor_repo = mocker.MagicMock()
    mock_factor_repo.get_factors_for_stock.return_value = [
        {
            "stk_cd": "005930",
            "event_dt": date(2018, 5, 4),
            "price_ratio": 0.02,
            "volume_ratio": 50.0,
            "price_source": "KIS",
            "details": "{}"
        }
    ]

    app.dependency_overrides[get_factor_repo] = lambda: mock_factor_repo
    client = TestClient(app)
    response = client.get("/api/data/factors/005930?price_source=KIS")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["price_ratio"] == 0.02

    app.dependency_overrides.clear()


def test_endpoint_adjusted_ohlcv_calculates_correct_prices(mocker):
    """
    [목적] GET /api/data/ohlcv/daily/adjusted API 호출 시 DB 원본 일봉과 수정계수 데이터를 조인하여 
           정확한 누적 수정 주가 및 수정 거래량을 실시간 계산(온더플라이)하는지 검증.
    """
    mock_ohlcv_repo = mocker.MagicMock()
    # 원본 OHLCV 모의 데이터 (2018-05-02, 03, 04)
    # 2018-05-04에 50:1 액면분할(수정계수 0.02, 거래량 50.0)이 반영된다고 가정.
    mock_ohlcv_repo.get_daily_ohlcv.return_value = [
        {"dt": date(2018, 5, 2), "stk_cd": "005930", "open": 2650000, "high": 2650000, "low": 2650000, "close": 2650000, "volume": 100},
        {"dt": date(2018, 5, 3), "stk_cd": "005930", "open": 2650000, "high": 2650000, "low": 2650000, "close": 2650000, "volume": 100},
        {"dt": date(2018, 5, 4), "stk_cd": "005930", "open": 51900, "high": 51900, "low": 51900, "close": 51900, "volume": 5000},
    ]

    mock_factor_repo = mocker.MagicMock()
    # 2018-05-04 수정계수 이벤트 등록
    mock_factor_repo.get_factors_for_stock.return_value = [
        {"stk_cd": "005930", "event_dt": date(2018, 5, 4), "price_ratio": 0.02, "volume_ratio": 50.0, "price_source": "KIS"}
    ]

    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_factor_repo] = lambda: mock_factor_repo

    client = TestClient(app)
    response = client.get("/api/data/ohlcv/daily/adjusted?stk_cd=005930&start_date=2018-05-02&end_date=2018-05-04&price_source=KIS")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3

    # 온더플라이 실시간 계산 알고리즘 검증:
    # 2018-05-04 이후에 이벤트가 없으므로 05-04 당일은 누적 비율 1.0 적용.
    # 2018-05-02, 05-03은 05-04 이벤트의 price_ratio=0.02, volume_ratio=50.0이 누적곱 적용되어 곱해짐.
    # 2018-05-02: cls_prc_adj = 2650000 * 0.02 = 53000, volume_adj = 100 * 50.0 = 5000
    # 2018-05-04: cls_prc_adj = 51900 * 1.0 = 51900, volume_adj = 5000 * 1.0 = 5000

    row_02 = next(r for r in body if r["dt"] == "2018-05-02")
    row_04 = next(r for r in body if r["dt"] == "2018-05-04")

    assert row_02["close"] == 53000
    assert row_02["volume"] == 5000
    assert row_04["close"] == 51900
    assert row_04["volume"] == 5000

    app.dependency_overrides.clear()


def test_endpoint_adjusted_ohlcv_direct_queries_physical_table(mocker):
    """
    [목적] GET /api/data/ohlcv/adjusted/{stk_cd} API가 복잡한 CTE 연산 없이 물리 테이블인 daily_ohlcv_adjusted 테이블을 
           직접 SELECT 쿼리로 최적화 조회하는지 검증.
    """
    mock_ohlcv_repo = mocker.MagicMock()
    mock_ohlcv_repo.get_adjusted_ohlcv_direct.return_value = [
        {"dt": date(2018, 5, 2), "stk_cd": "005930", "open": 53000, "high": 53000, "low": 53000, "close": 53000, "volume": 5000, "adj_factor": 0.02}
    ]

    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    client = TestClient(app)
    response = client.get("/api/data/ohlcv/adjusted/005930?start_date=2018-05-02&end_date=2018-05-02")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["close"] == 53000
    mock_ohlcv_repo.get_adjusted_ohlcv_direct.assert_called_once_with(
        "005930", date(2018, 5, 2), date(2018, 5, 2)
    )

    app.dependency_overrides.clear()
