"""
standalone_scripts/check_kis_daily_fields.py

[STEP 0-1] KIS 일봉 API 응답 필드명 및 adj_price 파라미터 동작 확인용 진단 스크립트.
이 스크립트는 실제 API를 한 종목(삼성전자)에만 소량 호출하여
utils.py에 추가할 DATA_MAPPER 키를 확정하기 위해 사용합니다.
- 조회 데이터를 DB에 저장하지 않음 (Read-Only).

실행 방법 (00_kdms/ 폴더에서):
    python standalone_scripts/check_kis_daily_fields.py
"""
import sys
import os

# 루트 경로를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.kis_rest import KisREST
from datetime import date, timedelta

SEPARATOR = "=" * 65

def check_fields():
    print(SEPARATOR)
    print(" KIS 일봉 API 진단 스크립트")
    print(SEPARATOR)

    try:
        kis = KisREST(mock=False, log_level=0)
    except Exception as e:
        print(f"[ERROR] KIS 초기화 실패: {e}")
        print("        .env 파일의 KIS_APP_KEY, KIS_APP_SECRET 설정을 확인하세요.")
        return

    end_str   = date.today().strftime('%Y%m%d')
    start_str = (date.today() - timedelta(days=15)).strftime('%Y%m%d')
    target    = '005930'  # 삼성전자

    print(f"\n[대상 종목] {target} (삼성전자)")
    print(f"[조회 기간] {start_str} ~ {end_str}\n")

    # --- 1. adj_price='0' 조회 ---
    print(f"{'-'*40}")
    print(" [테스트 1] adj_price='0' 조회 결과")
    print(f"{'-'*40}")
    try:
        data_0 = kis.fetch_daily_price(target, start_str, end_str, adj_price='0')
        if data_0:
            print(f"  레코드 수 : {len(data_0)}")
            print(f"  필드 목록 : {list(data_0[0].keys())}")
            print(f"  최신 레코드:")
            for k, v in data_0[0].items():
                print(f"      {k:30s}: {v}")
        else:
            print("  [WARNING] 응답 데이터 없음")
    except Exception as e:
        print(f"  [ERROR] {e}")
        data_0 = []

    print()

    # --- 2. adj_price='1' 조회 ---
    print(f"{'-'*40}")
    print(" [테스트 2] adj_price='1' 조회 결과")
    print(f"{'-'*40}")
    try:
        data_1 = kis.fetch_daily_price(target, start_str, end_str, adj_price='1')
        if data_1:
            print(f"  레코드 수 : {len(data_1)}")
            print(f"  필드 목록 : {list(data_1[0].keys())}")
            print(f"  최신 레코드:")
            for k, v in data_1[0].items():
                print(f"      {k:30s}: {v}")
        else:
            print("  [WARNING] 응답 데이터 없음")
    except Exception as e:
        print(f"  [ERROR] {e}")
        data_1 = []

    print()

    # --- 3. 종가 비교 (수정주가 vs 원본주가 판별) ---
    if data_0 and data_1:
        print(f"{'-'*40}")
        print(" [테스트 3] adj_price='0' vs '1' 종가 비교")
        print(f"{'-'*40}")
        # 종가로 추정되는 필드 후보 탐색
        candidate_close_fields = [
            'stck_clpr', 'prdy_clpr', 'stck_prpr', 'output', 'cls_prc'
        ]
        close_field = None
        for f in candidate_close_fields:
            if f in data_0[0]:
                close_field = f
                break

        if close_field:
            close_0 = data_0[0].get(close_field)
            close_1 = data_1[0].get(close_field)
            print(f"  종가 필드명 추정 : '{close_field}'")
            print(f"  adj_price='0' 최신 종가 : {close_0}")
            print(f"  adj_price='1' 최신 종가 : {close_1}")
            if close_0 == close_1:
                print(f"\n  [결과] 두 값이 동일 → 현재 시점에는 구분 불가 (최근 이벤트 없음)")
            else:
                diff = abs(float(str(close_0).replace(',','')) - float(str(close_1).replace(',','')))
                print(f"  [결과] 두 값이 다름 (차이: {diff}) → 구분 가능")
        else:
            print(f"  [INFO] 종가 필드를 자동 탐지하지 못했습니다.")
            print(f"         위 필드 목록을 직접 확인하여 날짜/종가 필드명을 파악하세요.")

    print(f"\n{SEPARATOR}")
    print(" 진단 완료 - 위 필드 목록을 확인하여 결과를 피드백해 주세요.")
    print(SEPARATOR)


if __name__ == '__main__':
    check_fields()
