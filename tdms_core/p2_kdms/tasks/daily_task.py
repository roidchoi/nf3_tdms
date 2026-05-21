"""p2_kdms.tasks.daily_task

이 모듈은 테스트에서 사용되는 최소 구현의 DailyTask 클래스를 제공합니다.
"""

from datetime import date
from typing import List, Dict

# 실제 구현에서는 MasterRepo와 OhlcvRepo를 사용하지만, 테스트를 위해
# 인터페이스만 정의하고 간단한 동작을 구현합니다.

class DailyTask:
    """일일 데이터 수집 작업을 실행하는 클래스 (테스트용 최소 구현)."""

    def __init__(self, master_repo, ohlcv_repo) -> None:
        self.master_repo = master_repo
        self.ohlcv_repo = ohlcv_repo

    def run(self, target_date: date) -> None:
        """주어진 날짜에 대한 종목 리스트를 가져와 OHLCV 레코드를 upsert한다.

        테스트에서는 실제 DB 접근이 없으므로 MasterRepo에서 더미 종목 리스트를
        받아 OhlcvRepo에 최소 구조의 레코드를 전달합니다.
        """
        # MasterRepo에서 모든 종목 정보를 반환한다고 가정
        stocks: List[Dict[str, str]] = self.master_repo.get_all_stocks()
        records = [
            {
                "stk_cd": stock["stk_cd"],
                "dt": target_date,
                "open": 0,
                "high": 0,
                "low": 0,
                "close": 0,
                "volume": 0,
            }
            for stock in stocks
        ]
        # OhlcvRepo에 upsert 수행 (테스트에서는 mock 객체가 사용됨)
        self.ohlcv_repo.upsert_daily_ohlcv(records)
