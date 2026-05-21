import urllib.request
import zipfile
import io
from datetime import date, datetime
from p1_shared.api.kis_api_core import KisApiCore

class KisKrClient:
    """KIS REST API KR 전용 래퍼. OHLCV + 종목마스터 수집 담당."""

    def __init__(self, api_core: KisApiCore) -> None:
        self.api_core = api_core
        # api_core에 get 메서드가 존재하지 않는 경우 동적 생성 (테스트 mock 지원 및 통합 인터페이스 제공)
        if not hasattr(self.api_core, "get"):
            def _dynamic_get(path, params=None, tr_id="", extra_headers=None, **kwargs):
                merged_params = params or {}
                if kwargs:
                    merged_params.update(kwargs)
                return self.api_core.request(
                    method="GET",
                    path=path,
                    params=merged_params,
                    tr_id=tr_id,
                    extra_headers=extra_headers
                )
            self.api_core.get = _dynamic_get

    def fetch_daily_ohlcv(self, stk_cd: str, target_date: date) -> dict | None:
        """
        특정 종목의 target_date 일봉 데이터를 수집.

        KIS API 파라미터 제약조건:
           adj_price='1'이 원본(Raw) 가격.

        Returns:
            dict: {"stk_cd", "dt", "open", "high", "low", "close", "volume"} 또는
            None: 해당 날짜 데이터 없음
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        date_str = target_date.strftime("%Y%m%d")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stk_cd,
            "FID_INPUT_DATE_1": date_str,
            "FID_INPUT_DATE_2": date_str,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1"  # 원본 시세 수집
        }
        
        try:
            res = self.api_core.get(
                path,
                params=params,
                tr_id="FHKST03010100",
                adj_price="1"
            )
        except Exception as e:
            raise e

        if not res or "output2" not in res:
            return None
            
        output2 = res["output2"]
        if not isinstance(output2, list) or len(output2) == 0:
            return None
            
        # KIS start_date 무시 대응: target_date 행만 필터링
        target_row = None
        for row in output2:
            if row.get("stck_bsop_date") == date_str:
                target_row = row
                break
                
        if not target_row:
            return None
            
        try:
            return {
                "stk_cd": stk_cd,
                "dt": target_date,
                "open": int(target_row["stck_oprc"]),
                "high": int(target_row["stck_hgpr"]),
                "low": int(target_row["stck_lwpr"]),
                "close": int(target_row["stck_clpr"]),
                "volume": int(target_row["acml_vol"])
            }
        except (ValueError, KeyError, TypeError):
            return None

    def fetch_stock_master(self) -> list[dict]:
        """
        KIS 마스터 파일(ZIP)을 직접 다운로드하여 KOSPI 및 KOSDAQ 상장 종목 마스터 수집.

        Returns:
            list[dict]: [{"stk_cd", "stk_nm", "market", "is_active", "listed_dt", "listed_shares"}, ...]
        """
        results = []
        
        # 1. KOSPI 수집
        kospi_url = "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip"
        try:
            req = urllib.request.Request(kospi_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                kospi_zip_bytes = response.read()
            
            with zipfile.ZipFile(io.BytesIO(kospi_zip_bytes)) as zf:
                with zf.open("kospi_code.mst") as f:
                    content = f.read().decode("cp949")
                    
            for line in content.splitlines():
                if not line.strip():
                    continue
                # KOSPI Part2 길이는 228자
                part1 = line[:len(line) - 228]
                part2 = line[-228:]
                
                stk_cd_raw = part1[0:9].strip()
                stk_cd = stk_cd_raw[1:] if stk_cd_raw.startswith("A") else stk_cd_raw
                if len(stk_cd) != 6:
                    continue
                
                stk_nm = part1[21:].strip()
                
                # Part2 오프셋 슬라이싱 (상장일자: 97:105, 상장주수: 105:120)
                listed_dt_raw = part2[97:105].strip()
                listed_shares_raw = part2[105:120].strip()
                
                try:
                    listed_dt = datetime.strptime(listed_dt_raw, "%Y%m%d").date()
                except ValueError:
                    listed_dt = None
                    
                try:
                    listed_shares = int(listed_shares_raw)
                except ValueError:
                    listed_shares = 0
                    
                results.append({
                    "stk_cd": stk_cd,
                    "stk_nm": stk_nm,
                    "market": "KOSPI",
                    "is_active": True,
                    "listed_dt": listed_dt,
                    "listed_shares": listed_shares
                })
        except Exception as e:
            # 외부 네트워크 오류 발생 시 마스터 수집 실패 방지
            pass

        # 2. KOSDAQ 수집
        kosdaq_url = "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"
        try:
            req = urllib.request.Request(kosdaq_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                kosdaq_zip_bytes = response.read()
            
            with zipfile.ZipFile(io.BytesIO(kosdaq_zip_bytes)) as zf:
                with zf.open("kosdaq_code.mst") as f:
                    content = f.read().decode("cp949")
                    
            for line in content.splitlines():
                if not line.strip():
                    continue
                # KOSDAQ Part2 길이는 222자
                part1 = line[:len(line) - 222]
                part2 = line[-222:]
                
                stk_cd_raw = part1[0:9].strip()
                stk_cd = stk_cd_raw[1:] if stk_cd_raw.startswith("A") else stk_cd_raw
                if len(stk_cd) != 6:
                    continue
                
                stk_nm = part1[21:].strip()
                
                # Part2 오프셋 슬라이싱 (상장일자: 92:100, 상장주수: 100:115)
                listed_dt_raw = part2[92:100].strip()
                listed_shares_raw = part2[100:115].strip()
                
                try:
                    listed_dt = datetime.strptime(listed_dt_raw, "%Y%m%d").date()
                except ValueError:
                    listed_dt = None
                    
                try:
                    # KOSDAQ 상장주수는 천주 단위이므로 1,000 곱함
                    listed_shares = int(listed_shares_raw) * 1000
                except ValueError:
                    listed_shares = 0
                    
                results.append({
                    "stk_cd": stk_cd,
                    "stk_nm": stk_nm,
                    "market": "KOSDAQ",
                    "is_active": True,
                    "listed_dt": listed_dt,
                    "listed_shares": listed_shares
                })
        except Exception as e:
            pass
            
        return results
