# collectors/factor_calculator.py

import pandas as pd
import numpy as np
import json
from typing import List, Dict, Any

def calculate_factors(df: pd.DataFrame, stk_cd: str, price_source: str) -> List[Dict[str, Any]]:
    """
    수정/원본 주가 DataFrame을 기반으로 수정계수(Price Factor) 이벤트를 역산합니다.

    :param df: 'dt', 'adj_close', 'raw_close' 컬럼을 포함하고, 날짜순으로 정렬된 DataFrame
    :param stk_cd: 종목 코드
    :param price_source: 시세 출처 (예: 'KIWOOM')
    :return: price_adjustment_factors 테이블 스키마에 맞는 딕셔너리 리스트
    """
    
    # 0으로 나누기 오류 방지 (원본 종가가 0인 경우 ratio를 0으로 설정)
    df['ratio'] = np.where(df['raw_close'] == 0, 0, df['adj_close'] / df['raw_close'])
    df['prev_ratio'] = df['ratio'].shift(1)

    # 0으로 나누기 오류 방지 (이전 ratio가 0인 경우 price_ratio를 1로 설정)
    df['price_ratio'] = np.where(df['prev_ratio'] == 0, 1.0, df['ratio'] / df['prev_ratio'])
    df['price_ratio'] = df['price_ratio'].fillna(1.0) # 첫 행의 NaN을 1.0으로 채움

    # 임계값: 1% (0.01) 이상 변동 시 이벤트로 간주
    threshold = 0.01
    
    # 실제 이벤트가 발생한 행(row)들을 필터링
    event_df = df[abs(df['price_ratio'] - 1.0) > threshold].copy()

    factor_list = []
    
    for index, row in event_df.iterrows():
        if index == 0: # 첫 번째 행은 prev_ratio가 NaN이므로 건너뜀
            continue
            
        price_ratio = row['price_ratio']
        volume_ratio = 1 / price_ratio
        
        # 추적성을 위한 계산 근거 데이터 (JSONB)
        prev_row = df.loc[index - 1]
        details = {
            'adj_close': row['adj_close'],
            'raw_close': row['raw_close'],
            'prev_adj_close': prev_row['adj_close'],
            'prev_raw_close': prev_row['raw_close']
        }

        # DB 스키마에 맞게 딕셔너리 생성
        factor_event = {
            'stk_cd': stk_cd,
            'event_dt': row['dt'], 
            'price_ratio': price_ratio,
            'volume_ratio': volume_ratio,
            'price_source': price_source,
            'details': json.dumps(details, default=str)
            # effective_dt는 DB의 DEFAULT NOW()에 의해 자동 설정됨
        }
        factor_list.append(factor_event)

    return factor_list

if __name__ == '__main__':
    # 간단한 유닛 테스트
    print("Factor Calculator 모듈 유닛 테스트 시작...")
    
    # 삼성전자 액면분할(2018-05-04) 데이터 모의 생성
    test_data = {
        'dt': pd.to_datetime(['2018-05-02', '2018-05-03', '2018-05-04']),
        'adj_close': [53000, 53000, 51900],
        'raw_close': [2650000, 2650000, 51900] # 50:1 액면분할
    }
    test_df = pd.DataFrame(test_data)
    
    factors = calculate_factors(test_df, '005930', 'KIWOOM')
    
    print(f"탐지된 이벤트: {len(factors)}개")
    if factors:
        event = factors[0]
        print(f"  - 날짜: {event['event_dt']}")
        print(f"  - Price Ratio: {event['price_ratio']:.6f}")
        print(f"  - Volume Ratio: {event['volume_ratio']:.2f}")
        print(f"  - 근거: {event['details']}")
        
        assert event['price_ratio'] == 50.0
        print("✅ 유닛 테스트 통과")