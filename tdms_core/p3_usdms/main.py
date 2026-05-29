from contextlib import asynccontextmanager
from fastapi import FastAPI
from p1_shared.ops.startup_validator import StartupValidator
from p3_usdms.repositories.base import BaseRepository
from p3_usdms.config import get_settings

# USDMS 필수 테이블 정의 (실제 us_ 스키마 테이블 매칭)
USDMS_EXPECTED_TABLES = [
    "us_ticker_master", "us_daily_price", "us_daily_valuation", "us_financial_facts",
    "us_financial_metrics", "us_price_adjustment_factors", "us_share_history",
    "us_standard_financials", "us_ticker_history", "us_collection_blacklist"
]

USDMS_MIN_ROW_COUNTS = {
    "us_daily_price": 100_000  # 로컬 검증 수준 (실제 13,969,437 rows 존재)
}

# 테스트용 Mock/생성 제어 함수 (test_fastapi_lifespan_executes_startup_sequence 에서 사용됨)
def create_kdms_pool():
    """테스트 모킹 호환을 위한 헬퍼 함수"""
    repo = BaseRepository()
    return repo._pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DSN 기반 DB 커넥션 풀 기동
    pool = create_kdms_pool()
    app.state.pool = pool
    
    # 2. StartupValidator 기동 유효성 검증
    # 볼륨 검증 건너뛰기( exists = True 고정 )를 위해 backup_manager=None 으로 호출
    validator = StartupValidator(pool, backup_manager=None)
    report = validator.validate(
        db_name="usdms",
        expected_tables=USDMS_EXPECTED_TABLES,
        min_row_counts=USDMS_MIN_ROW_COUNTS
    )
    
    if not report.is_healthy:
        raise RuntimeError(f"USDMS DB 기동 검증 실패: {report.missing_tables} / {report.low_row_tables}")
        
    yield
    
    # 3. 종료 시 커넥션 정리
    if pool:
        pool.close_all()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message": "USDMS API is running"}
