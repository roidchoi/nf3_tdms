# tasks/financial_task.py

import os
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

from p1_shared.api.kis_api_core import KisApiCore
from collectors.kis_kr_client import KisKrClient
from collectors import utils
from repositories.base import create_kdms_pool
from repositories.master_repo import MasterRepo
from repositories.financial_repo import FinancialRepo

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class DatabaseManager:
    """테스트 코드 및 레거시 태스크 구조와의 호환을 위한 DB 매니저 어댑터 클래스."""
    
    def __init__(self) -> None:
        self.pool = create_kdms_pool()
        self.master_repo = MasterRepo(self.pool)
        self.financial_repo = FinancialRepo(self.pool)

    def get_all_stock_codes(self, active_only: bool = True) -> List[str]:
        """활성 상태인 전 종목의 단축 코드를 조회합니다."""
        stocks = self.master_repo.get_all_active_stocks()
        return [s["stk_cd"] for s in stocks if s.get("stk_cd")]

    def get_latest_financial_statement(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]:
        return self.financial_repo.get_latest_statement(stk_cd, stac_yymm, div_cls_code)

    def get_latest_financial_ratio(self, stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]:
        return self.financial_repo.get_latest_ratio(stk_cd, stac_yymm, div_cls_code)

    def insert_financial_statements(self, data: List[Dict[str, Any]]) -> int:
        return self.financial_repo.insert_statements(data)

    def insert_financial_ratios(self, data: List[Dict[str, Any]]) -> int:
        return self.financial_repo.insert_ratios(data)


class KisREST:
    """KIS OpenAPI 연동 및 테스트 모킹 호환용 어댑터 클래스."""
    
    def __init__(self, mock: bool = False, log_level: int = 1) -> None:
        self.mock = mock
        if mock:
            self.client = None
        else:
            # 환경 프로파일 또는 환경변수에서 KIS API Credentials 로드
            from p1_shared.utils.env_detector import EnvDetector
            detector = EnvDetector()
            profile = detector.load_env_profile()
            
            env = detector.detect()
            is_dev = (env == "dev")
            
            appkey = profile.get("kis_app_key") or os.environ.get("KIS_APP_KEY", "")
            appsecret = profile.get("kis_app_secret") or os.environ.get("KIS_APP_SECRET", "")
            account_no = profile.get("kis_account_no") or os.environ.get("KIS_ACCOUNT_NO", "")
            
            api_core = KisApiCore(
                app_key=appkey,
                app_secret=appsecret,
                account_no=account_no
            )
            self.client = KisKrClient(api_core=api_core)

    def fetch_all_financial_data(self, stk_cd: str, div_cls_code: str = '1') -> Dict[str, List[Dict[str, Any]]]:
        if self.mock or self.client is None:
            return {}
        return self.client.fetch_all_financial_data(stk_cd, div_cls_code)


class KisAPIError(Exception):
    """KIS API 통신 관련 사용자 정의 예외 클래스."""
    def __init__(self, message: str, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.error_code = error_code


def run_financial_update(job_statuses: Dict[str, Any], test_mode: bool = False):
    """
    KIS 재무정보 수집 및 PIT 버전 관리 파이프라인 태스크.
    
    :param job_statuses: 전역 상태 공유용 딕셔너리
    :param test_mode: True일 경우 대표 종목군만 샘플링하여 수행
    """
    job_id = "financial_update"
    start_time = datetime.now(KST)

    # [PRD 4.1.2] 상태 초기화
    job_statuses[job_id] = {
        "is_running": True,
        "phase": "1/3",
        "phase_name": "작업 시작 및 초기화",
        "progress": 0,
        "start_time": start_time.isoformat(),
        "last_log": f"작업 시작 (Test Mode: {test_mode})",
        "stocks_processed": 0,
        "total_stocks": 0
    }
    logger.info(f"[{job_id}] 작업 시작. (Test Mode: {test_mode})")

    try:
        logger.info(f"[{job_id}] KIS API 및 Database 어댑터 초기화...")
        kis_api = KisREST(mock=test_mode, log_level=1)
        db = DatabaseManager()

        # 1. 대상 종목 결정
        job_statuses[job_id].update({
            "phase": "1/3",
            "phase_name": "대상 종목 조회",
            "progress": 10,
            "last_log": "DB에서 수집 대상 종목 조회 중..."
        })
        
        if test_mode:
            logger.info(f"[{job_id}] 테스트 모드: 대표 종목 필터링")
            target_stocks = ["005930", "000660"]
            logger.info(f"[{job_id}] 테스트 대상: {len(target_stocks)}개 종목")
        else:
            logger.info(f"[{job_id}] 전체 상장 종목 대상 재무정보 수집 시작")
            target_stocks = db.get_all_stock_codes(active_only=True)
            logger.info(f"[{job_id}] 총 {len(target_stocks)}개 종목 조회 완료")

        if not target_stocks:
            logger.warning(f"[{job_id}] 수집 대상 종목이 없습니다. 작업 종료.")
            raise ValueError("수집 대상 종목이 없습니다.")

        job_statuses[job_id]["total_stocks"] = len(target_stocks)
        
        statements_to_insert = []
        ratios_to_insert = []

        # 2. 종목 순회 및 PIT 변경 감지
        job_statuses[job_id].update({
            "phase": "2/3",
            "phase_name": "재무정보 수집 및 비교 (PIT)",
            "progress": 20
        })
        
        total = len(target_stocks)
        loop_start_time = time.time()
        
        for idx, stk_cd in enumerate(target_stocks):
            # KIS API Rate Limit (초당 20건) 대비 안전성 확보를 위해 종목당 0.5초 지연 추가 (테스트 모드 제외)
            if not test_mode and idx > 0:
                time.sleep(0.5)
                
            # tqdm 스타일 진척률 및 메트릭스 로깅
            if idx % 20 == 0 or idx == total - 1:
                progress = 20 + (idx / total * 60)  # Phase 2는 20% ~ 80%
                elapsed = time.time() - loop_start_time
                if elapsed == 0:
                    elapsed = 1e-6
                
                items_per_sec = (idx + 1) / elapsed
                eta_seconds = (total - (idx + 1)) / items_per_sec if items_per_sec > 0 else 0
                eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                
                progress_msg = (
                    f"[{job_id}] ({idx+1}/{total}) "
                    f"[{items_per_sec:.1f}it/s, ETA: {eta_str}] "
                    f"... (현재: {stk_cd})"
                )
                
                logger.info(progress_msg)
                job_statuses[job_id].update({
                    "progress": int(progress),
                    "stocks_processed": idx + 1,
                    "last_log": progress_msg
                })

            try:
                # KIS API를 통한 재무 데이터 7종 통합 조회
                all_fin_data = kis_api.fetch_all_financial_data(stk_cd, div_cls_code='1')
                if not all_fin_data:
                    # 테스트 Mock 대응 등 비어있을 경우 스킵
                    continue
                
                # API별 변환 및 stac_yymm 매핑 딕셔너리 구성
                api_maps = {}
                for api_name, data_list in all_fin_data.items():
                    if not data_list or not isinstance(data_list, list):
                        continue
                    transformed_list = utils.transform_data(data_list, 'kis', api_name)
                    api_maps[api_name] = {item['stac_yymm']: item for item in transformed_list if item.get('stac_yymm')}
                
                # 존재하는 모든 stac_yymm 결산년월 세트 추출
                all_yymm = set()
                for m in api_maps.values():
                    all_yymm.update(m.keys())
                
                if not all_yymm:
                    logger.debug(f"[{stk_cd}] API 응답에 유효한 결산 정보가 없습니다.")
                    continue
                
                # stac_yymm 기준으로 재무제표(BS/IS) 및 재무비율 병합 수행
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
                    
                    db_statement = db.get_latest_financial_statement(stk_cd, yymm, '1')
                    db_ratio = db.get_latest_financial_ratio(stk_cd, yymm, '1')
                    
                    # 비교 대상 필드 정의
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
                    
                    # 3. 변경 감지 시 INSERT 대기열에 추가
                    if _compare_financial_data(api_statement, db_statement, statement_cols, logger):
                        logger.debug(f"[{stk_cd}] {yymm} 재무제표 변경 또는 신규 생성 감지 → DB INSERT 대기")
                        statements_to_insert.append(api_statement)
                    
                    if _compare_financial_data(api_ratio, db_ratio, ratio_cols, logger):
                        logger.debug(f"[{stk_cd}] {yymm} 재무비율 변경 또는 신규 생성 감지 → DB INSERT 대기")
                        ratios_to_insert.append(api_ratio)
            
            except KisAPIError as e:
                logger.error(f"[{stk_cd}] KIS API 수집 실패 (에러코드: {e.error_code}): {e}")
                continue
            except Exception as e:
                logger.error(f"[{stk_cd}] 재무정보 처리 중 예외 발생: {e}", exc_info=True)
                continue
        
        loop_elapsed = time.time() - loop_start_time
        final_progress_msg = (
            f"[{job_id}] ({total}/{total}) "
            f"수집/비교 완료. (소요시간: {time.strftime('%H:%M:%S', time.gmtime(loop_elapsed))})"
        )
        logger.info(final_progress_msg)
        
        # 8. 일괄 저장 (Phase 3)
        job_statuses[job_id].update({
            "phase": "3/3",
            "phase_name": "DB 일괄 저장",
            "progress": 85,
            "last_log": final_progress_msg
        })
        
        if statements_to_insert:
            logger.info(f"[{job_id}] 신규/변경된 재무제표: {len(statements_to_insert)}건 저장 시작...")
            db.insert_financial_statements(statements_to_insert)
            logger.info(f"[{job_id}] ✅ 재무제표 벌크 저장 성공.")
        else:
            logger.info(f"[{job_id}] 신규/변경된 재무제표가 없어 DB 업데이트를 스킵합니다.")
            
        if ratios_to_insert:
            logger.info(f"[{job_id}] 신규/변경된 재무비율: {len(ratios_to_insert)}건 저장 시작...")
            db.insert_financial_ratios(ratios_to_insert)
            logger.info(f"[{job_id}] ✅ 재무비율 벌크 저장 성공.")
        else:
            logger.info(f"[{job_id}] 신규/변경된 재무비율이 없어 DB 업데이트를 스킵합니다.")

        # 성공 완료 상태 기록
        end_time = datetime.now(KST)
        duration = (end_time - start_time).total_seconds()
        final_msg = f"재무정보 수집 성공적으로 완료 (총 {total}개 처리, {duration/60:.1f}분 소요)"
        
        job_statuses[job_id].update({
            "is_running": False,
            "progress": 100,
            "last_status": "success",
            "end_time": end_time.isoformat(),
            "duration": f"{int(duration)}초 ({duration/60:.1f}분)",
            "last_log": final_msg
        })
        logger.info(f"✅ [{job_id}] {final_msg}")

    except Exception as e:
        logger.critical(f"[{job_id}] 수집 파이프라인 구동 중 치명적 오류 발생: {e}", exc_info=True)
        job_statuses[job_id].update({
            "is_running": False,
            "last_status": "failure",
            "error": str(e),
            "end_time": datetime.now(KST).isoformat()
        })
    finally:
        job_statuses[job_id]["is_running"] = False


def _compare_financial_data(api_data: dict, db_data: dict, columns: List[str], logger: logging.Logger) -> bool:
    """
    API 응답 데이터와 DB 내 최신 데이터 간 필드별 변경 감지 정규화 비교 함수.
    API 수집값 자체가 None, 0, 0.0인 경우 DB 값을 훼손하지 않기 위해 변경으로 보지 않습니다.
    오직 유효한 실제 값의 변경(신규/수치 변경)만 변경으로 감지합니다.
    """
    if db_data is None:
        return True  # DB에 없으므로 신규 생성 대상

    for col in columns:
        api_value = api_data.get(col)
        db_value = db_data.get(col)
        
        # API에서 유효하게 수집된 값이 없는 경우, 기존 DB 데이터를 그대로 유지
        if api_value in (None, 0, 0.0):
            continue
            
        if db_value in (None, 0, 0.0):
            db_value = None
            
        # 숫자 정밀 타입 정규화 변환
        if isinstance(db_value, (int, float, Decimal)):
            db_value = float(db_value)
        if isinstance(api_value, (int, float, Decimal)):
            api_value = float(api_value)
            
        if api_value != db_value:
            logger.debug(
                f"[{api_data.get('stk_cd')}/{api_data.get('stac_yymm')}] {col} 필드 변경 감지: "
                f"API={api_value} ({type(api_value).__name__}) vs DB={db_value} ({type(db_value).__name__})"
            )
            return True
            
    return False
