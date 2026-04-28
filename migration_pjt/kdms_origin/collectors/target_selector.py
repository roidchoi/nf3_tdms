# collectors/target_selector.py

import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from collectors.db_manager import DatabaseManager
from collectors.utils import setup_logger

logger = setup_logger(__name__)

def get_target_stocks(db: DatabaseManager, year: int, quarter: int,
                      market_type: str, top_n: int = 200) -> list[dict]:
    """
    지정된 연도/분기의 **직전 분기** 평균 거래대금 상위 N개 종목의 상세 정보를 반환합니다.
    (선정 기준: API에서 제공하는 'amt' 필드)

    :param db: DatabaseManager 인턴스
    :param year: 대상 연도 (예: 2025)
    :param quarter: 대상 분기 (1, 2, 3, 4)
    :param market_type: 'KOSPI' 또는 'KOSDAQ'
    :param top_n: 선정할 상위 종목의 개수
    :return: {'symbol', 'avg_trade_value', 'rank'} 키를 가진 딕셔너리의 리스트
    """
    if not 1 <= quarter <= 4:
        raise ValueError("분기는 1, 2, 3, 4 중 하나여야 합니다.")

    # 직전 분기 날짜 계산
    target_date = date(year, (quarter - 1) * 3 + 1, 1)
    prev_quarter_end_date = target_date - relativedelta(days=1)
    prev_quarter_start_date = prev_quarter_end_date - relativedelta(months=3) + relativedelta(days=1)
    
    log_msg = f"{prev_quarter_start_date.year}년 { (prev_quarter_start_date.month - 1) // 3 + 1 }분기({prev_quarter_start_date}~{prev_quarter_end_date}) 데이터 기준"
    logger.info(f"{year}년 {quarter}분기 {market_type} 대상 선정을 시작합니다.")
    logger.info(f"({log_msg})")

    try:
        ohlcv_data = db.get_ohlcv_data(
            table_name='daily_ohlcv',
            start_date=prev_quarter_start_date,
            end_date=prev_quarter_end_date,
            market_type=market_type
        )
        if not ohlcv_data:
            logger.warning(f"{market_type} 시장의 직전 분기 데이터가 없어 대상 선정을 건너뜁니다.")
            return []

        df = pd.DataFrame(ohlcv_data)
        
        # ✨ [수정] 일평균 거래대금 계산 (amt 필드 직접 사용)
        avg_trade_value = df.groupby('stk_cd')['amt'].mean().round(0).astype('int64')
        
        # 순위 매기기
        ranked_stocks = avg_trade_value.sort_values(ascending=False).reset_index()
        ranked_stocks.rename(columns={'amt': 'avg_trade_value'}, inplace=True) # 컬럼명 변경
        ranked_stocks['rank'] = ranked_stocks.index + 1
        
        # 최종 결과 생성 (상위 top_n개)
        top_stocks = ranked_stocks.head(top_n).copy()
        
        result = [
            {
                'quarter': f"{year}Q{quarter}",
                'market': market_type,
                'symbol': row['stk_cd'],
                'avg_trade_value': row['avg_trade_value'], # ✨ [수정] amt 기반 값 사용
                'rank': row['rank']
            }
            for index, row in top_stocks.iterrows()
        ]

        logger.info(f"{market_type} 시장 대상 {len(result)}개 선정 완료.")
        return result

    except Exception as e:
        logger.error(f"대상 종목 선정 중 에러 발생: {e}", exc_info=True)
        return []
    
if __name__ == '__main__':
    db_manager = DatabaseManager()
    print("--- 분봉 대상 선정 모듈 테스트 (2024년 1분기 KOSPI) ---")
    targets = get_target_stocks(db=db_manager, year=2024, quarter=1, market_type='KOSPI', top_n=5)
    print(f"선정된 대상 (최대 5개): {targets}")
    print("--- 테스트 완료 ---")