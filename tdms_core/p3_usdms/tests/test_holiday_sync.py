import pytest
from datetime import date
from unittest.mock import MagicMock, patch

# [Tier 1 — 단위]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
def test_is_us_trading_day_weekend_and_holidays():
    """
    [목적] is_us_trading_day 유틸리티가 미국의 주말(토, 일) 및 공휴일(신정, 독립기념일 등)에 대해 올바르게 False를 반환하고, 일반 평일에 True를 반환하는지 확인
    """
    from p1_shared.utils.date_utils import is_us_trading_day
    
    # 1. 일반 평일 (2026-06-03 수요일) -> True
    assert is_us_trading_day(date(2026, 6, 3)) is True
    # 2. 주말 (2026-06-06 토요일) -> False
    assert is_us_trading_day(date(2026, 6, 6)) is False
    # 3. 미국 공휴일 (2026-05-25 메모리얼 데이) -> False
    assert is_us_trading_day(date(2026, 5, 25)) is False


# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
@pytest.mark.asyncio
async def test_daily_routine_continues_even_when_holiday(mocker):
    """
    [목적] 수집 기준일(target_date)이 미국 주식시장 휴장일일 때도 DailyRoutine.run()이 스킵되지 않고 데이터를 정상 수집하는지 검증
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    
    # 2026-05-25 (메모리얼 데이, 미국 공휴일)
    target_dt = date(2026, 5, 25)
    
    # DB 커서 및 리포지토리 모킹
    mocker.patch("p3_usdms.tasks.daily_routine.MasterRepo")
    mocker.patch("p3_usdms.tasks.daily_routine.BlacklistRepo")
    mocker.patch("p3_usdms.tasks.daily_routine.BlacklistManager")
    
    routine = DailyRoutine()
    
    # 캘린더 동기화 모킹 (영향 차단)
    routine.sync_trading_calendar = mocker.MagicMock()
    # 외부 수집기들 모킹
    routine.master = mocker.MagicMock()
    routine.master.sync_daily = mocker.AsyncMock(return_value={"added_tickers": 0})
    routine.market_loader = mocker.MagicMock()
    routine.market_loader.collect_daily_updates = mocker.MagicMock()
    routine.fin_parser = mocker.MagicMock()
    routine.val_calc = mocker.MagicMock()
    routine.val_calc.repo = mocker.MagicMock()
    routine.val_calc.repo.get_all_latest_valuation_dates.return_value = {}
    
    # target 추출을 위한 mock 설정
    routine.master_repo = mocker.MagicMock()
    routine.master_repo.get_collect_targets.return_value = [{"cik": "0000320193"}]
    routine.blacklist_mgr = mocker.MagicMock()
    routine.blacklist_mgr.is_blacklisted.return_value = False
    
    # DB max price mock 설정
    mock_db = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = {"d": date(2026, 5, 22)}
    mock_db.get_cursor.return_value.__enter__.return_value = mock_cursor
    routine.db = mock_db
    
    # 헬스체크 및 격리/리포트 세이브 모킹
    routine._detect_anomalies_and_quarantine = mocker.Mock(return_value=[])
    routine._save_report = mocker.Mock()
    
    # 실행
    report = await routine.run(target_date=target_dt)
    
    # 검증: status가 SKIPPED가 아니며, sync_daily 및 collect_daily_updates 등이 정상 기동되었는지 검증
    assert report["status"] != "SKIPPED"
    routine.master.sync_daily.assert_called_once()
    routine.market_loader.collect_daily_updates.assert_called_once()


# [Tier 2 — 격리 통합]
# 파일: tdms_core/p3_usdms/tests/test_holiday_sync.py
def test_daily_routine_syncs_trading_calendar(mocker):
    """
    [목적] sync_trading_calendar가 데이터베이스의 trading_calendar 테이블에 미국 영업일 데이터를 정상적으로 자동 동기화하는지 검증
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    
    routine = DailyRoutine()
    
    # DB 커서 모킹
    mock_cursor = mocker.MagicMock()
    routine.db = mocker.MagicMock()
    routine.db.get_cursor = mocker.MagicMock()
    routine.db.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    # MAX(dt)가 2026-05-22(금)이고 target_date가 2026-05-26(화)인 시나리오
    # 2026-05-23(토), 2026-05-24(일), 2026-05-25(월: 메모리얼 데이)는 휴일/휴장('N')
    # 2026-05-26(화)는 개장('Y')
    
    # dict 타입과 tuple 타입 둘 다 지원 가능하도록 유연한 리턴 처리
    class Row(dict):
        def __getitem__(self, item):
            if isinstance(item, int):
                return date(2026, 5, 22)
            return super().__getitem__(item)
    mock_cursor.fetchone.return_value = Row({"d": date(2026, 5, 22), "max": date(2026, 5, 22)})
    
    routine.sync_trading_calendar(limit_date=date(2026, 5, 26))
    
    # execute가 총 4번(5/23, 5/24, 5/25, 5/26) 실행되었는지 확인
    calls = mock_cursor.execute.call_args_list
    insert_calls = [c for c in calls if "INSERT" in c[0][0].upper()]
    assert len(insert_calls) == 4
    
    # 2026-05-25(메모리얼 데이) -> 'N'
    memorial_day_call = [c for c in insert_calls if c[0][1][0] == date(2026, 5, 25)][0]
    assert memorial_day_call[0][1][1] == 'N'
    
    # 2026-05-26(정상 화요일) -> 'Y'
    tuesday_call = [c for c in insert_calls if c[0][1][0] == date(2026, 5, 26)][0]
    assert tuesday_call[0][1][1] == 'Y'
