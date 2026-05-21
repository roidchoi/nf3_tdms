# tests/test_ohlcv_repo_adjusted.py

import pytest
from datetime import date
from contextlib import contextmanager
from repositories.ohlcv_repo import OhlcvRepo

def test_refresh_adjusted_ohlcv_batch_executes_cte(mocker):
    """
    [목적] refresh_adjusted_ohlcv_batch 가 DB 레벨에서 SQL CTE 구문을 활용하여 원본 시세에 수정계수를 결합 및 누적곱 처리하고, 
           물리 테이블인 daily_ohlcv_adjusted 에 일괄 UPSERT를 완료하는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 100

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    row_count = repo.refresh_adjusted_ohlcv_batch(
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14)
    )

    assert row_count == 100
    mock_cursor.execute.assert_called_once()
    called_sql = mock_cursor.execute.call_args[0][0]
    # CTE 구문 핵심 키워드가 포함되었는지 검증
    assert "WITH" in called_sql
    assert "daily_ohlcv_adjusted" in called_sql
    assert "EXP(SUM(LN(" in called_sql or "EXP" in called_sql
