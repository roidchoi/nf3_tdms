import pytest
from datetime import date, datetime
from unittest.mock import MagicMock

# 수집기, 저장소 및 태스크 임포트
# 구현이 완료되면 정상적으로 임포트되어야 함.
from collectors.pub_data_client import PubDataClient
from repositories.market_cap_repo import MarketCapRepo
from tasks.backfill_task import run_backfill_market_cap
from tasks.daily_task import DailyTask
from routers.admin import router as admin_router


def test_pub_data_client_fetch_market_cap_success(mocker):
    """
    [목적] PubDataClient가 공공데이터 API 응답을 정상적으로 파싱하고 정규화된 형식으로 반환하는지 확인.
    [검증] 단축코드 6자리 변환(A005930 -> 005930), 문자열 데이터가 int로 적절하게 변환되었는지 검증.
    """
    # 1. API 응답 Mocking
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": {
                    "item": [
                        {
                            "basDt": "20260522",
                            "srtnCd": "A005930",
                            "clpr": "70000",
                            "mrktTotAmt": "418000000000000",
                            "trqu": "1200000",
                            "trPrc": "84000000000",
                            "lstgStCnt": "5969782550"
                        }
                    ]
                }
            }
        }
    }
    mocker.patch("httpx.get", return_value=mock_resp)

    # 2. 클라이언트 호출
    client = PubDataClient(api_key="test_api_key")
    result = client.get_market_cap_by_date(date(2026, 5, 22))

    # 3. 단언(Assert)
    assert len(result) == 1
    record = result[0]
    assert record["stk_cd"] == "005930"
    assert record["dt"] == date(2026, 5, 22)
    assert record["cls_prc"] == 70000
    assert record["mkt_cap"] == 418000000000000
    assert record["vol"] == 1200000
    assert record["amt"] == 84000000000
    assert record["listed_shares"] == 5969782550


def test_pub_data_client_handles_api_error(mocker):
    """
    [목적] 공공데이터 API 호출 중 오류 발생 시, 적절히 대처하고 빈 리스트를 반환하는지 확인.
    """
    # 1. HTTP 500 에러 Mocking
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 500
    mocker.patch("httpx.get", return_value=mock_resp)

    client = PubDataClient(api_key="test_api_key")
    result = client.get_market_cap_by_date(date(2026, 5, 22))

    assert result == []


def test_market_cap_repo_upsert_stores_properly(mocker):
    """
    [목적] MarketCapRepo가 DB 풀을 이용해 벌크 UPSERT를 정상 수행하는지 검증.
    """
    # 1. DB 커넥션 및 커서 Mocking
    mock_pool = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_pool.get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # execute_values 모킹
    mock_execute_values = mocker.patch("repositories.market_cap_repo.execute_values")

    # 2. 리포지토리 실행
    repo = MarketCapRepo(mock_pool)
    data = [
        {
            "dt": date(2026, 5, 22),
            "stk_cd": "005930",
            "cls_prc": 70000,
            "mkt_cap": 418000000000000,
            "vol": 1200000,
            "amt": 84000000000,
            "listed_shares": 5969782550
        }
    ]
    repo.upsert_daily_market_cap(data)

    # 3. SQL 실행 여부 단언
    mock_execute_values.assert_called_once()
    mock_conn.commit.assert_called_once()


def test_daily_task_calculates_and_stores_market_cap(mocker):
    """
    [목적] 데일리 태스크 구동 시 KIS 마스터의 상장주식수와 종가를 이용해 시총을 계산하고 적재하는지 확인.
    """
    # 1. 모의 클라이언트 및 리포지토리 구성
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = [
        {"stk_cd": "005930", "listed_shares": 5000000}
    ]
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 22),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 100000
    }

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930", "listed_shares": 5000000}]
    mock_market_cap_repo = mocker.MagicMock()

    # 2. 태스크 생성 및 실행
    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        market_cap_repo=mock_market_cap_repo
    )
    task.run(date(2026, 5, 22))

    # 3. 시가총액 계산 및 적재 단언
    # mkt_cap = 70500 (close) * 5000000 (listed_shares) = 352,500,000,000
    mock_market_cap_repo.upsert_daily_market_cap.assert_called_once()
    called_args = mock_market_cap_repo.upsert_daily_market_cap.call_args[0][0]
    assert len(called_args) == 1
    assert called_args[0]["mkt_cap"] == 352500000000


def test_backfill_market_cap_runs_and_updates_status(mocker):
    """
    [목적] 백필 태스크 수행 시 누락 영업일을 조회하고, 공공데이터 API를 통해 수집해 DB에 저장한 후
           job_statuses 딕셔너리의 상태 및 진행률이 정상 반영되는지 확인.
    """
    # 1. 모의 객체 주입
    mock_pub_client = mocker.MagicMock()
    mock_pub_client.get_market_cap_by_date.return_value = [
        {
            "dt": date(2026, 5, 20),
            "stk_cd": "005930",
            "cls_prc": 70000,
            "mkt_cap": 350000000000,
            "vol": 100000,
            "amt": 7000000000,
            "listed_shares": 5000000
        }
    ]

    mock_mc_repo = mocker.MagicMock()
    mock_mc_repo.get_market_cap_missing_dates.return_value = [date(2026, 5, 20)]

    # time.sleep 모킹 (딜레이 스킵하여 빠른 테스트 보장)
    mocker.patch("time.sleep")

    # 2. 실행
    job_statuses = {"backfill_market_cap": {"is_running": False, "last_status": "none"}}
    run_backfill_market_cap(
        job_statuses=job_statuses,
        pub_client=mock_pub_client,
        mc_repo=mock_mc_repo,
        start_date=date(2026, 5, 19),
        end_date=date(2026, 5, 21)
    )

    # 3. 단언
    assert job_statuses["backfill_market_cap"]["is_running"] is False
    assert job_statuses["backfill_market_cap"]["last_status"] == "success"
    assert job_statuses["backfill_market_cap"]["progress"] == 100
    mock_pub_client.get_market_cap_by_date.assert_called_once_with(date(2026, 5, 20))
    mock_mc_repo.upsert_daily_market_cap.assert_called_once()


def test_admin_run_task_triggers_scheduler_job(mocker):
    """
    [목적] 어드민 /api/v1/admin/tasks/{id}/run API 호출 시 즉시 1회성 스케줄러 등록이 진행되는지 단언.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1/admin")

    # 전역 의존성 객체들을 어드민 라우터에 주입하는 패턴 재현
    mock_scheduler = mocker.MagicMock()
    mock_scheduler.get_jobs.return_value = []
    
    import routers.admin as admin_module
    admin_module.scheduler = mock_scheduler
    admin_module.job_statuses = {
        "daily_update": {"is_running": False, "last_status": "none"},
        "backfill_market_cap": {"is_running": False, "last_status": "none"}
    }

    client = TestClient(app)
    response = client.post("/api/v1/admin/tasks/backfill_market_cap/run")

    assert response.status_code == 200
    assert response.json()["status"] == "triggered"
    mock_scheduler.add_job.assert_called_once()


class StubKisClient:
    """isinstance(obj, MagicMock)이 False가 되도록 하기 위한 스터브 KIS 클라이언트"""
    def fetch_stock_master(self):
        return []
    def fetch_daily_ohlcv(self, stk_cd, target_date):
        return None
    def fetch_ohlcv_range(self, stk_cd, start_dt, target_date, adj_price):
        return []


def test_daily_task_early_exit_on_holiday(mocker):
    """
    [목적] 한국 휴장일(예: 주말)인 경우 KIS API 호출 없이 조기 종료되는지 검증.
    """
    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    
    # 2026년 5월 24일은 일요일(주말 = 휴장일)
    holiday_date = date(2026, 5, 24)
    
    # MagicMock이 아니어야 휴장일 검사가 우회되지 않음
    kis_client = StubKisClient()
    
    task = DailyTask(
        kis_client=kis_client,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo
    )
    
    result = task.run(holiday_date)
    
    # skipped 카운트 확인 및 api 조회 미실행 확인
    assert result["skipped"] == 1
    mock_master_repo.get_all_active_stocks.assert_not_called()


def test_daily_task_factor_cleanup_and_loop2(mocker):
    """
    [목적] Loop 1/Loop 2에 의한 팩터 정화(Clean-up) 및 사후 소멸 보정이 정상적으로 호출되는지 검증.
    """
    import pandas as pd
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = [{"stk_cd": "005930"}]
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 22),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 100000
    }
    # KIS API에서 최근 45일 중 팩터가 2026-05-21만 존재하는 것으로 가정
    mock_kis.fetch_ohlcv_range.side_effect = lambda stk_cd, start_dt, target_date, adj_price: (
        # raw 가격 리스트
        [
            {"dt": date(2026, 5, 19), "close": 10000},
            {"dt": date(2026, 5, 20), "close": 10000},
            {"dt": date(2026, 5, 21), "close": 20000},
            {"dt": date(2026, 5, 22), "close": 20000},
        ] if adj_price == '1' else
        # adj 가격 리스트 (oldest_raw == oldest_adj를 맞춰 정합성을 보장하며, 21일에 팩터 0.5 발생)
        [
            {"dt": date(2026, 5, 19), "close": 10000},
            {"dt": date(2026, 5, 20), "close": 10000},
            {"dt": date(2026, 5, 21), "close": 10000},
            {"dt": date(2026, 5, 22), "close": 10000},
        ]
    )

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930", "listed_shares": 5000}]
    
    mock_factor_repo = mocker.MagicMock()
    
    # DB 상에는 2026-05-21 과 2026-05-18 두 날짜에 팩터가 기록되어 있었다고 모킹 (21일은 신규 생성, 18일은 obsolete 대상)
    # Loop 2 테스트를 위해 "000020"을 recent_event_map에 추가
    mock_factor_repo.get_recent_event_stocks_map.return_value = {
        "005930": [date(2026, 5, 21), date(2026, 5, 18)],
        "000020": [date(2026, 5, 15)]
    }
    
    # 000020에 대한 전체 시세 병합 데이터 모킹 (2026-05-15에 팩터가 없도록 계산되게 함)
    loop2_df = pd.DataFrame([
        {"dt": date(2026, 5, 14), "raw_close": 10000, "adj_close": 10000},
        {"dt": date(2026, 5, 15), "raw_close": 12000, "adj_close": 12000},
        {"dt": date(2026, 5, 16), "raw_close": 12000, "adj_close": 12000},
    ])
    mock_ohlcv_repo.fetch_ohlcv_for_factor_calc.return_value = loop2_df

    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        factor_repo=mock_factor_repo
    )
    
    # 2026년 5월 22일(금요일, 평일) 실행
    task.run(date(2026, 5, 22))

    # KIS API에 의한 45일 계산결과 팩터 날짜는 2026-05-21 하나뿐이므로,
    # DB에만 존재하는 2026-05-18 날짜는 obsolete 대상으로 감지되어 삭제되어야 함 (Loop 1).
    mock_factor_repo.delete_adjustment_factors_by_dates.assert_any_call(
        "005930", [date(2026, 5, 18)], price_source="KIS"
    )

    
    # Loop 2에서 "000020"의 2026-05-15 팩터가 가짜로 판명(API 계산결과 없음)되어 삭제되어야 함.
    mock_factor_repo.delete_adjustment_factors_by_dates.assert_any_call(
        "000020", [date(2026, 5, 15)], price_source="KIS"
    )


def test_daily_task_collects_minute_data(mocker):
    """
    [목적] DailyTask가 분봉 대상 상위 종목들을 올바르게 받아와 당일 분봉 수집을 호출하는지 검증.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = [{"stk_cd": "005930"}]
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 22),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 100000
    }
    
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]

    mock_ohlcv_repo = mocker.MagicMock()
    # 분기 상위 종목 1개 반환
    mock_ohlcv_repo.get_minute_target_history.return_value = [
        {"symbol": "005930", "market": "KOSPI"}
    ]

    mock_kiwoom = mocker.MagicMock()
    mock_kiwoom.get_minute_chart.return_value = [
        # 당일 2026-05-22 분봉 데이터
        {"cntr_tm": "20260522153000", "open": 70000, "high": 70500, "low": 69900, "close": 70100, "volume": 500}
    ]

    # transform_data 모킹
    mocker.patch("collectors.utils.transform_data", return_value=[
        {"dt_tm": datetime(2026, 5, 22, 15, 30), "stk_cd": "005930", "open_prc": 70000, "high_prc": 70500, "low_prc": 69900, "cls_prc": 70100, "vol": 500}
    ])

    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
        kiwoom_client=mock_kiwoom
    )

    task.run(date(2026, 5, 22))

    # Kiwoom API 호출 여부 검증 (start_date가 20260522)
    mock_kiwoom.get_minute_chart.assert_called_once_with("005930", start_date="20260522", max_requests=1)
    
    # ohlcv_repo에 저장되었는지 확인
    mock_ohlcv_repo.upsert_minute_ohlcv.assert_called_once()


