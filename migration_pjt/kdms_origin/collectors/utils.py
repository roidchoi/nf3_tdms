# collectors/utils.py

import os
import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from datetime import datetime
from zoneinfo import ZoneInfo # ✨ 시간대 처리를 위한 zoneinfo 임포트
from typing import List, Dict, Any
from psycopg2.extras import execute_values # DB UPSERT에 사용

# (주의) 아래 모듈은 이 함수를 호출하는 상위 스크립트(예: main)에서
#      이미 import 되어 객체로 전달되어야 합니다.
# from kis_rest import KisREST, KisAPIError
# from db_manager import DatabaseManager

def setup_logger(name: str, log_dir: str = 'logs', level: int = logging.INFO):
    """
    콘솔과 파일에 모두 로그를 남기는 표준 로거를 설정합니다.

    :param name: 로거의 이름 (일반적으로 __name__을 사용)
    :param log_dir: 로그 파일이 저장될 디렉토리
    :param level: 로깅 레벨 (예: logging.INFO, logging.DEBUG)
    :return: 설정이 완료된 logger 객체
    """
    logger = logging.getLogger(name)
    
    # 로거에 핸들러가 이미 설정되어 있는지 확인 (중복 방지)
    if logger.hasHandlers():
        return logger
        
    logger.setLevel(level)

    # 로그 디렉토리 생성
    os.makedirs(log_dir, exist_ok=True)

    # 로그 포맷 설정
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. 콘솔 핸들러 (rich 사용으로 가독성 향상)
    console_handler = RichHandler(rich_tracebacks=True, show_path=False)
    console_handler.setFormatter(logging.Formatter('%(message)s')) # 콘솔은 더 단순한 포맷 사용
    logger.addHandler(console_handler)

    # 2. 파일 핸들러 (RotatingFileHandler로 로그 파일 관리)
    log_file = os.path.join(log_dir, f'{name}.log')
    # 5MB 크기의 로그 파일을 최대 5개까지 유지
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

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
        # --- [신규 Phase KIS-1] KIS 일봉 시세 API 매핑 (FHKST03010100 output2 필드 기준) ---
        # adj_price='0' = 수정주가 / adj_price='1' = 원본주가 (키움과 반대)
        'daily_ohlcv': {
            'stk_cd':           'stk_cd',        # 종목코드 (호출 전 수동 추가)
            'stck_bsop_date':   'dt',             # 주식 영업 일자 (YYYYMMDD)
            'stck_oprc':        'open_prc',       # 시가
            'stck_hgpr':        'high_prc',       # 고가
            'stck_lwpr':        'low_prc',        # 저가
            'stck_clpr':        'cls_prc',        # 종가
            'acml_vol':         'vol',            # 누적 거래량
            'acml_tr_pbmn':     'amt',            # 누적 거래대금
        },
        # --- [Phase 4-B] KIS 재무 API 매핑 추가 ---
        # 1. 대차대조표
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
            # 'cfp_surp', 'prfi_surp'는 "출력 안 됨"으로 제외
        },
        # 2. 손익계산서
        'income_statement': {
            'stac_yymm': 'stac_yymm',
            'sale_account': 'sale_account',
            'sale_cost': 'sale_cost',
            'sale_totl_prfi': 'sale_totl_prfi',
            'bsop_prti': 'bsop_prti',
            'op_prfi': 'op_prfi',
            'thtr_ntin': 'thtr_ntin'
            # 'depr_cost', 'sell_mang' 등 "출력 안 됨"으로 제외
        },
        # 3. 재무비율
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
        # 4. 수익성비율
        'profit_ratio': {
            'stac_yymm': 'stac_yymm',
            'cptl_ntin_rate': 'cptl_ntin_rate',
            'self_cptl_ntin_inrt': 'self_cptl_ntin_inrt',
            'sale_ntin_rate': 'sale_ntin_rate',
            'sale_totl_rate': 'sale_totl_rate'
        },
        # 5. 기타주요비율
        'other_major_ratios': {
            'stac_yymm': 'stac_yymm',
            'eva': 'eva',
            'ebitda': 'ebitda',
            'ev_ebitda': 'ev_ebitda'
            # 'payout_rate'는 "비정상"으로 명시되어 제외
        },
        # 6. 안정성비율
        'stability_ratio': {
            'stac_yymm': 'stac_yymm',
            'lblt_rate': 'lblt_rate',
            'bram_depn': 'bram_depn',
            'crnt_rate': 'crnt_rate',
            'quck_rate': 'quck_rate'
        },
        # 7. 성장성비율
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
    [최종] 중앙화된 MAPPER를 사용하여 API 응답을 DB 스키마에 맞게 변환하고,
    데이터의 실제 형태에 맞게 타입을 지능적으로 변환합니다.
    """
    try:
        mapper = DATA_MAPPER[source][data_type]
        required_keys = set(mapper.keys())
        kst = ZoneInfo("Asia/Seoul")
        # ✨ [핵심 수정] 숫자 변환에서 제외할 DB 컬럼 목록
        NON_NUMERIC_COLS = {'stk_cd', 'dt', 'dt_tm', 'list_dt', 'stk_nm', 'stac_yymm'}
    except KeyError:
        raise ValueError(f"'{source}' 또는 '{data_type}'에 대한 매핑 정보가 DATA_MAPPER에 없습니다.")

    transformed_list = []
    for item in api_data:
        if not required_keys.issubset(item.keys()):
            missing_keys = required_keys - set(item.keys())
            raise KeyError(f"API 응답에 필수 키가 누락되었습니다: {missing_keys}. 응답: {item}")

        transformed_item = {}
        for api_key, db_key in mapper.items():
            value = item.get(api_key)

            # --- 1. 날짜/시간 타입 변환 ---
            # [수정] api_key → db_key 기준으로 변경하여 KIS/키움 모두 지원
            #  키움: api_key='dt'     → db_key='dt'
            #  KIS:  api_key='stck_bsop_date' → db_key='dt'
            if data_type == 'daily_ohlcv' and db_key == 'dt':
                try: value = datetime.strptime(str(value), '%Y%m%d').date()
                except (ValueError, TypeError): raise ValueError(f"일봉 날짜({value}) 형식 오류")
            
            elif data_type == 'minute_ohlcv' and api_key == 'cntr_tm':
                try:
                    naive_dt = datetime.strptime(value, '%Y%m%d%H%M%S')
                    value = naive_dt.replace(tzinfo=kst)
                except (ValueError, TypeError): raise ValueError(f"분봉 시간({value}) 형식 오류")

            elif data_type == 'stock_info' and api_key == 'regDay':
                try:
                    if value: value = datetime.strptime(value, '%Y%m%d').date()
                except (ValueError, TypeError): raise ValueError(f"상장일({value}) 형식 오류")

            # --- 2. 지능형 숫자 타입 변환 ---
            if db_key not in NON_NUMERIC_COLS and isinstance(value, str):
                # +/- 부호 제거
                if value.startswith(('+', '-')):
                    value = value[1:]
                
                # 비어있지 않은 문자열일 때만 변환 시도
                if value:
                    try:
                        # 정수로 변환 시도
                        value = int(value)
                    except ValueError:
                        try:
                            # 실패 시 실수로 변환 시도
                            value = float(value)
                        except ValueError:
                            # 모두 실패하면 원본(문자열) 유지
                            pass
            
            transformed_item[db_key] = value
        
        transformed_list.append(transformed_item)
        
    return transformed_list

logger = logging.getLogger(__name__) # utils 모듈의 로거 가져오기

def update_trading_calendar(kis_api: Any, db_manager: Any) -> bool:
    """
    KIS API를 호출하여 거래일 캘린더 캐시를 갱신합니다.
    API 응답이 단일 날짜가 아닌 '배열' 형태임을 전제로 합니다. (실제 응답 기반)

    :param kis_api: KisREST API 래퍼 인스턴스
    :param db_manager: DatabaseManager 인스턴스 (psycopg2 연결 관리)
    :return: 캐시 갱신 성공 여부
    """
    try:
        today_str = datetime.now().strftime('%Y%m%d')
        logger.info(f"🔄 KIS API 호출: 거래일 캘린더(CTCA0903R) 갱신 시도 (기준일: {today_str})...")
        
        # 1. API 호출
        # kis_rest_wrapper_소스코드.md
        # KIS_R_API_인증_휴장일조회.md
        response_data = kis_api.check_holiday(bass_dt=today_str)

        # 2. 응답 검증 (실제 응답 구조 기반)
        if response_data.get('rt_cd') != '0':
            # KIS_R_API_인증_휴장일조회.md
            raise Exception(f"API 응답 오류: {response_data.get('msg1', 'Unknown error')}")

        output_list: List[Dict[str, Any]] = response_data.get('output')
        
        # (중요) 실제 응답(터미널 출력)에 따라 output이 list인지 확인
        if not isinstance(output_list, list) or not output_list:
            logger.warning("⚠️ KIS API 응답 'output'이 비어있거나 배열(List) 형태가 아닙니다.")
            return False
            
        # 3. 데이터 파싱 및 UPSERT 준비
        calendar_data = []
        for item in output_list:
            # KIS_R_API_인증_휴장일조회.md
            dt_str = item.get('bass_dt')
            opnd_yn = item.get('opnd_yn') 
            
            if not dt_str or not opnd_yn:
                logger.warning(f"누락된 데이터 항목: {item}")
                continue
            
            calendar_data.append((dt_str, opnd_yn))
        
        if not calendar_data:
            logger.info("📅 갱신할 캘린더 데이터가 없습니다.")
            return False

        # 4. DB UPSERT (On Conflict)
        # TRD의 동적 UPSERT 로직과 유사하게
        # psycopg2.extras.execute_values를 활용합니다.
        upsert_query = """
        INSERT INTO trading_calendar (dt, opnd_yn)
        VALUES %s
        ON CONFLICT (dt) DO UPDATE SET
            opnd_yn = EXCLUDED.opnd_yn,
            updated_at = NOW();
        """
        
        conn = None
        try:
            # (가정) db_manager가 TRD에 정의된
            # _get_connection() 메서드를 제공
            conn = db_manager._get_connection() 
            with conn.cursor() as cur:
                execute_values(cur, upsert_query, calendar_data)
            conn.commit()
            logger.info(f"✅ 거래일 캘린더 캐시 {len(calendar_data)}건 UPSERT 완료.")
            return True
        except Exception as e:
            if conn:
                conn.rollback() #
            logger.error(f"❌ 캘린더 DB UPSERT 실패: {e}")
            raise
        finally:
            if conn:
                conn.close() #

    except Exception as e:
        # KisAPIError 포함, 모든 예외 처리
        logger.error(f"❌ KIS 캘린더 갱신 중 예외 발생: {e}")
        return False