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
    result = task.run(date(2026, 5, 14))

    # factor_repo 및 refresh_adjusted_ohlcv_batch 가 정상 호출되었는지 단언
    mock_factor_repo.upsert_adjustment_factors.assert_called_once()
    mock_ohlcv_repo.refresh_adjusted_ohlcv_batch.assert_called_once()
    assert result["collected"] == 1

