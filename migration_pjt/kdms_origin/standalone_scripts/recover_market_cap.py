import sys
import os
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any

# 루트 디렉토리 설정
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collectors.krx_loader import KRXLoader
from collectors.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('mkt_cap_recover')

def recover_market_cap(start_date: str, end_date: str):
    db = DatabaseManager()
    
    logger.info("1. FDR을 사용하여 최신 상장주식수 기준 데이터 로드 중...")
    loader = KRXLoader(logger=logger)
    today_str = datetime.now().strftime('%Y%m%d')
    latest_data = loader.get_market_cap_data(today_str)
    
    if not latest_data:
        logger.error("최신 시가총액/상장주식수 데이터를 가져오지 못했습니다.")
        sys.exit(1)
        
    # 종목별 상장주식수 매핑
    shares_map = {row['stk_cd']: row['listed_shares'] for row in latest_data if row['listed_shares']}
    logger.info(f" - 총 {len(shares_map):,}개 종목의 상장주식수 확보 완료")

    logger.info(f"2. {start_date} ~ {end_date} 기간의 daily_ohlcv 데이터 조회 중...")
    query = """
        SELECT dt, stk_cd, cls_prc, vol, amt
        FROM daily_ohlcv
        WHERE dt >= %s AND dt <= %s
    """
    rows = db._execute_query(query, params=(start_date, end_date), fetch='all')
    logger.info(f" - 조회된 과거 OHLCV 데이터: {len(rows):,} 건")

    if not rows:
        logger.warning("조회된 과거 데이터가 없습니다. 날짜를 확인하세요.")
        return

    logger.info("3. 누락된 시장 데이터(시가총액 등) 복원 계산 중...")
    recovery_data = []
    missing_shares = set()
    
    for row in rows:
        stk_cd = row['stk_cd']
        if stk_cd in shares_map:
            listed_shares = shares_map[stk_cd]
            # 상장주식수를 기반으로 시가총액을 역산
            mkt_cap = int(row['cls_prc'] * listed_shares) if row['cls_prc'] else 0
            
            recovery_data.append({
                'dt': row['dt'],
                'stk_cd': stk_cd,
                'cls_prc': row['cls_prc'],
                'mkt_cap': mkt_cap,
                'vol': row['vol'],
                'amt': row['amt'],
                'listed_shares': listed_shares
            })
        else:
            missing_shares.add(stk_cd)
            
    if missing_shares:
        logger.debug(f" - 상장폐지 또는 상장주식수 정보가 없는 종목 수: {len(missing_shares)}개 (복구에서 제외됨)")

    logger.info(f"4. 복구된 {len(recovery_data):,}건의 데이터를 daily_market_cap에 일괄 적재 (UPSERT)...")
    
    if recovery_data:
        # DB Manager의 기존 메서드 재활용
        upserted_count = db.upsert_daily_market_cap(recovery_data)
        logger.info(f"✅ {upserted_count:,}건의 시가총액 데이터 복구 및 적재 완료!")
    else:
        logger.warning("적재할 데이터가 없습니다.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="누락된 daily_market_cap 데이터를 KIS OHLCV 기반으로 복구합니다.")
    parser.add_argument("--start_date", type=str, required=True, help="복구 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end_date", type=str, required=True, help="복구 종료일 (YYYY-MM-DD)")
    args = parser.parse_args()
    
    recover_market_cap(args.start_date, args.end_date)
