# tests/test_financial_repo.py

import pytest
from datetime import datetime, date
from zoneinfo import ZoneInfo
from contextlib import contextmanager
from repositories.financial_repo import FinancialRepo

KST = ZoneInfo("Asia/Seoul")

def test_insert_statements_success(mocker):
    """
    [목적] financial_statements 벌크 인서트 호출 시 rowcount와 SQL 실행이 올바른지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 2

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FinancialRepo(pool=mock_pool)
    statements = [
        {
            "stk_cd": "005930",
            "stac_yymm": "202512",
            "div_cls_code": "1",
            "total_aset": 450000000000000,
            "total_lblt": 100000000000000,
            "total_cptl": 350000000000000
        },
        {
            "stk_cd": "000660",
            "stac_yymm": "202512",
            "div_cls_code": "1",
            "total_aset": 200000000000000,
            "total_lblt": 80000000000000,
            "total_cptl": 120000000000000
        }
    ]

    count = repo.insert_statements(statements)
    assert count == 2
    mock_cursor.executemany.assert_called_once()
    sql_arg = mock_cursor.executemany.call_args[0][0]
    assert "INSERT INTO financial_statements" in sql_arg


def test_insert_ratios_success(mocker):
    """
    [목적] financial_ratios 벌크 인서트 호출 시 rowcount와 SQL 실행이 올바른지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 1

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FinancialRepo(pool=mock_pool)
    ratios = [
        {
            "stk_cd": "005930",
            "stac_yymm": "202512",
            "div_cls_code": "1",
            "roe_val": 12.5,
            "eps": 5000
        }
    ]

    count = repo.insert_ratios(ratios)
    assert count == 1
    mock_cursor.executemany.assert_called_once()


def test_get_latest_statement(mocker):
    """
    [목적] 특정 종목의 특정 결산분 중 최신 버전(retrieved_at 기준) 1건을 조회하는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.description = [
        ("stk_cd",), ("stac_yymm",), ("div_cls_code",), ("total_aset",), ("retrieved_at",)
    ]
    mock_cursor.fetchone.return_value = (
        "005930", "202512", "1", 450000000000000, datetime(2026, 5, 21, 10, 0, tzinfo=KST)
    )

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FinancialRepo(pool=mock_pool)
    res = repo.get_latest_statement("005930", "202512", "1")

    assert res is not None
    assert res["stk_cd"] == "005930"
    assert res["total_aset"] == 450000000000000
    mock_cursor.execute.assert_called_once()
    called_sql = mock_cursor.execute.call_args[0][0]
    assert "ORDER BY retrieved_at DESC" in called_sql


def test_get_statements_as_of_normal_pit(mocker):
    """
    [목적] 일반적인 PIT 시점(2025-11-08 이후) 쿼리 시 as_of_date 필터가 정상적으로 들어가는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.description = [
        ("stac_yymm",), ("total_aset",)
    ]
    mock_cursor.fetchall.return_value = [
        ("202509", 440000000000000)
    ]

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FinancialRepo(pool=mock_pool)
    as_of = datetime(2026, 1, 1, tzinfo=KST)
    res = repo.get_statements_as_of("005930", "1", as_of)

    assert len(res) == 1
    assert res[0]["stac_yymm"] == "202509"
    assert res[0]["total_aset"] == 440000000000000
    mock_cursor.execute.assert_called_once()
    called_sql = mock_cursor.execute.call_args[0][0]
    called_params = mock_cursor.execute.call_args[0][1]
    
    # 2025-11-08 이후이므로 retrieved_at <= as_of_date 필터가 활성화되어야 함
    assert "retrieved_at <=" in called_sql
    assert called_params["as_of_date"] == as_of


def test_get_statements_as_of_historical_bypass(mocker):
    """
    [목적] 2025-11-08 이전 시점으로 쿼리할 때, retrieved_at 필터를 우회하여 데이터 소실을 방지하는지 검증.
    """
    mock_cursor = mocker.MagicMock()
    mock_cursor.description = [
        ("stac_yymm",), ("total_aset",)
    ]
    mock_cursor.fetchall.return_value = [
        ("202506", 420000000000000)
    ]

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = FinancialRepo(pool=mock_pool)
    # 2025-11-08 이전의 과거 시점으로 조회 시도
    as_of = datetime(2025, 6, 30, tzinfo=KST)
    res = repo.get_statements_as_of("005930", "1", as_of)

    assert len(res) == 1
    assert res[0]["stac_yymm"] == "202506"
    assert res[0]["total_aset"] == 420000000000000
    mock_cursor.execute.assert_called_once()
    called_sql = mock_cursor.execute.call_args[0][0]
    
    # 2025-11-08 이전 시점이므로 retrieved_at 필터링이 풀려 데이터가 모두 나오도록 우회되어야 함
    assert "retrieved_at <=" not in called_sql
