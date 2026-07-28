import pytest
from unittest.mock import Mock, MagicMock, ANY
from fastapi import FastAPI
from fastapi.testclient import TestClient

def test_daily_routine_health_check_isolates_and_rolls_back_anomalies(mocker):
    """
    [목적] Step 5 Health Check 실행 시 가격 이상치가 검증되면 당일 오염 데이터를 격리(삭제 롤백)하는지 검증.
    [유도] PRICE_SPIKE(50% 초과) 감지 시, 해당 CIK의 당일 가격 레코드를 테이블에서 DELETE 처리하는 로직 유도.
    """
    mock_db = mocker.MagicMock()
    
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.side_effect = [
        [{"cik": "0000320193", "today_prc": 200.0, "yesterday_prc": 100.0}], # 가격 검사
    ]
    mock_db.get_cursor.return_value.__enter__.return_value = mock_cursor

    from p3_usdms.tasks.daily_routine import DailyRoutine
    from datetime import date
    mock_blacklist_mgr = mocker.MagicMock()
    routine = DailyRoutine(
        master_repo=mock_db,
        blacklist_repo=mocker.MagicMock(),
        blacklist_mgr=mock_blacklist_mgr
    )
    
    # Anomaly Detection 및 롤백 실행
    anomalies = routine._detect_price_anomalies(date.today())
    
    assert len(anomalies) == 1
    assert anomalies[0]["type"] == "PRICE_SPIKE"
    assert anomalies[0]["ticker"] == "0000320193"
    
    # 롤백 SQL 호출 여부 검증
    delete_called = False
    for call in mock_cursor.execute.call_args_list:
        query_str = call[0][0].upper()
        if "DELETE FROM US_DAILY_PRICE" in query_str and "0000320193" in str(call[0][1]):
            delete_called = True
            break
    assert delete_called is True



@pytest.mark.asyncio
async def test_daily_routine_continues_on_step_failure(mocker):
    """
    [목적] 특정 Step이 FAILED 되더라도, 예외가 차단되어 다음 수집 Step이 정상 수행되는지 검증.
    [유도] Step 1 실행 시 강제 Exception을 발생시켰을 때, Step 2의 실행 메서드가 여전히 호출되는지 검증.
    """
    from p3_usdms.tasks.daily_routine import DailyRoutine
    routine = DailyRoutine(
        master_repo=mocker.MagicMock(),
        blacklist_repo=mocker.MagicMock(),
        blacklist_mgr=mocker.MagicMock()
    )
    
    # Step 1 (MasterSync) 강제 실패 설정
    mock_master = mocker.Mock()
    mock_master.sync_daily.side_effect = Exception("SEC Connection Failed")
    routine.master = mock_master
    
    # Step 2 (MarketDataLoader) 호출 확인용
    mock_loader = mocker.Mock()
    routine.market_loader = mock_loader
    
    # 기타 Step 모킹 처리하여 통과
    routine.fin_parser = mocker.Mock()
    routine.metric_calc = mocker.Mock()
    routine.val_calc = mocker.Mock()
    routine.db = mocker.Mock()
    routine._detect_anomalies_and_quarantine = mocker.Mock(return_value=[])
    routine._save_report = mocker.Mock()
    
    # 실행
    report = await routine.run()
    
    # Step 1은 실패
    step1 = next(s for s in report["steps"] if s["step"] == "Master Sync")
    assert step1["status"] == "FAILED"
    
    # Step 2는 정상적으로 호출 시도되어야 함
    mock_loader.collect_daily_updates.assert_called_once()


def test_daily_routine_manual_run_prevents_concurrency_conflict(mocker):
    """
    [목적] 이미 daily_routine이 구동 중일 때, 수동 실행 엔드포인트 `/api/admin/tasks/daily_routine/run`을 추가 요청하면 409 Conflict를 반환하는지 검증.
    [유도] 실행 잠금 장치(Lock) 상태일 때 API 동작 유도.
    """
    from p3_usdms.routers.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router)
    
    # 일일 루틴의 실행 상태를 나타내는 Lock 모킹
    mocker.patch("p3_usdms.routers.admin.is_routine_running", return_value=True)
    
    client = TestClient(app)
    response = client.post("/api/admin/tasks/daily_routine/run")
    
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


@pytest.mark.asyncio
async def test_financial_routine_uses_valuation_bulk_cache_and_disables_self_healing(mocker):
    """
    [목적] UsFinancialRoutine.run() 실행 시, CIK별 최신 가치평가 날짜를 벌크 캐시(get_all_latest_valuation_dates)하여
           calculate_and_save_bulk에 정상 연동하는지 검증.
    """
    from p3_usdms.tasks.us_financial_routine import UsFinancialRoutine
    from datetime import date
    
    routine = UsFinancialRoutine(
        master_repo=mocker.Mock(),
        blacklist_repo=mocker.Mock(),
        blacklist_mgr=mocker.Mock()
    )
    
    # dependencies 모킹
    routine.sec_client = mocker.Mock()
    routine.fetch_master_idx = mocker.Mock(return_value=[])
    routine.fin_parser = mocker.Mock()
    routine.fin_parser.run.return_value = (2, ["0000320193", "00000660"])
    
    # 밸류에이션 계산 모듈 및 리포지토리 모킹
    routine.val_calc = mocker.Mock()
    routine.val_calc.repo = mocker.Mock()
    
    # 2개 CIK에 대한 최신 날짜 벌크 리턴 설정
    mock_cache = {"0000320193": date(2026, 5, 13), "00000660": date(2026, 5, 12)}
    routine.val_calc.repo.get_all_latest_valuation_dates.return_value = mock_cache
    
    routine.metric_calc = mocker.Mock()
    
    # collect_targets 설정
    routine.master_repo = mocker.Mock()
    routine.master_repo.get_collect_targets.return_value = [
        {"cik": "0000320193"}, {"cik": "00000660"}
    ]
    routine.db = routine.master_repo
    routine.blacklist_mgr = mocker.Mock()
    routine.blacklist_mgr.is_blacklisted.return_value = False
    
    # anomaly detection 및 report 스킵
    routine._detect_valuation_anomalies = mocker.Mock(return_value=[])
    routine._save_report = mocker.Mock()
    
    # 실행
    await routine.run(target_date=date(2026, 5, 14), force_all=True)
    
    # assert get_all_latest_valuation_dates 가 올바르게 호출됨
    routine.val_calc.repo.get_all_latest_valuation_dates.assert_called_once_with(["0000320193", "00000660"])
    
    # calculate_and_save_bulk 에 캐시가 정상 주입됨을 확인
    routine.val_calc.calculate_and_save_bulk.assert_called_once_with(
        ["0000320193", "00000660"],
        rebuild=False,
        chunk_size=100,
        latest_val_dates_cache=mock_cache
    )



@pytest.mark.integration
def test_blacklist_repository_with_real_db(real_pool):
    """
    [목적] 실제 데이터베이스(real_pool)를 기동한 상태에서 BlacklistRepo의 CRUD 연동이 정상적으로 트랜잭션을 통해 영속화되는지 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    from p3_usdms.repositories.blacklist_repo import BlacklistRepo
    
    # real_pool을 master_repo 등에 주입하여 테스트
    repo = BlacklistRepo()
    # pool이 정상 기입되도록 로컬 pool 교체 지원 (테스트 목적)
    repo._pool = real_pool
    
    test_cik = "9999912345"
    
    # 1. 초기 상태 해제
    repo.release_blacklist(test_cik, admin_note="Test Init")
    assert repo.is_blocked(test_cik) is False
    
    # 2. 블랙리스트 등록
    repo.add_blacklist(test_cik, "TEST_403", reason_detail="Integration Test Block", ticker="TEST")
    assert repo.is_blocked(test_cik) is True
    
    # 3. 릴리즈 및 확인
    repo.release_blacklist(test_cik, admin_note="Test Release")
    assert repo.is_blocked(test_cik) is False




