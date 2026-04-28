# financial_update.py
"""
재무정보 수집 모듈 (KIS API)
- 재무제표 (대차대조표, 손익계산서)
- 재무비율 (재무, 수익성, 안정성, 성장성, 기타)
- PIT (Point-in-Time) 버전 관리

Usage:
    # 전체 종목 재무정보 수집
    python financial_update.py
    
    # 특정 종목만 수집
    python financial_update.py --stocks 005930 035720
"""

import argparse
import sys
from decimal import Decimal
from typing import List
from tqdm import tqdm

from collectors.kis_rest import KisREST, KisAPIError
from collectors.db_manager import DatabaseManager
from collectors import utils


def update_financials(kis_api: KisREST, db: DatabaseManager, logger,
                      target_stocks: List[str] = None):
    """
    KIS 재무정보 수집 및 PIT 버전 관리
    
    :param kis_api: KisREST API 인스턴스
    :param db: DatabaseManager 인스턴스
    :param logger: 로거 객체
    :param target_stocks: 특정 종목 리스트 (None이면 전체 상장 종목)
    """
    logger.info("=" * 60)
    logger.info("[재무정보 수집] KIS API 기반 PIT 버전 관리")
    logger.info("=" * 60)
    
    # 1. 대상 종목 결정
    if target_stocks:
        logger.info(f"--stocks 인자로 {len(target_stocks)}개 종목 지정")
    else:
        logger.info("전체 상장 종목 대상으로 재무정보 수집 시작")
        target_stocks = db.get_all_stock_codes(active_only=True)
        logger.info(f"총 {len(target_stocks)}개 종목 조회 완료")
    
    statements_to_insert = []
    ratios_to_insert = []
    
    # 2. 종목 순회
    for stk_cd in tqdm(target_stocks, desc="재무정보 수집 및 비교"):
        try:
            # 3. KIS API 일괄 호출 (7개 API)
            all_fin_data = kis_api.fetch_all_financial_data(stk_cd, div_cls_code='1')
            
            # 4. API별로 변환 및 'stac_yymm'를 키로 하는 맵 생성
            api_maps = {}
            for api_name, data_list in all_fin_data.items():
                if not data_list or not isinstance(data_list, list):
                    continue
                
                # utils.transform_data로 API 응답 변환
                transformed_list = utils.transform_data(data_list, 'kis', api_name)
                
                # 'stac_yymm'를 키로 하는 딕셔너리 생성
                api_maps[api_name] = {item['stac_yymm']: item for item in transformed_list}
            
            # 5. 모든 'stac_yymm' 키 수집
            all_yymm = set()
            for m in api_maps.values():
                all_yymm.update(m.keys())
            
            if not all_yymm:
                logger.warning(f"[{stk_cd}] API 응답이 비어있습니다.")
                continue
            
            # 6. 'stac_yymm' 기준으로 모든 재무 데이터 병합
            for yymm in all_yymm:
                # --- API 신규 버전 (병합된 레코드) ---
                api_statement = {
                    'stk_cd': stk_cd, 
                    'stac_yymm': yymm, 
                    'div_cls_code': '1'
                }
                api_ratio = {
                    'stk_cd': stk_cd, 
                    'stac_yymm': yymm, 
                    'div_cls_code': '1'
                }
                
                # 7개 API 맵에서 데이터 병합
                api_statement.update(api_maps.get('balance_sheet', {}).get(yymm, {}))
                api_statement.update(api_maps.get('income_statement', {}).get(yymm, {}))
                api_ratio.update(api_maps.get('financial_ratio', {}).get(yymm, {}))
                api_ratio.update(api_maps.get('profit_ratio', {}).get(yymm, {}))
                api_ratio.update(api_maps.get('other_major_ratios', {}).get(yymm, {}))
                api_ratio.update(api_maps.get('stability_ratio', {}).get(yymm, {}))
                api_ratio.update(api_maps.get('growth_ratio', {}).get(yymm, {}))
                
                # --- DB 최신 버전 (비교 대상) ---
                db_statement = db.get_latest_financial_statement(stk_cd, yymm, '1')
                db_ratio = db.get_latest_financial_ratio(stk_cd, yymm, '1')
                
                # 7. 변경 감지 (PIT)
                statement_cols = [
                    'cras', 'fxas', 'total_aset', 'flow_lblt', 'fix_lblt', 'total_lblt',
                    'cpfn', 'total_cptl', 'sale_account', 'sale_cost', 'sale_totl_prfi',
                    'bsop_prti', 'op_prfi', 'thtr_ntin'
                ]
                ratio_cols = [
                    'grs', 'bsop_prfi_inrt', 'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps',
                    'rsrv_rate', 'lblt_rate', 'cptl_ntin_rate', 'self_cptl_ntin_inrt',
                    'sale_ntin_rate', 'sale_totl_rate', 'eva', 'ebitda', 'ev_ebitda',
                    'bram_depn', 'crnt_rate', 'quck_rate', 'equt_inrt', 'totl_aset_inrt'
                ]
                
                # 재무제표 변경 감지
                if _compare_financial_data(api_statement, db_statement, statement_cols, logger):
                    logger.debug(f"[{stk_cd}] {yymm} 재무제표 변경 감지 → INSERT 대상 추가")
                    statements_to_insert.append(api_statement)
                
                # 재무비율 변경 감지
                if _compare_financial_data(api_ratio, db_ratio, ratio_cols, logger):
                    logger.debug(f"[{stk_cd}] {yymm} 재무비율 변경 감지 → INSERT 대상 추가")
                    ratios_to_insert.append(api_ratio)
        
        except KisAPIError as e:
            logger.error(f"[{stk_cd}] KIS API 오류: {e} (Error Code: {e.error_code})")
            continue
        except Exception as e:
            logger.error(f"[{stk_cd}] 재무정보 처리 중 예외 발생: {e}", exc_info=True)
            continue
    
    # 8. 일괄 저장 (Loop 종료 후)
    logger.info("=" * 60)
    logger.info("전체 종목 비교 완료. DB 일괄 INSERT 시작...")
    logger.info("=" * 60)
    
    if statements_to_insert:
        logger.info(f"신규/변경된 재무제표: {len(statements_to_insert)}건")
        db.insert_financial_statements(statements_to_insert)
        logger.info("✅ 재무제표 INSERT 완료")
    else:
        logger.info("신규/변경된 재무제표 데이터가 없습니다.")
    
    if ratios_to_insert:
        logger.info(f"신규/변경된 재무비율: {len(ratios_to_insert)}건")
        db.insert_financial_ratios(ratios_to_insert)
        logger.info("✅ 재무비율 INSERT 완료")
    else:
        logger.info("신규/변경된 재무비율 데이터가 없습니다.")
    
    logger.info("=" * 60)
    logger.info("✅ [재무정보 수집] 성공적으로 완료")
    logger.info("=" * 60)


def _compare_financial_data(api_data: dict, db_data: dict, 
                            columns: List[str], logger) -> bool:
    """
    API 신규 버전과 DB 최신 버전의 필드를 비교
    
    :param api_data: API에서 받은 신규 데이터
    :param db_data: DB에 저장된 최신 버전 데이터
    :param columns: 비교할 컬럼 리스트
    :param logger: 로거 객체
    :return: 변경 감지 여부 (True: 변경됨/신규, False: 변경 없음)
    """
    if db_data is None:
        return True  # DB에 없음 = 신규 데이터
    
    for col in columns:
        api_value = api_data.get(col)
        db_value = db_data.get(col)
        
        # 데이터 정합성: 0, 0.0, None은 모두 '없음'으로 동일 취급
        if api_value in (None, 0, 0.0):
            api_value = None
        if db_value in (None, 0, 0.0):
            db_value = None
        
        # DB의 Decimal 타입을 float로 변환 (숫자 비교 정규화)
        if isinstance(db_value, (int, float, Decimal)):
            db_value = float(db_value)
        if isinstance(api_value, (int, float)):
            api_value = float(api_value)
        
        # 비교 실패 시 로그 출력 (WARNING 레벨)
        if api_value != db_value:
            logger.warning(
                f"[{api_data.get('stk_cd')}/{api_data.get('stac_yymm')}] 변경 감지: "
                f"Column={col}, API_Value={api_value} (type={type(api_value).__name__}), "
                f"DB_Value={db_value} (type={type(db_value).__name__})"
            )
            return True  # 변경 감지
    
    return False  # 변경 없음


def main():
    parser = argparse.ArgumentParser(
        description="KDMS 재무정보 수집 (KIS API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 전체 상장 종목 재무정보 수집
  python financial_update.py
  
  # 특정 종목만 수집
  python financial_update.py --stocks 005930 035720
  
  # KOSPI 200 종목만 수집
  python financial_update.py --stocks 005930 000660 035420 051910 035720
  
수집 내용:
  - 대차대조표 (Balance Sheet)
  - 손익계산서 (Income Statement)
  - 재무비율 7종 (재무, 수익성, 안정성, 성장성, 기타)
  - PIT (Point-in-Time) 버전 관리
  
권장 실행 주기:
  - 분기 결산 발표 시즌: 주 1회
  - 평상시: 월 1회
        """
    )
    
    parser.add_argument('--stocks', type=str, nargs='+',
                       help='특정 종목 코드 리스트 (예: 005930 035720)')
    
    args = parser.parse_args()
    
    # 로거 설정
    logger = utils.setup_logger('financial_update')
    
    logger.info("🚀 KIS API 초기화...")
    try:
        kis_api = KisREST(mock=False, log_level=1)
    except Exception as e:
        logger.critical(f"KIS API 초기화 실패: {e}")
        logger.critical("재무정보 수집이 불가능합니다. KIS API 자격증명을 확인하세요.")
        sys.exit(1)
    
    logger.info("🚀 DatabaseManager 초기화...")
    db = DatabaseManager()
    
    try:
        update_financials(kis_api, db, logger, target_stocks=args.stocks)
    except Exception as e:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()