# collectors/factor_calculator.py

import pandas as pd
import numpy as np
import json
from typing import List, Dict, Any

def calculate_factors(df: pd.DataFrame, stk_cd: str, price_source: str) -> List[Dict[str, Any]]:
    """
    수정/원본 주가 DataFrame을 기반으로 곱셈 형식의 수정계수(Price Factor) 이벤트를 역산합니다.
    (USDMS 호환: adjusted_price = raw_price * price_ratio)

    :param df: 'dt', 'adj_close', 'raw_close' 컬럼을 포함하고 날짜순으로 정렬된 DataFrame
    :param stk_cd: 종목 코드
    :param price_source: 시세 출처 (예: 'KIS')
    :return: price_adjustment_factors 테이블 포맷에 맞는 딕셔너리 리스트
    """
    if df.empty or len(df) < 2:
        return []

    # 날짜 순 정렬 보장
    df = df.sort_values('dt').reset_index(drop=True)

    # [보완 1] 음수 시세 정제: raw_close나 adj_close가 0 이하인 경우 유효가격(abs)으로 보정
    df['raw_close_clean'] = df['raw_close'].apply(lambda x: abs(x) if x != 0 else 0.0)
    df['adj_close_clean'] = df['adj_close'].apply(lambda x: abs(x) if x != 0 else 0.0)

    # 0으로 나누기 및 음수 비율 방지
    df['ratio'] = np.where(
        (df['raw_close_clean'] <= 0) | (df['adj_close_clean'] <= 0),
        0.0,
        df['adj_close_clean'] / df['raw_close_clean']
    )
    df['prev_ratio'] = df['ratio'].shift(1)

    # 수정비율 곱셈 승수 계산: price_ratio = prev_ratio / ratio (50:1 액면분할 시 0.02/1.0 = 0.02)
    # 0으로 나누기 방지 및 음수 방어: prev_ratio 또는 ratio가 0 이하이면 1.0으로 매핑
    df['price_ratio'] = np.where(
        (df['prev_ratio'] <= 0.0) | (df['ratio'] <= 0.0),
        1.0,
        df['prev_ratio'] / df['ratio']
    )
    df['price_ratio'] = df['price_ratio'].fillna(1.0)

    # 임계값: 0.3% (0.003) 초과 변동 시 수정계수 변동 이벤트로 간주 (3자 대조 기준 0.5% 미만 소액 팩터 누락 방어)
    threshold = 0.003
    
    # 첫 행은 prev_ratio가 없으므로 제외하고, 임계값을 초과하는 행 필터링
    event_mask = (abs(df['price_ratio'] - 1.0) > threshold) & (df.index > 0)
    event_df = df[event_mask].copy()

    factor_list = []
    
    for index, row in event_df.iterrows():
        price_ratio = row['price_ratio']
        
        # [보완 2] 팩터 불변성 검증: price_ratio가 0 이하인 비정상 수치 엄격 배제
        if price_ratio <= 0.0:
            continue
            
        # volume_ratio는 price_ratio의 역수
        volume_ratio = 1.0 / price_ratio
        if volume_ratio <= 0.0:
            continue
        
        # 이전 행 데이터 획득
        prev_row = df.loc[index - 1]
        
        # 세부 정보 JSON 구성
        details = {
            'adj_close': float(row['adj_close']),
            'raw_close': float(row['raw_close']),
            'prev_adj_close': float(prev_row['adj_close']),
            'prev_raw_close': float(prev_row['raw_close'])
        }

        # dt 컬럼 처리 (Timestamp인 경우 date로 변환)
        event_dt = row['dt']
        if hasattr(event_dt, 'date'):
            event_dt = event_dt.date()

        factor_event = {
            'stk_cd': stk_cd,
            'event_dt': event_dt,
            'price_ratio': float(price_ratio),
            'volume_ratio': float(volume_ratio),
            'price_source': price_source,
            'details': json.dumps(details)
        }
        factor_list.append(factor_event)

    return factor_list
