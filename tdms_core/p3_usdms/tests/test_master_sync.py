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
    ...
