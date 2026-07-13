import pytest
import requests
import pandas as pd
from unittest.mock import MagicMock
from p3_usdms.collectors.xbrl_mapper import XBRLMapper
from p3_usdms.collectors.financial_parser import FinancialParser
from p3_usdms.repositories.financial_repo import FinancialRepo

# =====================================================================
# TIER 1 - 단위 테스트 (Unit Tests)
# =====================================================================

def test_xbrl_mapper_maps_primary_tag_successfully():
    """
    [Tier 1 — 단위]
    [목적] XBRLMapper가 주어진 팩츠 리스트에서 최우선 순위 태그를 올바르게 매핑하는지 확인
    [유도] XBRLMapper.map_fact가 우선순위 배열대로 매치하며 가산/감산 노멀라이즈를 수행하게 유도
    """
    facts = [
        {"tag": "AssetsCurrent", "val": 1000.0},
        {"tag": "Assets", "val": 5000.0}
    ]
    val = XBRLMapper.map_fact("total_assets", facts)
    assert val == 5000.0


def test_xbrl_mapper_falls_back_when_primary_missing():
    """
    [Tier 1 — 단위]
    [목적] 최우선 순위 태그가 없을 때 대체 태그(Fallback)를 성공적으로 로드하는지 확인
    [유도] map_fact 내부의 fallback tag 매칭 루프를 유도
    """
    facts = [
        {"tag": "AssetsNet", "val": 4500.0}
    ]
    val = XBRLMapper.map_fact("total_assets", facts)
    assert val == 4500.0


def test_xbrl_mapper_normalizes_capex_to_positive():
    """
    [Tier 1 — 단위]
    [목적] Capex와 같은 음수 혹은 양수로 혼용되어 기록되는 Expense 항목을 양수 크기로 정규화하는지 검증
    [유도] normalize_sign이 'capex'에 대해 abs(value)를 강제하게 유도
    """
    facts = [
        {"tag": "PaymentsToAcquirePropertyPlantAndEquipment", "val": -300.0}
    ]
    val = XBRLMapper.map_fact("capex", facts)
    assert val == 300.0


def test_xbrl_mapper_includes_hardcoded_fallback_tags():
    """
    [Tier 1 — 단위]
    [목적] Operating Income 등 하드코딩된 폴백 태그들이 get_all_tracked_tags에 포함되어 필터링 누락을 방지하는지 검증
    """
    tracked_tags = XBRLMapper.get_all_tracked_tags()
    fallback_tags = [
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxes',
        'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
        'IncomeLossBeforeIncomeTaxes',
    ]
    for tag in fallback_tags:
        assert tag in tracked_tags


def test_financial_parser_with_empty_raw_facts_returns_empty():
    """
    [Tier 1 — 단위]
    [목적] 입력 데이터가 없을 때 빈 리스트를 예외 없이 반환하는지 확인
    [유도] _standardize_financials_v2에 빈 리스트를 넣었을 때 에러 없이 []을 반환하게 함
    """
    parser = FinancialParser()
    assert parser._standardize_financials_v2("0000000001", []) == []


# =====================================================================
# TIER 2 - 격리 통합 테스트 (Mocked Integration Tests)
# =====================================================================

def test_financial_parser_standardizes_discrete_q2_values(mocker):
    """
    [Tier 2 — 격리 통합]
    [목적] YTD 누적값에서 이전 분기값을 차감하여 Q2 이산(discrete) 값을 정확히 도출하는지 확인
    [유도] _derive_discrete_from_ytd 메서드가 Q2_discrete = Q2_YTD - Q1_YTD 공식을 올바르게 계산하도록 함
    """
    parser = FinancialParser()
    
    raw_facts = [
        # Q1 (90 days duration)
        {"cik": "0000000001", "tag": "Revenues", "val": 100.0, "period_start": "2026-01-01", "period_end": "2026-03-31", "filed_dt": "2026-04-10", "form": "10-Q", "fy": 2026, "fp": "Q1", "unit": "USD"},
        # Q2 YTD (180 days duration)
        {"cik": "0000000001", "tag": "Revenues", "val": 220.0, "period_start": "2026-01-01", "period_end": "2026-06-30", "filed_dt": "2026-07-10", "form": "10-Q", "fy": 2026, "fp": "Q2", "unit": "USD"},
    ]
    
    std_records = parser._standardize_financials_v2("0000000001", raw_facts)
    # Q2 레코드의 revenue가 220 - 100 = 120 인지 검증
    q2_record = next(r for r in std_records if r["fiscal_period"] == "Q2")
    assert q2_record["revenue"] == 120.0


def test_financial_parser_handles_sec_client_timeout(mocker):
    """
    [Tier 2 — 격리 통합]
    [목적] SEC EDGAR facts API가 타임아웃 오류를 낼 때 적절히 로깅하고 예외를 격리 처리하는지 검증
    [유도] SECClient.get_company_facts가 ReadTimeout을 뱉어도 run() 루프가 끊기지 않고 다음 CIK로 진행되게 유도
    """
    parser = FinancialParser()
    mocker.patch.object(parser.sec_client, "get_company_facts", side_effect=requests.exceptions.ReadTimeout("SEC Timeout"))
    
    # 예외가 상위 run 루프에서 포착되어 격리되고, 정상 종료되어야 함
    parser.run(["0000320193"]) 


def test_financial_parser_handles_304_not_modified_by_skipping(mocker):
    """
    [목적] SECClient.get_company_facts가 None(304 Not Modified)을 반환할 때,
           FinancialParser가 parsing 및 적재 로직을 조기 스킵하는지 검증.
    """
    parser = FinancialParser()
    mocker.patch.object(parser.sec_client, "get_company_facts", return_value=None)
    mock_process_shares = mocker.patch.object(parser, "_process_shares_outstanding")
    
    # 304 상태이므로 get_company_facts가 None을 리턴하고, 
    # 이후 _process_shares_outstanding이나 레포지토리 저장 호출 등이 스킵되어야 함.
    parser.run(["0000320193"])
    
    mock_process_shares.assert_not_called()


# =====================================================================
# TIER 3 - 실제 통합 테스트 (Physical Integration Tests)
# =====================================================================

@pytest.mark.integration
def test_financial_pipeline_stores_to_real_db(real_pool, mocker):
    """
    [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
    [목적] 실제 DB 연결 상태에서 FinancialRepo가 EAV, 표준 재무 데이터, 주식수 역사를 올바르게 삽입/업서트하는지 확인
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    repo = FinancialRepo()
    
    test_cik = "9999999999"
    
    # 1. EAV Clean & Insert 테스트
    with repo.get_cursor() as cur:
        cur.execute("DELETE FROM us_standard_financials WHERE cik = %s", (test_cik,))
        cur.execute("DELETE FROM us_share_history WHERE cik = %s", (test_cik,))
    repo.delete_raw_facts_by_cik(test_cik)
    
    raw_facts = [
        {"cik": test_cik, "tag": "Assets", "val": 1000000.0, "period_start": None, "period_end": "2026-12-31", "filed_dt": "2027-02-15", "frame": "CY2026", "fy": 2026, "fp": "FY", "form": "10-K"}
    ]
    repo.insert_financial_facts(raw_facts)
    
    # 2. 표준 재무 데이터 업서트 테스트
    std_data = [
        {
            "cik": test_cik, "report_period": "2026-12-31", "filed_dt": "2027-02-15", 
            "fiscal_year": 2026, "fiscal_period": "FY", "total_assets": 1000000.0, "total_debt": 200000.0,
            "shares_outstanding": 50000.0, "revenue": 800000.0, "gross_profit": 400000.0, "op_income": 150000.0,
            "rnd_expense": 30000.0, "interest_expense": 10000.0, "net_income": 100000.0, "ebitda": 180000.0,
            "ocf": 120000.0, "capex": 40000.0, "fcf": 80000.0
        }
    ]
    repo.upsert_standard_financials(std_data)
    
    # 3. 주식 수 역사 업서트 테스트
    shares_data = [
        {"cik": test_cik, "filed_dt": "2027-02-15", "val": 50000.0}
    ]
    repo.upsert_share_history(shares_data)
    
    # DB 조회 검증
    with repo.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM us_financial_facts WHERE cik = %s", (test_cik,))
        assert cur.fetchone()["count"] == 1
        
        cur.execute("SELECT total_assets, revenue FROM us_standard_financials WHERE cik = %s", (test_cik,))
        row = cur.fetchone()
        assert row["total_assets"] == 1000000.0
        assert row["revenue"] == 800000.0
        
        cur.execute("SELECT val FROM us_share_history WHERE cik = %s", (test_cik,))
        assert cur.fetchone()["val"] == 50000.0
        
    # 테스트 종료 후 클린업
    with repo.get_cursor() as cur:
        cur.execute("DELETE FROM us_standard_financials WHERE cik = %s", (test_cik,))
        cur.execute("DELETE FROM us_share_history WHERE cik = %s", (test_cik,))
        repo.delete_raw_facts_by_cik(test_cik)
