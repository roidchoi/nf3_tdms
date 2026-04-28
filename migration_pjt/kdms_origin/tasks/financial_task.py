#
# tasks/financial_task.py
#
"""
재무정보 수집 태스크 (PRD Phase 6 아키텍처)
- financial_update.py의 실제 로직을 FastAPI/APScheduler 백그라운드 태스크로 이식
- KIS API 기반 PIT 버전 관리
- PRD 4.1.2에 따라 job_statuses 딕셔너리를 실시간으로 업데이트
- (수정) tqdm 스타일의 지능형 로그 추가
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any
from datetime import datetime
import time # (신규) tqdm 스타일 로그를 위한 time 임포트

# --- [이식] financial_update 소스코드.md의 임포트 ---
from collectors.kis_rest import KisREST, KisAPIError
from collectors.db_manager import DatabaseManager
from collectors import utils
# (test_utils는 daily_task와 공유)
from test_utils import TestEnvironment
# ----------------------------------------------

# 로거 설정 (모듈 레벨)
logger = logging.getLogger(__name__)


def run_financial_update(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    KIS 재무정보 수집 및 PIT 버전 관리 (PRD 4.1.2 기반)
    
    :param job_statuses: 전역 상태 딕셔너리 (FastAPI에서 전달)
    :param test_mode: 테스트 모드 여부
    """
    job_id = "financial_update"
    start_time = datetime.now() #

    # --- [PRD 4.1.2] 상태 초기화 ---
    job_statuses[job_id] = {
        "is_running": True, #
        "phase": "1/3", #
        "phase_name": "작업 시작 및 초기화", #
        "progress": 0, #
        "start_time": start_time.isoformat(), #
        "last_log": f"작업 시작 (Test Mode: {test_mode})", #
        "stocks_processed": 0, #
        "total_stocks": 0 #
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})") #

    try:
        # --- [이식] financial_update.py main()의 객체 초기화 ---
        logger.info(f"[{job_id}] KIS API 초기화...") #
        kis_api = KisREST(mock=test_mode, log_level=1) #
        
        logger.info(f"[{job_id}] DatabaseManager 초기화...") #
        db = DatabaseManager() #
        
        test_env = TestEnvironment(db, logger) if test_mode else None #
        # ----------------------------------------------

        # 1. 대상 종목 결정
        job_statuses[job_id].update({
            "phase": "1/3", #
            "phase_name": "대상 종목 조회", #
            "progress": 10, #
            "last_log": "DB에서 수집 대상 종목 조회 중..." #
        })
        
        target_stocks: List[str] = [] #
        if test_mode:
            logger.info(f"[{job_id}] 테스트 모드: 소수 종목 필터링") #
            target_stocks = test_env.get_test_stock_codes() #
            logger.info(f"[{job_id}] 테스트 대상: {len(target_stocks)}개 종목") #
        else:
            logger.info(f"[{job_id}] 전체 상장 종목 대상으로 재무정보 수집 시작") #
            target_stocks = db.get_all_stock_codes(active_only=True) #
            logger.info(f"[{job_id}] 총 {len(target_stocks)}개 종목 조회 완료") #
        
        if not target_stocks:
            logger.warning(f"[{job_id}] 수집 대상 종목이 없습니다. 작업 종료.") #
            raise ValueError("수집 대상 종목이 없습니다.") #

        job_statuses[job_id]["total_stocks"] = len(target_stocks) #
        
        statements_to_insert = [] #
        ratios_to_insert = [] #

        # 2. 종목 순회
        job_statuses[job_id].update({
            "phase": "2/3", #
            "phase_name": "재무정보 수집 및 비교 (PIT)", #
            "progress": 20 #
        })
        
        total = len(target_stocks) #
        
        # (신규) tqdm 스타일 로깅 변수 초기화
        loop_start_time = time.time()
        
        for idx, stk_cd in enumerate(target_stocks): #
            
            # --- (수정) tqdm 스타일 상태 업데이트 ---
            # (기존 5건마다 -> 20건마다 로깅)
            if idx % 20 == 0: #
                progress = 20 + (idx / total * 60)  # Phase 2는 20% ~ 80%
                
                elapsed = time.time() - loop_start_time
                if elapsed == 0: elapsed = 1e-6 
                
                items_per_sec = (idx + 1) / elapsed # (idx가 0부터 시작하므로 +1)
                
                if items_per_sec == 0:
                    eta_str = "N/A"
                else:
                    eta_seconds = (total - (idx + 1)) / items_per_sec
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                
                progress_msg = (
                    f"[{job_id}] ({idx+1}/{total}) "
                    f"[{items_per_sec:.1f}it/s, ETA: {eta_str}] "
                    f"... (현재: {stk_cd})"
                )
                
                # (수정) logger.info로 유용한 로그 출력
                logger.info(progress_msg)
                
                job_statuses[job_id].update({
                    "progress": progress,
                    "stocks_processed": idx, #
                    "last_log": progress_msg # (수정) last_log를 tqdm 메시지로 변경
                })
            # ----------------------------------------

            try:
                # 3. KIS API 일괄 호출 (7개 API)
                all_fin_data = kis_api.fetch_all_financial_data(stk_cd, div_cls_code='1')
                
                # 4. API별로 변환 및 'stac_yymm'를 키로 하는 맵 생성
                api_maps = {}
                for api_name, data_list in all_fin_data.items():
                    if not data_list or not isinstance(data_list, list):
                        continue
                    transformed_list = utils.transform_data(data_list, 'kis', api_name)
                    api_maps[api_name] = {item['stac_yymm']: item for item in transformed_list}
                
                # 5. 모든 'stac_yymm' 키 수집
                all_yymm = set()
                for m in api_maps.values():
                    all_yymm.update(m.keys())
                
                if not all_yymm:
                    logger.warning(f"[{stk_cd}] API 응답이 비어있습니다.") #
                    continue
                
                # 6. 'stac_yymm' 기준으로 모든 재무 데이터 병합
                for yymm in all_yymm:
                    api_statement = {'stk_cd': stk_cd, 'stac_yymm': yymm, 'div_cls_code': '1'}
                    api_ratio = {'stk_cd': stk_cd, 'stac_yymm': yymm, 'div_cls_code': '1'}
                    
                    api_statement.update(api_maps.get('balance_sheet', {}).get(yymm, {}))
                    api_statement.update(api_maps.get('income_statement', {}).get(yymm, {}))
                    api_ratio.update(api_maps.get('financial_ratio', {}).get(yymm, {}))
                    api_ratio.update(api_maps.get('profit_ratio', {}).get(yymm, {}))
                    api_ratio.update(api_maps.get('other_major_ratios', {}).get(yymm, {}))
                    api_ratio.update(api_maps.get('stability_ratio', {}).get(yymm, {}))
                    api_ratio.update(api_maps.get('growth_ratio', {}).get(yymm, {}))
                    
                    db_statement = db.get_latest_financial_statement(stk_cd, yymm, '1') #
                    db_ratio = db.get_latest_financial_ratio(stk_cd, yymm, '1') #
                    
                    # 7. 변경 감지 (PIT)
                    statement_cols = [
                        'cras', 'fxas', 'total_aset', 'flow_lblt', 'fix_lblt', 'total_lblt',
                        'cpfn', 'total_cptl', 'sale_account', 'sale_cost', 'sale_totl_prfi',
                        'bsop_prti', 'op_prfi', 'thtr_ntin'
                    ] #
                    ratio_cols = [
                        'grs', 'bsop_prfi_inrt', 'ntin_inrt', 'roe_val', 'eps', 'sps', 'bps',
                        'rsrv_rate', 'lblt_rate', 'cptl_ntin_rate', 'self_cptl_ntin_inrt',
                        'sale_ntin_rate', 'sale_totl_rate', 'eva', 'ebitda', 'ev_ebitda',
                        'bram_depn', 'crnt_rate', 'quck_rate', 'equt_inrt', 'totl_aset_inrt'
                    ] #
                    
                    if _compare_financial_data(api_statement, db_statement, statement_cols, logger): #
                        logger.debug(f"[{stk_cd}] {yymm} 재무제표 변경 감지 → INSERT 대상 추가") #
                        statements_to_insert.append(api_statement) #
                    
                    if _compare_financial_data(api_ratio, db_ratio, ratio_cols, logger): #
                        logger.debug(f"[{stk_cd}] {yymm} 재무비율 변경 감지 → INSERT 대상 추가") #
                        ratios_to_insert.append(api_ratio) #
            
            except KisAPIError as e:
                logger.error(f"[{stk_cd}] KIS API 오류: {e} (Error Code: {e.error_code})") #
                continue #
            except Exception as e:
                logger.error(f"[{stk_cd}] 재무정보 처리 중 예외 발생: {e}", exc_info=True) #
                continue #
        
        # (신규) 루프 종료 직후 최종 진행률 로깅
        loop_elapsed = time.time() - loop_start_time
        final_progress_msg = (
            f"[{job_id}] ({total}/{total}) "
            f"수집/비교 완료. (소요시간: {time.strftime('%H:%M:%S', time.gmtime(loop_elapsed))})"
        )
        logger.info(final_progress_msg)
        
        # 8. 일괄 저장 (Loop 종료 후)
        job_statuses[job_id].update({
            "phase": "3/3", #
            "phase_name": "DB 일괄 저장", #
            "progress": 85, #
            "last_log": final_progress_msg # (수정)
        })
        
        if statements_to_insert:
            logger.info(f"[{job_id}] 신규/변경된 재무제표: {len(statements_to_insert)}건") #
            db.insert_financial_statements(statements_to_insert) #
            logger.info(f"[{job_id}] ✅ 재무제표 INSERT 완료") #
        else:
            logger.info(f"[{job_id}] 신규/변경된 재무제표 데이터가 없습니다.") #
        
        if ratios_to_insert:
            logger.info(f"[{job_id}] 신규/변경된 재무비율: {len(ratios_to_insert)}건") #
            db.insert_financial_ratios(ratios_to_insert) #
            logger.info(f"[{job_id}] ✅ 재무비율 INSERT 완료") #
        else:
            logger.info(f"[{job_id}] 신규/변경된 재무비율 데이터가 없습니다.") #

        # --- [PRD 4.1.2] 완료 상태 ---
        end_time = datetime.now() #
        duration = (end_time - start_time).total_seconds() #
        
        final_msg = f"재무정보 수집 성공적으로 완료 (총 {total}개 처리, {duration/60:.1f}분 소요)" # (수정)
        
        job_statuses[job_id].update({
            "is_running": False, #
            "progress": 100, #
            "last_status": "success", #
            "end_time": end_time.isoformat(), #
            "duration": f"{int(duration)}초 ({duration/60:.1f}분)", #
            "last_log": final_msg # (수정)
        })
        logger.info(f"✅ [{job_id}] {final_msg}") # (수정)

    except Exception as e:
        logger.critical(f"[{job_id}] 치명적 오류 발생: {e}", exc_info=True) #
        # --- [PRD 4.1.2] 실패 상태 ---
        job_statuses[job_id].update({
            "is_running": False, #
            "last_status": "failure", #
            "error": str(e), #
            "end_time": datetime.now().isoformat() #
        })
    
    finally:
        # --- [PRD 4.1.2] (안전장치) 항상 is_running = False 보장 ---
        job_statuses[job_id]["is_running"] = False #


def _compare_financial_data(api_data: dict, db_data: dict, 
                            columns: List[str], logger: logging.Logger) -> bool:
    """
    API 신규 버전과 DB 최신 버전의 필드를 비교 (financial_update.py 원본 로직)
   
    """
    if db_data is None:
        return True  # DB에 없음 = 신규 데이터
    
    for col in columns: #
        api_value = api_data.get(col) #
        db_value = db_data.get(col) #
        
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
        
        if api_value != db_value: #
            # (로그 레벨을 debug로 조정 - 너무 많은 로그 방지)
            logger.debug(
                f"[{api_data.get('stk_cd')}/{api_data.get('stac_yymm')}] 변경 감지: "
                f"Column={col}, API_Value={api_value} (type={type(api_value).__name__}), "
                f"DB_Value={db_value} (type={type(db_value).__name__})"
            ) #
            return True  # 변경 감지
    
    return False  # 변경 없음

#
# --- (제거) financial_update.py의 main() 및 if __name__ == '__main__' ---
#