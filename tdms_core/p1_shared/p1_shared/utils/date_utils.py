from datetime import date, timedelta
import holidays

def is_kr_trading_day(dt: date) -> bool:
    """주말 및 한국 공휴일 제외."""
    kr_holidays = holidays.KR(years=dt.year)
    return dt.weekday() < 5 and dt not in kr_holidays

def get_kr_trading_days(start_date: date, end_date: date) -> list[date]:
    """start_date ~ end_date(포함) 사이의 영업일 목록 (오름차순)."""
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")
        
    days = []
    current = start_date
    while current <= end_date:
        if is_kr_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days

def last_kr_trading_day(reference: date) -> date:
    """reference 기준 직전(과거) 영업일 반환."""
    current = reference - timedelta(days=1)
    while not is_kr_trading_day(current):
        current -= timedelta(days=1)
    return current
