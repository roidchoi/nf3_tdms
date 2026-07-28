# tests/test_factor_calculator.py

import pandas as pd
import json
from collectors.factor_calculator import calculate_factors

def test_calculate_factors_detects_split_correctly():
    """
    [목적] 삼성전자 50:1 액면분할(2018-05-04)과 유사한 상황을 가정하여, 가격 비율 변동을 성공적으로 감지하고 
           '곱셈 형식'의 수정계수(Price Ratio = 0.02, Volume Ratio = 50.0)를 산출하는지 검증.
    """
    test_data = {
        "dt": [pd.Timestamp("2018-05-02"), pd.Timestamp("2018-05-03"), pd.Timestamp("2018-05-04")],
        "raw_close": [2650000.0, 2650000.0, 51900.0],
        "adj_close": [53000.0, 53000.0, 51900.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    
    assert len(factors) == 1
    event = factors[0]
    assert event["stk_cd"] == "005930"
    assert event["event_dt"] == pd.Timestamp("2018-05-04").date()
    assert float(event["price_ratio"]) == 0.02
    assert float(event["volume_ratio"]) == 50.0
    assert event["price_source"] == "KIS"
    
    details = json.loads(event["details"])
    assert details["raw_close"] == 51900.0
    assert details["adj_close"] == 51900.0
    assert details["prev_raw_close"] == 2650000.0
    assert details["prev_adj_close"] == 53000.0


def test_calculate_factors_returns_empty_when_no_adjustments():
    """
    [목적] 원본 종가와 수정 종가의 비율이 일정하여 수정계수 변경 이벤트가 존재하지 않는 경우 빈 리스트를 반환하는지 검증.
    """
    test_data = {
        "dt": [pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-02"), pd.Timestamp("2026-05-03")],
        "raw_close": [70000.0, 70500.0, 71000.0],
        "adj_close": [70000.0, 70500.0, 71000.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    assert factors == []


def test_calculate_factors_avoids_division_by_zero():
    """
    [목적] 시세 데이터 오염으로 원본 종가(raw_close)가 0이거나 이전 비율이 0인 행이 포함된 경우 ZeroDivisionError를 방지하고 정상 연산 처리하는지 검증.
    """
    test_data = {
        "dt": [pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-02"), pd.Timestamp("2026-05-03")],
        "raw_close": [70000.0, 0.0, 71000.0],
        "adj_close": [70000.0, 70500.0, 71000.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "005930", "KIS")
    assert isinstance(factors, list)


def test_calculate_factors_handles_negative_prices_safely():
    """
    [목적] 과거 레거시 시세 데이터 오류로 마이너스 주가(prev_adj_close = -3599.0)가 유입되더라도
           price_ratio <= 0 인 음수 팩터를 절대 생성하지 않고 안전 정제하는지 검증.
    """
    test_data = {
        "dt": [pd.Timestamp("1998-12-09"), pd.Timestamp("1998-12-10"), pd.Timestamp("1998-12-11")],
        "raw_close": [4040.0, 4520.0, 460.0],
        "adj_close": [4040.0, -3599.0, 460.0]
    }
    df = pd.DataFrame(test_data)
    
    factors = calculate_factors(df, "017510", "KIS")
    # 음수 주가 유입 시 price_ratio <= 0 인 팩터는 절대 생성되지 않아야 함
    for f in factors:
        assert f["price_ratio"] > 0.0
        assert f["volume_ratio"] > 0.0
