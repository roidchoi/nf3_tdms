import pytest
from unittest.mock import Mock, ANY

@pytest.mark.asyncio
async def test_master_enricher_filters_adr_and_excludes_from_collect(mocker):
    """
    [목적] yfinance 조회 결과 국가가 'United States'가 아니면 수집 대상(is_collect_target)에서 제외됨을 검증.
    [유도] yfinance Ticker info.country = 'United Kingdom'인 경우 is_collect_target=False를 update_metadata에 전달해야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_missing_enrichment_targets.return_value = [
        {"cik": "0001000000", "latest_ticker": "BP"}
    ]
    
    # yfinance Mock
    mock_ticker = mocker.Mock()
    mock_ticker.info = {"country": "United Kingdom", "sector": "Energy", "industry": "Oil & Gas", "quoteType": "EQUITY"}
    mocker.patch("yfinance.Ticker", return_value=mock_ticker)
    
    mock_bl = mocker.Mock()
    mock_bl.is_blacklisted.return_value = False
    
    from p3_usdms.collectors.master_enricher import MasterEnricher
    enricher = MasterEnricher(master_repo=mock_repo, blacklist_mgr=mock_bl)
    await enricher.run_enrichment(limit=1)
    
    mock_repo.update_metadata.assert_called_once_with(
        "0001000000", "United Kingdom", "Energy", "Oil & Gas", False
    )


@pytest.mark.asyncio
async def test_master_enricher_handles_rate_limit_without_blacklisting(mocker):
    """
    [목적] yfinance가 HTTP 429(Rate Limit) 등의 일시적인 오류 로그를 기록할 때 블랙리스트 등록을 스킵하고 스킵 상태를 유지하는지 검증.
    [유도] yfinance 로깅 또는 리턴 결과에 'Rate limit' 단어가 들어 있을 때 record_failure에서 CIK를 차단 처리하지 말아야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_missing_enrichment_targets.return_value = [
        {"cik": "0000320193", "latest_ticker": "AAPL"}
    ]
    
    mock_bl = mocker.Mock()
    mock_bl.is_blacklisted.return_value = False
    
    # yfinance 호출 시 Exception (429 Too Many Requests) 발생 모사
    mocker.patch("yfinance.Ticker", side_effect=Exception("HTTP Error 429: Too Many Requests"))
    
    from p3_usdms.collectors.master_enricher import MasterEnricher
    enricher = MasterEnricher(master_repo=mock_repo, blacklist_mgr=mock_bl)
    await enricher.run_enrichment(limit=1)
    
    # blacklisted 처리가 되지 않아야 함 (즉, 영구 차단 add_blacklist가 아닌 일시적 기록만)
    mock_bl.record_failure.assert_called_once_with(
        "0000320193", "RATE_LIMIT", detail=ANY, ticker="AAPL"
    )
