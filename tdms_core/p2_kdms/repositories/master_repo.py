"""p2_kdms.repositories.master_repo

테스트용 최소 구현 MasterRepo 클래스.
"""

from typing import List, Dict

class MasterRepo:
    """마스터 종목 정보를 제공하는 최소 구현 클래스.
    테스트에서는 더미 데이터를 반환한다.
    """

    def __init__(self) -> None:
        # 테스트용 더미 종목 리스트
        self._stocks: List[Dict[str, str]] = [
            {"stk_cd": "005930", "stk_nm": "삼성전자"},
            {"stk_cd": "000660", "stk_nm": "SK하이닉스"},
        ]

    def get_all_stocks(self) -> List[Dict[str, str]]:
        """전체 종목 리스트 반환"""
        return self._stocks
