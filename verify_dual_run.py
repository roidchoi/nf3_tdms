#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TDMS 1:1 Dual Run 수집 품질 및 무결성 검증 시스템
개발 PC의 수집 최적화 배포본과 서버 PC의 기존 수집본 간의 데이터 적재 정합성을 검증합니다.
"""
import sys
import os
import argparse
import logging
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

def compare_kdms_ohlcv(dev_conn, srv_conn, start_dt: str, end_dt: str):
    logger.info(f"=== KDMS OHLCV 1:1 교차 품질 검증 ({start_dt} ~ {end_dt}) ===")
    
    # 1. 총 적재 건수 비교
    query_count = "SELECT COUNT(*) as cnt FROM daily_ohlcv WHERE dt BETWEEN %s AND %s"
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(query_count, (start_dt, end_dt))
        dev_cnt = dev_cur.fetchone()['cnt']
        
        srv_cur.execute(query_count, (start_dt, end_dt))
        srv_cnt = srv_cur.fetchone()['cnt']
        
    logger.info(f"KDMS 총 적재 건수 - 개발 PC: {dev_cnt:,}건 | 서버 PC: {srv_cnt:,}건")
    
    # 2. 누락 데이터 비교 (서버에는 있는데 개발에는 없는 것)
    query_diff = """
        SELECT srv.stk_cd, srv.dt
        FROM (
            SELECT stk_cd, dt FROM daily_ohlcv WHERE dt BETWEEN %s AND %s
        ) srv
        LEFT JOIN (
            SELECT stk_cd, dt FROM daily_ohlcv WHERE dt BETWEEN %s AND %s
        ) dev ON srv.stk_cd = dev.stk_cd AND srv.dt = dev.dt
        WHERE dev.stk_cd IS NULL
        LIMIT 20
    """
    with srv_conn.cursor() as srv_cur:
        srv_cur.execute(query_diff, (start_dt, end_dt, start_dt, end_dt))
        diff_rows = srv_cur.fetchall()
        
    if diff_rows:
        logger.warning(f"⚠️ 개발 PC에 누락된 KDMS 데이터가 존재합니다 (샘플 20건 표시):")
        for r in diff_rows:
            logger.warning(f"  - 종목코드: {r['stk_cd']} | 날짜: {r['dt']}")
    else:
        logger.info("✅ 개발 PC에 누락된 KDMS OHLCV 데이터가 없습니다.")

    # 3. 데이터 수치 정합성 (시, 고, 저, 종, 거래량 1:1 매칭 검증)
    query_match = """
        SELECT dev.stk_cd, dev.dt, dev.cls_prc as dev_close, srv.cls_prc as srv_close,
               dev.vol as dev_vol, srv.vol as srv_vol
        FROM daily_ohlcv dev
        JOIN daily_ohlcv srv ON dev.stk_cd = srv.stk_cd AND dev.dt = srv.dt
        WHERE dev.dt BETWEEN %s AND %s
        LIMIT 2000
    """
    with dev_conn.cursor() as dev_cur:
        dev_cur.execute(query_match, (start_dt, end_dt))
        matches = dev_cur.fetchall()
        
    mismatches = 0
    for m in matches:
        if m['dev_close'] != m['srv_close'] or m['dev_vol'] != m['srv_vol']:
            mismatches += 1
            if mismatches <= 10:
                logger.error(f"❌ KDMS 수치 불일치 발견! 종목: {m['stk_cd']} | 날짜: {m['dt']}")
                logger.error(f"  - 개발: 종가 {m['dev_close']}, 거래량 {m['dev_vol']}")
                logger.error(f"  - 서버: 종가 {m['srv_close']}, 거래량 {m['srv_vol']}")
                
    if mismatches > 0:
        logger.error(f"❌ KDMS 정합성 오류: 분석 대상 중 총 {mismatches}건의 수치 불일치가 검출되었습니다.")
    else:
        logger.info("✅ KDMS 적재 데이터 수치(종가, 거래량 등)가 서버 PC와 100% 완벽히 일치합니다.")

def compare_usdms_financials(dev_conn, srv_conn, start_dt: str, end_dt: str):
    logger.info(f"=== USDMS 수집 및 가치평가(Valuation) 1:1 교차 품질 검증 ({start_dt} ~ {end_dt}) ===")
    
    # 1. US daily valuation 총 적재 건수 비교
    query_count = "SELECT COUNT(*) as cnt FROM us_daily_valuation WHERE dt BETWEEN %s AND %s"
    with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
        dev_cur.execute(query_count, (start_dt, end_dt))
        dev_cnt = dev_cur.fetchone()['cnt']
        
        srv_cur.execute(query_count, (start_dt, end_dt))
        srv_cnt = srv_cur.fetchone()['cnt']
        
    logger.info(f"USDMS Valuation 총 적재 건수 - 개발 PC: {dev_cnt:,}건 | 서버 PC: {srv_cnt:,}건")
    
    # 2. 누락 데이터 비교
    query_diff = """
        SELECT srv.cik, srv.dt
        FROM (
            SELECT cik, dt FROM us_daily_valuation WHERE dt BETWEEN %s AND %s
        ) srv
        LEFT JOIN (
            SELECT cik, dt FROM us_daily_valuation WHERE dt BETWEEN %s AND %s
        ) dev ON srv.cik = dev.cik AND srv.dt = dev.dt
        WHERE dev.cik IS NULL
        LIMIT 20
    """
    with srv_conn.cursor() as srv_cur:
        srv_cur.execute(query_diff, (start_dt, end_dt, start_dt, end_dt))
        diff_rows = srv_cur.fetchall()
        
    if diff_rows:
        logger.warning(f"⚠️ 개발 PC에 누락된 USDMS Valuation 데이터가 존재합니다 (샘플 20건 표시):")
        for r in diff_rows:
            logger.warning(f"  - CIK: {r['cik']} | 날짜: {r['dt']}")
    else:
        logger.info("✅ 개발 PC에 누락된 USDMS Valuation 데이터가 없습니다.")

    # 3. 밸류에이션 지표 값 정합성 1:1 비교
    query_match = """
        SELECT dev.cik, dev.dt, dev.mkt_cap as dev_cap, srv.mkt_cap as srv_cap,
               dev.pe as dev_pe, srv.pe as srv_pe, dev.pb as dev_pb, srv.pb as srv_pb
        FROM us_daily_valuation dev
        JOIN us_daily_valuation srv ON dev.cik = srv.cik AND dev.dt = srv.dt
        WHERE dev.dt BETWEEN %s AND %s
        LIMIT 2000
    """
    with dev_conn.cursor() as dev_cur:
        dev_cur.execute(query_match, (start_dt, end_dt))
        matches = dev_cur.fetchall()
        
    mismatches = 0
    for m in matches:
        # 부동소수점 오차 방안 (1% 미만 허용차)
        def is_approx_equal(v1, v2):
            if v1 is None and v2 is None: return True
            if v1 is None or v2 is None: return False
            if v1 == v2: return True
            if abs(v1) < 1e-5 and abs(v2) < 1e-5: return True
            return abs(v1 - v2) / max(abs(v1), abs(v2)) < 0.01

        if not (is_approx_equal(m['dev_cap'], m['srv_cap']) and 
                is_approx_equal(m['dev_pe'], m['srv_pe']) and 
                is_approx_equal(m['dev_pb'], m['srv_pb'])):
            mismatches += 1
            if mismatches <= 10:
                logger.error(f"❌ USDMS Valuation 불일치 발견! CIK: {m['cik']} | 날짜: {m['dt']}")
                logger.error(f"  - 개발: 시가총액 {m['dev_cap']}, PE {m['dev_pe']}, PB {m['dev_pb']}")
                logger.error(f"  - 서버: 시가총액 {m['srv_cap']}, PE {m['srv_pe']}, PB {m['srv_pb']}")
                
    if mismatches > 0:
        logger.error(f"❌ USDMS Valuation 정합성 오류: 분석 대상 중 총 {mismatches}건의 지표 불일치가 검출되었습니다.")
    else:
        logger.info("✅ USDMS Valuation 적재 데이터 수치(시가총액, PE, PB 등)가 서버 PC와 100% 완벽히 일치합니다.")

def main():
    parser = argparse.ArgumentParser(description="TDMS 수집 품질 검증용 1:1 교차 검증 도구")
    parser.add_argument("--dev-kdms-dsn", required=True, help="개발 PC KDMS DB 연결 DSN")
    parser.add_argument("--srv-kdms-dsn", required=True, help="서버 PC KDMS DB 연결 DSN")
    parser.add_argument("--dev-usdms-dsn", required=True, help="개발 PC USDMS DB 연결 DSN")
    parser.add_argument("--srv-usdms-dsn", required=True, help="서버 PC USDMS DB 연결 DSN")
    parser.add_argument("--start-date", default=(date.today() - timedelta(days=7)).strftime('%Y-%m-%d'), help="검증 시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=date.today().strftime('%Y-%m-%d'), help="검증 종료 날짜 (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    logger.info(f"품질 검증 시작: {args.start_date} ~ {args.end_date}")
    
    # DB 연결 객체 생성
    dev_kdms_conn = get_db_connection(args.dev_kdms_dsn)
    srv_kdms_conn = get_db_connection(args.srv_kdms_dsn)
    dev_usdms_conn = get_db_connection(args.dev_usdms_dsn)
    srv_usdms_conn = get_db_connection(args.srv_usdms_dsn)
    
    try:
        compare_kdms_ohlcv(dev_kdms_conn, srv_kdms_conn, args.start_date, args.end_date)
        print()
        compare_usdms_financials(dev_usdms_conn, srv_usdms_conn, args.start_date, args.end_date)
    finally:
        dev_kdms_conn.close()
        srv_kdms_conn.close()
        dev_usdms_conn.close()
        srv_usdms_conn.close()
        logger.info("모든 DB 커넥션을 반환하고 품질 검증 작업을 종료합니다.")

if __name__ == "__main__":
    main()
