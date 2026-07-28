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


@pytest.mark.integration
def test_blacklist_cooldown_integration(real_pool):
    """
    [목적] 누적 실패 기반의 쿨다운 유예(1일, 7일, 30일, 60일, 영구 제외)에 대해 
          실제 DB(us_collection_blacklist) 테이블을 대상으로 한 트랜잭션 흐름을 통합 검증.
    """
    from p3_usdms.repositories.blacklist_repo import BlacklistRepo
    repo = BlacklistRepo(pool=real_pool)
    
    test_cik = "9999999999"
    test_ticker = "TEST"
    
    # 0. 클린업
    with repo.get_cursor() as cur:
        cur.execute("DELETE FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
    
    try:
        # 1. 1회차 차단 (re_blocked_count = 0)
        repo.add_blacklist(test_cik, "RATE_LIMIT", "1st fail", test_ticker)
        
        with repo.get_cursor() as cur:
            cur.execute("SELECT is_blocked, fail_count, re_blocked_count, is_permanently_blocked FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
            row = cur.fetchone()
            assert row["is_blocked"] is True
            assert row["re_blocked_count"] == 0
            assert row["is_permanently_blocked"] is False
            
        # 1-1. 1일 경과 후 자동 해제 후보군 포함 여부 확인 (last_failed_at 강제 변경)
        with repo.get_cursor() as cur:
            cur.execute("UPDATE us_collection_blacklist SET last_failed_at = NOW() - INTERVAL '2 days' WHERE cik = %s", (test_cik,))
        
        candidates = repo.get_auto_release_candidates()
        ciks = [c["cik"] for c in candidates]
        assert test_cik in ciks
        
        # 1-2. 자동 해제 실행 (re_blocked_count 유지)
        repo.release_blacklist(test_cik, "1st Auto Release", reset_counters=False)
        with repo.get_cursor() as cur:
            cur.execute("SELECT is_blocked, re_blocked_count FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
            row = cur.fetchone()
            assert row["is_blocked"] is False
            assert row["re_blocked_count"] == 0
            
        # 2. 2회차 차단 (re_blocked_count = 1)
        repo.add_blacklist(test_cik, "RATE_LIMIT", "2nd fail", test_ticker)
        with repo.get_cursor() as cur:
            cur.execute("SELECT is_blocked, re_blocked_count, is_permanently_blocked FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
            row = cur.fetchone()
            assert row["is_blocked"] is True
            assert row["re_blocked_count"] == 1
            assert row["is_permanently_blocked"] is False
            
        # 2-1. 2일만 경과 시 7일 쿨다운 미달로 자동 해제 후보에서 제외 검증
        with repo.get_cursor() as cur:
            cur.execute("UPDATE us_collection_blacklist SET last_failed_at = NOW() - INTERVAL '2 days' WHERE cik = %s", (test_cik,))
        candidates = repo.get_auto_release_candidates()
        ciks = [c["cik"] for c in candidates]
        assert test_cik not in ciks
        
        # 2-2. 8일 경과 시 7일 쿨다운 통과로 자동 해제 후보 포함 검증
        with repo.get_cursor() as cur:
            cur.execute("UPDATE us_collection_blacklist SET last_failed_at = NOW() - INTERVAL '8 days' WHERE cik = %s", (test_cik,))
        candidates = repo.get_auto_release_candidates()
        ciks = [c["cik"] for c in candidates]
        assert test_cik in ciks
        
        # 2-3. 자동 해제 실행
        repo.release_blacklist(test_cik, "2nd Auto Release", reset_counters=False)
        
        # 3. 3회차 차단 (re_blocked_count = 2)
        repo.add_blacklist(test_cik, "RATE_LIMIT", "3rd fail", test_ticker)
        # 3-1. 자동 해제
        repo.release_blacklist(test_cik, "3rd Auto Release", reset_counters=False)
        
        # 4. 4회차 차단 (re_blocked_count = 3)
        repo.add_blacklist(test_cik, "RATE_LIMIT", "4th fail", test_ticker)
        # 4-1. 자동 해제
        repo.release_blacklist(test_cik, "4th Auto Release", reset_counters=False)
        
        # 5. 5회차 차단 (re_blocked_count = 4 -> 영구 제외)
        repo.add_blacklist(test_cik, "RATE_LIMIT", "5th fail", test_ticker)
        with repo.get_cursor() as cur:
            cur.execute("SELECT is_blocked, re_blocked_count, is_permanently_blocked FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
            row = cur.fetchone()
            assert row["is_blocked"] is True
            assert row["re_blocked_count"] == 4
            assert row["is_permanently_blocked"] is True
            
        # 5-1. 100일이 지나도 자동 해제 후보에서 영구 제외됨을 검증
        with repo.get_cursor() as cur:
            cur.execute("UPDATE us_collection_blacklist SET last_failed_at = NOW() - INTERVAL '100 days' WHERE cik = %s", (test_cik,))
        candidates = repo.get_auto_release_candidates()
        ciks = [c["cik"] for c in candidates]
        assert test_cik not in ciks
        
        # 6. 수동 해제 시 완전 리셋 검증
        repo.release_blacklist(test_cik, "Manual Master Release", reset_counters=True)
        with repo.get_cursor() as cur:
            cur.execute("SELECT is_blocked, fail_count, re_blocked_count, is_permanently_blocked FROM us_collection_blacklist WHERE cik = %s", (test_cik,))
            row = cur.fetchone()
            assert row["is_blocked"] is False
            assert row["fail_count"] == 0
            assert row["re_blocked_count"] == 0
            assert row["is_permanently_blocked"] is False
            
    finally:
        # 클린업
        with repo.get_cursor() as cur:
            cur.execute("DELETE FROM us_collection_blacklist WHERE cik = %s", (test_cik,))

