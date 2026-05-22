import logging
import re
from datetime import date
from typing import List, Dict, Any
import httpx

logger = logging.getLogger(__name__)

class PubDataClient:
    """
    공공데이터포털 금융위원회 주식시세정보 API 연동 클라이언트
    """
    
    def __init__(self, api_key: str) -> None:
        """
        api_key: 공공데이터포털에서 발급받은 일반 인증키 (Decoding 키 권장)
        """
        if not api_key:
            raise ValueError("공공데이터 API 인증키가 정의되지 않았습니다.")
        self.api_key = api_key
        self.base_url = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"

    def get_market_cap_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """
        지정된 날짜의 전 종목 시가총액 및 시세 정보를 일괄 수집합니다.
        
        :param target_date: 수집 대상 날짜
        :return: 정형화된 시총 데이터 리스트
        """
        bas_dt = target_date.strftime("%Y%m%d")
        params = {
            "serviceKey": self.api_key,
            "basDt": bas_dt,
            "numOfRows": 5000,
            "resultType": "json"
        }
        
        logger.info(f"공공데이터 API 호출: {self.base_url} (기준일: {bas_dt})")
        
        try:
            # params를 통해 쿼리 파라미터를 요청하면 httpx가 인코딩을 처리합니다.
            response = httpx.get(self.base_url, params=params, timeout=30.0)
            if response.status_code != 200:
                logger.error(f"공공데이터 API 응답 에러 (HTTP status: {response.status_code})")
                return []
                
            data = response.json()
            
            # API 응답 구조 검증
            res_header = data.get("response", {}).get("header", {})
            result_code = res_header.get("resultCode")
            if result_code != "00":
                logger.error(f"공공데이터 API 서비스 에러: {res_header.get('resultMsg')} (Code: {result_code})")
                return []
                
            items_container = data.get("response", {}).get("body", {}).get("items", {})
            if not items_container:
                logger.warning(f"공공데이터 API 응답에 items 정보가 없습니다. (기준일: {bas_dt})")
                return []
                
            item_list = items_container.get("item", [])
            if not isinstance(item_list, list):
                item_list = [item_list]
                
            normalized_records = []
            for item in item_list:
                srtn_cd = item.get("srtnCd", "").strip()
                if not srtn_cd:
                    continue
                    
                # A005930 등 접두어 제거하고 뒤의 6자리 숫자만 추출
                stk_cd = srtn_cd[-6:]
                if not re.match(r"^\d{6}$", stk_cd):
                    continue
                    
                try:
                    cls_prc = int(item.get("clpr", 0) or 0)
                    mkt_cap = int(item.get("mrktTotAmt", 0) or 0)
                    vol = int(item.get("trqu", 0) or 0)
                    amt = int(item.get("trPrc", 0) or 0)
                    listed_shares = int(item.get("lstgStCnt", 0) or 0)
                except (ValueError, TypeError) as e:
                    logger.warning(f"데이터 파싱 에러 (종목코드 {stk_cd}): {e}")
                    continue
                    
                normalized_records.append({
                    "dt": target_date,
                    "stk_cd": stk_cd,
                    "cls_prc": cls_prc,
                    "mkt_cap": mkt_cap,
                    "vol": vol,
                    "amt": amt,
                    "listed_shares": listed_shares
                })
                
            logger.info(f"공공데이터 API 수집 완료: 총 {len(normalized_records)}건 (기준일: {bas_dt})")
            return normalized_records
            
        except Exception as e:
            logger.error(f"공공데이터 API 연동 중 오류 발생: {e}", exc_info=True)
            return []
