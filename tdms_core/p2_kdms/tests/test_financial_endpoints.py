# tests/test_financial_endpoints.py

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from main import app
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

@pytest.fixture
def client():
    return TestClient(app)

def test_get_financials_endpoint_returns_json(client, mocker):
    """
    [목적] GET /api/data/financials 호출 시 200 OK와 함께 재무제표 및 재무비율 목록이 구조에 맞게 리턴되는지 검증.
    """
    # FinancialRepo 모킹
    mock_statements = [
        {
            "stk_cd": "005930",
            "stac_yymm": "202512",
            "div_cls_code": "1",
            "total_aset": 450000000000000.0,
            "total_lblt": 100000000000000.0,
            "total_cptl": 350000000000000.0,
            "retrieved_at": "2026-05-21T10:00:00+09:00"
        }
    ]
    mock_ratios = [
        {
            "stk_cd": "005930",
            "stac_yymm": "202512",
            "div_cls_code": "1",
            "roe_val": 12.5,
            "eps": 5000.0,
            "retrieved_at": "2026-05-21T10:00:00+09:00"
        }
    ]

    mocker.patch("repositories.financial_repo.FinancialRepo.get_statements_as_of", return_value=mock_statements)
    mocker.patch("repositories.financial_repo.FinancialRepo.get_ratios_as_of", return_value=mock_ratios)

    response = client.get("/api/data/financials?stk_cd=005930&div_cls_code=1")
    assert response.status_code == 200
    
    json_data = response.json()
    assert "statements" in json_data
    assert "ratios" in json_data
    assert len(json_data["statements"]) == 1
    assert json_data["statements"][0]["stk_cd"] == "005930"
    assert json_data["statements"][0]["total_aset"] == 450000000000000.0
    assert len(json_data["ratios"]) == 1
    assert json_data["ratios"][0]["roe_val"] == 12.5


def test_get_financials_endpoint_with_as_of_date_filtering(client, mocker):
    """
    [목적] as_of_date 쿼리 파라미터가 명시적으로 지정되었을 때,
           해당 일시가 ISO format 또는 YYYYMMDD 파싱되어 Repository로 전달되는지 검증.
    """
    mock_get_statements = mocker.patch("repositories.financial_repo.FinancialRepo.get_statements_as_of", return_value=[])
    mocker.patch("repositories.financial_repo.FinancialRepo.get_ratios_as_of", return_value=[])

    # 1. ISO 포맷
    response = client.get("/api/data/financials?stk_cd=005930&div_cls_code=1&as_of_date=2026-05-21T12:00:00")
    assert response.status_code == 200
    mock_get_statements.assert_called_once()
    called_dt = mock_get_statements.call_args[0][2]
    assert called_dt.year == 2026
    assert called_dt.month == 5
    assert called_dt.day == 21

    # 2. YYYYMMDD 포맷 지원
    mock_get_statements.reset_mock()
    response = client.get("/api/data/financials?stk_cd=005930&div_cls_code=1&as_of_date=20260521")
    assert response.status_code == 200
    mock_get_statements.assert_called_once()
    called_dt = mock_get_statements.call_args[0][2]
    assert called_dt.year == 2026
    assert called_dt.month == 5
    assert called_dt.day == 21


def test_get_financials_invalid_params_returns_422(client):
    """
    [목적] 필수 파라미터(stk_cd 등) 누락 시 FastAPI가 422 Unprocessable Entity 에러를 올바르게 리턴하는지 검증.
    """
    response = client.get("/api/data/financials?div_cls_code=1")  # stk_cd 없음
    assert response.status_code == 422
