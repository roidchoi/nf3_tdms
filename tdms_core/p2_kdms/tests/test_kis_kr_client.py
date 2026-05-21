import pytest
from datetime import date
from p2_kdms.collectors.kis_kr_client import KisKrClient

def test_fetch_daily_ohlcv_returns_target_date_row_only(mocker):
    """
    [목적] KIS API 응답에서 target_date에 해당하는 행만 반환하며, 반드시 원본 가격(adj_price='1')을 요청하는지 검증.
    [유도] end_date=target_date, adj_price='1'로 요청 후 응답 리스트에서 필터링하는 로직 구현 유도.
           start_date 무시 대응 및 KIS API 파라미터 규칙 준수 보장.
    """
    mock_core = mocker.MagicMock()
    mock_core.get.return_value = {
        "output2": [
            {"stck_bsop_date": "20260514", "stck_oprc": "70000",
             "stck_hgpr": "71000", "stck_lwpr": "69000",
             "stck_clpr": "70500", "acml_vol": "1000000"},
            {"stck_bsop_date": "20260513", "stck_oprc": "69000",
             "stck_hgpr": "70000", "stck_lwpr": "68000",
             "stck_clpr": "69500", "acml_vol": "900000"},
        ]
    }
    client = KisKrClient(api_core=mock_core)
    result = client.fetch_daily_ohlcv("005930", date(2026, 5, 14))

    assert result is not None
    assert result["dt"] == date(2026, 5, 14)
    assert result["stk_cd"] == "005930"
    assert result["close"] == 70500
    assert result["volume"] == 1000000

    # KIS API에 원본 주가(adj_price='1')가 전달되었는지 검증
    # fetch_daily_ohlcv 내부에서 api_core.get을 호출할 때 adj_price='1'이 포함되어야 함
    mock_core.get.assert_called_once()
    called_kwargs = mock_core.get.call_args[1]
    assert called_kwargs.get("adj_price") == "1"


def test_fetch_daily_ohlcv_returns_none_when_date_not_in_response(mocker):
    """
    [목적] API 응답에 target_date가 없을 때(휴장일 등) None을 반환하는지 검증.
    [유도] 필터링 결과가 빈 경우 None 반환 처리 구현 유도.
    """
    mock_core = mocker.MagicMock()
    mock_core.get.return_value = {
        "output2": [
            {"stck_bsop_date": "20260513", "stck_oprc": "69000",
             "stck_hgpr": "70000", "stck_lwpr": "68000",
             "stck_clpr": "69500", "acml_vol": "900000"},
        ]
    }
    client = KisKrClient(api_core=mock_core)
    result = client.fetch_daily_ohlcv("005930", date(2026, 5, 14))

    assert result is None


def test_fetch_daily_ohlcv_raises_kis_api_error_on_api_failure(mocker):
    """
    [목적] KIS API 오류 시 KisApiError(또는 원본 예외)가 전파되는지 검증.
    [유도] 광범위한 except Exception 대신 구체적 예외 처리 구현 유도.
    """
    mock_core = mocker.MagicMock()
    mock_core.get.side_effect = Exception("API 서버 오류")

    client = KisKrClient(api_core=mock_core)
    with pytest.raises(Exception):
        client.fetch_daily_ohlcv("005930", date(2026, 5, 14))


def test_fetch_stock_master_downloads_and_parses_mst(mocker):
    """
    [목적] KIS 마스터 ZIP 파일을 다운로드하여 단축코드, 종목명, 상장일자, 상장주식을 올바르게 파싱 및 정규화하는지 검증.
    """
    import io
    import zipfile
    
    # 1. KOSPI MST 모의 내용 생성 (Part1과 Part2 병합된 1줄)
    # Part 1: 단축코드(9바이트), 표준코드(12바이트), 한글명(남은부분)
    # Part 2: 228바이트 고정 폭 필드들
    # 단축코드 'A005930   ', 표준코드 'KR7005930003', 한글명 '삼성전자            '
    # Part 2에서 상장일자: 50번째 컬럼 (widths: ... 12, 12, 8(상장일자: '19750611'), 15(상장주수: ' 5969782550     '), ...)
    # widths 전체 합은 228이어야 합니다.
    # widths = [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1]
    # sum(widths) = 228
    
    # KOSPI Part2 Mocking
    kospi_part2_fields = ["  "] * len(field_specs_kospi := [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 9, 3, 1, 1, 1])
    kospi_part2_fields[49] = "19750611" # 상장일자 (8바이트)
    kospi_part2_fields[50] = "5969782550     " # 상장주수 (15바이트)
    
    kospi_part2_str = ""
    for width, field in zip(field_specs_kospi, kospi_part2_fields):
        kospi_part2_str += field.ljust(width)[:width]
    
    kospi_part1_str = "A005930  " + "KR7005930003" + "삼성전자            "
    kospi_line = kospi_part1_str + kospi_part2_str + "\n"
    
    # 2. KOSDAQ MST 모의 내용 생성 (Part1과 Part2 병합된 1줄, Part2는 222바이트)
    # widths = [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1]
    # sum(widths) = 222
    # 상장일자: 44번째 컬럼 (widths: ... 12, 12, 8(상장일자: '19991111'), 15(상장주수: '          50000'), ...)
    
    kosdaq_part2_fields = ["  "] * len(field_specs_kosdaq := [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 9, 3, 1, 1, 1])
    kosdaq_part2_fields[44] = "19991111" # 상장일자 (8바이트)
    kosdaq_part2_fields[45] = "          50000" # 상장주수(천주) (15바이트)
    
    kosdaq_part2_str = ""
    for width, field in zip(field_specs_kosdaq, kosdaq_part2_fields):
        kosdaq_part2_str += field.ljust(width)[:width]
        
    kosdaq_part1_str = "A035420  " + "KR7035420009" + "네이버              "
    kosdaq_line = kosdaq_part1_str + kosdaq_part2_str + "\n"
    
    # ZIP 바이트 생성 함수
    def make_zip(filename, data):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(filename, data.encode("cp949"))
        return buf.getvalue()
        
    kospi_zip_bytes = make_zip("kospi_code.mst", kospi_line)
    kosdaq_zip_bytes = make_zip("kosdaq_code.mst", kosdaq_line)
    
    # requests.get 또는 urllib.request.urlopen 모킹
    mock_response_kospi = mocker.MagicMock()
    mock_response_kospi.__enter__.return_value = mock_response_kospi
    mock_response_kospi.read.return_value = kospi_zip_bytes
    mock_response_kospi.status = 200
    
    mock_response_kosdaq = mocker.MagicMock()
    mock_response_kosdaq.__enter__.return_value = mock_response_kosdaq
    mock_response_kosdaq.read.return_value = kosdaq_zip_bytes
    mock_response_kosdaq.status = 200
    
    # urlopen 모킹
    mock_urlopen = mocker.patch("urllib.request.urlopen")
    mock_urlopen.side_effect = [mock_response_kospi, mock_response_kosdaq]
    
    client = KisKrClient(api_core=mocker.MagicMock())
    stocks = client.fetch_stock_master()
    
    assert len(stocks) == 2
    
    # KOSPI 검증
    kospi_stock = next(s for s in stocks if s["market"] == "KOSPI")
    assert kospi_stock["stk_cd"] == "005930"
    assert kospi_stock["stk_nm"] == "삼성전자"
    assert kospi_stock["listed_dt"] == date(1975, 6, 11)
    assert kospi_stock["listed_shares"] == 5969782550
    assert kospi_stock["is_active"] is True
    
    # KOSDAQ 검증
    kosdaq_stock = next(s for s in stocks if s["market"] == "KOSDAQ")
    assert kosdaq_stock["stk_cd"] == "035420"
    assert kosdaq_stock["stk_nm"] == "네이버"
    assert kosdaq_stock["listed_dt"] == date(1999, 11, 11)
    # KOSDAQ은 상장주수가 천주 단위이므로 50,000 * 1,000 = 50,000,000
    assert kosdaq_stock["listed_shares"] == 50000000
    assert kosdaq_stock["is_active"] is True

