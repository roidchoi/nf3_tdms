# tests/test_factor_repo.py

import pytest
from datetime import date
from contextlib import contextmanager
from repositories.factor_repo import FactorRepo

def test_upsert_adjustment_factors_returns_row_count(mocker):
    """
    [목적] 수정계수 리스트 업서트 후 처리된 행 수를 정상 반환하는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 2

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FactorRepo(pool=mock_pool)
    factors = [
        {
            "stk_cd": "005930",
            "event_dt": date(2018, 5, 4),
            "price_ratio": 0.02,
            "volume_ratio": 50.0,
            "price_source": "KIS",
            "details": '{"adj_close": 51900.0, "raw_close": 51900.0}'
        },
        {
            "stk_cd": "000660",
            "event_dt": date(2026, 5, 14),
            "price_ratio": 1.0,
            "volume_ratio": 1.0,
            "price_source": "KIS",
            "details": '{}'
        }
    ]
    
    count = repo.upsert_adjustment_factors(factors)
    assert count == 2
    mock_cursor.executemany.assert_called_once()


def test_get_factors_for_stock_queries_and_returns_list(mocker):
    """
    [목적] 특정 종목에 대해 event_dt 오름차순으로 수정계수 이력을 정확히 조회하는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [
        ("005930", date(2018, 5, 4), 0.02, 50.0, "KIS", '{"adj_close": 51900.0}')
    ]

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FactorRepo(pool=mock_pool)
    result = repo.get_factors_for_stock("005930", "KIS")

    assert len(result) == 1
    assert result[0]["stk_cd"] == "005930"
    assert result[0]["price_ratio"] == 0.02
    assert result[0]["volume_ratio"] == 50.0


def test_delete_adjustment_factors_calls_execute_with_params(mocker):
    """
    [목적] delete_adjustment_factors()가 올바른 파라미터로 DELETE 쿼리를 수행하는지 검증.
    """
    mock_cursor = mocker.MagicMock()

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FactorRepo(pool=mock_pool)
    repo.delete_adjustment_factors("005930", "KIS")

    mock_cursor.execute.assert_called_once()
    called_args = mock_cursor.execute.call_args[0]
    assert "DELETE" in called_args[0]
    assert called_args[1] == ("005930", "KIS")
