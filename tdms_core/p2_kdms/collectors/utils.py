# collectors/utils.py

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any

# 중앙화된 데이터 변환 규칙 정의
DATA_MAPPER = {
    'kiwoom': {
        'stock_info': { # ka10099
            'code': 'stk_cd',
            'name': 'stk_nm',
            'regDay': 'list_dt'
        },
        'daily_ohlcv': { # ka10081
            'stk_cd': 'stk_cd',
            'dt': 'dt',
            'cur_prc': 'cls_prc',
            'open_pric': 'open_prc',
            'high_pric': 'high_prc',
            'low_pric': 'low_prc',
            'trde_qty': 'vol',
            'trde_prica': 'amt',
            'trde_tern_rt': 'turn_rt'
        },
        'minute_ohlcv': { # ka10080
            'stk_cd': 'stk_cd',
            'cntr_tm': 'dt_tm',
            'cur_prc': 'cls_prc',
            'open_pric': 'open_prc',
            'high_pric': 'high_prc',
            'low_pric': 'low_prc',
            'trde_qty': 'vol'
        }
    },
    'kis': {
        'daily_ohlcv': {
            'stk_cd':           'stk_cd',
            'stck_bsop_date':   'dt',
            'stck_oprc':        'open_prc',
            'stck_hgpr':        'high_prc',
            'stck_lwpr':        'low_prc',
            'stck_clpr':        'cls_prc',
            'acml_vol':         'vol',
            'acml_tr_pbmn':     'amt',
        },
        'balance_sheet': {
            'stac_yymm': 'stac_yymm',
            'cras': 'cras',
            'fxas': 'fxas',
            'total_aset': 'total_aset',
            'flow_lblt': 'flow_lblt',
            'fix_lblt': 'fix_lblt',
            'total_lblt': 'total_lblt',
            'cpfn': 'cpfn',
            'total_cptl': 'total_cptl'
        },
        'income_statement': {
            'stac_yymm': 'stac_yymm',
            'sale_account': 'sale_account',
            'sale_cost': 'sale_cost',
            'sale_totl_prfi': 'sale_totl_prfi',
            'bsop_prti': 'bsop_prti',
            'op_prfi': 'op_prfi',
            'thtr_ntin': 'thtr_ntin'
        },
        'financial_ratio': {
            'stac_yymm': 'stac_yymm',
            'grs': 'grs',
            'bsop_prfi_inrt': 'bsop_prfi_inrt',
            'ntin_inrt': 'ntin_inrt',
            'roe_val': 'roe_val',
            'eps': 'eps',
            'sps': 'sps',
            'bps': 'bps',
            'rsrv_rate': 'rsrv_rate',
            'lblt_rate': 'lblt_rate'
        },
        'profit_ratio': {
            'stac_yymm': 'stac_yymm',
            'cptl_ntin_rate': 'cptl_ntin_rate',
            'self_cptl_ntin_inrt': 'self_cptl_ntin_inrt',
            'sale_ntin_rate': 'sale_ntin_rate',
            'sale_totl_rate': 'sale_totl_rate'
        },
        'other_major_ratios': {
            'stac_yymm': 'stac_yymm',
            'eva': 'eva',
            'ebitda': 'ebitda',
            'ev_ebitda': 'ev_ebitda'
        },
        'stability_ratio': {
            'stac_yymm': 'stac_yymm',
            'lblt_rate': 'lblt_rate',
            'bram_depn': 'bram_depn',
            'crnt_rate': 'crnt_rate',
            'quck_rate': 'quck_rate'
        },
        'growth_ratio': {
            'stac_yymm': 'stac_yymm',
            'grs': 'grs',
            'bsop_prfi_inrt': 'bsop_prfi_inrt',
            'equt_inrt': 'equt_inrt',
            'totl_aset_inrt': 'totl_aset_inrt'
        }
    }
}

def transform_data(api_data: list[dict], source: str, data_type: str) -> list[dict]:
    """
    중앙화된 MAPPER를 사용하여 API 응답을 DB 스키마에 맞게 변환하고,
    데이터의 실제 형태에 맞게 타입을 지능적으로 변환합니다.
    """
    try:
        mapper = DATA_MAPPER[source][data_type]
        required_keys = set(mapper.keys())
        kst = ZoneInfo("Asia/Seoul")
        NON_NUMERIC_COLS = {'stk_cd', 'dt', 'dt_tm', 'list_dt', 'stk_nm', 'stac_yymm'}
    except KeyError:
        raise ValueError(f"'{source}' 또는 '{data_type}'에 대한 매핑 정보가 DATA_MAPPER에 없습니다.")

    transformed_list = []
    for item in api_data:
        # API 결과의 일부 키가 빠져있어도, 데이터 매핑 유연성을 위해 defaults를 설정하고 계속 진행합니다
        transformed_item = {}
        for api_key, db_key in mapper.items():
            value = item.get(api_key)

            # --- 1. 날짜/시간 타입 변환 ---
            if data_type == 'daily_ohlcv' and db_key == 'dt':
                try: 
                    if value:
                        value = datetime.strptime(str(value), '%Y%m%d').date()
                except (ValueError, TypeError): 
                    raise ValueError(f"일봉 날짜({value}) 형식 오류")
            elif data_type == 'minute_ohlcv' and api_key == 'cntr_tm':
                try:
                    if value:
                        naive_dt = datetime.strptime(str(value), '%Y%m%d%H%M%S')
                        value = naive_dt.replace(tzinfo=kst)
                except (ValueError, TypeError):
                    raise ValueError(f"분봉 시간({value}) 형식 오류")
            elif data_type == 'stock_info' and api_key == 'regDay':
                try:
                    if value:
                        value = datetime.strptime(str(value), '%Y%m%d').date()
                except (ValueError, TypeError):
                    raise ValueError(f"상장일({value}) 형식 오류")
            
            # --- 2. 지능형 숫자 타입 변환 ---
            if db_key not in NON_NUMERIC_COLS and isinstance(value, str):
                if value.startswith(('+', '-')):
                    value = value[1:]
                
                if value:
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
            
            transformed_item[db_key] = value
        
        transformed_list.append(transformed_item)
        
    return transformed_list
