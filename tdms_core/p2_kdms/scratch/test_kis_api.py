import os
import sys
from datetime import date
import json

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

from dotenv import load_dotenv
load_dotenv("/home/roid2/pjt/nf3/01_nf3_tdms/.env")

from p1_shared.api.kis_api_core import KisApiCore
from p1_shared.utils.env_detector import EnvDetector

def test_api():
    print("=== Testing KIS API inquire-daily-itemchartprice ===")
    
    # 1. API 키 정보 가져오기
    detector = EnvDetector()
    profile = detector.load_env_profile()
    env = detector.detect()
    is_dev = (env == "dev")
    
    appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
    appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
    
    print(f"Environment: {env}, is_dev (mock client 사용 여부의 역): {is_dev}")
    print(f"App Key: {appkey[:5]}... {len(appkey)} chars")
    
    api_core = KisApiCore(
        app_key=appkey,
        app_secret=appsecret,
        account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
        is_mock=not is_dev
    )
    
    # 2. API 호출
    path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    target_date = date(2026, 6, 25)
    date_str = target_date.strftime("%Y%m%d")
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_DATE_1": date_str,
        "FID_INPUT_DATE_2": date_str,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "1"
    }
    
    # tr_id 바인딩
    res = api_core.request("GET", path, params=params, tr_id="FHKST03010100")
    
    print("\n=== API RESPONSE (truncated) ===")
    print(json.dumps(res, indent=2, ensure_ascii=False)[:3000])

if __name__ == "__main__":
    test_api()
