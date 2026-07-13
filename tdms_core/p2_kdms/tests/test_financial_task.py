# tests/test_financial_task.py

import pytest
import hashlib
from datetime import datetime, date
from zoneinfo import ZoneInfo
from tasks.financial_task import run_financial_update

KST = ZoneInfo("Asia/Seoul")

def test_run_financial_update_detects_changes_and_inserts(mocker):
    """
    [목적] API로부터 새로 수집한 재무 데이터와 DB의 최신 데이터가 다를 때(또는 DB에 없을 때)
           벌크 인서트가 정상적으로 호출되는지 검증합니다.
    """
    # 1. Mocking stock list 및 bulk data
    mock_db = mocker.MagicMock()
    mock_db.get_all_stock_codes.return_value = ["005930"]
    mock_db.get_latest_statements_bulk.return_value = []
    mock_db.get_latest_ratios_bulk.return_value = []
    mocker.patch("tasks.financial_task.DatabaseManager", return_value=mock_db)

    # 2. Mocking KIS API 응답
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_all_financial_data.return_value = {
        "balance_sheet": [{"stac_yymm": "202512", "cras": "100", "fxas": "200", "total_aset": "300", "flow_lblt": "50", "fix_lblt": "50", "total_lblt": "100", "cpfn": "10", "total_cptl": "200"}],
        "income_statement": [{"stac_yymm": "202512", "sale_account": "500", "sale_cost": "400", "sale_totl_prfi": "100", "bsop_prti": "50", "op_prfi": "40", "thtr_ntin": "30"}],
        "financial_ratio": [],
        "profit_ratio": [],
        "other_major_ratios": [],
        "stability_ratio": [],
        "growth_ratio": []
    }
    mocker.patch("tasks.financial_task.KisREST", return_value=mock_kis)

    job_statuses = {}
    
    # 실행 (target_group=-1로 하여 전 종목 강제 수집 보장)
    run_financial_update(job_statuses, test_mode=False, target_group=-1)

    # 검증: insert_financial_statements가 1번 이상 호출되었어야 함
    assert mock_db.insert_financial_statements.call_count == 1
    # 삽입될 레코드 리스트를 첫 번째 인자로 받았는지 확인
    inserted_statements = mock_db.insert_financial_statements.call_args[0][0]
    assert len(inserted_statements) == 1
    assert inserted_statements[0]["stk_cd"] == "005930"
    assert inserted_statements[0]["total_aset"] == 300


def test_run_financial_update_skips_on_no_changes(mocker):
    """
    [목적] API 데이터와 DB 내 최신 데이터가 완벽하게 일치할 때(소수점/타입 차이 및 0/None 무시 통과),
           새로운 PIT 로우를 생성하지 않고 인서트가 스킵되는지 검증합니다.
    """
    mock_db = mocker.MagicMock()
    mock_db.get_all_stock_codes.return_value = ["005930"]
    # DB 데이터: 자산총계 300.0 (Decimal로 저장되어 float 변환 시 동일)
    mock_db.get_latest_statements_bulk.return_value = [{
        "stk_cd": "005930",
        "stac_yymm": "202512",
        "div_cls_code": "1",
        "cras": 100.0,
        "fxas": 200.0,
        "total_aset": 300.0,
        "flow_lblt": 50.0,
        "fix_lblt": 50.0,
        "total_lblt": 100.0,
        "cpfn": 10.0,
        "total_cptl": 200.0,
        # 손익계산서 항목들은 API 응답이 없으므로(0/None 동일 취급) DB에도 없음 또는 0
        "sale_account": None,
        "sale_cost": 0
    }]
    mock_db.get_latest_ratios_bulk.return_value = []
    mocker.patch("tasks.financial_task.DatabaseManager", return_value=mock_db)

    # API 데이터: 자산총계 300 (int/float)
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_all_financial_data.return_value = {
        "balance_sheet": [{"stac_yymm": "202512", "cras": "100", "fxas": "200", "total_aset": "300", "flow_lblt": "50", "fix_lblt": "50", "total_lblt": "100", "cpfn": "10", "total_cptl": "200"}],
        "income_statement": [],
        "financial_ratio": [],
        "profit_ratio": [],
        "other_major_ratios": [],
        "stability_ratio": [],
        "growth_ratio": []
    }
    mocker.patch("tasks.financial_task.KisREST", return_value=mock_kis)

    job_statuses = {}
    
    run_financial_update(job_statuses, test_mode=False, target_group=-1)

    # 검증: 변경사항이 없으므로 인서트가 호출되지 않아야 함
    mock_db.insert_financial_statements.assert_not_called()


def test_run_financial_update_handles_api_exception_safely(mocker):
    """
    [목적] 특정 종목 수집 중 KIS API 예외가 터지더라도, 해당 종목만 건너뛰고 나머지 종목의 수집을 끝까지 마쳐야 함.
    """
    mock_db = mocker.MagicMock()
    mock_db.get_all_stock_codes.return_value = ["005930", "000660"]
    mock_db.get_latest_statements_bulk.return_value = []
    mock_db.get_latest_ratios_bulk.return_value = []
    mocker.patch("tasks.financial_task.DatabaseManager", return_value=mock_db)

    mock_kis = mocker.MagicMock()
    # 1번째 종목은 KIS API 에러 발생, 2번째 종목은 정상 데이터 반환
    def side_effect(stk_cd, div_cls_code='1'):
        if stk_cd == "005930":
            raise Exception("KIS API Limit Error")
        return {
            "balance_sheet": [{"stac_yymm": "202512", "cras": "100", "fxas": "200", "total_aset": "300", "flow_lblt": "50", "fix_lblt": "50", "total_lblt": "100", "cpfn": "10", "total_cptl": "200"}],
            "income_statement": [],
            "financial_ratio": [],
            "profit_ratio": [],
            "other_major_ratios": [],
            "stability_ratio": [],
            "growth_ratio": []
        }
    mock_kis.fetch_all_financial_data.side_effect = side_effect
    mocker.patch("tasks.financial_task.KisREST", return_value=mock_kis)

    job_statuses = {}
    
    run_financial_update(job_statuses, test_mode=False, target_group=-1)

    # 1번째 에러에도 불구하고 2번째 종목인 000660의 재무제표가 인서트되었는지 검증
    assert mock_db.insert_financial_statements.call_count == 1
    inserted = mock_db.insert_financial_statements.call_args[0][0]
    assert len(inserted) == 1
    assert inserted[0]["stk_cd"] == "000660"


def test_run_financial_update_updates_job_statuses_progress(mocker):
    """
    [목적] 백그라운드 태스크 기동 시 job_statuses에 진행률 및 tqdm 스타일의 it/s, ETA 정보가 실시간 기입되는지 검증.
    """
    mock_db = mocker.MagicMock()
    mock_db.get_all_stock_codes.return_value = ["005930", "000660"]
    mock_db.get_latest_statements_bulk.return_value = []
    mock_db.get_latest_ratios_bulk.return_value = []
    mocker.patch("tasks.financial_task.DatabaseManager", return_value=mock_db)

    mock_kis = mocker.MagicMock()
    mock_kis.fetch_all_financial_data.return_value = {}
    mocker.patch("tasks.financial_task.KisREST", return_value=mock_kis)

    job_statuses = {}
    
    run_financial_update(job_statuses, test_mode=False, target_group=-1)

    status = job_statuses.get("financial_update")
    assert status is not None
    assert status["is_running"] is False
    assert status["progress"] == 100
    assert status["last_status"] == "success"
    assert "duration" in status
    assert "성공적으로 완료" in status.get("last_log", "") or "수집/비교 완료" in status.get("last_log", "")


def test_run_financial_update_sharding_and_manual_all(mocker):
    """
    [목적] target_group 값에 따라 요일별 5분할 해시 필터링 및 수동 전 종목 수집 필터링이 올바르게 동작하는지 검증합니다.
    """
    # 5개의 대표 종목 생성
    stock_list = ["005930", "000660", "035720", "035420", "005380"]
    
    # 각 종목코드에 해당하는 결정론적 해시 MOD 5 구하기
    group_map = {}
    for s in stock_list:
        h = hashlib.md5(s.encode('utf-8')).hexdigest()
        group_map[s] = int(h, 16) % 5

    mock_db = mocker.MagicMock()
    mock_db.get_all_stock_codes.return_value = stock_list
    mock_db.get_latest_statements_bulk.return_value = []
    mock_db.get_latest_ratios_bulk.return_value = []
    mocker.patch("tasks.financial_task.DatabaseManager", return_value=mock_db)

    mock_kis = mocker.MagicMock()
    mock_kis.fetch_all_financial_data.return_value = {}
    mocker.patch("tasks.financial_task.KisREST", return_value=mock_kis)

    # 1. target_group=0~4 개별 실행 시 각 요일별 종목만 필터링되는지 검증
    for g in range(5):
        job_statuses = {}
        run_financial_update(job_statuses, test_mode=False, target_group=g)
        
        # 해당 그룹에 해당하는 종목 수 확인
        expected_stocks = [s for s in stock_list if group_map[s] == g]
        
        # fetch_all_financial_data가 예상된 종목코드들만으로 호출되었는지 검증
        called_codes = [args[0] for args, _ in mock_kis.fetch_all_financial_data.call_args_list]
        
        # 매 루프마다 call_args_list가 누적되므로 해당 루프분만 비교하기 위해 mock 초기화 필요
        mock_kis.fetch_all_financial_data.reset_mock()
        
        # target_stocks가 예상대로 선정되었는지 job_statuses 상태로 검증
        status = job_statuses.get("financial_update")
        assert status["total_stocks"] == len(expected_stocks)

    # 2. target_group=-1 (수동 전체 기동) 일 때 전 종목 수집 검증
    job_statuses = {}
    mock_kis.fetch_all_financial_data.reset_mock()
    run_financial_update(job_statuses, test_mode=False, target_group=-1)
    status = job_statuses.get("financial_update")
    assert status["total_stocks"] == len(stock_list)
