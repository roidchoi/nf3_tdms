import os
import time
import logging
import requests
from typing import Optional, Dict, List
from p1_shared.api.kiwoom_api_core import KiwoomApiCore

logger = logging.getLogger(__name__)

class KiwoomClient(KiwoomApiCore):
    """
    Kiwoom OpenAPI 실전/모의투자 클라이언트.
    p1_shared의 KiwoomApiCore를 확장하여 연속 조회(페이지네이션) 기능과 
    Rate Limiting이 적용된 분봉 데이터 조회 메소드를 제공합니다.
    """
    
    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        token_cache_path: str = "~/.cache/tdms/kiwoom_token.json",
        mock: bool = False
    ) -> None:
        # 환경변수 로드 및 주입
        # MOCK_ 또는 일반 키 지원
        prefix = "MOCK_" if mock else ""
        self.app_key = app_key or os.getenv(f"{prefix}KIWOOM_APP_KEY") or os.getenv("KIWOOM_APP_KEY")
        self.app_secret = app_secret or os.getenv(f"{prefix}KIWOOM_APP_SECRET") or os.getenv("KIWOOM_APP_SECRET")
        
        if not self.app_key or not self.app_secret:
            logger.warning("Kiwoom API Key 또는 App Secret이 설정되지 않았습니다. 환경변수를 확인하세요.")
            
        super().__init__(
            app_key=self.app_key or "DUMMY_KEY",
            app_secret=self.app_secret or "DUMMY_SECRET",
            token_cache_path=token_cache_path
        )
        
        # 실전/모의에 따라 Base URL 설정
        self.BASE_URL = "https://mockapi.kiwoom.com" if mock else "https://api.kiwoom.com"
        self.rate_limit_interval = 0.2  # 초당 5회 제한을 지키기 위한 0.2초 딜레이
        
    def get_minute_chart(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
        tic_scope: str = "1",
        adjusted_price: str = "1",
        max_requests: int = 30
    ) -> List[Dict]:
        """
        특정 기간 동안의 분봉 데이터를 연속 조회(Pagination)하여 반환합니다.
        
        :param stock_code: 종목코드
        :param start_date: 시작일 (YYYYMMDD)
        :param end_date: 종료일 (YYYYMMDD, 생략 시 오늘)
        :param tic_scope: 틱 범위 (1: 1분봉)
        :param adjusted_price: 수정주가 여부 (1: 적용)
        :param max_requests: 최대 연속 요청 횟수 (기본값 30회)
        :return: 정규화된 분봉 데이터 목록
        """
        api_id = "ka10080"
        endpoint = "/api/dostk/chart"
        url = f"{self.BASE_URL}{endpoint}"
        
        # 시작/종료 일시 포맷 (YYYYMMDDHHMMSS)
        start_dt = f"{start_date}000000"
        curr_end_date = end_date or time.strftime("%Y%m%d")
        end_dt = f"{curr_end_date}235959"
        
        data = {
            "stk_cd": stock_code,
            "tic_scope": tic_scope,
            "upd_stkpc_tp": adjusted_price
        }
        
        all_results = []
        next_key = ""
        
        for i in range(max_requests):
            # 헤더 준비 및 연속조회 키 추가
            try:
                headers = self.get_headers()
            except Exception as e:
                logger.error(f"Kiwoom Authorization 헤더 획득 실패: {e}")
                break
                
            headers["Content-Type"] = "application/json; charset=UTF-8"
            headers["api-id"] = api_id
            headers["cont-yn"] = "Y" if next_key else "N"
            if next_key:
                headers["next-key"] = next_key
                
            # Rate Limiting
            time.sleep(self.rate_limit_interval)
            
            try:
                res = requests.post(url, headers=headers, json=data)
                res.raise_for_status()
                res_json = res.json()
            except Exception as e:
                logger.error(f"Kiwoom API 호출 실패 ({i+1}/{max_requests}): {e}")
                break
                
            results_list = res_json.get("stk_min_pole_chart_qry", [])
            if not results_list:
                logger.warning(f"Kiwoom API 가 데이터를 반환하지 않았습니다: {res_json}")
                break
                
            all_results.extend(results_list)
            
            # 페이지네이션 종료 감지 (응답 헤더 확인)
            cont_yn = res.headers.get("cont-yn", "N")
            next_key = res.headers.get("next-key", "").strip()
            
            # 시작일자에 도달했는지 날짜 기준 판단
            # 결과 리스트의 마지막 데이터의 cntr_tm 확인
            last_item_time = results_list[-1].get("cntr_tm", "")
            if last_item_time and last_item_time < start_dt:
                logger.info(f"수집 데이터가 조회 시작일({start_date})에 도달하여 수집을 중단합니다.")
                break
                
            if cont_yn != "Y" or not next_key:
                break
                
        # 날짜 범위 내의 데이터만 필터링하여 반환
        filtered_results = []
        for item in all_results:
            cntr_tm = item.get("cntr_tm", "")
            if cntr_tm and start_dt <= cntr_tm <= end_dt:
                filtered_results.append(item)
                
        return filtered_results
