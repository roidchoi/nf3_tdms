import pytest
from datetime import date
from p2_kdms.tasks.daily_task import DailyTask

def test_daily_task_run_updates_master_before_ohlcv(mocker):
    """
    [목적] DailyTask.run()이 종목마스터 갱신 → OHLCV 수집 순서를 보장하는지 검증.
    [유도] PRD §5.1: "팩터 → OHLCV 순서 보장 로직" 준수. 종목마스터가 선행해야
           get_all_active_stocks()로 수집 대상을 확정할 수 있음.
    """
    call_order = []

    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.side_effect = lambda: call_order.append("master") or []
    mock_kis.fetch_daily_ohlcv.side_effect = lambda *a, **kw: call_order.append("ohlcv") or None

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = []

    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
    )
    task.run(target_date=date(2026, 5, 14))

    assert call_order[0] == "master"


def test_daily_task_run_returns_summary_dict(mocker):
    """
    [목적] run() 결과가 collected/failed/skipped 키를 포함한 dict인지 검증.
    [유도] 수집 결과를 구조화된 형태로 반환하여 로깅 및 모니터링에 활용.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930"}, {"stk_cd": "000660"}
    ]
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 14),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 1000000
    }

    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 14))

    assert "collected" in result
    assert "failed" in result
    assert "skipped" in result
    assert isinstance(result["collected"], int)


def test_daily_task_records_gap_when_fetch_returns_none(mocker):
    """
    [목적] fetch_daily_ohlcv()가 None을 반환한 종목이 gap으로 기록되는지 검증.
    [유도] 수집 실패 → ohlcv_repo.record_gap() 호출 구현 유도.
           PRD F-01: "수집 실패 종목을 gap 목록으로 별도 기록"
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_kis.fetch_daily_ohlcv.return_value = None  # 수집 실패

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]

    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 14))

    mock_ohlcv_repo.record_gap.assert_called_once_with(
        "005930", date(2026, 5, 14), mocker.ANY
    )
    assert result["failed"] == 1


def test_daily_task_runs_factor_calculation_and_refresh(mocker):
    """
    [목적] factor_repo 가 제공되었을 때 DailyTask 가 수정계수(factor) 역산 및 
           물리 테이블 배치 갱신(refresh_adjusted_ohlcv_batch)까지 완수하는지 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    # target_date에 1건 리턴
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 14),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 1000000
    }
    # fetch_ohlcv_range 모의 데이터 (계산식에서 ratio 변동을 발생시켜 factor가 1개 나오도록 설정)
    mock_kis.fetch_ohlcv_range.side_effect = [
        [
            {"dt": date(2026, 5, 13), "close": 100.0},
            {"dt": date(2026, 5, 14), "close": 50.0}
        ], # raw
        [
            {"dt": date(2026, 5, 13), "close": 2.0},
            {"dt": date(2026, 5, 14), "close": 2.0}
        ]  # adj
    ]

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]
    mock_factor_repo = mocker.MagicMock()

    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        factor_repo=mock_factor_repo
    )
    result = task.run(date(2026, 5, 14), rebuild_factors=True)

    # factor_repo 및 refresh_adjusted_ohlcv_batch 가 정상 호출되었는지 단언
    mock_factor_repo.upsert_adjustment_factors.assert_called_once()
    mock_ohlcv_repo.refresh_adjusted_ohlcv_batch.assert_called_once()
    assert result["collected"] == 1


def test_target_date_is_yesterday_when_run_before_market_close(mocker):
    """
    [목적] 17:00 KST 이전에 run_daily_update()가 실행되면
           target_date가 전날(yesterday)로 결정되는지 검증.
    [유도] 장 중 수동 실행 시 미확정 당일 데이터 오염 방지.
           start_time.hour < 17 → target_date = start_time.date() - 1일
    """
    from datetime import datetime, date, timedelta
    from zoneinfo import ZoneInfo
    from tasks.daily_task import run_daily_update
 
    KST = ZoneInfo("Asia/Seoul")
    # 09:30 KST (장 중) 시뮬레이션
    fake_now = datetime(2026, 5, 27, 9, 30, 0, tzinfo=KST)
    mocker.patch("tasks.daily_task.datetime", wraps=datetime)
    mocker.patch("tasks.daily_task.datetime").now.return_value = fake_now
 
    captured_target_date = {}
 
    def fake_run(start_date, end_date=None, **kwargs):
        captured_target_date["date"] = end_date if end_date else start_date
        return {"collected": 0, "failed": 0, "skipped": 1}
 
    mock_task = mocker.MagicMock()
    mock_task.run.side_effect = fake_run
 
    mocker.patch("tasks.daily_task.create_kdms_pool")
    mocker.patch("tasks.daily_task.MasterRepo")
    mocker.patch("tasks.daily_task.OhlcvRepo")
    mocker.patch("tasks.daily_task.FactorRepo")
    mocker.patch("tasks.daily_task.MarketCapRepo")
    mocker.patch("tasks.daily_task.DailyTask", return_value=mock_task)
    # test_mode=True로 KIS/Kiwoom 클라이언트 초기화 우회
    job_statuses = {}
    run_daily_update(job_statuses, test_mode=True)
 
    expected_date = date(2026, 5, 26)  # 전날
    assert captured_target_date.get("date") == expected_date, (
        f"장 중 실행 시 target_date는 전날이어야 함. 실제: {captured_target_date.get('date')}"
    )
 
 
def test_target_date_is_today_when_run_after_market_close(mocker):
    """
    [목적] 17:00 KST 이후에 run_daily_update()가 실행되면
           target_date가 당일(today)로 결정되는지 검증.
    [유도] 장 종료 후 수동 실행 시 당일 확정 데이터 정상 수집.
           start_time.hour >= 17 → target_date = start_time.date()
    """
    from datetime import datetime, date
    from zoneinfo import ZoneInfo
    from tasks.daily_task import run_daily_update
 
    KST = ZoneInfo("Asia/Seoul")
    # 17:30 KST (장 종료 후) 시뮬레이션
    fake_now = datetime(2026, 5, 27, 17, 30, 0, tzinfo=KST)
    mocker.patch("tasks.daily_task.datetime", wraps=datetime)
    mocker.patch("tasks.daily_task.datetime").now.return_value = fake_now
 
    captured_target_date = {}
 
    def fake_run(start_date, end_date=None, **kwargs):
        captured_target_date["date"] = end_date if end_date else start_date
        return {"collected": 0, "failed": 0, "skipped": 1}
 
    mock_task = mocker.MagicMock()
    mock_task.run.side_effect = fake_run
 
    mocker.patch("tasks.daily_task.create_kdms_pool")
    mocker.patch("tasks.daily_task.MasterRepo")
    mocker.patch("tasks.daily_task.OhlcvRepo")
    mocker.patch("tasks.daily_task.FactorRepo")
    mocker.patch("tasks.daily_task.MarketCapRepo")
    mocker.patch("tasks.daily_task.DailyTask", return_value=mock_task)
    job_statuses = {}
    run_daily_update(job_statuses, test_mode=True)
 
    expected_date = date(2026, 5, 27)  # 당일
    assert captured_target_date.get("date") == expected_date, (
        f"장 종료 후 실행 시 target_date는 당일이어야 함. 실제: {captured_target_date.get('date')}"
    )


def test_daily_task_stock_specific_gap_collection(mocker):
    """
    [목적] 종목별 DB 상의 마지막 적재일에 맞춰 수집 범위(stk_start)가 동적으로 확장되는지 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    
    # 갭 시나리오:
    # 005930 (삼성전자) - 5일 전 수집 완료 상태 (갭 있음) -> T-4 ~ T 수집 예정
    # 000660 (SK하이닉스) - 이미 당일(T)까지 완료 상태 -> T-1 ~ T 덮어쓰기 예정
    # 035720 (카카오) - DB 적재 이력 없음 (신규) -> T-5 ~ T 수집 예정
    
    mock_ohlcv_repo = mocker.MagicMock()
    mock_ohlcv_repo.get_all_stocks_latest_dates.return_value = {
        "005930": date(2026, 5, 9),
        "000660": date(2026, 5, 14),
    }
    mock_ohlcv_repo.get_all_stocks_latest_adjusted_info.return_value = {}
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930"},
        {"stk_cd": "000660"},
        {"stk_cd": "035720"},
    ]
    
    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    task.run(target_date=date(2026, 5, 9), end_date=date(2026, 5, 14))
    
    # 각 종목에 대한 fetch_daily_ohlcv_range 또는 fetch_daily_ohlcv가 동적으로 기동되었는지 확인
    # 005930: last_dt=5/9 이므로 start=5/10, end=5/14 (base_start: 5/8, stk_last_dt+1: 5/10 -> min(5/8, 5/10) = 5/8)
    mock_kis.fetch_daily_ohlcv_range.assert_any_call("005930", date(2026, 5, 8), date(2026, 5, 14))
    
    # 000660: last_dt=5/14 이므로 start=5/8, end=5/14 (base_start: target_date-1 -> 5/8)
    mock_kis.fetch_daily_ohlcv_range.assert_any_call("000660", date(2026, 5, 8), date(2026, 5, 14))
    
    # 035720: last_dt 없음 이므로 start=5/4 (T-5), end=5/14
    mock_kis.fetch_daily_ohlcv_range.assert_any_call("035720", date(2026, 5, 4), date(2026, 5, 14))


def test_daily_task_two_stage_factor_discrepancy_rebuild(mocker):
    """
    [목적] Stage 1에서 임계치 5% 미만인 변동률이더라도 Stage 2에서 API와 DB 수정종가 괴리 발생 시
           수정계수(factors) 재계산이 정상 트리거되는지 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    
    # 일봉 수집 데이터 (괴리율 1% 미만, Stage 1에서는 주가 anomaly로 판정되지 않음)
    mock_kis.fetch_daily_ohlcv_range.return_value = [
        {"stk_cd": "005930", "dt": date(2026, 5, 13), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 1000000},
        {"stk_cd": "005930", "dt": date(2026, 5, 14), "open": 70000, "high": 71000, "low": 69000, "close": 70200, "volume": 1000000},
    ]
    
    # Stage 2: KIS API로 최근 5일치 수정주가 조회 결과 (여기서 5/13 종가가 35000으로 권리락 반영되어 있음)
    mock_kis.fetch_ohlcv_range.side_effect = [
        # Stage 2 check_start ~ end_date 범위
        [
            {"dt": date(2026, 5, 13), "close": 35000.0},
            {"dt": date(2026, 5, 14), "close": 70200.0}
        ],
        # Stage 2 통과 후 Factor 계산용 Raw/Adj 시세
        [{"dt": date(2026, 5, 13), "close": 70000.0}, {"dt": date(2026, 5, 14), "close": 70200.0}], # Raw
        [{"dt": date(2026, 5, 13), "close": 35000.0}, {"dt": date(2026, 5, 14), "close": 70200.0}]  # Adj
    ]
    
    mock_ohlcv_repo = mocker.MagicMock()
    # DB상 마지막 적재일은 5/13, 수정종가는 70000 (권리락 반영 안 됨)
    mock_ohlcv_repo.get_all_stocks_latest_adjusted_info.return_value = {
        "005930": (date(2026, 5, 13), 70000)
    }
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]
    mock_factor_repo = mocker.MagicMock()
    
    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        factor_repo=mock_factor_repo
    )
    task.run(target_date=date(2026, 5, 13), end_date=date(2026, 5, 14))
    
    # 수정종가 괴리 (DB: 70000 vs API: 35000)로 인해 factor 계산 및 upsert가 일어나야 함.
    mock_factor_repo.upsert_adjustment_factors.assert_called_once()


def test_daily_task_fallback_no_previous_data(mocker):
    """
    [목적] 과거 DB 수정종가 데이터가 없는 Fallback 상황에서 팩터 재구축이 강제 기동되는지 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_kis.fetch_daily_ohlcv_range.return_value = [
        {"stk_cd": "005930", "dt": date(2026, 5, 14), "open": 70000, "high": 71000, "low": 69000, "close": 70000, "volume": 1000000}
    ]
    mock_kis.fetch_ohlcv_range.side_effect = [
        [{"dt": date(2026, 5, 13), "close": 100.0}, {"dt": date(2026, 5, 14), "close": 50.0}], # Raw
        [{"dt": date(2026, 5, 13), "close": 2.0}, {"dt": date(2026, 5, 14), "close": 2.0}]  # Adj
    ]
    
    mock_ohlcv_repo = mocker.MagicMock()
    # DB에 해당 종목 정보가 없음
    mock_ohlcv_repo.get_all_stocks_latest_adjusted_info.return_value = {}
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]
    mock_factor_repo = mocker.MagicMock()
    
    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        factor_repo=mock_factor_repo
    )
    task.run(target_date=date(2026, 5, 14))
    
    # DB 내 수정종가 정보가 부재하므로 rebuild_factors 작동하여 upsert 호출되어야 함.
    mock_factor_repo.upsert_adjustment_factors.assert_called_once()


def test_daily_task_minute_gap_skipping_and_dynamic_requests(mocker):
    """
    [목적] 분봉 수집 기동 시 종목별 분봉 적재 유무 및 갭(Gap) 크기에 따라 스킵 또는 max_requests가 조정되는지 검증.
    """
    from datetime import datetime
    
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    
    mock_kiwoom = mocker.MagicMock()
    # 수집 모의 데이터 반환 (필터 통과용)
    mock_kiwoom.get_minute_chart.return_value = [
        {"cntr_tm": "20260514153000", "open": 70000, "high": 71000, "low": 69000, "close": 70500, "volume": 100}
    ]
    
    mock_ohlcv_repo = mocker.MagicMock()
    mock_ohlcv_repo.get_all_stocks_latest_dates.return_value = {}
    mock_ohlcv_repo.get_all_stocks_latest_adjusted_info.return_value = {}
    
    # 갭 시나리오:
    # 1. 005930 - 이미 오늘(5/14)까지 완벽하게 분봉 수집 완료 -> 수집 스킵
    # 2. 000660 - 5/12 까지 분봉 수집 완료 (갭 2영업일 발생) -> max_requests = 2로 수집
    # 3. 035720 - 분봉 수집 이력 없음 -> max_requests = 7로 수집
    mock_ohlcv_repo.get_all_minute_latest_datetimes.return_value = {
        "005930": datetime(2026, 5, 14, 15, 30, 0),
        "000660": datetime(2026, 5, 12, 15, 30, 0),
    }
    
    # get_trading_days_count mock
    # 005930: (5/15 ~ 5/14) -> 0일
    # 000660: (5/13 ~ 5/14) -> 2일
    def fake_get_trading_days_count(start, end):
        if start > end:
            return 0
        if start == date(2026, 5, 13) and end == date(2026, 5, 14):
            return 2
        return 1
    
    mock_ohlcv_repo.get_trading_days_count.side_effect = fake_get_trading_days_count
    
    # 타겟 종목들 (분기별 분봉 수집 대상 선정 결과 모킹)
    mock_ohlcv_repo.get_minute_target_history.return_value = [
        {"symbol": "005930"},
        {"symbol": "000660"},
        {"symbol": "035720"}
    ]
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930"},
        {"stk_cd": "000660"},
        {"stk_cd": "035720"}
    ]
    
    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        kiwoom_client=mock_kiwoom
    )
    task.run(target_date=date(2026, 5, 9), end_date=date(2026, 5, 14))
    
    # 1. 005930 (갭 0일) -> 스킵되어 get_minute_chart 미호출 검증
    for call_args in mock_kiwoom.get_minute_chart.call_args_list:
        assert call_args[0][0] != "005930"
        
    # 2. 000660 (갭 2일) -> max_requests = (2 * 380) // 600 + 1 = 2
    mock_kiwoom.get_minute_chart.assert_any_call("000660", start_date="20260514", max_requests=2)
    
    # 3. 035720 (이력 없음) -> max_requests = 7
    mock_kiwoom.get_minute_chart.assert_any_call("035720", start_date="20260514", max_requests=7)



