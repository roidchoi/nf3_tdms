"""
standalone_scripts/verify_rebuilt_factors.py

적재된 KIS 팩터와 DB 수정주가 산출 정확성을 검증합니다.

검증 항목:
  1. DB에 적재된 팩터 조회 (KIS vs KIWOOM 역수 관계 확인)
  2. DB 산출 수정주가 vs KIS API 실제 수정주가 1:1 비교

실행 방법:
  python standalone_scripts/verify_rebuilt_factors.py
  python standalone_scripts/verify_rebuilt_factors.py --stk_cd 000040 --stk_cd 000070
"""
from __future__ import annotations

import sys
import os
import argparse
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.db_manager import DatabaseManager
from collectors.kis_rest import KisREST

SEP = "-" * 72


def to_float(val):
    """Decimal / str / float 모두 float으로 변환"""
    if isinstance(val, Decimal):
        return float(val)
    return float(val) if val is not None else None


def verify_stock(db: DatabaseManager, kis: KisREST, stk_cd: str) -> bool:
    print(f"\n{SEP}")
    print(f"  [{stk_cd}] 검증 시작")
    print(SEP)

    # ── 1. 적재 팩터 조회 ──────────────────────────────────────────────────
    factors_sql = """
    SELECT event_dt, price_ratio, price_source, effective_dt
    FROM price_adjustment_factors
    WHERE stk_cd = %(stk_cd)s
    ORDER BY event_dt DESC, price_source;
    """
    rows = db._execute_query(factors_sql, {"stk_cd": stk_cd}, fetch="all")

    if not rows:
        print("⚠️  DB에 적재된 팩터가 없습니다 (이벤트 없는 종목 또는 미처리).")
        return True

    print(f"\n[1] 적재 팩터 ({len(rows)}개)")
    print(f"  {'이벤트일':<12} {'price_ratio':>14} {'소스':<8} {'KIS×KIWOOM':>14}  메모")

    # 날짜별 KIS/KIWOOM 역수 관계 확인
    by_date: dict[date, dict] = {}
    for r in rows:
        edt = r["event_dt"]
        src = r["price_source"]
        ratio = to_float(r["price_ratio"])
        by_date.setdefault(edt, {})[src] = ratio

    for r in rows:
        edt   = r["event_dt"]
        src   = r["price_source"]
        ratio = to_float(r["price_ratio"])
        # KIS-KIWOOM 쌍이 있으면 역수 관계 확인
        pair  = by_date.get(edt, {})
        product_str = ""
        note        = ""
        if "KIS" in pair and "KIWOOM" in pair:
            product = pair["KIS"] * pair["KIWOOM"]
            product_str = f"{product:>14.6f}"
            note = "✅ 역수 일치" if abs(product - 1.0) < 0.01 else "❌ 역수 불일치"
        effective = str(r["effective_dt"])[:19]
        print(f"  {str(edt):<12} {ratio:>14.8f} {src:<8} {product_str}  {note} ({effective})")

    # ── 2. 이벤트 전후 DB vs KIS API 수정주가 비교 ─────────────────────────
    kis_only = [r for r in rows if r["price_source"] == "KIS"]
    if not kis_only:
        print("\n⚠️  KIS 소스 팩터가 없어 수정주가 비교를 건너뜁니다.")
        return True

    # 첫 번째 + 마지막 KIS 이벤트 검증
    check_events = []
    if kis_only:
        check_events.append(("가장 최근 이벤트", kis_only[0]["event_dt"]))
    if len(kis_only) > 1:
        check_events.append(("가장 오래된 이벤트", kis_only[-1]["event_dt"]))

    all_pass = True
    for label, event_dt in check_events:
        ok = _compare_window(db, kis, stk_cd, event_dt, label)
        all_pass = all_pass and ok

    return all_pass


def _compare_window(db, kis, stk_cd, event_dt, label) -> bool:
    win_start = event_dt - timedelta(days=10)
    win_end   = min(event_dt + timedelta(days=10), date.today() - timedelta(days=1))

    print(f"\n[2] {label} ({event_dt}) 전후 수정주가 비교")
    print(f"    기간: {win_start} ~ {win_end}")

    # DB 수정주가
    db_adj = db.get_adjusted_ohlcv_data(stk_cd, win_start, win_end)
    if not db_adj:
        print("  ⚠️  DB 수정주가 없음")
        return True

    db_df = pd.DataFrame(db_adj)
    db_df["dt"]      = pd.to_datetime(db_df["dt"]).dt.date
    db_df["cls_prc"] = db_df["cls_prc"].apply(to_float)
    db_df["factor"]  = db_df["factor"].apply(to_float)

    # KIS API 수정주가 (adj_price='0')
    try:
        kis_recs = kis.fetch_daily_price(
            stk_cd,
            win_start.strftime("%Y%m%d"),
            win_end.strftime("%Y%m%d"),
            adj_price="0",
        )
    except Exception as e:
        print(f"  ⚠️  KIS API 오류: {e}")
        return False

    if not kis_recs:
        print("  ⚠️  KIS API 응답 없음")
        return False

    kis_df = pd.DataFrame(kis_recs)
    kis_df["dt"]      = pd.to_datetime(kis_df["stck_bsop_date"]).dt.date
    kis_df["kis_adj"] = kis_df["stck_clpr"].astype(float)
    kis_df = kis_df.sort_values("dt").reset_index(drop=True)

    # 병합
    merged = pd.merge(
        db_df[["dt", "cls_prc", "factor"]],
        kis_df[["dt", "kis_adj"]],
        on="dt", how="inner",
    )

    if merged.empty:
        print("  ⚠️  공통 날짜 없음 (병합 실패)")
        return False

    merged["diff"] = (merged["cls_prc"] - merged["kis_adj"]).abs()
    merged["tol"]  = (merged["kis_adj"] * 0.5 / 100).clip(lower=1.0)
    merged["ok"]   = merged["diff"] <= merged["tol"]
    merged["mark"] = merged["dt"].apply(lambda d: "◀ 이벤트" if d == event_dt else "")

    print(f"\n  {'날짜':<12} {'DB수정주가':>12} {'KIS수정주가':>12} "
          f"{'팩터':>10} {'차이':>8} {'결과':>4}")
    for _, row in merged.iterrows():
        icon = "✅" if row["ok"] else "❌"
        print(f"  {str(row['dt']):<12} {row['cls_prc']:>12,.2f} "
              f"{row['kis_adj']:>12,.0f} {row['factor']:>10.6f} "
              f"{row['diff']:>8.2f} {icon}  {row['mark']}")

    pass_n = merged["ok"].sum()
    fail_n = (~merged["ok"]).sum()
    result = "✅ 일치" if fail_n == 0 else f"❌ {fail_n}건 불일치"
    print(f"\n  → {pass_n}건 PASS / {fail_n}건 FAIL  {result}")
    return fail_n == 0


def main():
    parser = argparse.ArgumentParser(description="적재 팩터 및 수정주가 산출 검증")
    parser.add_argument("--stk_cd", type=str, action="append", default=None,
                        help="검증 종목 (반복 지정 가능). 기본값: 000040 000070 000100")
    args = parser.parse_args()

    stk_list = args.stk_cd or ["000040", "000070", "000100"]

    db  = DatabaseManager()
    kis = KisREST(mock=False, log_level=0)

    results = {}
    for stk_cd in stk_list:
        results[stk_cd] = verify_stock(db, kis, stk_cd)

    print(f"\n{SEP}")
    print("  최종 요약")
    print(SEP)
    for stk_cd, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} [{stk_cd}]")
    overall = all(results.values())
    print(f"\n  전체: {'✅ 모두 정상' if overall else '❌ 일부 불일치'}")
    print(SEP)


if __name__ == "__main__":
    main()
