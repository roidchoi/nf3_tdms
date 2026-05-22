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
