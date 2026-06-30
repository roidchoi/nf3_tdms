import pytest
from datetime import date
from contextlib import contextmanager
from p2_kdms.repositories.ohlcv_repo import OhlcvRepo

def test_upsert_daily_ohlcv_inserts_new_records(mocker):
    """
    [목적] 신규 레코드가 daily_ohlcv에 삽입되고 행 수를 반환하는지 검증.
    [유도] DbConnectionPool.get_cursor() 사용 + INSERT ON CONFLICT DO UPDATE 구현 유도.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 2

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    records = [
        {"stk_cd": "005930", "dt": date(2026, 5, 14),
         "open": 70000, "high": 71000, "low": 69000,
         "close": 70500, "volume": 1000000, "amt": 70500000000, "turn_rt": 1.25},
        {"stk_cd": "000660", "dt": date(2026, 5, 14),
         "open": 180000, "high": 182000, "low": 178000,
         "close": 181000, "volume": 500000, "amt": 90500000000, "turn_rt": 2.11},
    ]
    count = repo.upsert_daily_ohlcv(records)

    assert count == 2
    mock_cursor.executemany.assert_called_once_with(
        mocker.ANY,
        [
            ("005930", date(2026, 5, 14), 70000, 71000, 69000, 70500, 1000000, 70500000000, 1.25),
            ("000660", date(2026, 5, 14), 180000, 182000, 178000, 181000, 500000, 90500000000, 2.11),
        ]
    )


def test_get_latest_date_returns_most_recent_date(mocker):
    """
    [목적] get_latest_date()가 특정 종목의 가장 최근 수집일을 반환하는지 검증.
    [유도] SELECT MAX(dt) FROM daily_ohlcv WHERE stk_cd=%s 쿼리 구현 유도.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = (date(2026, 5, 13),)

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    result = repo.get_latest_date("005930")

    assert result == date(2026, 5, 13)


def test_upsert_daily_ohlcv_with_empty_list_returns_zero(mocker):
    """
    [목적] 빈 리스트 입력 시 0을 반환하고 DB 쿼리를 실행하지 않는지 검증.
    [유도] 불필요한 빈 쿼리 방지 로직 구현 유도.
    """
    mock_pool = mocker.MagicMock()
    repo = OhlcvRepo(pool=mock_pool)
    result = repo.upsert_daily_ohlcv([])

    assert result == 0
    mock_pool.get_cursor.assert_not_called()


def test_get_latest_date_returns_none_for_new_stock(mocker):
    """
    [목적] 한 번도 수집된 적 없는 종목의 get_latest_date()가 None을 반환하는지 검증.
    [유도] fetchone()이 (None,)을 반환하는 경우 None 반환 처리 구현 유도.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = (None,)

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    result = repo.get_latest_date("999999")

    assert result is None
