"""
standalone_scripts/check_kis_date_range.py

KIS 일봉 API의 실제 동작 방식을 진단합니다.

[KIS API 핵심 제약]
  - start_date 파라미터는 실질적으로 무시됨
  - end_date 기준 이전 100건만 반환 (역순: 최신→과거)
  - 장기 조회를 위해 end_date를 점점 과거로 이동하며 반복 호출 필요

이 스크립트에서 진단하는 내용:
  1. 100건 반환 확인 (start_date 무관)
  2. end_date를 과거로 이동한 연속 조회 방식의 도달 가능 최초 날짜
  3. adj_price=0(수정) vs adj_price=1(원본) 비교 (과거 이벤트 발생 종목)
  4. 연속 조회 총 호출 수 추정

실행 방법 (00_kdms/ 폴더, 가상환경 활성화 상태):
    python standalone_scripts/check_kis_date_range.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.kis_rest import KisREST
from datetime import date, timedelta

SEPARATOR = "=" * 70

# 진단용 대표 종목
# - 005930 삼성전자: 2018-05-04 50:1 액면분할 (수정/원본 차이 명확)
# - 000660 SK하이닉스: 여러 배당 조정 이력
TEST_STOCKS = [
    ('005930', '삼성전자'),
    ('000660', 'SK하이닉스'),
]

# 연속 조회 최대 반복 횟수 (무한 루프 방지)
MAX_PAGES = 150   # 100건 × 150페이지 = 최대 15,000 거래일 ≈ 약 60년
RECORDS_PER_CALL = 100


def single_call_test(kis: KisREST, stk_cd: str, stk_nm: str):
    """
    [테스트 1] start_date를 다양하게 설정해 실제 반환 건수/기간 확인.
    → KIS는 start_date를 무시하고 end_date 기준 100건만 반환함을 검증.
    """
    today_str = date.today().strftime('%Y%m%d')
    print(f"\n[테스트 1] {stk_cd} {stk_nm} - start_date 무관성 확인 (end_date=오늘)")
    print(f"  {'start_date':<12} {'실제 가장 오래된':<16} {'실제 최신':<12} {'건수':>6}")
    print(f"  {'-'*55}")

    for year in [2000, 2015, 2020, 2023, 2025]:
        start_str = f"{year}0101"
        try:
            recs = kis.fetch_daily_price(stk_cd, start_str, today_str, adj_price='0')
            if recs:
                oldest = recs[-1].get('stck_bsop_date', 'N/A')
                newest = recs[0].get('stck_bsop_date', 'N/A')
                print(f"  {start_str:<12} {oldest:<16} {newest:<12} {len(recs):>6}건")
            else:
                print(f"  {start_str:<12} {'(데이터 없음)':<16} {'-':<12} {'0':>6}건")
        except Exception as e:
            print(f"  {start_str:<12} [오류: {e}]")


def pagination_test(kis: KisREST, stk_cd: str, stk_nm: str):
    """
    [테스트 2] end_date를 반복적으로 과거로 이동하여 연속 조회 방식 검증.
    실제 조회 가능한 최초 날짜와 총 호출 수를 확인합니다.
    """
    print(f"\n[테스트 2] {stk_cd} {stk_nm} - end_date 이동 연속 조회")
    print(f"  {'페이지':<6} {'end_date':<12} {'실제 최신':<12} {'실제 가장오래된':<16} {'건수':>6}")
    print(f"  {'-'*60}")

    current_end = date.today()
    all_dates = []
    page = 0

    while page < MAX_PAGES:
        end_str = current_end.strftime('%Y%m%d')
        # start_date는 충분히 과거로 설정 (사실상 무시됨)
        start_str = '19800101'

        try:
            recs = kis.fetch_daily_price(stk_cd, start_str, end_str, adj_price='0')
        except Exception as e:
            print(f"  [페이지 {page+1}] 오류: {e}")
            break

        if not recs:
            print(f"  [페이지 {page+1}] 데이터 없음 - 조회 종료")
            break

        page += 1
        newest = recs[0].get('stck_bsop_date', 'N/A')
        oldest = recs[-1].get('stck_bsop_date', 'N/A')
        count  = len(recs)

        # 10페이지마다, 또는 마지막 페이지만 출력 (중간 생략)
        if page <= 10 or count < RECORDS_PER_CALL:
            print(f"  {page:<6} {end_str:<12} {newest:<12} {oldest:<16} {count:>6}건")
        elif page == 10:
            print(f"  ... 10회 단위로 출력 (중간 생략)")
        elif page > 10 and page % 10 == 0:
            print(f"  {page:<6} {end_str:<12} {newest:<12} {oldest:<16} {count:>6}건")

        all_dates.extend([r.get('stck_bsop_date') for r in recs])

        # 종료 조건: 100건 미만 반환 → 더 이상 과거 데이터 없음
        if count < RECORDS_PER_CALL:
            print(f"\n  ✅ 최종 조회 완료!")
            break

        # 다음 end_date = 현재 가장 오래된 날짜 - 1일
        try:
            oldest_date = date(int(oldest[:4]), int(oldest[4:6]), int(oldest[6:8]))
            current_end = oldest_date - timedelta(days=1)
        except Exception:
            print(f"  날짜 파싱 실패: {oldest}")
            break
    else:
        print(f"\n  ⚠️  MAX_PAGES({MAX_PAGES}) 도달 - 더 오래된 데이터 존재 가능")

    # 최종 요약
    valid_dates = sorted([d for d in all_dates if d])
    if valid_dates:
        print(f"\n  📊 연속 조회 결과 요약:")
        print(f"     총 호출 수     : {page}회")
        print(f"     총 수집 레코드 : {len(all_dates)}건")
        print(f"     최초 날짜       : {valid_dates[0]}")
        print(f"     최신 날짜       : {valid_dates[-1]}")
        earliest_year = int(valid_dates[0][:4])
        print(f"     → --start_year 권장값: {earliest_year}")
        print(f"     → 전 종목 조회 시 종목당 API 호출: ~{page}회 × 2(수정/원본) = ~{page*2}회")


def adj_vs_raw_test(kis: KisREST, stk_cd: str, stk_nm: str,
                    around_event_date: str = '20180504'):
    """
    [테스트 3] 특정 과거 시점에서 수정주가(0) vs 원본주가(1) 비교.
    삼성전자 2018-05-04 50:1 액면분할 기준으로 검증.
    adj_price=0이 수정가, adj_price=1이 원본가임을 확인.
    """
    # 이벤트 전후 20일 조회: around_event_date를 end_date로, 이전 30 거래일치
    print(f"\n[테스트 3] {stk_cd} {stk_nm} - 수정(0) vs 원본(1) 비교 ({around_event_date} 기준)")
    print(f"  {'날짜':<12} {'수정주가(adj=0)':>14} {'원본주가(adj=1)':>14} {'비율(adj/raw)':>14} {'비고'}")
    print(f"  {'-'*65}")

    try:
        # end_date를 이벤트일 이후로 설정하여 이벤트 전후 데이터 포함
        event_dt = date(int(around_event_date[:4]),
                        int(around_event_date[4:6]),
                        int(around_event_date[6:8]))
        end_dt  = event_dt + timedelta(days=10)
        end_str = end_dt.strftime('%Y%m%d')

        adj_recs = kis.fetch_daily_price(stk_cd, '20000101', end_str, adj_price='0')
        raw_recs = kis.fetch_daily_price(stk_cd, '20000101', end_str, adj_price='1')

        if not adj_recs or not raw_recs:
            print("  데이터 없음")
            return

        # 날짜별 매핑
        adj_map = {r['stck_bsop_date']: int(r.get('stck_clpr', 0)) for r in adj_recs}
        raw_map = {r['stck_bsop_date']: int(r.get('stck_clpr', 0)) for r in raw_recs}

        all_dates = sorted(set(adj_map) | set(raw_map), reverse=True)[:20]  # 최근 20일

        for dt_str in reversed(all_dates):
            adj_p = adj_map.get(dt_str, 0)
            raw_p = raw_map.get(dt_str, 0)
            ratio = f"{adj_p/raw_p:.4f}" if raw_p else "N/A"
            note  = "← 이벤트일" if dt_str == around_event_date else ""
            changed = "★" if adj_p != raw_p else ""
            print(f"  {dt_str:<12} {adj_p:>14,} {raw_p:>14,} {ratio:>14} {changed} {note}")

    except Exception as e:
        print(f"  [오류: {e}]")


def main():
    print(SEPARATOR)
    print(" KIS 일봉 API 조회 범위 및 연속 조회 방식 진단")
    print(SEPARATOR)

    try:
        kis = KisREST(mock=False, log_level=0)
    except Exception as e:
        print(f"[ERROR] KIS 초기화 실패: {e}")
        sys.exit(1)

    stk_cd, stk_nm = TEST_STOCKS[0]  # 삼성전자로 전체 테스트

    # 테스트 1: start_date 무관성 확인
    single_call_test(kis, stk_cd, stk_nm)

    # 테스트 2: 연속 조회 가능 범위 확인 (삼성전자만, 시간 절약을 위해 20페이지 제한)
    global MAX_PAGES
    MAX_PAGES = 150  # 150 × 100 = 15,000 거래일 ≈ 60년치
    pagination_test(kis, stk_cd, stk_nm)

    # 테스트 3: 수정/원본 비교 (삼성전자 2018 액면분할)
    adj_vs_raw_test(kis, stk_cd, stk_nm, around_event_date='20180504')

    print(f"\n{SEPARATOR}")
    print(" 요약 및 rebuild_factors_from_kis.py 구현 방향:")
    print("  1. fetch_full_history()는 end_date를 반복 감소하는 페이지네이션 방식으로 재구현")
    print("  2. 100건 미만 반환 시 마지막 페이지로 판단하고 루프 종료")
    print("  3. adj_price=0=수정주가, adj_price=1=원본주가 (KIS 공식 확인)")
    print(SEPARATOR)


if __name__ == '__main__':
    main()
