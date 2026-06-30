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
             "stck_clpr": "70500", "acml_vol": "1000000",
             "acml_tr_pbmn": "70500000000"},
            {"stck_bsop_date": "20260513", "stck_oprc": "69000",
             "stck_hgpr": "70000", "stck_lwpr": "68000",
             "stck_clpr": "69500", "acml_vol": "900000",
             "acml_tr_pbmn": "62550000000"},
        ]
    }
    client = KisKrClient(api_core=mock_core)
    result = client.fetch_daily_ohlcv("005930", date(2026, 5, 14))

    assert result is not None
    assert result["dt"] == date(2026, 5, 14)
    assert result["stk_cd"] == "005930"
    assert result["close"] == 70500
    assert result["volume"] == 1000000
    assert result["amt"] == 70500000000
    assert result["turn_rt"] == 0.0

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
    [목적] KIS 마스터 ZIP 파일을 다운로드하여 단축코드, 종목명, 상장일자, 상장주식, 자본금을 올바르게 파싱 및 정규화하는지 검증.
    """
    import io
    import zipfile
    
    # 1. KOSPI MST 모의 내용 생성 (Part1: 63B, Part2: 225B -> 총 288B)
    # '삼성전자'는 8바이트이므로 공백 32개 패딩하여 40바이트 채움
    kospi_part1_str = "A005930  " + "KR7005930003" + "삼성전자" + " " * 32 + "ST"
    
    part2_chars = [" "] * 225
    part2_chars[103:111] = list("19750611")  # 절대 오프셋 166 (166-63=103)
    part2_chars[111:126] = list("        5969782")  # 절대 오프셋 174 (174-63=111)
    part2_chars[126:147] = list("         778046685000")  # 절대 오프셋 189 (189-63=126)
    kospi_part2_str = "".join(part2_chars)
    kospi_line = kospi_part1_str + kospi_part2_str + "\n"
    
    # 2. KOSDAQ MST 모의 내용 생성 (Part1: 63B, Part2: 219B -> 총 282B)
    # '네이버'는 6바이트이므로 공백 34개 패딩하여 40바이트 채움
    kosdaq_part1_str = "A035420  " + "KR7035420009" + "네이버" + " " * 34 + "ST"
    
    part2_chars_daq = [" "] * 219
    part2_chars_daq[98:106] = list("19991111")  # 절대 오프셋 161 (161-63=98)
    part2_chars_daq[106:121] = list("          50000")  # 절대 오프셋 169 (169-63=106)
    part2_chars_daq[121:142] = list("          50070150000")  # 절대 오프셋 184 (184-63=121)
    kosdaq_part2_str = "".join(part2_chars_daq)
    
    # 알파벳 혼용 종목코드 (0008Z0) mock 데이터 추가
    # '에스엔시스'는 10바이트이므로 공백 30개 패딩하여 40바이트 채움
    kosdaq_part1_str_2 = "A0008Z0  " + "KR70008Z0002" + "에스엔시스" + " " * 30 + "ST"
    part2_chars_daq_2 = [" "] * 219
    part2_chars_daq_2[98:106] = list("20250819")
    part2_chars_daq_2[106:121] = list("          10000")
    part2_chars_daq_2[121:142] = list("          10000000000")
    kosdaq_part2_str_2 = "".join(part2_chars_daq_2)
    
    kosdaq_line = kosdaq_part1_str + kosdaq_part2_str + "\n" + kosdaq_part1_str_2 + kosdaq_part2_str_2 + "\n"
    
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
    
    assert len(stocks) == 3
    
    # KOSPI 검증
    kospi_stock = next(s for s in stocks if s["market"] == "KOSPI")
    assert kospi_stock["stk_cd"] == "005930"
    assert kospi_stock["stk_nm"] == "삼성전자"
    assert kospi_stock["listed_dt"] == date(1975, 6, 11)
    assert kospi_stock["listed_shares"] == 5969782000  # 1000배 보정 적용
    assert kospi_stock["cap"] == 778046685000  # 자본금 검증
    assert kospi_stock["is_active"] is True
    
    # KOSDAQ 검증 (네이버)
    naver_stock = next(s for s in stocks if s["stk_cd"] == "035420")
    assert naver_stock["stk_nm"] == "네이버"
    assert naver_stock["market"] == "KOSDAQ"
    assert naver_stock["listed_dt"] == date(1999, 11, 11)
    assert naver_stock["listed_shares"] == 50000000
    assert naver_stock["cap"] == 50070150000  # 자본금 검증
    assert naver_stock["is_active"] is True
    
    # KOSDAQ 검증 (알파벳 혼용 종목 - 에스엔시스)
    sn_stock = next(s for s in stocks if s["stk_cd"] == "0008Z0")
    assert sn_stock["stk_nm"] == "에스엔시스"
    assert sn_stock["market"] == "KOSDAQ"
    assert sn_stock["listed_dt"] == date(2025, 8, 19)
    assert sn_stock["listed_shares"] == 10000000
    assert sn_stock["cap"] == 10000000000  # 자본금 검증
    assert sn_stock["is_active"] is True


def test_fetch_stock_master_filters_funds(mocker):
    """
    [목적] 그룹코드가 BC(수익증권), MF(뮤추얼펀드), EW(ELW)인 경우 수집 대상에서 제외하는지 검증.
    """
    import io
    import zipfile
    
    def make_part1(code, std_code, name, group):
        code_bytes = code.encode("cp949").ljust(9)[:9]
        std_bytes = std_code.encode("cp949").ljust(12)[:12]
        name_bytes = name.encode("cp949").ljust(40)[:40]
        group_bytes = group.encode("cp949").ljust(2)[:2]
        return code_bytes + std_bytes + name_bytes + group_bytes

    def make_part2_kospi():
        part2_chars = [" "] * 225
        part2_chars[103:111] = list("20260101")
        part2_chars[111:126] = list("        1000000")
        part2_chars[126:147] = list("         100000000000")
        return "".join(part2_chars).encode("cp949")

    # 1. 일반 주식 (그룹코드 ST)
    part1_st = make_part1("A000010", "KR7000010004", "일반주식", "ST")
    line_st = part1_st + make_part2_kospi() + b"\n"
    
    # 2. 펀드/수익증권 (그룹코드 BC)
    part1_bc = make_part1("A100020", "KR5100020008", "수익증권펀드", "BC")
    line_bc = part1_bc + make_part2_kospi() + b"\n"
    
    # 3. 뮤추얼펀드 (그룹코드 MF)
    part1_mf = make_part1("A200030", "KR5200030007", "뮤추얼펀드", "MF")
    line_mf = part1_mf + make_part2_kospi() + b"\n"
    
    kospi_line_bytes = line_st + line_bc + line_mf
    
    def make_zip(filename, data_bytes):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(filename, data_bytes)
        return buf.getvalue()
        
    kospi_zip_bytes = make_zip("kospi_code.mst", kospi_line_bytes)
    
    mock_response = mocker.MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = kospi_zip_bytes
    mock_response.status = 200
    
    mock_urlopen = mocker.patch("urllib.request.urlopen")
    mock_urlopen.return_value = mock_response
    
    mock_response_empty = mocker.MagicMock()
    mock_response_empty.__enter__.return_value = mock_response_empty
    mock_response_empty.read.return_value = make_zip("kosdaq_code.mst", b"")
    mock_response_empty.status = 200
    mock_urlopen.side_effect = [mock_response, mock_response_empty]
    
    client = KisKrClient(api_core=mocker.MagicMock())
    stocks = client.fetch_stock_master()
    
    # BC, MF 그룹코드를 가진 펀드 종목들은 필터링되어, ST 그룹코드를 가진 '일반주식' 1건만 수집되어야 함
    assert len(stocks) == 1
    assert stocks[0]["stk_cd"] == "000010"
    assert stocks[0]["stk_nm"] == "일반주식"


