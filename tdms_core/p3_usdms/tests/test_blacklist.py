import pytest
from unittest.mock import Mock, ANY

def test_blacklist_manager_records_failure_and_blocks_on_threshold(mocker):
    """
    [목적] BlacklistManager가 실패 횟수를 누적시키고, 임계치에 도달하면 CIK를 차단 상태로 변경하는지 검증.
    [유도] threshold가 3으로 주어졌을 때, 3번째 record_failure가 호출되면 is_blocked=True 상태가 되어야 함.
    """
    mock_repo = mocker.Mock()
    mock_repo.is_blocked.return_value = False
    
    # fail_count 상태를 모방하기 위한 state
    fail_counts = {}
    def inc_fail(cik, reason_code, ticker=None):
        fail_counts[cik] = fail_counts.get(cik, 0) + 1
    def add_bl(cik, reason_code, reason_detail=None, ticker=None):
        pass
    def get_fail(cik):
        return fail_counts.get(cik, 0)
        
    mock_repo.increment_fail_count.side_effect = inc_fail
    mock_repo.add_blacklist.side_effect = add_bl
    mock_repo.get_fail_count.side_effect = get_fail
    
    from p3_usdms.utils.blacklist_manager import BlacklistManager
    mgr = BlacklistManager(repo=mock_repo)
    
    # 2번의 일시적 오류 발생 기록 (임계치 3)
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    
    mock_repo.increment_fail_count.assert_called()
    assert fail_counts["0000320193"] == 2
    mock_repo.add_blacklist.assert_not_called()
    
    # 3번째 실패 기록 -> add_blacklist가 호출되어 영구 차단으로 전환되어야 함
    mgr.record_failure("0000320193", "RATE_LIMIT", threshold=3)
    mock_repo.add_blacklist.assert_called_once_with("0000320193", "RATE_LIMIT", mocker.ANY, None)


def test_blacklist_manager_auto_release_with_zero_expired_records(mocker):
    """
    [목적] 자동 차단 해제 기한이 지난 레코드가 없을 때, 에러 없이 0을 반환하는가 검증.
    """
    mock_repo = mocker.Mock()
    mock_repo.get_auto_release_candidates.return_value = []
    
    from p3_usdms.utils.blacklist_manager import BlacklistManager
    mgr = BlacklistManager(repo=mock_repo)
    released_count = mgr.auto_release_expired_blocks(cool_off_days=7)
    
    assert released_count == 0
    mock_repo.release_blacklist.assert_not_called()
