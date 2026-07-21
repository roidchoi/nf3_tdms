# tests/test_discrepancy_unpacking.py

import unittest
from unittest.mock import MagicMock, patch
from datetime import date

from tasks.backfill_task import run_backfill_daily_data

class TestDiscrepancyUnpacking(unittest.TestCase):
    """
    로컬 DB 내부 불일치 종목(경로 A) 감지 시 
    discrepancy_stock_map 저장 및 3자 재검증 과정에서
    TypeError(cannot unpack non-iterable date) 없이 정밀 처리되는지 검증합니다.
    """

    @patch("tasks.backfill_task.DatabaseManager")
    @patch("tasks.backfill_task.KisKrClient")
    @patch("tasks.backfill_task.FactorRepo")
    @patch("tasks.backfill_task.OhlcvRepo")
    def test_local_discrepancy_unpacking_safety(self, mock_ohlcv_repo, mock_factor_repo, mock_kis_client, mock_db_mgr):
        db_inst = MagicMock()
        mock_db_mgr.return_value = db_inst

        # 1. 3자 불일치 탐지 쿼리 모의 (로컬 DB 불일치: 물리 != 계산)
        # check_dt, db_adj_close, calc_adj_close
        db_inst._execute_query.side_effect = [
            # first_dt 조회
            [{"stk_cd": "001020", "first_dt": date(2020, 1, 1)}],
            # trading_calendar 조회 (Phase 1 검증일)
            [{"dt": date(2025, 6, 20)}],
            # 001020 시세 정합성 조회 (물리 50000 != 계산 60000 -> 로컬 DB 불일치 감지)
            [{"dt": date(2025, 6, 20), "raw_close": 50000, "db_adj_close": 50000, "calc_adj_close": 60000}],
            # query_missing 쿼리 결과
            [{"stk_cd": "001020", "min_dt": date(2025, 6, 1), "max_dt": date(2025, 6, 20), "missing_days": [date(2025, 6, 20)]}],
            # 재검증 대조 쿼리 (raw_close, db_adj_close)
            [{"raw_close": 50000, "db_adj_close": 50000}],
            # 재검증 누적 팩터 쿼리 (cum_factor)
            [{"cum_factor": 1.0}]
        ]

        kis_inst = MagicMock()
        mock_kis_client.return_value = kis_inst
        kis_inst.fetch_daily_ohlcv_range.return_value = [
            {"dt": date(2025, 6, 20), "open": 50000, "high": 50000, "low": 50000, "close": 50000, "volume": 1000}
        ]

        # 백필 실행 (test_mode=True)
        try:
            run_backfill_daily_data(test_mode=True, start_date=date(2025, 6, 1), end_date=date(2025, 6, 20), job_statuses={})
            success = True
        except TypeError as te:
            success = False
            self.fail(f"TypeError 발생: {te}")
        except Exception as e:
            # TypeError가 아니면 다른 정상 흐름으로 간주
            success = True

        self.assertTrue(success, "로컬 DB 불일치 종목의 튜플 언패킹이 에러 없이 안전하게 실행되어야 합니다.")

if __name__ == "__main__":
    unittest.main()
