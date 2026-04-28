"""
standalone_scripts/rebuild_factors_from_kis.py

[Phase 3-A] 전 종목 수정계수(price_adjustment_factors)를 KIS 기반으로 재산출하는 일회성 마이그레이션 스크립트.

처리 흐름:
  1. DB에서 전체 상장 종목 코드 로드
  2. 종목별 KIS 일봉(수정/원본) 청크 단위 수집 → calculate_factors() → UPSERT (source='KIS')
  3. 전 종목 완료 후 KIWOOM 팩터 일괄 삭제
  4. 마일스톤 기록: 'LOGIC:FACTOR_SOURCE:KIS_COMPLETE'

실행 방법 (00_kdms/ 폴더, 가상환경 활성화 상태):
    python standalone_scripts/rebuild_factors_from_kis.py [--start_year 2015] [--dry_run]

주의:
  - KIS Rate Limit 20건/초 기준 약 2~3시간 소요 예상 (2,500종목 × 청크 수 × 2회 호출)
  - 네트워크/API 오류 발생 종목은 skip 후 계속 진행 (오류 목록 별도 출력)
  - 개발 PC에서 검증 후 운영 서버에 배포하여 실행할 것
"""

from __future__ import annotations  # Python 3.9 타입 힌트 호환

import sys
import os
import time
import argparse
import logging
import pandas as pd
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

# 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.kis_rest import KisREST
from collectors.db_manager import DatabaseManager
from collectors.factor_calculator import calculate_factors
from collectors import utils

# ---------------------------------------------------------------------------
# 설정 상수
# ---------------------------------------------------------------------------
CHUNK_MONTHS   = 6       # KIS API 단건 조회 최대 안전 기간 (6개월)
RATE_SLEEP     = 0.0     # KisREST 내부 RateLimiter(20/s)가 처리하므로 추가 대기 불필요
ERROR_MAX_SKIP = 50      # 누적 오류 종목이 이 수를 초과하면 스크립트 중단
PRICE_SOURCE   = 'KIS'
LOG_FORMAT     = '%(asctime)s [%(levelname)s] %(message)s'
SEPARATOR      = '=' * 65

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger('rebuild_factors')


def _fetch_page(kis: KisREST, stk_cd: str, end_date_str: str, adj_price: str) -> list[dict]:
    """KIS 일봉 단일 페이지 호출 (end_date 기준 이전 최대 100건)."""
    try:
        recs = kis.fetch_daily_price(stk_cd, '20000101', end_date_str, adj_price=adj_price)
        if recs:
            for r in recs:
                r['stk_cd'] = stk_cd
        return recs or []
    except Exception as ex:
        logger.warning(f"  [{stk_cd}] API 호출 실패 (end={end_date_str}, adj={adj_price}): {ex}")
        return []


def _has_adj_event_in_page(recs_adj: list, recs_raw: list) -> bool:
    """
    페이지 내 수정/원본 가격 차이 존재 여부 빠른 확인.
    adj_close != raw_close 인 레코드가 1건이라도 있으면 True.
    """
    raw_map = {r.get('stck_bsop_date'): r.get('stck_clpr') for r in recs_raw}
    for r in recs_adj:
        if r.get('stck_clpr') != raw_map.get(r.get('stck_bsop_date')):
            return True
    return False


def fetch_full_history(kis: KisREST, stk_cd: str,
                       start_year: int, adj_price: str,
                       max_pages: int = 35) -> list[dict]:
    """
    [KIS 실제 동작 기반] end_date 페이지네이션으로 전 기간 일봉 수집.

    KIS API 특성:
      - start_date 파라미터는 무시됨
      - end_date 기준 이전 100건만 반환 (역순: 최신→과거)
      - 연속 조회: 다음 end_date = 현재 페이지의 가장 오래된 날짜 - 1일

    종료 조건:
      ① 반환 건수 < 100 (마지막 페이지)
      ② start_year 이전 날짜 도달
      ③ max_pages 초과

    :param adj_price: '0'=수정주가, '1'=원본주가
    :param max_pages: 최대 페이지 수 (35 × 100건 ≈ 14년치)
    :return: 전 기간 레코드 리스트 (최신→과거 순, stk_cd 포함)
    """
    start_year_int = start_year
    current_end    = date.today()
    all_data       = []

    for _ in range(max_pages):
        end_str = current_end.strftime('%Y%m%d')
        recs    = _fetch_page(kis, stk_cd, end_str, adj_price)

        if not recs:
            break

        # start_year 이전 레코드 필터링 + 조기 종료
        filtered = []
        reached_start = False
        for r in recs:
            dt_str = r.get('stck_bsop_date', '')
            if dt_str and len(dt_str) >= 4 and int(dt_str[:4]) < start_year_int:
                reached_start = True
                break
            filtered.append(r)

        all_data.extend(filtered)

        if reached_start or len(recs) < 100:
            break

        # 다음 end_date = 현재 가장 오래된 날짜 - 1일
        oldest_str = recs[-1].get('stck_bsop_date', '')
        if not oldest_str:
            break
        try:
            oldest_date = date(int(oldest_str[:4]), int(oldest_str[4:6]), int(oldest_str[6:8]))
            current_end = oldest_date - timedelta(days=1)
        except ValueError:
            break

    return all_data



def process_stock(kis: KisREST, db: DatabaseManager,
                  stk_cd: str, start_year: int, dry_run: bool,
                  do_validate: bool = False) -> tuple[bool, dict | None]:
    """
    단일 종목의 팩터를 KIS 데이터 기반으로 재산출하고 UPSERT합니다.

    최적화 전략 (2단계):
      1. Quick Check: 최신 1페이지(100건)에서 수정=원본이면 이벤트 없음 → 즉시 skip (2 API calls)
      2. 이벤트 감지 시: 전 기간 페이지네이션 수행 (~40 API calls)

    :param do_validate: True이면 팩터 정확성 검증 결과를 추가로 반환
    :return: (success, validation_result | None)
    """
    try:

        # -------------------------------------------------------
        # [Full Scan] 전 기간 페이지네이션 수집
        #
        # Quick Check(최신/과거 단일 페이지 비교)은 다음 케이스에서 틀림:
        #   - 이벤트가 최신 100건 이전 + start_year 이후에 발생한 경우
        #   - 종목이 start_year 이후 신규 상장한 경우
        # → 올바른 판단은 전 기간 데이터를 수집한 후
        #   adj vs raw를 전체 비교하는 데이터 레벨 판단만 정확함.
        # -------------------------------------------------------

        # 1. 수정주가 전 기간 수집 (adj_price='0')
        adj_records = fetch_full_history(kis, stk_cd, start_year, adj_price='0')
        # 2. 원본주가 전 기간 수집 (adj_price='1')
        raw_records = fetch_full_history(kis, stk_cd, start_year, adj_price='1')

        if not adj_records or not raw_records:
            logger.debug(f"  [{stk_cd}] 수집 데이터 없음 - 건너뜀")
            return True, None


        # 3. 표준 형식으로 변환 + 날짜순 정렬
        adj_df = pd.DataFrame(utils.transform_data(adj_records, 'kis', 'daily_ohlcv'))
        raw_df = pd.DataFrame(utils.transform_data(raw_records, 'kis', 'daily_ohlcv'))

        if adj_df.empty or raw_df.empty:
            return True

        adj_df = adj_df.sort_values('dt').reset_index(drop=True)
        raw_df = raw_df.sort_values('dt').reset_index(drop=True)

        # 4. 수정/원본 merge → 팩터 계산
        adj_renamed = adj_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'adj_close'})
        raw_renamed = raw_df[['dt', 'cls_prc']].rename(columns={'cls_prc': 'raw_close'})
        merged = pd.merge(adj_renamed, raw_renamed, on='dt', how='inner')

        if merged.empty:
            return True, None

        # 전 기간 adj == raw → 이벤트 없음 → skip (데이터 레벨 판단)
        if (merged['adj_close'] == merged['raw_close']).all():
            logger.debug(f"  [{stk_cd}] 전 기간 adj==raw - 이벤트 없음 skip")
            return True, None

        factors = calculate_factors(merged, stk_cd, PRICE_SOURCE)

        # 5. [팩터 방향 변환] calculate_factors()는 '나누기' 형식(> 1)으로 반환.
        #    USDMS 호환을 위해 '직접 곱하기' 형식(< 1)으로 변환하여 저장.
        #    adj_price = raw_price × factor  (이전: adj_price = raw_price ÷ factor)
        if factors:
            for f in factors:
                ratio = f.get('price_ratio', 0)
                f['price_ratio'] = round(1.0 / ratio, 10) if ratio > 0 else 0.0

        # 6. 검증 (dry_run + do_validate)
        val_result = None
        if do_validate and factors:
            val_result = validate_factors(factors, adj_df, raw_df, stk_cd)

        if dry_run:
            factor_txt = f"{len(factors)}개"
            val_txt    = f"  [검증: {val_result['status']} | 확인날짜 {val_result['checked']}개 | 오류 {val_result['errors']}건]" if val_result else ""
            logger.info(f"  [DRY-RUN] [{stk_cd}] 팩터 {factor_txt} 산출{val_txt}")
            return True, val_result

        # 7. UPSERT
        if factors:
            db.upsert_adjustment_factors(factors, table_name='price_adjustment_factors')
            logger.debug(f"  [{stk_cd}] {len(factors)}개 팩터 UPSERT 완료")

        return True, val_result

    except Exception as e:
        logger.error(f"  [{stk_cd}] 처리 중 오류: {e}", exc_info=False)
        return False, None


def validate_factors(factors: list, adj_df: pd.DataFrame, raw_df: pd.DataFrame,
                     stk_cd: str, tolerance_pct: float = 0.5) -> dict:
    """
    팩터 정확성 검증.
    저장될 팩터(곱셈 방식)로 원본주가를 역산하여 KIS 수정주가와 비교합니다.

    역산 로직 (곱셈 방식):
      reconstructed_adj[d] = raw_close[d] × product(price_ratio | event_dt > d)
    허용 오차: max(tolerance_pct%, 1원) 이내

    Note:
      - 오늘 날짜는 배당락 당일 등 데이터 불완전 가능성으로 검증에서 제외.
      - 전달되는 factors의 price_ratio는 이미 역수(곱셈 방식)로 변환된 값.
    """
    today   = date.today()
    adj_map = dict(zip(adj_df['dt'], adj_df['cls_prc']))
    raw_map = dict(zip(raw_df['dt'], raw_df['cls_prc']))

    factor_events = sorted(factors, key=lambda x: x['event_dt'])
    event_dates   = [f['event_dt'] for f in factor_events]
    event_ratios  = [f['price_ratio'] for f in factor_events]

    errors  = []
    checked = 0

    for dt in sorted(raw_map.keys()):
        # 오늘 날짜 제외: 배당락 당일 등 adj/raw 불일치 가능성 (이벤트 미캡처)
        if hasattr(dt, 'date'):
            dt_date = dt.date()
        else:
            dt_date = dt
        if dt_date >= today:
            continue

        raw_prc     = raw_map.get(dt)
        adj_prc_kis = adj_map.get(dt)
        if raw_prc is None or adj_prc_kis is None or raw_prc == 0:
            continue

        # 곱셈 방식: event_dt > dt 인 팩터들의 누적 곱
        cum_factor = 1.0
        for ed, er in zip(event_dates, event_ratios):
            if ed > dt_date:
                cum_factor *= er

        reconstructed = raw_prc * cum_factor   # ← 곱셈 (구: raw_prc / cum_factor)
        checked += 1

        diff = abs(reconstructed - adj_prc_kis)
        tol  = max(adj_prc_kis * tolerance_pct / 100.0, 1.0)

        if diff > tol:
            errors.append({
                'dt':            str(dt),
                'raw':           int(raw_prc),
                'kis_adj':       int(adj_prc_kis),
                'reconstructed': round(reconstructed, 2),
                'diff':          round(diff, 2),
                'cum_factor':    round(cum_factor, 8),
            })

    return {
        'stk_cd':  stk_cd,
        'status':  'PASS' if not errors else 'FAIL',
        'factors': len(factors),
        'checked': checked,
        'errors':  len(errors),
        'samples': errors[:3],
    }


# ---------------------------------------------------------------------------
# 체크포인트 유틸
# ---------------------------------------------------------------------------
CHECKPOINT_DEFAULT = 'standalone_scripts/.rebuild_checkpoint.json'


def _load_checkpoint(path: str) -> str | None:
    """체크포인트 파일에서 마지막으로 완료된 종목 코드를 반환합니다."""
    import json
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        code = data.get('last_completed')
        logger.info(f"📌 체크포인트 로드: 마지막 완료 종목 = {code} ({path})")
        return code
    except FileNotFoundError:
        logger.warning(f"⚠️  체크포인트 파일 없음: {path} → 처음부터 시작")
        return None
    except Exception as e:
        logger.warning(f"⚠️  체크포인트 로드 실패: {e} → 처음부터 시작")
        return None


def _save_checkpoint(path: str, stk_cd: str) -> None:
    """현재 완료된 종목을 체크포인트 파일에 저장합니다."""
    import json
    try:
        with open(path, 'w') as f:
            json.dump({'last_completed': stk_cd,
                       'timestamp': datetime.now().isoformat()}, f)
    except Exception as e:
        logger.warning(f"체크포인트 저장 실패 ({stk_cd}): {e}")


def main():
    parser = argparse.ArgumentParser(description='KIS 기반 수정계수 전면 재산출 스크립트')
    parser.add_argument('--start_year', type=int, default=2000,
                        help='팩터 재산출 시작 연도 (기본값: 2000)')
    parser.add_argument('--dry_run', action='store_true',
                        help='실제 DB 저장 없이 팩터 산출만 수행 (검증용)')
    parser.add_argument('--delete_kiwoom', action='store_true',
                        help='완료 후 KIWOOM 팩터 삭제 (기본값: False)')
    parser.add_argument('--limit', type=int, default=None,
                        help='처리 종목 수 제한 (기본값: 전체). 예: --limit 100')
    parser.add_argument('--start_from', type=str, default=None,
                        help='지정 종목 코드부터 시작 (해당 코드 포함). 예: --start_from 000660')
    parser.add_argument('--resume', action='store_true',
                        help='체크포인트 파일에서 마지막 완료 종목 다음부터 재개')
    parser.add_argument('--checkpoint_file', type=str, default=CHECKPOINT_DEFAULT,
                        help=f'체크포인트 파일 경로 (기본값: {CHECKPOINT_DEFAULT})')
    parser.add_argument('--validate', action='store_true',
                        help='dry_run 시 팩터 정확성 검증 활성화')
    args = parser.parse_args()

    logger.info(SEPARATOR)
    logger.info(f" KIS 팩터 재산출 시작 (곱셈 방식 저장)")
    logger.info(f"  기간     : {args.start_year}-01-01 ~ 오늘")
    logger.info(f"  DRY-RUN  : {args.dry_run}")
    logger.info(f"  KIWOOM삭제: {args.delete_kiwoom}")
    logger.info(f"  종목 제한 : {args.limit if args.limit else '전체'}")
    logger.info(f"  시작 종목 : {args.start_from or '처음'}")
    logger.info(f"  재개 모드 : {args.resume}")
    logger.info(f"  정확성검증: {args.validate}")
    logger.info(SEPARATOR)

    # --- 초기화 ---
    try:
        kis = KisREST(mock=False, log_level=0)
        db  = DatabaseManager()
    except Exception as e:
        logger.critical(f"초기화 실패: {e}")
        sys.exit(1)

    # --- start_from 결정 ---
    start_from = args.start_from
    if args.resume and not start_from:
        last = _load_checkpoint(args.checkpoint_file)
        if last:
            # 마지막 완료 종목의 '다음' 종목부터 시작
            start_from = f"{last}_NEXT"   # 정렬 기준 다음

    # --- 종목 목록 ---
    all_stocks = db.get_all_stock_codes(active_only=True)

    # start_from 필터 적용
    if start_from:
        if start_from.endswith('_NEXT'):
            pivot = start_from[:-5]
            all_stocks = [s for s in all_stocks if s > pivot]
            logger.info(f"📌 체크포인트 재개: {pivot} 이후 종목부터")
        else:
            all_stocks = [s for s in all_stocks if s >= start_from]
            logger.info(f"📌 --start_from: {start_from}부터 시작")

    if args.limit:
        all_stocks = all_stocks[:args.limit]
        logger.info(f"⚠️  --limit {args.limit} 적용: {len(all_stocks)}개 종목 처리")

    total = len(all_stocks)
    logger.info(f"총 {total}개 종목 처리 시작\n")


    # --- 진행 ---
    success_count  = 0
    error_stocks   = []
    val_results    = []  # 검증 결과 수집
    start_ts       = time.time()

    for idx, stk_cd in enumerate(all_stocks, start=1):
        # 진행률 로그 (100종목마다)
        if idx % 100 == 1 or idx == total:
            elapsed  = time.time() - start_ts
            speed    = idx / elapsed if elapsed > 0 else 0
            eta_sec  = (total - idx) / speed if speed > 0 else 0
            eta_str  = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
            logger.info(
                f"[{idx:4d}/{total}] {stk_cd}  "
                f"({speed:.1f} stk/s, ETA {eta_str}, "
                f"오류 {len(error_stocks)}개)"
            )

        ok = process_stock(kis, db, stk_cd, args.start_year, args.dry_run,
                           do_validate=args.validate)
        ok, val = ok  # unpack tuple
        if ok:
            success_count += 1
            if val:
                val_results.append(val)
            # 체크포인트 저장 (dry_run 제외)
            if not args.dry_run:
                _save_checkpoint(args.checkpoint_file, stk_cd)
        else:
            error_stocks.append(stk_cd)
            if len(error_stocks) >= ERROR_MAX_SKIP:
                logger.critical(f"누적 오류 {ERROR_MAX_SKIP}개 초과. 스크립트 중단.")
                break

    # --- KIWOOM 팩터 삭제 ---
    if args.delete_kiwoom and not args.dry_run:
        logger.info("\nKIWOOM 팩터 삭제 시작...")
        try:
            deleted = db._execute_query(
                "DELETE FROM price_adjustment_factors WHERE price_source = 'KIWOOM';",
                fetch=None
            )
            logger.info("✅ KIWOOM 팩터 삭제 완료")
        except Exception as e:
            logger.error(f"KIWOOM 팩터 삭제 실패: {e}")

    # --- 마일스톤 ---
    if not args.dry_run and len(error_stocks) < ERROR_MAX_SKIP:
        try:
            db.set_milestone(
                'LOGIC:FACTOR_SOURCE:KIS_COMPLETE',
                date.today(),
                f"KIS 기반 수정계수 전면 재산출 완료. "
                f"성공 {success_count}/{total}개, 오류 {len(error_stocks)}개."
            )
        except Exception as e:
            logger.warning(f"마일스톤 기록 실패: {e}")

    # --- 검증 결과 요약 ---
    if val_results:
        passed = [v for v in val_results if v['status'] == 'PASS']
        failed = [v for v in val_results if v['status'] == 'FAIL']
        logger.info(SEPARATOR)
        logger.info(f" 팩터 정확성 검증 결과")
        logger.info(f"  검증 대상  : {len(val_results)}개 종목 (팩터 있는 종목만)")
        logger.info(f"  PASS    : {len(passed)}개")
        logger.info(f"  FAIL    : {len(failed)}개")
        if failed:
            logger.warning(" FAIL 종목 상세:")
            for v in failed:
                logger.warning(
                    f"  [{v['stk_cd']}] 팩터 {v['factors']}개 | "
                    f"확인날짜 {v['checked']}개 | 오류 {v['errors']}건"
                )
                for s in v['samples']:
                    logger.warning(
                        f"    dt={s['dt']} | raw={s['raw']:,} | "
                        f"KIS_adj={s['kis_adj']:,} | "
                        f"역산={s['reconstructed']:,.2f} | "
                        f"diff={s['diff']:.2f} | 누적팩터={s['cum_factor']}"
                    )
        else:
            logger.info("  ✅ 모든 팩터가 KIS 수정주가와 일치합니다.")

    # --- 최종 요약 ---
    elapsed_total = time.time() - start_ts
    logger.info(SEPARATOR)
    logger.info(f" 작업 완료")
    logger.info(f"  성공  : {success_count} / {total}")
    logger.info(f"  오류  : {len(error_stocks)}")
    logger.info(f"  소요  : {time.strftime('%H:%M:%S', time.gmtime(elapsed_total))}")
    if error_stocks:
        logger.info(f"  오류 종목: {error_stocks}")
    logger.info(SEPARATOR)


if __name__ == '__main__':
    main()
