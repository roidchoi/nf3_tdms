# collectors/krx_loader.py

"""
KRX 시가총액 데이터 수집기 (FinanceDataReader 활용)
- fdr.StockListing('KRX-MARCAP') 호출
- NaN → None 변환
- DB 포맷 변환
"""

import FinanceDataReader as fdr
import pandas as pd
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

class KRXLoader:
    """
    FinanceDataReader를 활용한 KRX 시가총액 데이터 수집기
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def get_market_cap_data(self, target_date: str) -> List[Dict[str, Any]]:
        """
        당일의 전 종목 시가총액 데이터를 수집하여 DB 포맷으로 변환
        *주의: fdr.StockListing('KRX-MARCAP')은 호출 시점(최근 영업일)의 데이터만 반환합니다.
        
        :param target_date: 날짜 (YYYYMMDD 형식 문자열) - DB 적재 시 dt 값으로 쓰임
        :return: List of Dict (dt, stk_cd, cls_prc, mkt_cap, vol, amt, listed_shares)
        """
        try:
            # FDR API 호출 (당일 전종목 시가총액/거래량 한 번에 로드)
            df = fdr.StockListing('KRX-MARCAP')

            # Empty DataFrame 처리
            if df is None or df.empty:
                self.logger.warning(f"[FDR/KRX] {target_date}: 데이터 없음 (휴장일 또는 서버 불안정)")
                return []

            # [디버깅] DataFrame 정보 출력
            self.logger.info(f"[FDR/KRX] {target_date}: DataFrame 크기 = {len(df)}행")
            self.logger.debug(f"[FDR/KRX] {target_date}: DataFrame 컬럼 = {list(df.columns)}")

            if len(df) > 0:
                first_row = df.iloc[0]
                self.logger.debug(f"[FDR/KRX] {target_date}: 샘플 [{first_row.get('Code')}] = {dict(first_row)}")

            result = []
            dt_obj = datetime.strptime(target_date, '%Y%m%d').date()

            # iterrows 대신 좀 더 안전하게 처리할 수 있지만, 기존 구조 호환성을 위해 유지
            for _, row in df.iterrows():
                # FinanceDataReader 'KRX-MARCAP'의 반환 컬럼: Code, Close, Marcap, Volume, Amount, Stocks 등
                ticker = str(row.get('Code', ''))
                if not ticker:
                    continue
                    
                result.append({
                    'dt': dt_obj,
                    'stk_cd': ticker,
                    'cls_prc': self._to_int(row.get('Close', None)),
                    'mkt_cap': self._to_int(row.get('Marcap', None)),
                    'vol': self._to_int(row.get('Volume', None)),
                    'amt': self._to_int(row.get('Amount', None)),
                    'listed_shares': self._to_int(row.get('Stocks', None))
                })

            # [디버깅] 변환 후 크기 확인
            self.logger.info(
                f"[FDR/KRX] {target_date}: 변환 완료 - "
                f"입력 {len(df)}건 → 출력 {len(result)}건"
            )

            if len(result) > 0:
                self.logger.debug(f"[FDR/KRX] {target_date}: 변환 샘플 = {result[0]}")

            return result

        except Exception as e:
            self.logger.error(f"[FDR/KRX] {target_date}: 데이터 수집 실패 - {e}", exc_info=True)
            return []

    @staticmethod
    def _to_int(value) -> Optional[int]:
        """NaN을 None으로 변환하고 정수형으로 변환"""
        if pd.isna(value):
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
