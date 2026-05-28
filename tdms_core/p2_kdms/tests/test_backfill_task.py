import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime
import requests

from collectors.kiwoom_client import KiwoomClient
from collectors.target_selector import TargetSelector
from tasks.backfill_task import run_backfill_minute_data


# 1. KiwoomClient 페이지네이션 테스트
def test_kiwoom_client_fetch_minute_chart_returns_normalized_records():
    # KiwoomClient의 get_headers()가 토큰 발급을 위해 네트워크로 가지 않도록 mock
    with patch.object(KiwoomClient, "get_headers", return_value={"Authorization": "Bearer test_token"}):
        client = KiwoomClient(app_key="test_key", app_secret="test_secret")
        
        mock_responses = [
            {
                "stk_min_pole_chart_qry": [
                    {"cntr_tm": "20260521090100", "stk_cd": "005930", "open": 1000, "high": 1100, "low": 900, "close": 1050, "vol": 100},
                    {"cntr_tm": "20260521090200", "stk_cd": "005930", "open": 1050, "high": 1060, "low": 1040, "close": 1050, "vol": 200}
                ]
            },
            {
                "stk_min_pole_chart_qry": [
                    {"cntr_tm": "20260521090300", "stk_cd": "005930", "open": 1050, "high": 1080, "low": 1050, "close": 1070, "vol": 300}
                ]
            }
        ]
        
        with patch("collectors.kiwoom_client.requests.post") as mock_post:
            # 첫 번째 응답 헤더에 cont-yn = 'Y' 및 next-key = 'key_1' 설정
            res1 = MagicMock()
            res1.json.return_value = mock_responses[0]
            res1.headers = {"cont-yn": "Y", "next-key": "key_1"}
            
            res2 = MagicMock()
            res2.json.return_value = mock_responses[1]
            res2.headers = {"cont-yn": "N", "next-key": ""}
            
            mock_post.side_effect = [res1, res2]
            
            records = client.get_minute_chart(stock_code="005930", start_date="20260521", max_requests=2)
            
            assert len(records) == 3
            assert records[0]["cntr_tm"] == "20260521090100"
            assert records[2]["cntr_tm"] == "20260521090300"


# 2. TargetSelector 거래대금 상위 N 추출 검증
def test_target_selector_selects_top_n_by_volume():
    db_mock = MagicMock()
    # 3개의 종목 데이터를 흉내냄 (symbol, avg_amount)
    db_mock._execute_query.return_value = [
        {"symbol": "005930", "avg_amount": 100000000.0},
        {"symbol": "000660", "avg_amount": 50000000.0},
        {"symbol": "035420", "avg_amount": 1000000.0}
    ]
    
    selector = TargetSelector(db=db_mock)
    
    top_stocks = selector.select_top_n_stocks(quarter="2026Q1", top_n=2, market="KOSPI")
    
    assert len(top_stocks) == 2
    symbols = [s["symbol"] for s in top_stocks]
    assert "005930" in symbols
    assert "000660" in symbols
    assert "035420" not in symbols



# 3. KiwoomClient API 에러 예외 격리 검증
def test_kiwoom_client_handles_api_exception_safely():
    with patch.object(KiwoomClient, "get_headers", return_value={"Authorization": "Bearer test_token"}):
        client = KiwoomClient(app_key="test_key", app_secret="test_secret")
        
        with patch("collectors.kiwoom_client.requests.post") as mock_post:
            mock_post.side_effect = requests.HTTPError("API Server Error")
            
            records = client.get_minute_chart(stock_code="005930", start_date="20260521")
            assert records == []


# 4. 누락일이 전혀 없을 때 백필 생략 테스트
def test_backfill_task_skips_when_no_missing_days():
    db_mock = MagicMock()
    
    # get_target_stocks, trading_calendar, minute_ohlcv 조회 결과 순차 모킹
    db_mock._execute_query.side_effect = [
        # get_target_stocks 에서 minute_target_history 조회 시 결과
        [{"symbol": "005930"}],
        # trading_calendar 에서 dt 조회 시 결과
        [{"dt": date(2026, 5, 20)}],
        # minute_ohlcv 에서 stk_cd, dt, count 기수집 수량 조회 시 결과
        [{"stk_cd": "005930", "dt": date(2026, 5, 20), "record_count": 380}]  # 360분 이상
    ]
    
    job_statuses = {}
    
    # KiwoomClient, DatabaseManager, 그리고 _sync_trading_calendar_history 를 mock 처리하여 DB 부하 및 에러 차단
    with patch("tasks.backfill_task.KiwoomClient") as mock_client_cls, \
         patch("tasks.backfill_task.DatabaseManager", return_value=db_mock), \
         patch("tasks.backfill_task._sync_trading_calendar_history") as mock_sync:
        
        run_backfill_minute_data(job_statuses, test_mode=False)
        
        # API 호출(`get_minute_chart`)이 전혀 발생하지 않았어야 함
        mock_client_cls.return_value.get_minute_chart.assert_not_called()
        
        # 상태 업데이트 검증
        assert "backfill_minute_data" in job_statuses
        assert job_statuses["backfill_minute_data"]["is_running"] is False
        assert "누락 없음" in job_statuses["backfill_minute_data"]["last_status"]
