# test_utils.py
"""
테스트 환경 관리 유틸리티
- 테스트용 임시 테이블 생성/삭제
- 테스트 데이터 준비
- 데이터 오염 시뮬레이션
"""

import logging
from datetime import date, timedelta
from typing import List
from collectors.db_manager import DatabaseManager

# 테스트 설정
TEST_SUFFIX = '_test'
TEST_STOCKS = ['005930', '035720']  # 삼성전자, 카카오

class TestEnvironment:
    """테스트 환경을 관리하는 클래스"""
    
    def __init__(self, db: DatabaseManager, logger: logging.Logger):
        self.db = db
        self.logger = logger
        self.test_suffix = TEST_SUFFIX
        self.test_stocks = TEST_STOCKS
    
    def setup_test_tables(self):
        """테스트용 임시 테이블 생성"""
        self.logger.info("🧪 테스트용 임시 테이블 생성 중...")
        try:
            self.db.setup_test_tables(suffix=self.test_suffix)
            self.logger.info("✅ 테스트 테이블 생성 완료")
        except Exception as e:
            self.logger.error(f"테스트 테이블 생성 실패: {e}", exc_info=True)
            raise
    
    def cleanup_test_tables(self):
        """테스트용 임시 테이블 삭제"""
        self.logger.info("🧹 테스트용 임시 테이블 삭제 중...")
        try:
            self.db.cleanup_test_tables(suffix=self.test_suffix)
            self.logger.info("✅ 테스트 테이블 삭제 완료")
        except Exception as e:
            self.logger.error(f"테스트 테이블 삭제 실패: {e}", exc_info=True)
            raise
    
    def get_test_table_name(self, base_table: str) -> str:
        """테스트 테이블명 반환"""
        return f"{base_table}{self.test_suffix}"
    
    def filter_test_stocks(self, stock_list: List[dict]) -> List[dict]:
        """테스트 대상 종목만 필터링"""
        return [s for s in stock_list if s.get('stk_cd') in self.test_stocks]
    
    def simulate_data_corruption(self):
        """데이터 오염 시뮬레이션 (테스트 검증용)"""
        self.logger.info("🧪 데이터 오염 시뮬레이션 시작...")
        try:
            t_minus_3_dt = date.today() - timedelta(days=3)
            
            # 가짜 팩터 삽입 (DELETE 검증용)
            fake_factor = {
                'stk_cd': '005930',
                'event_dt': t_minus_3_dt,
                'price_ratio': 99.0,
                'volume_ratio': 1/99.0,
                'price_source': 'KIWOOM_TEST',
                'details': '{"reason": "Fake factor for DELETE test"}'
            }
            
            self.db.upsert_adjustment_factors(
                [fake_factor], 
                table_name=self.get_test_table_name('price_adjustment_factors')
            )
            
            self.logger.info("✅ 데이터 오염 시뮬레이션 완료")
        except Exception as e:
            self.logger.error(f"데이터 오염 시뮬레이션 실패: {e}", exc_info=True)
            raise


def cleanup_all_test_tables():
    """
    [독립 실행 함수] 모든 테스트 테이블 일괄 삭제
    
    Usage:
        python test_utils.py
    """
    from collectors import utils
    logger = utils.setup_logger('test_cleanup')
    db = DatabaseManager()
    
    logger.info("=" * 60)
    logger.info("🧹 테스트 테이블 일괄 정리 시작")
    logger.info("=" * 60)
    
    try:
        test_env = TestEnvironment(db, logger)
        test_env.cleanup_test_tables()
        logger.info("✅ 모든 테스트 테이블이 성공적으로 삭제되었습니다.")
    except Exception as e:
        logger.critical("테스트 테이블 정리 실패", exc_info=True)
        raise


if __name__ == '__main__':
    # 스크립트 직접 실행 시 테스트 테이블 정리
    cleanup_all_test_tables()