import sys
import logging
from datetime import date
from p3_usdms.repositories.base import BaseRepository

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("IntegrityVerifier")

class IntegrityVerifier(BaseRepository):
    def run_all_checks(self) -> bool:
        logger.info("=== USDMS Data Integrity Audit Starting ===")
        all_passed = True

        # Check 1. 가격-가치평가 레코드 1:1 매칭 누락 검사
        # (가격은 수집되었으나 가치평가 정보가 비어있는 레코드 발견 시 실패, 단 계산 불가한 ETF/CEF/주식수 부재종목 제외)
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_daily_price p
                LEFT JOIN us_daily_valuation v ON p.dt = v.dt AND p.cik = v.cik
                WHERE p.dt >= '2026-05-15' 
                  AND v.cik IS NULL
                  AND EXISTS (SELECT 1 FROM us_standard_financials f WHERE f.cik = p.cik)
                  AND (
                      EXISTS (SELECT 1 FROM us_share_history s WHERE s.cik = p.cik)
                      OR EXISTS (SELECT 1 FROM us_standard_financials f WHERE f.cik = p.cik AND f.shares_outstanding IS NOT NULL)
                  )
            """)
            missing_valuation = cur.fetchone()['cnt']
            if missing_valuation > 0:
                logger.error(f"[FAIL] Check 1: 가격 데이터는 존재하나 가치평가(Valuation) 정보가 매칭되지 않는 레코드가 {missing_valuation}건 발견되었습니다!")
                all_passed = False
            else:
                logger.info("[PASS] Check 1: 신규 적재 가격과 가치평가 데이터 간의 1:1 대칭 매칭 확인 완료.")

        # Check 2. 블랙리스트 차단 정합성 검사
        # (블랙리스트에 차단된 CIK의 신규 가격 데이터가 DB에 삽입되었는지 체크)
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_daily_price p
                JOIN us_collection_blacklist b ON p.cik = b.cik
                WHERE p.dt >= '2026-05-16'
            """)
            blacklist_leak = cur.fetchone()['cnt']
            if blacklist_leak > 0:
                logger.error(f"[FAIL] Check 2: 블랙리스트 종목의 데이터 수집 차단 실패! (유출 적재: {blacklist_leak}건 발견)")
                all_passed = False
            else:
                logger.info("[PASS] Check 2: 블랙리스트 종목에 대한 수집 원천 차단 상태 검증 완료.")

        # Check 3. ADR (외국 주식) 수집 제외 필터 검사
        # (미국 외 국가 종목 중 target 플래그가 잘못 활성화되어 있는지 감사)
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_ticker_master
                WHERE LOWER(TRIM(country)) != 'united states' AND is_collect_target = TRUE
            """)
            adr_leak = cur.fetchone()['cnt']
            if adr_leak > 0:
                logger.error(f"[FAIL] Check 3: ADR 및 외국 종목의 수집 제외 규칙 위반! (수집 타겟에 외국 종목 {adr_leak}건 포함됨)")
                all_passed = False
            else:
                logger.info("[PASS] Check 3: ADR 및 foreign 종목의 타겟 수집 제외 규칙 검증 완료.")

        # Check 4. 데이터 도메인 범위 및 아웃라이어 검사 (가격/거래량)
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_daily_price
                WHERE dt >= '2026-05-15' AND (cls_prc <= 0.0 OR vol < 0)
            """)
            bad_prices = cur.fetchone()['cnt']
            if bad_prices > 0:
                logger.error(f"[FAIL] Check 4: 기형적인 가격(0 이하) 또는 거래량(음수) 레코드가 {bad_prices}건 발견되었습니다!")
                all_passed = False
            else:
                logger.info("[PASS] Check 4: 수집된 가격/거래량 수치 정상 도메인 범위 확인 완료.")

        # Check 5. 가치평가(Valuation/Metrics) 아웃라이어 및 시총 왜곡 검사
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_daily_valuation
                WHERE dt >= '2026-05-15' AND (mkt_cap <= 0.0 OR pe > 100000.0 OR pb > 10000.0)
            """)
            bad_valuations = cur.fetchone()['cnt']
            if bad_valuations > 0:
                logger.warning(f"[WARN] Check 5: 시가총액이 0 이하이거나 PE(10만 초과), PB(1만 초과) 등 비정상 지표가 {bad_valuations}건 검출되었습니다. 정밀 감사가 필요할 수 있습니다.")
            else:
                logger.info("[PASS] Check 5: 시가총액 산출 및 밸류에이션 지표 임계 범위 확인 완료.")

        # Check 6. 수정계수(Factor Value) 비정상 범위 검증
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_price_adjustment_factors
                WHERE event_dt >= '2026-05-15' AND (factor_val <= 0.0 OR factor_val > 100.0)
            """)
            bad_factors = cur.fetchone()['cnt']
            if bad_factors > 0:
                logger.error(f"[FAIL] Check 6: 비정상 범위의 수정 비율(Factor Value)이 {bad_factors}건 존재합니다! (음수 혹은 100배 초과)")
                all_passed = False
            else:
                logger.info("[PASS] Check 6: 적재된 배당/분할 수정계수 비율 상태 검증 완료.")

        # Check 7. 수집 종료일 동적 제한 정합성 검증
        # (미래 시점 혹은 오늘 날짜인 2026-06-03 이후 데이터 오염 적재 유무 판별)
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM us_daily_price
                WHERE dt > '2026-06-02'
            """)
            future_data = cur.fetchone()['cnt']
            if future_data > 0:
                logger.error(f"[FAIL] Check 7: 동적 종료일 제한 오작동! 2026-06-02 이후의 미확정 가격 데이터 {future_data}건이 적재되어 있습니다!")
                all_passed = False
            else:
                logger.info("[PASS] Check 7: 한국 시간 기준 동적 장 마감 판단 및 2026-06-02 수집 최종일 제어 정상 작동 완료.")

        logger.info("=== USDMS Data Integrity Audit Finished ===")
        return all_passed

if __name__ == "__main__":
    verifier = IntegrityVerifier()
    success = verifier.run_all_checks()
    if not success:
        sys.exit(1)
    sys.exit(0)
