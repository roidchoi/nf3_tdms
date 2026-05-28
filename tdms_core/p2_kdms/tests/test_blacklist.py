import pytest
from datetime import date
from unittest.mock import MagicMock
from p2_kdms.tasks.daily_task import DailyTask
from repositories.ohlcv_repo import OhlcvRepo

def test_blacklist_gap_threshold_isolation(mocker):
    """
    TC-14: ohlcv_repo.get_blacklisted_stocks가 특정 일수(예: 5일) 이상 누적 실패한 종목만 올바르게 추출하는지 검증
    """
    mock_pool = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    # 5번 이상 실패한 종목 A, 3번 실패한 종목 B 가정
    mock_cursor.fetchall.return_value = [("A",)]
    
    repo = OhlcvRepo(mock_pool)
    blacklist = repo.get_blacklisted_stocks(threshold_days=5)
    
    assert blacklist == ["A"]
    sql = mock_cursor.execute.call_args[0][0]
    # daily_ohlcv_gap 테이블과 COUNT(*), GROUP BY stk_cd, HAVING COUNT(*) >= %s 가 포함되는지 검증
    assert "daily_ohlcv_gap" in sql.lower()
    assert "having count" in sql.lower()
    assert mock_cursor.execute.call_args[0][1] == (5,)

def test_daily_task_skips_blacklisted_stocks(mocker):
    """
    TC-15: DailyTask 실행 시 블랙리스트 등록된 종목은 수집을 건너뛰고 skipped 카운트에 올바르게 반영하는지 검증
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    
    mock_ohlcv_repo = mocker.MagicMock()
    mock_ohlcv_repo.get_blacklisted_stocks.return_value = ["005930"] # 삼성전자 블랙리스트
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자"}
    ]
    
    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 23))
    
    # KIS API 호출이 skip 되어야 함
    assert not mock_kis.fetch_daily_ohlcv.called
    assert result["skipped"] == 1
    assert result["collected"] == 0

def test_daily_task_collects_non_blacklisted_stocks(mocker):
    """
    TC-16: 블랙리스트에 없는 종목은 정상 수집하는지 검증
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "000660", "dt": date(2026, 5, 23),
        "open": 180000, "high": 182000, "low": 178000,
        "close": 180000, "volume": 50000
    }
    
    mock_ohlcv_repo = mocker.MagicMock()
    mock_ohlcv_repo.get_blacklisted_stocks.return_value = ["005930"] # 삼성전자만 블랙리스트
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자"},
        {"stk_cd": "000660", "stk_nm": "SK하이닉스"}
    ]
    
    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 23))
    
    # 000660은 정상 호출되어야 함
    mock_kis.fetch_daily_ohlcv.assert_called_once_with("000660", date(2026, 5, 23))
    assert result["skipped"] == 1 # 005930
    assert result["collected"] == 1 # 000660
