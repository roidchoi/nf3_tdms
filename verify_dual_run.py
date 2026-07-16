#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TDMS 1:1 Dual Run 수집 품질 및 무결성 검증 시스템 (고도화 버전)
개발 PC의 수집 최적화 배포본과 서버 PC의 기존 수집본 간의 데이터 적재 정합성을 검증합니다.
"""
import sys
import os
import argparse
import logging
import random
from datetime import datetime, date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("verify_dual_run")

def get_db_connection(dsn: str):
    try:
        return psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Failed to connect to DB with DSN: {dsn}. Error: {e}")
        sys.exit(1)

def is_approx_equal(v1, v2, tolerance=0.01):
    if v1 is None and v2 is None: return True
    if v1 is None or v2 is None: return False
    if v1 == v2: return True
    try:
        f1, f2 = float(v1), float(v2)
        if abs(f1) < 1e-5 and abs(f2) < 1e-5: return True
        return abs(f1 - f2) / max(abs(f1), abs(f2)) < tolerance
    except Exception:
        return False

def compare_table_generic(dev_conn, srv_conn, table_name, pk_cols, compare_cols, 
                          date_col=None, start_dt=None, end_dt=None, mode="deep", tolerance=0.01):
    logger.info(f"--- 테이블 비교: {table_name} ---")
    
    # 1. 건수 비교용 쿼리 작성
    where_clause = ""
    params = []
    if date_col and start_dt and end_dt:
        where_clause = f"WHERE {date_col} BETWEEN %s AND %s"
        params = [start_dt, end_dt]
        
    count_query = f"SELECT COUNT(*) as cnt FROM {table_name} {where_clause}"
    
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(count_query, params)
        dev_cnt = dev_cur.fetchone()['cnt']
        
        srv_cur.execute(count_query, params)
        srv_cnt = srv_cur.fetchone()['cnt']
        
    logger.info(f"[{table_name}] 총 건수 - 개발 PC: {dev_cnt:,}건 | 서버 PC: {srv_cnt:,}건")
    
    if mode == "fast":
        if dev_cnt == srv_cnt:
            logger.info(f"✅ [{table_name}] 행 수가 일치합니다.")
        else:
            logger.warning(f"⚠️ [{table_name}] 행 수가 불일치합니다. (차이: {abs(dev_cnt - srv_cnt):,}건)")
        return
        
    # 2. Deep 모드인 경우 데이터 비교
    select_cols = ", ".join(list(set(pk_cols + compare_cols)))
    if date_col and date_col not in pk_cols and date_col not in compare_cols:
        select_cols += f", {date_col}"
        
    data_query = f"SELECT {select_cols} FROM {table_name} {where_clause}"
    
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(data_query, params)
        dev_rows = dev_cur.fetchall()
        
        srv_cur.execute(data_query, params)
        srv_rows = srv_cur.fetchall()
        
    # PK를 키로 매핑
    def get_pk_key(row):
        return tuple(str(row[c]) for c in pk_cols)
        
    dev_map = {get_pk_key(r): r for r in dev_rows}
    
    # 누락 데이터 비교 (서버에는 있는데 개발에는 없는 것)
    missing_rows = []
    for r in srv_rows:
        key = get_pk_key(r)
        if key not in dev_map:
            missing_rows.append(r)
            
    if missing_rows:
        logger.warning(f"⚠️ [{table_name}] 개발 PC에 누락된 데이터가 존재합니다. (총 {len(missing_rows)}건 중 샘플 10건 표시):")
        for r in missing_rows[:10]:
            pk_info = ", ".join([f"{c}={r[c]}" for c in pk_cols])
            logger.warning(f"  - 누락 PK: {pk_info}")
    else:
        logger.info(f"✅ [{table_name}] 개발 PC에 누락된 데이터가 없습니다.")
        
    # 수치/값 정합성 비교
    mismatches = 0
    for r in srv_rows:
        key = get_pk_key(r)
        if key in dev_map:
            dev_row = dev_map[key]
            row_mismatch = False
            mismatch_details = []
            
            for col in compare_cols:
                v1, v2 = dev_row[col], r[col]
                # 날짜/시간 포맷 통일 처리
                if isinstance(v1, (date, datetime)): v1 = str(v1)
                if isinstance(v2, (date, datetime)): v2 = str(v2)
                
                # 수치형 비교 시 부동소수점 오차 적용
                if not is_approx_equal(v1, v2, tolerance):
                    row_mismatch = True
                    mismatch_details.append(f"{col}: 개발={v1}, 서버={v2}")
                    
            if row_mismatch:
                mismatches += 1
                if mismatches <= 10:
                    pk_info = ", ".join([f"{c}={r[c]}" for c in pk_cols])
                    logger.error(f"❌ [{table_name}] 수치 불일치 발견! PK: {pk_info}")
                    for detail in mismatch_details:
                        logger.error(f"  - {detail}")
                        
    if mismatches > 0:
        logger.error(f"❌ [{table_name}] 정합성 오류: 총 {mismatches}건의 수치 불일치가 검출되었습니다.")
    else:
        logger.info(f"✅ [{table_name}] 적재 데이터 값이 서버 PC와 100% 완벽히 일치합니다.")

def compare_financial_table(dev_conn, srv_conn, table_name, pk_cols, compare_cols, mode="deep", tolerance=0.01):
    logger.info(f"--- 테이블 비교 (최신 수집본 1:1 대조): {table_name} ---")
    
    pk_no_time = [c for c in pk_cols if c != "retrieved_at"]
    partition_by = ", ".join(pk_no_time)
    select_cols = ", ".join(list(set(pk_cols + compare_cols)))
    
    query = f"""
        WITH ranked AS (
            SELECT {select_cols},
                   ROW_NUMBER() OVER (PARTITION BY {partition_by} ORDER BY retrieved_at DESC) as rn
            FROM {table_name}
        )
        SELECT {select_cols}
        FROM ranked
        WHERE rn = 1
    """
    
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(query)
        dev_rows = dev_cur.fetchall()
        
        srv_cur.execute(query)
        srv_rows = srv_cur.fetchall()
        
    logger.info(f"[{table_name}] 최종본 건수 - 개발 PC: {len(dev_rows):,}건 | 서버 PC: {len(srv_rows):,}건")
    
    if mode == "fast":
        if len(dev_rows) == len(srv_rows):
            logger.info(f"✅ [{table_name}] 행 수가 일치합니다.")
        else:
            logger.warning(f"⚠️ [{table_name}] 행 수가 불일치합니다. (차이: {abs(len(dev_rows) - len(srv_rows)):,}건)")
        return
        
    def get_pk_key(row):
        return tuple(str(row[c]) for c in pk_no_time)
        
    dev_map = {get_pk_key(r): r for r in dev_rows}
    
    missing_rows = []
    for r in srv_rows:
        key = get_pk_key(r)
        if key not in dev_map:
            missing_rows.append(r)
            
    if missing_rows:
        logger.warning(f"⚠️ [{table_name}] 개발 PC에 누락된 데이터가 존재합니다. (총 {len(missing_rows)}건 중 샘플 10건 표시):")
        for r in missing_rows[:10]:
            pk_info = ", ".join([f"{c}={r[c]}" for c in pk_no_time])
            logger.warning(f"  - 누락 PK: {pk_info}")
    else:
        logger.info(f"✅ [{table_name}] 개발 PC에 누락된 데이터가 없습니다.")
        
    mismatches = 0
    for r in srv_rows:
        key = get_pk_key(r)
        if key in dev_map:
            dev_row = dev_map[key]
            row_mismatch = False
            mismatch_details = []
            
            for col in compare_cols:
                v1, v2 = dev_row[col], r[col]
                if isinstance(v1, (date, datetime)): v1 = str(v1)
                if isinstance(v2, (date, datetime)): v2 = str(v2)
                
                if not is_approx_equal(v1, v2, tolerance):
                    row_mismatch = True
                    mismatch_details.append(f"{col}: 개발={v1}, 서버={v2}")
                    
            if row_mismatch:
                mismatches += 1
                if mismatches <= 10:
                    pk_info = ", ".join([f"{c}={r[c]}" for c in pk_no_time])
                    logger.error(f"❌ [{table_name}] 수치 불일치 발견! PK: {pk_info}")
                    for detail in mismatch_details:
                        logger.error(f"  - {detail}")
                        
    if mismatches > 0:
        logger.error(f"❌ [{table_name}] 정합성 오류: 총 {mismatches}건의 수치 불일치가 검출되었습니다.")
    else:
        logger.info(f"✅ [{table_name}] 적재 데이터 값이 서버 PC와 100% 완벽히 일치합니다.")

def compare_kdms_minute_ohlcv(dev_conn, srv_conn, start_dt: str, end_dt: str, mode="deep"):
    logger.info("--- 테이블 비교: minute_ohlcv (분봉) ---")
    
    # 1. 행 수 대조
    query_count = "SELECT COUNT(*) as cnt FROM minute_ohlcv WHERE dt_tm >= %s AND dt_tm < %s"
    # start_dt ~ end_dt 범위를 KST 날짜 기준 타임스탬프로 환산
    start_ts = f"{start_dt} 09:00:00+09"
    end_ts = f"{(datetime.strptime(end_dt, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')} 16:00:00+09"
    
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(query_count, (start_ts, end_ts))
        dev_cnt = dev_cur.fetchone()['cnt']
        
        srv_cur.execute(query_count, (start_ts, end_ts))
        srv_cnt = srv_cur.fetchone()['cnt']
        
    logger.info(f"[minute_ohlcv] 총 적재 건수 - 개발 PC: {dev_cnt:,}건 | 서버 PC: {srv_cnt:,}건")
    
    if mode == "fast":
        if dev_cnt == srv_cnt:
            logger.info("✅ [minute_ohlcv] 행 수가 일치합니다.")
        else:
            logger.warning(f"⚠️ [minute_ohlcv] 행 수가 불일치합니다. (차이: {abs(dev_cnt - srv_cnt):,}건)")
        return
        
    # 2. Deep 모드일 경우 대용량이므로 샘플 종목 5개 무작위 대조
    # 양쪽에서 해당 기간 동안 분봉이 존재하는 종목코드를 찾아 교집합에서 무작위 추출
    query_tickers = """
        SELECT DISTINCT stk_cd FROM minute_ohlcv 
        WHERE dt_tm >= %s AND dt_tm < %s 
        LIMIT 100
    """
    with srv_conn.cursor() as srv_cur:
        srv_cur.execute(query_tickers, (start_ts, end_ts))
        srv_tickers = [r['stk_cd'] for r in srv_cur.fetchall()]
        
    with dev_conn.cursor() as dev_cur:
        dev_cur.execute(query_tickers, (start_ts, end_ts))
        dev_tickers = [r['stk_cd'] for r in dev_cur.fetchall()]
        
    common_tickers = list(set(srv_tickers) & set(dev_tickers))
    if not common_tickers:
        logger.warning("⚠️ [minute_ohlcv] 대조할 공통 종목 코드가 존재하지 않습니다.")
        return
        
    sample_tickers = random.sample(common_tickers, min(5, len(common_tickers)))
    logger.info(f"[minute_ohlcv] 무작위 샘플 종목 대조 (샘플: {sample_tickers})")
    
    query_data = """
        SELECT dt_tm, stk_cd, open_prc, high_prc, low_prc, cls_prc, vol 
        FROM minute_ohlcv 
        WHERE dt_tm >= %s AND dt_tm < %s AND stk_cd = %s
    """
    
    mismatches = 0
    for ticker in sample_tickers:
        with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
            dev_cur.execute(query_data, (start_ts, end_ts, ticker))
            dev_rows = dev_cur.fetchall()
            
            srv_cur.execute(query_data, (start_ts, end_ts, ticker))
            srv_rows = srv_cur.fetchall()
            
        dev_map = {r['dt_tm']: r for r in dev_rows}
        
        # 누락 비교
        missing = 0
        for r in srv_rows:
            if r['dt_tm'] not in dev_map:
                missing += 1
        if missing > 0:
            logger.warning(f"  - 종목 {ticker}: 개발 PC에 {missing}건의 분봉 누락 발견")
            
        # 값 비교
        for r in srv_rows:
            if r['dt_tm'] in dev_map:
                dev_row = dev_map[r['dt_tm']]
                if (dev_row['cls_prc'] != r['cls_prc'] or dev_row['vol'] != r['vol']):
                    mismatches += 1
                    if mismatches <= 5:
                        logger.error(f"❌ [minute_ohlcv] 수치 불일치 종목: {ticker} | 시각: {r['dt_tm']}")
                        logger.error(f"  - 개발: 종가 {dev_row['cls_prc']}, 거래량 {dev_row['vol']}")
                        logger.error(f"  - 서버: 종가 {r['cls_prc']}, 거래량 {r['vol']}")
                        
    if mismatches > 0:
        logger.error(f"❌ [minute_ohlcv] 샘플 비교 결과 수치 불일치가 검출되었습니다.")
    else:
        logger.info("✅ [minute_ohlcv] 샘플 종목들의 분봉 수치가 서버 PC와 100% 일치합니다.")

def run_kdms_validation(dev_conn, srv_conn, start_dt, end_dt, mode, target_table):
    logger.info("=========================================")
    logger.info("      KDMS (한국 주식 DB) 교차 검증 시작")
    logger.info("=========================================")
    
    tables_to_run = [
        # (테이블명, pk_cols, compare_cols, date_col)
        ("daily_ohlcv", ["dt", "stk_cd"], ["cls_prc", Vol := "vol"], "dt"),
        ("daily_ohlcv_adjusted", ["dt", "stk_cd"], ["cls_prc", "vol", "adj_factor"], "dt"),
        ("daily_market_cap", ["dt", "stk_cd"], ["cls_prc", "mkt_cap", "vol", "amt", "listed_shares"], "dt"),
        ("stock_info", ["stk_cd"], ["stk_nm", "market_type", "status", "m_vol", "cap"], None),
        ("price_adjustment_factors", ["stk_cd", "event_dt", "price_source"], ["price_ratio", "volume_ratio"], None),
        ("financial_statements", ["stk_cd", "stac_yymm", "div_cls_code", "retrieved_at"], ["total_aset", "bsop_prti", "thtr_ntin"], None),
        ("financial_ratios", ["stk_cd", "stac_yymm", "div_cls_code", "retrieved_at"], ["roe_val", "eps", "bps"], None),
        ("minute_target_history", ["quarter", "market", "symbol"], ["rank", "avg_trade_value"], None),
        ("trading_calendar", ["dt"], ["opnd_yn"], "dt"),
        ("daily_ohlcv_gap", ["stk_cd", "dt"], ["reason"], "dt"),
        ("system_milestones", ["milestone_name"], ["milestone_date", "description"], None)
    ]
    
    # 핀포인트 테이블 필터링
    if target_table and target_table != "all":
        tables_to_run = [t for t in tables_to_run if t[0] == target_table]
        if not tables_to_run and target_table != "minute_ohlcv":
            logger.error(f"지원하지 않거나 존재하지 않는 KDMS 테이블명: {target_table}")
            return
            
    # 일반 테이블 비교 구동
    for t_name, pk, cmp_cols, date_c in tables_to_run:
        if t_name in ["financial_statements", "financial_ratios"]:
            compare_financial_table(dev_conn, srv_conn, t_name, pk, cmp_cols, mode=mode)
        else:
            compare_table_generic(dev_conn, srv_conn, t_name, pk, cmp_cols, date_col=date_c, 
                                  start_dt=start_dt, end_dt=end_dt, mode=mode)
        print()
        
    # minute_ohlcv 테이블은 별도 처리
    if not target_table or target_table in ["all", "minute_ohlcv"]:
        compare_kdms_minute_ohlcv(dev_conn, srv_conn, start_dt, end_dt, mode=mode)
        print()

def run_usdms_validation(dev_conn, srv_conn, start_dt, end_dt, mode, target_table):
    logger.info("=========================================")
    logger.info("     USDMS (미국 주식 DB) 교차 검증 시작")
    logger.info("=========================================")
    
    tables_to_run = [
        # (테이블명, pk_cols, compare_cols, date_col)
        ("us_daily_price", ["dt", "cik"], ["cls_prc", "vol", "amt"], "dt"),
        ("us_daily_valuation", ["dt", "cik"], ["mkt_cap", "pe", "pb"], "dt"),
        ("us_ticker_master", ["cik"], ["latest_ticker", "latest_name", "exchange", "is_collect_target", "is_active"], None),
        ("us_ticker_history", ["cik", "ticker", "start_dt"], ["end_dt"], "start_dt"),
        ("us_price_adjustment_factors", ["cik", "event_dt", "event_type"], ["factor_val"], "event_dt"),
        ("us_standard_financials", ["cik", "report_period", "filed_dt"], ["total_assets", "revenue", "net_income", "ocf", "fcf"], "filed_dt"),
        ("us_share_history", ["cik", "filed_dt"], ["val"], "filed_dt"),
        ("us_financial_metrics", ["cik", "report_period", "filed_dt"], ["roe", "roa", "debt_ratio", "rev_growth_yoy"], "filed_dt"),
        ("us_collection_blacklist", ["cik"], ["ticker", "reason_code", "is_blocked", "fail_count"], None),
        ("trading_calendar", ["dt"], ["opnd_yn"], "dt")
    ]
    
    # us_financial_facts 는 제외 (방대한 로그 방지)
    if target_table == "us_financial_facts":
        logger.warning("⚠️ 'us_financial_facts' 테이블은 고용량 원시 데이터이므로 설계 정책 상 검증 대상에서 제외됩니다.")
        return
        
    # 핀포인트 테이블 필터링
    if target_table and target_table != "all":
        tables_to_run = [t for t in tables_to_run if t[0] == target_table]
        if not tables_to_run:
            logger.error(f"지원하지 않거나 존재하지 않는 USDMS 테이블명: {target_table}")
            return
            
    for t_name, pk, cmp_cols, date_c in tables_to_run:
        compare_table_generic(dev_conn, srv_conn, t_name, pk, cmp_cols, date_col=date_c, 
                              start_dt=start_dt, end_dt=end_dt, mode=mode)
        print()

def main():
    parser = argparse.ArgumentParser(description="TDMS 수집 품질 검증용 1:1 교차 검증 도구 (고도화 버전)")
    parser.add_argument("--dev-kdms-dsn", required=True, help="개발 PC KDMS DB 연결 DSN")
    parser.add_argument("--srv-kdms-dsn", required=True, help="서버 PC KDMS DB 연결 DSN")
    parser.add_argument("--dev-usdms-dsn", required=True, help="개발 PC USDMS DB 연결 DSN")
    parser.add_argument("--srv-usdms-dsn", required=True, help="서버 PC USDMS DB 연결 DSN")
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=7)).strftime('%Y-%m-%d'), help="검증 시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=date.today().strftime('%Y-%m-%d'), help="검증 종료 날짜 (YYYY-MM-DD)")
    parser.add_argument("--mode", default="deep", choices=["fast", "deep"], help="검증 모드 (fast: 행 수 대조, deep: 수치 정밀 대조)")
    parser.add_argument("--market", default="all", choices=["all", "kdms", "usdms"], help="검증 대상 시장")
    parser.add_argument("--table", default="all", help="검증 대상 특정 테이블명 (all: 전체)")
    
    args = parser.parse_args()
    
    logger.info(f"종합 품질 검증 기동 (모드: {args.mode.upper()} | 기간: {args.start_date} ~ {args.end_date})")
    
    # 시장 검증 분기 수행
    if args.market in ["all", "kdms"]:
        dev_kdms_conn = get_db_connection(args.dev_kdms_dsn)
        srv_kdms_conn = get_db_connection(args.srv_kdms_dsn)
        try:
            run_kdms_validation(dev_kdms_conn, srv_kdms_conn, args.start_date, args.end_date, args.mode, args.table)
        finally:
            dev_kdms_conn.close()
            srv_kdms_conn.close()
            
    if args.market in ["all", "usdms"]:
        dev_usdms_conn = get_db_connection(args.dev_usdms_dsn)
        srv_usdms_conn = get_db_connection(args.srv_usdms_dsn)
        try:
            run_usdms_validation(dev_usdms_conn, srv_usdms_conn, args.start_date, args.end_date, args.mode, args.table)
        finally:
            dev_usdms_conn.close()
            srv_usdms_conn.close()
            
    logger.info("모든 품질 검증 프로세스를 완료하고 DB 커넥션을 안전하게 정리합니다.")

if __name__ == "__main__":
    main()
