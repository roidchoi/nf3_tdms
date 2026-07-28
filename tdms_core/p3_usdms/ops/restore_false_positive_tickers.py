#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
오탐으로 비활성화(is_active=FALSE) 처리된 XOM 등 우량 종목 복구 스크립트
"""
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("restore_false_positive_tickers")

DEV_USDMS_DSN = "postgresql://postgres:pjsr104edml511@127.0.0.1:5433/usdms_db"
SRV_USDMS_DSN = "postgresql://postgres:pjsr104edml511@192.168.35.176:5433/usdms_db"

def main():
    logger.info("Starting restoration of false positive delisted tickers...")
    
    dev_conn = psycopg2.connect(DEV_USDMS_DSN, cursor_factory=RealDictCursor)
    srv_conn = psycopg2.connect(SRV_USDMS_DSN, cursor_factory=RealDictCursor)
    
    try:
        with dev_conn.cursor() as dev_cur, srv_conn.cursor() as srv_cur:
            # 1. 서버 PC에서 active이고 target인 CIK 목록 조회
            srv_cur.execute("""
                SELECT cik, latest_ticker, latest_name, exchange, is_collect_target
                FROM us_ticker_master
                WHERE is_active = TRUE
            """)
            srv_active_map = {r['cik']: r for r in srv_cur.fetchall()}
            
            # 2. 개발 PC에서 inactive 처리된 CIK 중 서버 PC에서 active인 대상을 추출
            dev_cur.execute("""
                SELECT cik, latest_ticker, latest_name, exchange, is_active, is_collect_target
                FROM us_ticker_master
                WHERE is_active = FALSE
            """)
            dev_inactive_rows = dev_cur.fetchall()
            
            restore_targets = []
            for r in dev_inactive_rows:
                cik = r['cik']
                if cik in srv_active_map:
                    srv_info = srv_active_map[cik]
                    restore_targets.append({
                        'cik': cik,
                        'ticker': srv_info['latest_ticker'],
                        'name': srv_info['latest_name'],
                        'exchange': srv_info['exchange'],
                        'is_collect_target': srv_info['is_collect_target']
                    })
                    
            logger.info(f"Identified {len(restore_targets)} false positive delisted CIKs to restore.")
            
            if not restore_targets:
                logger.info("No tickers to restore. Exiting.")
                return
                
            # 3. 개발 PC DB 복구 갱신 수행
            for item in restore_targets:
                cik = item['cik']
                target_flag = item['is_collect_target']
                
                # master 테이블 복구
                dev_cur.execute("""
                    UPDATE us_ticker_master
                    SET is_active = TRUE,
                        is_collect_target = %s,
                        updated_at = NOW()
                    WHERE cik = %s
                """, (target_flag, cik))
                
                # history 테이블 end_dt '9999-12-31'로 복원
                dev_cur.execute("""
                    UPDATE us_ticker_history
                    SET end_dt = '9999-12-31'
                    WHERE cik = %s AND end_dt = CURRENT_DATE
                """, (cik,))
                
                logger.info(f"Restored CIK {cik} ({item['ticker']}): active=True, target={target_flag}")
                
            dev_conn.commit()
            logger.info(f"Successfully restored {len(restore_targets)} tickers in Dev DB.")
            
    finally:
        dev_conn.close()
        srv_conn.close()

if __name__ == "__main__":
    main()
