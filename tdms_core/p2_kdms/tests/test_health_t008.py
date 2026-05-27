import pytest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app

# routers/health 가 정의하는 의존성 주입 게터 임포트 예정
from routers.health import (
    get_ohlcv_repo,
    get_master_repo,
    get_factor_repo,
    get_financial_repo,
    get_market_cap_repo,
    get_db_pool
)

KST = ZoneInfo("Asia/Seoul")

@pytest.fixture
def client():
    return TestClient(app)

# =================================================================
# A. Freshness 및 Gap 검증 테스트 (TC-01 ~ TC-04)
# =================================================================

def test_health_freshness_green_when_high_coverage(client):
    """
    TC-01: 수집 커버리지가 95% 이상이고 지연이 없는 경우 GREEN 반환 검증
    """
    mock_ohlcv_repo = MagicMock()
    mock_master_repo = MagicMock()
    mock_db_pool = MagicMock()
    
    # 2026-05-26의 listed 종목 = 100개
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": f"{i:06d}"} for i in range(100)]
    
    # 98개 종목 수집 완료
    mock_ohlcv_repo.get_daily_ohlcv_count_for_date.return_value = 98
    mock_ohlcv_repo.get_latest_minute_dt_tm.return_value = datetime.now(KST) - timedelta(minutes=10)
    
    # 달력 mock: 최신 영업일 = 2026-05-26
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [date(2026, 5, 26)]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    
    response = client.get("/api/health/freshness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "GREEN"
    assert body["daily_coverage_ratio"] == 0.98
    assert body["is_daily_fresh"] is True
    
    app.dependency_overrides.clear()

def test_health_freshness_red_when_stale(client):
    """
    TC-02: 수집 데이터가 최신 영업일 대비 1거래일 이상 지연된 경우 RED 반환
    """
    mock_ohlcv_repo = MagicMock()
    mock_master_repo = MagicMock()
    mock_db_pool = MagicMock()
    
    # 2026-05-26 최신 영업일
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": f"{i:06d}"} for i in range(100)]
    
    # 최신 수집 데이터 날짜는 2026-05-22로 2거래일 지연
    # 2026-05-26 기준으로는 수집된 것이 0개이므로 coverage는 0
    mock_ohlcv_repo.get_daily_ohlcv_count_for_date.return_value = 0
    mock_ohlcv_repo.get_latest_minute_dt_tm.return_value = datetime.now(KST) - timedelta(days=4)
    
    mock_cursor = MagicMock()
    # 캘린더에서 최신 2개 영업일 목록 반환: [2026-05-26, 2026-05-25]
    mock_cursor.fetchall.return_value = [(date(2026, 5, 26),), (date(2026, 5, 25),)]
    # 최신 영업일 단건 조회는 2026-05-26
    mock_cursor.fetchone.return_value = [date(2026, 5, 26)]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    
    response = client.get("/api/health/freshness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RED"
    assert body["is_daily_fresh"] is False
    
    app.dependency_overrides.clear()

def test_health_gaps_excludes_suspended_stocks_from_rate(client):
    """
    TC-03: 일봉 상 거래량이 0인 종목을 분봉 누락 모수에서 제외하고 성공률 계산
    """
    mock_ohlcv_repo = MagicMock()
    mock_db_pool = MagicMock()
    
    # 3개 종목 타겟 중 A, B는 381개 분봉 적재 완료
    # C는 분봉 없음, 그러나 일봉 daily_ohlcv.vol == 0 (거래정지)
    mock_ohlcv_repo.get_minute_target_history_for_date.return_value = ["A", "B", "C"]
    
    # mock cursor:
    mock_cursor = MagicMock()
    # 첫번째 쿼리: 캘린더 조회 -> [(date(2026, 5, 26),)]
    # 두번째 쿼리: 각 종목별 분봉 개수 조회 -> (stk_cd, cnt)
    # 세번째 쿼리: 각 종목별 일봉 거래량 조회 -> (stk_cd, vol)
    # 네번째 쿼리: daily_ohlcv_gap 사유 조회 -> (stk_cd, reason)
    mock_cursor.fetchall.side_effect = [
        [(date(2026, 5, 26),)], # 캘린더 조회
        [("A", 381), ("B", 381), ("C", 0)], # 분봉 count
        [("A", 1000), ("B", 2000), ("C", 0)], # 일봉 vol
        [] # 수집 예외 gap 사유
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    
    response = client.get("/api/health/gaps?start_date=2026-05-26&end_date=2026-05-26")
    assert response.status_code == 200
    body = response.json()
    
    # C는 거래정지이므로 미시적 누락 목록에서 제외되어야 하고 성공률은 100%여야 함
    minute_gaps = body["minute_gaps"]
    assert len(minute_gaps) == 1
    assert "C" not in minute_gaps[0]["missing_stocks"]
    assert minute_gaps[0]["valid_collection_rate"] == 100.0
    
    app.dependency_overrides.clear()

def test_health_gaps_warning_when_rate_under_98(client):
    """
    TC-04: 수집 성공률이 95% 이상 98% 미만인 경우 WARNING 등급 및 누락 목록 제공
    """
    mock_ohlcv_repo = MagicMock()
    mock_db_pool = MagicMock()
    
    # 타겟 종목 100개
    targets = [f"{i:06d}" for i in range(100)]
    mock_ohlcv_repo.get_minute_target_history_for_date.return_value = targets
    
    # 97개 정상 수집, 3개 누락 (거래정지 아님, 거래량 > 0)
    cnt_rows = [(targets[i], 381) for i in range(97)] + [(targets[i], 0) for i in range(97, 100)]
    vol_rows = [(targets[i], 1000) for i in range(100)]
    
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [
        [(date(2026, 5, 26),)], # 캘린더 조회
        cnt_rows,
        vol_rows,
        [] # gap 사유 없음
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    app.dependency_overrides[get_ohlcv_repo] = lambda: mock_ohlcv_repo
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    
    response = client.get("/api/health/gaps?start_date=2026-05-26&end_date=2026-05-26")
    assert response.status_code == 200
    body = response.json()
    
    minute_gaps = body["minute_gaps"]
    assert len(minute_gaps) == 1
    assert minute_gaps[0]["valid_collection_rate"] == 97.0
    assert minute_gaps[0]["missing_stocks_count"] == 3
    assert set(minute_gaps[0]["missing_stocks"]) == set(targets[97:100])
    
    app.dependency_overrides.clear()

# =================================================================
# B. 수정주가 및 정합성 테스트 (TC-05 ~ TC-09)
# =================================================================

def test_integrity_adjusted_price_mismatch_detection(client):
    """
    TC-05: 물리 수정주가와 팩터 역산 공식 결과가 불일치하는 경우 검출 확인
    """
    mock_db_pool = MagicMock()
    mock_cursor = MagicMock()
    
    # 1건의 불일치 데이터 반환하도록 mock 설정
    # daily_ohlcv.cls_prc = 10000, adj_factor = 0.5 이면 기대값은 5000인데, actual_adjusted_close = 5500 인 상황
    mock_cursor.fetchall.side_effect = [
        [("005930", date(2026, 5, 26), 10000, 0.5, 5500)], # adjusted mismatch
        [], # price limit violation
        [], # market cap mismatch
        []  # financial ratios mismatch
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_master_repo = MagicMock()
    mock_master_repo.get_ipo_dates.return_value = {}
    
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    
    response = client.get("/api/health/integrity")
    assert response.status_code == 200
    body = response.json()
    
    assert body["status"] == "RED"
    assert body["adjusted_price_mismatch_count"] == 1
    assert body["adjusted_price_mismatches"][0]["stk_cd"] == "005930"
    assert body["adjusted_price_mismatches"][0]["expected"] == 5000.0
    assert body["adjusted_price_mismatches"][0]["actual"] == 5500.0
    
    app.dependency_overrides.clear()

def test_integrity_price_limit_violation_over_30_percent(client):
    """
    TC-06: 일별 변동폭이 30%를 초과하는 종목이 수정주가에 적재된 경우 이상 검출
    """
    mock_db_pool = MagicMock()
    mock_cursor = MagicMock()
    
    # daily_ohlcv_adjusted 에서 전일 종가 10000 대비 당일 종가 13500 (35% 상승)
    # 첫번째 fetchall: adjusted mismatch (정상) -> []
    # 두번째 fetchall: price limit violation -> [("000020", date(2026, 5, 20), 10000, 13500)]
    mock_cursor.fetchall.side_effect = [
        [], # adjusted mismatch 없음
        [("000020", date(2026, 5, 20), 10000, 13500)], # limit violation 1건
        [], # market cap mismatch 없음
        [] # financial ratio mismatch 없음
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_master_repo = MagicMock()
    mock_master_repo.get_ipo_dates.return_value = {}
    
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    
    response = client.get("/api/health/integrity")
    assert response.status_code == 200
    body = response.json()
    
    assert body["status"] == "RED"
    assert body["price_limit_violations_count"] == 1
    assert body["price_limit_violations"][0]["stk_cd"] == "000020"
    # 등락률 계산: (13500 - 10000) / 10000 * 100 = 35.0%
    assert abs(body["price_limit_violations"][0]["change_rate"] - 35.0) < 0.1
    
    app.dependency_overrides.clear()

def test_integrity_price_limit_excludes_ipo_listing_date(client):
    """
    TC-07: 최초 상장일(IPO) 당일의 변동률은 30% 초과하더라도 검출에서 제외
    """
    mock_db_pool = MagicMock()
    mock_cursor = MagicMock()
    
    # 000020 종목의 최초 상장일(list_dt)이 2026-05-26이고, 등락폭 초과일도 2026-05-26인 상황
    # 이 경우 상장일 당일 변동이므로 이상치 검출에서 제외되어야 함
    mock_cursor.fetchall.side_effect = [
        [], # adjusted mismatch 없음
        [("000020", date(2026, 5, 26), 10000, 15000)], # 상장일 당일 50% 폭등
        [], # market cap mismatch 없음
        [] # financial ratio mismatch 없음
    ]
    # list_dt 쿼리 모의화: 상장일이 2026-05-26 임을 반환하도록 설정
    # list_dt 가 2026-05-26 인지 매칭하는 내부 필터링 로직이 있음
    # DB 쿼리 파라미터나 내부 로직 상 stock_info 와 JOIN 하여 list_dt 가 event_dt 인 것은 쿼리에서 이미 필터링하거나
    # Python 코드에서 필터링함. 여기서는 Python 코드 필터링용으로 stock_info list_dt 딕셔너리 리턴 등을 모의화
    
    # DB 쿼리에서 `WHERE event_dt != list_dt` 와 같이 거르거나, Python에서 거른다고 가정.
    # mock_cursor가 실행될 때 list_dt가 반환되도록 설정하거나, list_dt와 dt가 같은 레코드는 쿼리 자체에서 제외되므로 fetchall.side_effect 의 두번째 리스트는 빈 리스트가 됨.
    # 테스트 코드가 DB 쿼리의 IPO 필터 논리를 통과시키도록, list_dt == dt 인 경우 fetchall 결과에서 제외되거나 Python 단에서 걸러지도록 작성.
    # 여기서는 Python 단에서 걸러지는 상황을 테스트하기 위해, master_repo.get_ipo_dates.return_value = {"000020": date(2026, 5, 26)} 와 같이 mock을 제공하고
    # fetchall에서는 리턴되었으나 list_dt와 일치하여 제외되어 violations_count가 0이 되는 것을 검증함.
    
    mock_master_repo = MagicMock()
    mock_master_repo.get_ipo_dates.return_value = {"000020": date(2026, 5, 26)}
    
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    
    response = client.get("/api/health/integrity")
    assert response.status_code == 200
    body = response.json()
    
    # 50% 변동이 상장일 당일이므로 제외되어 violations_count 가 0이어야 함
    assert body["price_limit_violations_count"] == 0
    assert body["status"] == "GREEN"
    
    app.dependency_overrides.clear()

def test_integrity_market_cap_close_mismatch(client):
    """
    TC-08: daily_ohlcv의 종가와 daily_market_cap의 종가가 불일치하는 종목 검출
    """
    mock_db_pool = MagicMock()
    mock_cursor = MagicMock()
    
    # 005930 종목에 대해 daily_ohlcv.close = 70000, daily_market_cap.cls_prc = 70500 불일치 반환
    mock_cursor.fetchall.side_effect = [
        [], # adjusted mismatch 없음
        [], # limit violation 없음
        [("005930", date(2026, 5, 26), 70000, 70500)], # market cap mismatch 1건
        [] # financial ratio mismatch 없음
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_master_repo = MagicMock()
    mock_master_repo.get_ipo_dates.return_value = {}
    
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    
    response = client.get("/api/health/integrity")
    assert response.status_code == 200
    body = response.json()
    
    assert body["status"] == "RED"
    assert body["market_cap_mismatch_count"] == 1
    assert body["market_cap_mismatches"][0]["stk_cd"] == "005930"
    assert body["market_cap_mismatches"][0]["ohlcv_close"] == 70000
    assert body["market_cap_mismatches"][0]["mkt_cap_close"] == 70500
    
    app.dependency_overrides.clear()

def test_integrity_financials_missing_ratios_mismatch(client):
    """
    TC-09: 재무제표는 있는데 재무비율이 없는 적재 불완전 감지
    """
    mock_db_pool = MagicMock()
    mock_cursor = MagicMock()
    
    # financial_statements 는 있으나 financial_ratios 가 없는 005930 (202512 결산분)
    mock_cursor.fetchall.side_effect = [
        [], # adjusted mismatch 없음
        [], # limit violation 없음
        [], # market cap mismatch 없음
        [("005930", "202512", "1", "Ratios missing")] # financial ratio mismatch 1건
    ]
    mock_db_pool.get_cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_master_repo = MagicMock()
    mock_master_repo.get_ipo_dates.return_value = {}
    
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo
    
    response = client.get("/api/health/integrity")
    assert response.status_code == 200
    body = response.json()
    
    assert body["status"] == "RED"
    assert body["financial_ratio_mismatch_count"] == 1
    assert body["financial_ratio_mismatches"][0]["stk_cd"] == "005930"
    assert body["financial_ratio_mismatches"][0]["stac_yymm"] == "202512"
    
    app.dependency_overrides.clear()
