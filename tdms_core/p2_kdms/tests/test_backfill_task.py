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
  # 4. 누락일이 전혀 없을 때 백필 생략 테스트
def test_backfill_task_skips_when_no_missing_days():
    db_mock = MagicMock()
    
    db_mock._execute_query.side_effect = [
        # get_target_stocks 결과
        [{"symbol": "005930"}],
        # _detect_missing_and_partial_days 내의 LEFT JOIN bulk 대조 결과 (정상)
        [
            {"dt": date(2026, 5, 20), "stk_cd": "005930", "daily_volume": 10000, "record_count": 380, "sum_min_vol": 10000}
        ]
    ]
    
    job_statuses = {}
    
    # KiwoomClient, DatabaseManager, 그리고 _sync_trading_calendar_history 를 mock 처리하여 DB 부하 및 에러 차단
    with patch("tasks.backfill_task.KiwoomClient") as mock_client_cls, \
         patch("tasks.backfill_task.DatabaseManager", return_value=db_mock), \
         patch("tasks.backfill_task._sync_trading_calendar_history") as mock_sync:
        
        run_backfill_minute_data(job_statuses, test_mode=False, start_date=date(2026, 5, 20), end_date=date(2026, 5, 20))
        
        # API 호출(`get_minute_chart`)이 전혀 발생하지 않았어야 함
        mock_client_cls.return_value.get_minute_chart.assert_not_called()
        
        # 상태 업데이트 검증
        assert "backfill_minute_data" in job_statuses
        assert job_statuses["backfill_minute_data"]["is_running"] is False
        assert "누락 없음" in job_statuses["backfill_minute_data"]["last_status"] or "success (누락 없음)" in job_statuses["backfill_minute_data"]["last_status"]


def test_backfill_task_dynamic_max_requests():
    """
    [목적] 분봉 백필 태스크 수행 시 갭 크기에 따라 max_requests가 동적으로 조정되는지 검증.
    """
    db_mock = MagicMock()
    
    db_mock._execute_query.side_effect = [
        # 1. get_target_stocks
        [{"symbol": "005930"}],
        # 2. _detect_missing_and_partial_days 내의 LEFT JOIN bulk 대조 결과 (5/19 누락)
        [
            {"dt": date(2026, 5, 19), "stk_cd": "005930", "daily_volume": 10000, "record_count": 0, "sum_min_vol": 0},
            {"dt": date(2026, 5, 20), "stk_cd": "005930", "daily_volume": 10000, "record_count": 380, "sum_min_vol": 10000}
        ],
        # 3. trading_calendar 영업일 카운트 결과 (1일)
        [{"count": 1}]
    ]
    
    job_statuses = {}
    
    with patch("tasks.backfill_task.KiwoomClient") as mock_client_cls, \
         patch("tasks.backfill_task.DatabaseManager", return_value=db_mock), \
         patch("tasks.backfill_task._sync_trading_calendar_history"):
        
        # get_minute_chart mock
        mock_api = mock_client_cls.return_value
        mock_api.get_minute_chart.return_value = [
            {"cntr_tm": "20260519153000", "stk_cd": "005930", "open": 1000, "high": 1100, "low": 900, "close": 1050, "vol": 100}
        ]
        
        # 5/19 ~ 5/20 백필 기동
        run_backfill_minute_data(job_statuses, test_mode=False, start_date=date(2026, 5, 19), end_date=date(2026, 5, 20))
        
        # 갭 1일에 대해 max_requests = (1 * 380) // 600 + 1 = 1 로 기동되어야 함
        mock_api.get_minute_chart.assert_called_once_with("005930", start_date="20260519", max_requests=1)


def test_backfill_minute_hybrid_threshold():
    """
    [목적] 분봉 백필 시, 개수가 360건 미만이더라도 거래량 정합성(오차 5% 이하)이 맞으면 누락으로 판정하지 않는 하이브리드 누락 감지 검증.
    """
    db_mock = MagicMock()
    
    # 3개 종목 시나리오:
    # 1. 005930: 분봉 370건 (정규장 활발) -> 정상
    # 2. 000660: 분봉 45건, 분봉거래량합 1000주, 일봉거래량 1000주 (오차 0%) -> 정상 (거래 희소 종목 구제)
    # 3. 035420: 분봉 150건, 분봉거래량합 500주, 일봉거래량 1000주 (오차 50%) -> 누락 (진짜 누락)
    
    db_mock._execute_query.side_effect = [
        # 1. get_target_stocks
        [{"symbol": "005930"}, {"symbol": "000660"}, {"symbol": "035420"}],
        # 2. _detect_missing_and_partial_days 내의 캘린더/일봉/분봉 LEFT JOIN bulk 쿼리 결과
        [
            # 005930 (정상)
            {"dt": date(2026, 5, 20), "stk_cd": "005930", "daily_volume": 1000000, "record_count": 370, "sum_min_vol": 950000},
            # 000660 (거래 희소 정상 구제)
            {"dt": date(2026, 5, 20), "stk_cd": "000660", "daily_volume": 1000, "record_count": 45, "sum_min_vol": 1000},
            # 035420 (진짜 누락)
            {"dt": date(2026, 5, 20), "stk_cd": "035420", "daily_volume": 1000, "record_count": 150, "sum_min_vol": 500}
        ]
    ]
    
    job_statuses = {}
    
    with patch("tasks.backfill_task.KiwoomClient") as mock_client_cls, \
         patch("tasks.backfill_task.DatabaseManager", return_value=db_mock), \
         patch("tasks.backfill_task._sync_trading_calendar_history"):
        
        mock_api = mock_client_cls.return_value
        mock_api.get_minute_chart.return_value = []
        
        run_backfill_minute_data(job_statuses, test_mode=False, start_date=date(2026, 5, 20), end_date=date(2026, 5, 20))
        
        # 오직 진짜 누락인 035420 에 대해서만 get_minute_chart API 호출이 일어나야 함!
        mock_api.get_minute_chart.assert_called_once_with("035420", start_date="20260520", max_requests=1)


def test_backfill_daily_data_detects_middle_gap():
    """
    [목적] 일봉 백필 실행 시 trading_calendar와 daily_ohlcv를 대조하여 
    중간 누락된 영업일을 검출하고 핀포인트로 KIS API 수집 및 수정계수 재역산을 연계 호출하는지 검증.
    """
    from tasks.backfill_task import run_backfill_daily_data
    import pandas as pd
    
    db_mock = MagicMock()
    master_repo_mock = MagicMock()
    ohlcv_repo_mock = MagicMock()
    factor_repo_mock = MagicMock()
    
    # 005930 종목이 활성 종목으로 등록
    master_repo_mock.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]
    
    # 5/19 (누락일), 5/20 (정상일) 대조 쿼리 결과 모킹
    db_mock._execute_query.side_effect = [
        # 1. query_missing 쿼리 결과: 5/19 누락 감지
        [{"dt": date(2026, 5, 19), "stk_cd": "005930"}]
    ]
    
    job_statuses = {}
    
    with patch("tasks.backfill_task.DatabaseManager", return_value=db_mock), \
         patch("tasks.backfill_task.MasterRepo", return_value=master_repo_mock), \
         patch("tasks.backfill_task.OhlcvRepo", return_value=ohlcv_repo_mock), \
         patch("tasks.backfill_task.FactorRepo", return_value=factor_repo_mock), \
         patch("tasks.backfill_task.KisKrClient") as mock_kis_cls, \
         patch("collectors.factor_calculator.calculate_factors", return_value=[{"stk_cd": "005930", "ratio": 1.0}]) as mock_calc:
        
        # KIS API mock
        mock_kis = mock_kis_cls.return_value
        # 5/19 일봉 데이터 반환
        mock_kis.fetch_daily_ohlcv_range.return_value = [
            {
                "dt": date(2026, 5, 19),
                "open": 50000,
                "close": 50500,
                "high": 51000,
                "low": 49900,
                "volume": 100000,
                "amt": 5000000000
            }
        ]
        
        # 수정계수 계산용 범위 시세 반환 모킹
        mock_kis.fetch_ohlcv_range.return_value = [
            {"dt": date(2026, 5, 18), "close": 49000},
            {"dt": date(2026, 5, 19), "close": 50000}
        ]
        
        # 일봉 백필 구동
        run_backfill_daily_data(job_statuses, test_mode=False, start_date=date(2026, 5, 19), end_date=date(2026, 5, 20))
        
        # 1. KIS API가 5/19 ~ 5/19 범위로 핀포인트 호출되었는지 검증
        mock_kis.fetch_daily_ohlcv_range.assert_called_once_with("005930", start_date=date(2026, 5, 19), end_date=date(2026, 5, 19))
        
        # 2. upsert_daily_ohlcv 가 호출되어 적재되었는지 검증
        ohlcv_repo_mock.upsert_daily_ohlcv.assert_called_once()
        
        # 3. 수정계수 재역산이 연동 호출되었는지 검증
        mock_calc.assert_called_once()
        factor_repo_mock.upsert_adjustment_factors.assert_called_once()
        
        # 4. 물리 수정주가 테이블 갱신 호출 검증
        ohlcv_repo_mock.refresh_adjusted_ohlcv_batch.assert_called_once_with(
            date(2026, 5, 14), # 5/19 - 5일
            date(2026, 5, 19),
            'KIS'
        )
        
        # 완료 상태 확인
        assert "backfill_daily_data" in job_statuses
        assert job_statuses["backfill_daily_data"]["is_running"] is False
        assert job_statuses["backfill_daily_data"]["last_status"] == "success"


