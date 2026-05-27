# tests/test_range_backfill_t010.py

import unittest
from unittest.mock import MagicMock, patch
from datetime import date, datetime
import pandas as pd

from tasks.daily_task import DailyTask, run_daily_update

class TestRangeBackfillT010(unittest.TestCase):
    def setUp(self):
        self.kis_client = MagicMock()
        self.ohlcv_repo = MagicMock()
        self.master_repo = MagicMock()
        self.factor_repo = MagicMock()
        self.market_cap_repo = MagicMock()
        self.kiwoom_client = MagicMock()

        self.task = DailyTask(
            kis_client=self.kis_client,
            ohlcv_repo=self.ohlcv_repo,
            master_repo=self.master_repo,
            factor_repo=self.factor_repo,
            market_cap_repo=self.market_cap_repo,
            kiwoom_client=self.kiwoom_client
        )

    def test_range_based_daily_task_success(self):
        """
        마지막 적재일이 5영업일 전이고 공백이 5일일 때 범위 수집 기능이 단 1회 호출로 벌크 적재되는지 검증합니다.
        """
        start_date = date(2026, 5, 20)
        end_date = date(2026, 5, 24)

        # 1. Mocking 리포지토리 및 캘린더 개수 설정 (5일)
        self.ohlcv_repo.get_trading_days_count.return_value = 5
        self.master_repo.get_all_active_stocks.return_value = [
            {"stk_cd": "005930", "listed_shares": 1000000, "is_active": True}
        ]

        # 2. 5영업일치의 일봉 모의 데이터 빌드
        mock_ohlcvs = [
            {"stk_cd": "005930", "dt": date(2026, 5, 20), "open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100000},
            {"stk_cd": "005930", "dt": date(2026, 5, 21), "open": 50500, "high": 52000, "low": 50000, "close": 51500, "volume": 120000},
            {"stk_cd": "005930", "dt": date(2026, 5, 22), "open": 51500, "high": 52500, "low": 51000, "close": 52000, "volume": 110000},
            {"stk_cd": "005930", "dt": date(2026, 5, 23), "open": 52000, "high": 53000, "low": 51800, "close": 52500, "volume": 130000},
            {"stk_cd": "005930", "dt": date(2026, 5, 24), "open": 52500, "high": 53500, "low": 52200, "close": 53000, "volume": 140000},
        ]
        self.kis_client.fetch_daily_ohlcv_range.return_value = mock_ohlcvs

        # 수정계수 역산을 위한 범위 시세 조회 모의
        self.kis_client.fetch_ohlcv_range.side_effect = [
            [{"dt": d["dt"], "close": d["close"]} for d in mock_ohlcvs], # raw
            [{"dt": d["dt"], "close": d["close"]} for d in mock_ohlcvs], # adj
        ]

        self.factor_repo.get_recent_event_stocks_map.return_value = {}

        # 3. Task 실행
        res = self.task.run(start_date, end_date)

        # 4. 검증 단언 (Assertion)
        self.assertEqual(res["collected"], 5)
        # 종목당 fetch_daily_ohlcv_range가 단 1회 호출되었는지 확인
        self.kis_client.fetch_daily_ohlcv_range.assert_called_once_with("005930", start_date, end_date)
        
        # upsert_daily_ohlcv가 1번 일괄 호출되었는지 확인
        self.ohlcv_repo.upsert_daily_ohlcv.assert_called_once_with(mock_ohlcvs)

        # 시가총액 일괄 upsert 검증
        self.market_cap_repo.upsert_daily_market_cap.assert_called_once()
        mc_records = self.market_cap_repo.upsert_daily_market_cap.call_args[0][0]
        self.assertEqual(len(mc_records), 5)
        self.assertEqual(mc_records[0]["mkt_cap"], 50500 * 1000000)

        # 물리 수정주가 테이블 일괄 갱신 범위 검증
        self.ohlcv_repo.refresh_adjusted_ohlcv_batch.assert_called_once_with(
            date(2026, 4, 20), end_date, 'KIS'
        )

    def test_range_based_minute_task_success(self):
        """
        공백이 3일일 때 분봉 수집 시 max_requests가 동적으로 커지고 범위 필터링되어 벌크 업서트되는지 검증합니다.
        """
        start_date = date(2026, 5, 20)
        end_date = date(2026, 5, 22)

        # 1. 3일 영업일 모의 설정
        self.ohlcv_repo.get_trading_days_count.return_value = 3
        self.ohlcv_repo.get_minute_target_history.return_value = [{"symbol": "005930"}]

        # 2. 3일 범위에 해당하는 분봉 및 외부 날짜 분봉 믹스 모의 데이터 설정
        # 1일 380개 기준, 3일치 영업일 = 약 1140개. max_requests = max(1, 3 * 380 // 600 + 1) = 2
        # 키들은 DATA_MAPPER['kiwoom']['minute_ohlcv'] 스펙에 맞춤
        mock_minute_data = [
            {"cntr_tm": "20260519153000", "cur_prc": "50000", "open_pric": "50000", "high_pric": "50100", "low_pric": "49900", "trde_qty": "1000"}, # start_date 이전 (필터링 되어야 함)
            {"cntr_tm": "20260520090100", "cur_prc": "50100", "open_pric": "50100", "high_pric": "50200", "low_pric": "50000", "trde_qty": "2000"}, # 5/20 (적재 대상)
            {"cntr_tm": "20260521090100", "cur_prc": "50200", "open_pric": "50200", "high_pric": "50300", "low_pric": "50100", "trde_qty": "3000"}, # 5/21 (적재 대상)
            {"cntr_tm": "20260522153000", "cur_prc": "50500", "open_pric": "50500", "high_pric": "50600", "low_pric": "50400", "trde_qty": "4000"}, # 5/22 (적재 대상)
            {"cntr_tm": "20260523090100", "cur_prc": "50600", "open_pric": "50600", "high_pric": "50700", "low_pric": "50500", "trde_qty": "5000"}, # end_date 이후 (필터링 되어야 함)
        ]
        self.kiwoom_client.get_minute_chart.return_value = mock_minute_data

        # 3. 분봉 범위 수집 메서드 직접 실행
        self.task._collect_daily_minute_data_range(start_date, end_date)

        # 4. 검증 단언 (Assertion)
        # max_requests가 2로 기동되었는지 검증
        self.kiwoom_client.get_minute_chart.assert_called_once_with("005930", start_date="20260522", max_requests=2)
        
        # upsert_minute_ohlcv가 호출되었으며, 필터링 후 3개 레코드만 전달되었는지 검증
        self.ohlcv_repo.upsert_minute_ohlcv.assert_called_once()
        inserted_list = self.ohlcv_repo.upsert_minute_ohlcv.call_args[0][0]
        
        # 날짜 필터링 검증
        self.assertEqual(len(inserted_list), 3)
        self.assertTrue(all(item["stk_cd"] == "005930" for item in inserted_list))
        
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        dt_tms = [item["dt_tm"] for item in inserted_list]
        
        self.assertIn(datetime(2026, 5, 20, 9, 1, 0, tzinfo=kst), dt_tms)
        self.assertIn(datetime(2026, 5, 21, 9, 1, 0, tzinfo=kst), dt_tms)
        self.assertIn(datetime(2026, 5, 22, 15, 30, 0, tzinfo=kst), dt_tms)
        
        self.assertNotIn(datetime(2026, 5, 19, 15, 30, 0, tzinfo=kst), dt_tms)
        self.assertNotIn(datetime(2026, 5, 23, 9, 1, 0, tzinfo=kst), dt_tms)

    @patch("tasks.daily_task.datetime")
    @patch("tasks.daily_task.DailyTask")
    @patch("tasks.daily_task.OhlcvRepo")
    @patch("tasks.daily_task.create_kdms_pool")
    def test_run_daily_update_calculates_correct_dates_with_gaps(self, mock_create_pool, mock_ohlcv_repo_class, mock_task_class, mock_datetime):
        """
        run_daily_update 진입점이 DB 상의 최종 수집일과 17시 종료 기준을 토대로
        공백 시작일(start_date)과 최후 목표일(end_date)을 동적으로 정확히 산출하는지 테스트합니다.
        """
        # mock datetime 설정 (2026-05-27 18:00 KST)
        mock_datetime.now.return_value = datetime(2026, 5, 27, 18, 0, 0)
        
        # ohlcv_repo 인스턴스 모킹
        mock_ohlcv_repo = MagicMock()
        mock_ohlcv_repo.get_last_collected_date.return_value = date(2026, 5, 22)
        mock_ohlcv_repo.get_open_trading_days.return_value = [
            date(2026, 5, 25), # 월요일
            date(2026, 5, 26), # 화요일
            date(2026, 5, 27), # 수요일 (오늘)
        ]
        mock_ohlcv_repo_class.return_value = mock_ohlcv_repo
        
        mock_task_instance = MagicMock()
        mock_task_instance.run.return_value = {"collected": 5, "failed": 0, "skipped": 0}
        mock_task_class.return_value = mock_task_instance
        
        job_statuses = {"daily_update": {}}

        
        # run_daily_update 테스트 실행 (test_mode=True)
        with patch("tasks.daily_task.MasterRepo", MagicMock()), \
             patch("tasks.daily_task.FactorRepo", MagicMock()), \
             patch("tasks.daily_task.MarketCapRepo", MagicMock()):
            run_daily_update(job_statuses, test_mode=True)

        # 검증: start_date=2026-05-25 (공백 첫 영업일), end_date=2026-05-27 (오늘)로 기동되었는지 검증
        mock_task_instance.run.assert_called_once_with(date(2026, 5, 25), date(2026, 5, 27))

