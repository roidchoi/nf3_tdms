# collectors/kis_kr_client.py

import urllib.request
import zipfile
import io
import os
import re
import tempfile
from datetime import datetime, date

class KisKrClient:
    """
    KIS REST API KR 전용 래퍼. OHLCV + 종목마스터 수집 담당.
    """

    def __init__(self, api_core) -> None:
        self.api_core = api_core
        # api_core에 get 메서드 바인딩 (테스트 및 실제 런타임 호환용)
        if not hasattr(self.api_core, "get"):
            def get(path: str, **kwargs):
                tr_id = kwargs.pop("tr_id", "FHKST03010100")
                return self.api_core.request("GET", path, params=kwargs, tr_id=tr_id)
            self.api_core.get = get

    def fetch_daily_ohlcv(self, stk_cd: str, target_date: date) -> dict | None:
        """
        특정 종목의 target_date 일봉 데이터를 수집.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        date_str = target_date.strftime("%Y%m%d")
        
        # T-002 스펙: end_date=target_date, adj_price='1' (Raw 주가)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stk_cd,
            "FID_INPUT_DATE_1": date_str,
            "FID_INPUT_DATE_2": date_str,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1"  # 원본 가격 요청
        }
        
        try:
            # api_core.get을 호출 (테스트 케이스 검증용)
            res = self.api_core.get(path, adj_price="1", **params)
        except Exception as e:
            # API 오류 시 예외 전파
            raise e
            
        output2 = res.get("output2", [])
        for row in output2:
            if row.get("stck_bsop_date") == date_str:
                return {
                    "stk_cd": stk_cd,
                    "dt": target_date,
                    "open": int(row["stck_oprc"]),
                    "high": int(row["stck_hgpr"]),
                    "low": int(row["stck_lwpr"]),
                    "close": int(row["stck_clpr"]),
                    "volume": int(row["acml_vol"])
                }
        return None

    def fetch_ohlcv_range(self, stk_cd: str, start_date: date, end_date: date, adj_price: str = '1') -> list[dict]:
        """
        특정 종목의 지정 범위 시세 데이터를 수집합니다.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stk_cd,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": adj_price
        }
        
        try:
            res = self.api_core.get(path, adj_price=adj_price, **params)
        except Exception as e:
            raise e
            
        output2 = res.get("output2", [])
        records = []
        for row in output2:
            dt_str = row.get("stck_bsop_date")
            if dt_str:
                dt_val = datetime.strptime(dt_str, "%Y%m%d").date()
                if start_date <= dt_val <= end_date:
                    records.append({
                        "dt": dt_val,
                        "close": float(row["stck_clpr"])
                    })
        return records


    def fetch_stock_master(self) -> list[dict]:
        """
        KIS 마스터 파일(ZIP)을 직접 다운로드하여 KOSPI 및 KOSDAQ 상장 종목 마스터 수집.
        """
        urls = {
            "KOSPI": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
            "KOSDAQ": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"
        }
        
        records = []
        temp_dir = tempfile.gettempdir()
        
        for market, url in urls.items():
            zip_path = os.path.join(temp_dir, f"{market.lower()}_code.mst.zip")
            try:
                # urllib.request.urlopen을 호출하여 다운로드 수행 (테스트 Mocking 호환)
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    zip_data = response.read()
                
                with open(zip_path, "wb") as temp_f:
                    temp_f.write(zip_data)
                
                # 고정폭 필드 규격 정의
                field_specs_kospi = [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 9, 3, 1, 1, 1]
                field_specs_kosdaq = [2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9, 9, 3, 1, 1, 1]

                offset_kospi_dt = sum(field_specs_kospi[:49])
                offset_kospi_shares = sum(field_specs_kospi[:50])
                total_kospi_width = sum(field_specs_kospi)

                offset_kosdaq_dt = sum(field_specs_kosdaq[:44])
                offset_kosdaq_shares = sum(field_specs_kosdaq[:45])
                total_kosdaq_width = sum(field_specs_kosdaq)

                with zipfile.ZipFile(zip_path) as z:
                    for filename in z.namelist():
                        if filename.endswith(".mst"):
                            with z.open(filename) as f:
                                # 바이트 단위로 읽고 개행문자 기준으로 분리
                                content_bytes = f.read()
                                for line_bytes in content_bytes.splitlines():
                                    if not line_bytes.strip():
                                        continue
                                    
                                    # 파이프 구분자가 포함되어 있는지 바이트 단위로 검사
                                    if b'|' in line_bytes:
                                        line_str = line_bytes.decode('cp949', errors='ignore')
                                        parts = line_str.split('|')
                                        if len(parts) >= 10:
                                            stk_cd = parts[0].strip()[-6:]
                                            stk_nm = parts[2].strip() if len(parts) > 2 else ""
                                            
                                            if market == "KOSPI":
                                                listed_dt_str = parts[49].strip() if len(parts) > 49 else ""
                                                listed_shares_str = parts[50].strip() if len(parts) > 50 else "0"
                                            else:
                                                listed_dt_str = parts[44].strip() if len(parts) > 44 else ""
                                                listed_shares_str = parts[45].strip() if len(parts) > 45 else "0"
                                        else:
                                            continue
                                    else:
                                        # 고정 폭 바이트 슬라이싱 처리
                                        # Part1: 단축코드 9바이트, 표준코드 12바이트, 한글명 40바이트
                                        stk_cd_bytes = line_bytes[0:9]
                                        stk_nm_bytes = line_bytes[21:61]
                                        
                                        if market == "KOSPI":
                                            part2_bytes = line_bytes[-total_kospi_width:]
                                        else:
                                            part2_bytes = line_bytes[-total_kosdaq_width:]
                                        
                                        stk_cd = stk_cd_bytes.decode('cp949', errors='ignore').strip()[-6:]
                                        stk_nm = stk_nm_bytes.decode('cp949', errors='ignore').strip()
                                        
                                        if market == "KOSPI":
                                            listed_dt_bytes = part2_bytes[offset_kospi_dt : offset_kospi_dt + 8]
                                            listed_shares_bytes = part2_bytes[offset_kospi_shares : offset_kospi_shares + 15]
                                        else:
                                            listed_dt_bytes = part2_bytes[offset_kosdaq_dt : offset_kosdaq_dt + 8]
                                            listed_shares_bytes = part2_bytes[offset_kosdaq_shares : offset_kosdaq_shares + 15]
                                            
                                        listed_dt_str = listed_dt_bytes.decode('cp949', errors='ignore').strip()
                                        listed_shares_str = listed_shares_bytes.decode('cp949', errors='ignore').strip()
                                    
                                    # 6자리 숫자로 구성된 단축코드만 수집
                                    if not re.match(r'^\d{6}$', stk_cd):
                                        continue
                                    
                                    # 상장일자 파싱
                                    listed_dt = None
                                    if len(listed_dt_str) == 8:
                                        try:
                                            listed_dt = datetime.strptime(listed_dt_str, "%Y%m%d").date()
                                        except ValueError:
                                            pass
                                            
                                    # 상장주수 파싱 및 KOSDAQ 1,000배 보정
                                    try:
                                        listed_shares = int(listed_shares_str)
                                        if market == "KOSDAQ":
                                            listed_shares *= 1000
                                    except ValueError:
                                        listed_shares = 0
                                        
                                    records.append({
                                        "stk_cd": stk_cd,
                                        "stk_nm": stk_nm,
                                        "market": market,
                                        "is_active": True,
                                        "listed_dt": listed_dt,
                                        "listed_shares": listed_shares
                                    })
            except Exception as e:
                # 에러 로그 출력 후 다음 시장 진행
                print(f"Error fetching stock master for {market}: {e}")
            finally:
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
                        
        return records

    def fetch_financial_data_by_type(self, stk_cd: str, api_type: str, div_cls_code: str = '1') -> list[dict]:
        """
        KIS OpenAPI를 호출하여 지정된 유형의 재무 데이터(단건)를 조회합니다.

        :param stk_cd: 종목코드 (6자리)
        :param api_type: balance_sheet, income_statement 등
        :param div_cls_code: '1' (분기) 또는 '0' (연간)
        """
        configs = {
            'balance_sheet': ('/uapi/domestic-stock/v1/finance/balance-sheet', 'FHKST66430100'),
            'income_statement': ('/uapi/domestic-stock/v1/finance/income-statement', 'FHKST66430200'),
            'financial_ratio': ('/uapi/domestic-stock/v1/finance/financial-ratio', 'FHKST66430300'),
            'profit_ratio': ('/uapi/domestic-stock/v1/finance/profit-ratio', 'FHKST66430400'),
            'other_major_ratios': ('/uapi/domestic-stock/v1/finance/other-major-ratios', 'FHKST66430500'),
            'stability_ratio': ('/uapi/domestic-stock/v1/finance/stability-ratio', 'FHKST66430600'),
            'growth_ratio': ('/uapi/domestic-stock/v1/finance/growth-ratio', 'FHKST66430800')
        }

        if api_type not in configs:
            raise ValueError(f"지원하지 않는 재무 API 유형입니다: {api_type}")

        path, tr_id = configs[api_type]
        params = {
            "FID_DIV_CLS_CODE": div_cls_code,
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stk_cd
        }

        res = self.api_core.get(path, tr_id=tr_id, **params)
        output = res.get("output", [])
        if not isinstance(output, list):
            output = [output]
        return output

    def fetch_all_financial_data(self, stk_cd: str, div_cls_code: str = '1') -> dict[str, list[dict]]:
        """
        7종의 KIS 재무 데이터를 일괄 호출하여 병합 가능한 형태로 반환합니다.
        """
        api_types = [
            'balance_sheet', 'income_statement', 'financial_ratio', 'profit_ratio',
            'other_major_ratios', 'stability_ratio', 'growth_ratio'
        ]
        results = {}
        for api_type in api_types:
            try:
                results[api_type] = self.fetch_financial_data_by_type(stk_cd, api_type, div_cls_code)
            except Exception as e:
                # 개별 API 실패 시 에러 로그를 기록하고 빈 리스트로 대응
                print(f"Error fetching financial {api_type} for {stk_cd}: {e}")
                results[api_type] = []
        return results

