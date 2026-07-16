import os
import sys
from datetime import datetime, timedelta

# 프로젝트 루트 및 tdms_core 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")

from p1_shared.api.kis_api_core import KisApiCore
from p1_shared.utils.env_detector import EnvDetector

def test_api():
    detector = EnvDetector()
    profile = detector.load_env_profile()
    env = detector.detect()
    is_dev = (env == "dev")
    appkey = os.environ.get("KIS_APP_KEY") or profile.get("kis_app_key") or ""
    appsecret = os.environ.get("KIS_APP_SECRET") or profile.get("kis_app_secret") or ""
    
    print(f"Detect Env: {env}, is_dev: {is_dev}")
    print(f"AppKey: {appkey[:5]}...")
    
    api_core = KisApiCore(
        app_key=appkey,
        app_secret=appsecret,
        account_no="",
        is_mock=False  # 실전 API 포트로 강제 테스트 (모의는 이 API 미지원하므로)
    )
    
    # 테스트 날짜 목록 (초장기 과거 날짜 확인)
    test_dates = [
        "20150721",  # 약 11년 전 (화요일)
        "20100720",  # 약 16년 전 (화요일)
        "20050719",  # 약 21년 전 (화요일)
        "20000718",  # 약 26년 전 (화요일)
    ]
    
    for dt_str in test_dates:
        print(f"\n--- Requesting Investor Trade for date: {dt_str} ---")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "005930",  # 삼성전자
            "FID_INPUT_DATE_1": dt_str,
            "FID_ORG_ADJ_PRC": "",
            "FID_ETC_CLS_CODE": "1"
        }
        try:
            res = api_core.request(
                method="GET",
                path="/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
                params=params,
                tr_id="FHPTJ04160001"
            )
            rt_cd = res.get("rt_cd")
            msg1 = res.get("msg1")
            print(f"Response rt_cd: {rt_cd}, msg1: {msg1}")
            output2 = res.get("output2", [])
            print(f"Output2 length: {len(output2)}")
            if output2:
                # API는 뒤에서부터 (최신일부터 과거로) 돌려주는지 또는 역순인지 확인
                print(f"First record date in output2: {output2[0].get('stck_bsop_date')}")
                print(f"Last record date in output2: {output2[-1].get('stck_bsop_date')}")
            else:
                print("No data in output2")
        except Exception as e:
            print(f"Failed for date {dt_str}: {e}")

if __name__ == "__main__":
    test_api()
