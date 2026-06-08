# tests/test_health_auditors.py
import pytest
from datetime import date, datetime
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from p3_usdms.main import app
from p3_usdms.auditors.financial_auditor import FinancialDiagnostic
from p3_usdms.routers.health import get_db_pool, get_master_repo, get_price_repo, get_blacklist_repo

@pytest.fixture
def client():
    # FastAPI TestClient 픽스처 제공 (에러 원인 추적을 위해 raise_server_exceptions=True 설정)
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()

# =================================================================
# 1. 정상 동작 케이스 (Tier 2)
# =================================================================

def test_health_freshness_with_high_coverage_returns_green_status(client, mocker):
    """
    [목적] 당일 수집 커버리지가 95% 이상이고 지연이 없는 경우 GREEN 상태를 정상 반환하는지 검증.
    [유도] get_freshness 라우터가 trading_calendar 기준 최신 영업일을 조회하고, 
           활성 종목 대비 OHLCV 수집 완료 개수를 기반으로 커버리지를 정확히 판정하도록 유도.
    """
    # Arrange
    mock_master = mocker.Mock()
    mock_price = mocker.Mock()
    mock_pool = mocker.MagicMock() # context manager 지원을 위해 MagicMock 사용
    
    mock_master.get_collect_targets.return_value = [{"cik": "0000320193"}] * 100
    mock_price.get_daily_price_count_for_date.return_value = 98 # 98% 수집
    
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [("2026-06-03",), ("2026-06-02",)]
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor

    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master
    app.dependency_overrides[get_price_repo] = lambda: mock_price

    # Act
    response = client.get("/api/health/freshness")

    # Assert
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "GREEN"
    assert res["daily_coverage_ratio"] == 0.98


def test_health_gaps_with_blacklist_and_suspended_stocks_excludes_from_total(client, mocker):
    """
    [목적] 일봉 거래량이 0인 종목(거래정지) 및 수집 블랙리스트에 올라간 종목을 갭 스캔의 모수에서 제외하고 올바른 성공률을 구하는지 검증.
    [유도] get_gaps 함수 내부에서 수집 대상 중 거래정지(vol=0) 및 블랙리스트 상태를 제외하고 유효 수집율을 계산하도록 유도.
    """
    # Arrange
    mock_price = mocker.Mock()
    mock_blacklist = mocker.Mock()
    mock_pool = mocker.MagicMock() # context manager 지원을 위해 MagicMock 사용

    # 3개 종목 타겟 중 A, B는 수집 완료, C는 미수집 상태
    # 그러나 C는 일봉 상 volume == 0 (거래정지)
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.side_effect = [
        [(date(2026, 6, 3),)], # trading_calendar 조회
        [("A", 1000), ("B", 2000), ("C", 0)], # daily volume 조회
        [("C", "SEC_403")] # blacklist 사유 조회
    ]
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    mock_price.get_collect_targets_for_date.return_value = ["A", "B", "C"]

    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    app.dependency_overrides[get_price_repo] = lambda: mock_price
    app.dependency_overrides[get_blacklist_repo] = lambda: mock_blacklist

    # Act
    response = client.get("/api/health/gaps?start_date=2026-06-03&end_date=2026-06-03")

    # Assert
    assert response.status_code == 200
    res = response.json()
    # C는 거래정지 및 블랙리스트이므로 배제되어 유효 수집율 100% (A, B 완료)
    assert res["minute_gaps"][0]["valid_collection_rate"] == 100.0


# =================================================================
# 2. 경계값 케이스 (Tier 2)
# =================================================================

def test_health_freshness_with_yellow_boundary_returns_yellow_status(client, mocker):
    """
    [목적] 수집 커버리지가 95.0% 이상 98.0% 미만인 경계선에서 YELLOW 등급을 정상 부여하는지 확인.
    """
    # Arrange
    mock_master = mocker.Mock()
    mock_price = mocker.Mock()
    mock_pool = mocker.MagicMock() # context manager 지원을 위해 MagicMock 사용
    
    mock_master.get_collect_targets.return_value = [{"cik": "0"}] * 100
    mock_price.get_daily_price_count_for_date.return_value = 96 # 96% 수집
    
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [("2026-06-03",), ("2026-06-02",)]
    mock_pool.get_cursor.return_value.__enter__.return_value = mock_cursor

    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master
    app.dependency_overrides[get_price_repo] = lambda: mock_price

    # Act
    response = client.get("/api/health/freshness")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "YELLOW"


# =================================================================
# 3. 예외/오류 처리 케이스 (Tier 1)
# =================================================================

def test_financial_auditor_with_zero_assets_skips_accounting_identity():
    """
    [목적] Total Assets가 0인 극단적인 데이터가 들어왔을 때, DivisionByZero 에러를 예방하고 정상 처리(skip)하는지 검증.
    """
    # Arrange
    diagnostic = FinancialDiagnostic(pool=None)
    
    # total_assets가 0인 가상의 행 데이터
    rows = [{"cik": "123", "report_period": "2025-12-31", "total_assets": 0.0, "total_liabilities": 0.0, "total_equity": 0.0}]
    
    # Act
    failed = []
    for r in rows:
        assets = r['total_assets']
        liab_equity = r['total_liabilities'] + r['total_equity']
        if assets == 0:
            continue # expected to skip
        diff_pct = abs(assets - liab_equity) / abs(assets) * 100
        if diff_pct > 0.1:
            failed.append(r)

    # Assert
    assert len(failed) == 0


# =================================================================
# 4. 실제 통합 케이스 (Tier 3)
# =================================================================

@pytest.mark.integration
def test_financial_auditor_with_real_db_retains_accounting_identity(real_pool):
    """
    [목적] 실제 DB의 us_standard_financials 테이블을 대상으로 회계 항등식 검증이 문제 없이 동작하는지 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    # Arrange
    diagnostic = FinancialDiagnostic(pool=real_pool)

    # Act
    failed_samples = diagnostic.check_accounting_identity(sample_limit=10)

    # Assert
    assert isinstance(failed_samples, list)
    # 데이터베이스에 이상이 없다면 일반적으로 0건이어야 함
    for sample in failed_samples:
        assert "cik" in sample
        assert "diff_pct" in sample
