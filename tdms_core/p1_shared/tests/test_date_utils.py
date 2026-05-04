import pytest
from datetime import date
from p1_shared.utils.date_utils import is_kr_trading_day, get_kr_trading_days, last_kr_trading_day

def test_is_kr_trading_day_returns_true_for_normal_weekday():
    monday = date(2024, 1, 2)
    assert is_kr_trading_day(monday) is True

def test_is_kr_trading_day_returns_false_for_weekend():
    saturday = date(2024, 1, 6)
    sunday = date(2024, 1, 7)
    assert is_kr_trading_day(saturday) is False
    assert is_kr_trading_day(sunday) is False

def test_get_kr_trading_days_excludes_weekends_and_returns_sorted():
    days = get_kr_trading_days(date(2024, 1, 1), date(2024, 1, 7))
    for d in days:
        assert d.weekday() < 5
    assert days == sorted(days)

def test_last_kr_trading_day_returns_friday_when_reference_is_monday():
    monday = date(2024, 1, 8)
    expected_friday = date(2024, 1, 5)
    assert last_kr_trading_day(monday) == expected_friday

def test_get_kr_trading_days_returns_empty_for_weekend_only_range():
    result = get_kr_trading_days(date(2024, 1, 6), date(2024, 1, 7))
    assert result == []

def test_get_kr_trading_days_raises_when_start_after_end():
    with pytest.raises(ValueError):
        get_kr_trading_days(date(2024, 1, 7), date(2024, 1, 1))
