import pytest
from datetime import date
from contextlib import contextmanager
from p2_kdms.repositories.master_repo import MasterRepo

def test_upsert_stock_info_returns_row_count(mocker):
    """
    [목적] 종목 마스터 upsert 후 처리된 행 수를 반환하는지 검증.
    [유도] INSERT INTO stock_info ON CONFLICT(stk_cd) DO UPDATE 구현 유도.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 3

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = MasterRepo(pool=mock_pool)
    records = [
        {"stk_cd": "005930", "stk_nm": "삼성전자",
         "market": "KOSPI", "is_active": True, "listed_dt": date(1975, 6, 11), "listed_shares": 5969782550},
    ]
    count = repo.upsert_stock_info(records)
    assert count == 3


def test_get_all_active_stocks_returns_only_active(mocker):
    """
    [목적] get_all_active_stocks()가 is_active=True인 종목만 반환하는지 검증.
    [유도] WHERE is_active = TRUE 조건 구현 유도.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [
        ("005930", "삼성전자", "KOSPI", True),
        ("000660", "SK하이닉스", "KOSPI", True),
    ]

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = MasterRepo(pool=mock_pool)
    stocks = repo.get_all_active_stocks()

    assert len(stocks) == 2
    assert all(s["is_active"] for s in stocks)


def test_stocks_endpoint_returns_200_with_stock_list(mocker):
    """
    [목적] GET /api/data/stocks 응답이 200과 종목 목록을 반환하는지 검증.
    [유도] routers/data.py에 /api/data/stocks GET 엔드포인트 + MasterRepo 의존성 주입 구현 유도.
    """
    from fastapi.testclient import TestClient

    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자",
         "market": "KOSPI", "is_active": True, "listed_dt": "1975-06-11"},
    ]

    from p2_kdms.main import app
    # DI override (FastAPI dependency_overrides 사용)
    from p2_kdms.routers.data import get_master_repo
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo

    client = TestClient(app)
    response = client.get("/api/data/stocks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["stk_cd"] == "005930"

    app.dependency_overrides.clear()
