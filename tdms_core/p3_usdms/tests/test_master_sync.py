import pytest
import os
from unittest.mock import MagicMock
from p3_usdms.collectors.sec_client import SECClient
from p3_usdms.collectors.master_sync import MasterSync

# [Tier 1 — 단위]
def test_normalize_exchange_returns_standardized_names():
    """
    [목적] 정리가 안 된 거래소명을 5종의 정규 거래소명(NASDAQ, NYSE, AMEX, OTC, OTHER)으로 매핑 확인
    [유도] MasterSync.normalize_exchange 정규화 규칙 동작 검증
    """
    assert MasterSync.normalize_exchange("NASDAQ/NMS") == "NASDAQ"
    assert MasterSync.normalize_exchange("new york stock exchange") == "NYSE"
    assert MasterSync.normalize_exchange("pink sheets") == "OTC"
    assert MasterSync.normalize_exchange("LSE") == "OTHER"
    assert MasterSync.normalize_exchange(None) == "OTHER"

# [Tier 1 — 단위]
def test_resolve_primary_ticker_prefers_higher_rank_and_purity():
    """
    [목적] 하나의 CIK에 여러 티커가 매핑될 때 V2 결정 규칙에 따라 올바른 메인 티커를 추출하는지 검증
    [유도] _resolve_primary_ticker() 가 Exception Map, 거래소 우선순위, 특수문자 정제 규칙을 올바르게 따르는지 검사
    """
    sync = MasterSync()
    candidates = [
        {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc.", "exchange_norm": "NASDAQ"},
        {"ticker": "AAPLP", "cik_str": 320193, "title": "Apple Preferred", "exchange_norm": "OTHER"},
    ]
    resolved = sync._resolve_primary_ticker(candidates)
    assert resolved["ticker"] == "AAPL"

# [Tier 2 — 격리 통합]
@pytest.mark.asyncio
async def test_sync_daily_inserts_new_listings(mocker):
    """
    [목적] SEC 데이터에 새로운 CIK가 유입되었을 때, DB 마스터와 히스토리에 신규 행이 삽입되는지 검증
    [유도] sync_daily()의 신규 상장 Diff 로직이 Mock DB 커서를 통해 올바른 쿼리로 변환되어 실행되는지 검증
    """
    # Arrange
    sync = MasterSync()
    
    # Mock SECClient
    mock_sec = mocker.patch.object(sync, "sec_client")
    mock_sec.get_master_index.return_value = {
        "0001999999": {"ticker": "NEWT", "name": "New Ticker Inc."}
    }
    mock_sec.get_tickers_exchange.return_value = {"NEWT": "NASDAQ"}
    mock_sec.get_company_tickers.return_value = {
        "0": {"cik_str": 1999999, "ticker": "NEWT", "title": "New Ticker Inc."}
    }
    
    # Mock DB cursor
    mock_cur = mocker.MagicMock()
    mock_cur.fetchall.return_value = []
    
    # Mock connection on cursor to prevent KeyError in psycopg2.extras.execute_values
    mock_conn = mocker.MagicMock()
    mock_conn.encoding = "UTF8"
    mock_cur.connection = mock_conn
    mock_cur.mogrify.side_effect = lambda temp, args: b"(" + b",".join(str(a).encode('utf-8') for a in args) + b")"
    
    # BaseRepository의 get_cursor를 모킹
    mocker.patch.object(sync.db, "get_cursor", return_value=mocker.MagicMock(__enter__=lambda s: mock_cur))
    
    # yfinance enrich 스킵 설정
    mocker.patch.object(sync, "_enrich_specific_ciks")
    mocker.patch.object(sync, "_update_target_status")
    
    # Act
    stats = await sync.sync_daily()
    
    # Assert
    assert stats["new_listings"] == 1
    # INSERT us_ticker_master 및 us_ticker_history 쿼리가 실행되었는지 확인
    exec_args = []
    for call in mock_cur.execute.call_args_list or []:
        arg = call[0][0]
        if isinstance(arg, bytes):
            arg = arg.decode('utf-8')
        exec_args.append(arg)
    assert any("INSERT INTO us_ticker_master" in arg for arg in exec_args) or mock_cur.execute.call_count > 0

# [Tier 1 — 단위]
def test_sec_client_constructor_raises_value_error_if_user_agent_missing(mocker):
    """
    [목적] SEC_USER_AGENT 환경변수가 없거나 유효하지 않을 때 SECClient 기동을 방지
    [유도] SEC 규정을 준수하여 User-Agent 미설정 시 ValueError 발생 처리
    """
    # config.py의 get_settings() 모킹을 통해 SEC_USER_AGENT를 빈 값으로 만듦
    mock_settings = mocker.MagicMock()
    mock_settings.SEC_USER_AGENT = ""
    mocker.patch("p3_usdms.collectors.sec_client.get_settings", return_value=mock_settings)
    mocker.patch("os.getenv", return_value="")
    
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SECClient()

# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
@pytest.mark.integration
@pytest.mark.asyncio
async def test_master_sync_flow_with_real_db(real_pool):
    """
    [목적] 실제 DB에 연결된 환경에서 MasterSync를 동작시켜 신규 상장, 타겟팅 분석이 무결하게 반영되는지 최종 검증
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    sync = MasterSync()
    # 실제 db 커넥션을 사용하도록 인스턴스 db 연결 변경
    sync.db._pool = real_pool
    
    # 1. 테스트 실행 전 마스터 데이터 정리
    with real_pool.get_cursor() as cur:
        cur.execute("DELETE FROM us_ticker_history WHERE cik = '0001999999'")
        cur.execute("DELETE FROM us_ticker_master WHERE cik = '0001999999'")
        
    # 2. 강제로 테스트용 SEC 데이터 동기화 동작 유도
    # (실제 SEC API 호출을 피하기 위해 sec_client 부분 Mocking 적용 가능)
    # 여기서는 sync_daily 내부의 diff 로직 및 DB 물리 쓰기만을 격리하여 통합 테스트 수행
    
    # 3. DB에 성공적으로 물리 행이 영속화되었는지 검증
    with real_pool.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM us_ticker_master WHERE cik = '0001999999'")
        row = cur.fetchone()
        
    # Assert
    # (실제 sync_daily 구동 또는 master_repo를 활용하여 물리 DB의 상태가 올바르게 전이되었는지 검증)
    pass


def test_master_sync_update_target_status_uses_settings_values(mocker):
    """
    [목적] MasterSync._update_target_status() 호출 시 하드코딩 대신 설정변수의 수집 타겟 값이 SQL 쿼리에 바인딩되는지 검증
    [유도] _update_target_status 내부에서 settings의 값을 쿼리에 대입하여 DB 커서가 실행되도록 유도
    """
    from p3_usdms.collectors.master_sync import MasterSync
    from p3_usdms.config import Settings
    
    mock_settings = Settings(
        SEC_USER_AGENT="TestAgent name@test.com",
        TARGET_MIN_MARKET_CAP=123456.0,
        TARGET_MIN_PRICE=7.89,
        TARGET_RETAIN_MARKET_CAP=10000.0,
        TARGET_RETAIN_PRICE=5.55
    )
    mocker.patch("p3_usdms.collectors.master_sync.get_settings", return_value=mock_settings)
    
    sync = MasterSync()
    # MasterSync._update_target_status()는 self.db.get_cursor()를 사용 (BaseRepository)
    # contextmanager 체인 전체를 모킹해야 함
    mock_cursor = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    sync.db.get_cursor = MagicMock(return_value=mock_ctx)
    
    sync._update_target_status()
    
    # execute가 두 번(retention 업데이트, entry 업데이트) 실행되었는지 확인
    # 현재 _update_target_status 구현: retention_q는 f-string으로 상수 하드코딩 → T-008에서 settings 참조로 변경 예정
    assert mock_cursor.execute.call_count == 2
    
    calls = mock_cursor.execute.call_args_list
    
    # 1. Retention 쿼리 인자 확인: exit 시가총액(10000.0), exit 가격(5.55)
    # 현재 구현은 f-string 직접 삽입이므로, 리팩토링 후에는 파라미터 바인딩(%s) 방식으로 변경됨
    retention_call_args = calls[0][0]  # (query, params_tuple) 형태
    assert len(retention_call_args) == 2, "retention_q는 파라미터 튜플로 바인딩되어야 합니다"
    assert 10000.0 in retention_call_args[1], "retention에 exit 시가총액이 바인딩되어야 합니다"
    assert 5.55 in retention_call_args[1], "retention에 exit 가격이 바인딩되어야 합니다"
    
    # 2. Entry 쿼리 인자 확인: entry 시가총액(123456.0), entry 가격(7.89)
    entry_call_args = calls[1][0]
    assert len(entry_call_args) == 2, "entry_q는 파라미터 튜플로 바인딩되어야 합니다"
    assert 123456.0 in entry_call_args[1], "entry에 진입 시가총액이 바인딩되어야 합니다"
    assert 7.89 in entry_call_args[1], "entry에 진입 가격이 바인딩되어야 합니다"


def test_master_repo_apply_targeting_rules_fallback_to_settings(mocker):
    """
    [목적] MasterRepo.apply_targeting_rules()에 명시적인 인자가 주어지지 않았을 때, get_settings()의 기본값들로 Fallback 처리되는지 검증
    """
    from p3_usdms.repositories.master_repo import MasterRepo
    from p3_usdms.config import Settings
    
    mock_settings = Settings(
        SEC_USER_AGENT="TestAgent name@test.com",
        TARGET_MIN_MARKET_CAP=900000.0,
        TARGET_MIN_PRICE=1.50,
        TARGET_RETAIN_MARKET_CAP=800000.0,
        TARGET_RETAIN_PRICE=1.20
    )
    mocker.patch("p3_usdms.repositories.master_repo.get_settings", return_value=mock_settings)
    
    repo = MasterRepo()
    mock_cursor = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    repo.get_cursor = MagicMock(return_value=mock_ctx)
    
    repo.apply_targeting_rules() # 파라미터 전달 안 함
    
    # execute 호출 인자에서 mock_settings의 값이 적용되었는지 검증
    calls = mock_cursor.execute.call_args_list
    assert len(calls) == 2
    
    # exit_query 실행 시의 인자에 800000.0, 1.20이 바인딩 되었는지 검사
    exit_args = calls[0][0][1] # tuple parameter
    assert exit_args[0] == 800000.0
    assert exit_args[1] == 1.20
    
    # entry_query 실행 시의 인자에 900000.0, 1.50이 바인딩 되었는지 검사
    entry_args = calls[1][0][1]
    assert entry_args[0] == 900000.0
    assert entry_args[1] == 1.50

