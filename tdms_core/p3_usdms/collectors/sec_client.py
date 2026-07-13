import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from p3_usdms.config import get_settings

logger = logging.getLogger(__name__)

class SECClient:
    """
    SEC EDGAR API Client with Rate Limiting and User-Agent compliance.
    """
    BASE_URL = "https://data.sec.gov"
    ARCHIVE_URL = "https://www.sec.gov/Archives"
    
    def __init__(self) -> None:
        """
        config.py의 get_settings().SEC_USER_AGENT 로딩 검증.
        호스트(data.sec.gov, www.sec.gov)별 헤더 설정 및 세션 초기화.
        """
        settings = get_settings()
        self.user_agent = settings.SEC_USER_AGENT
        if not self.user_agent:
            self.user_agent = os.getenv("SEC_USER_AGENT", "")
            if not self.user_agent:
                raise ValueError("SEC_USER_AGENT 환경변수가 누락되었습니다")
                
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov"
        }
        self.last_request_time = 0
        self.rate_limit_delay = 0.15  # ~6.6 requests per second (Limit is 10)
        
        self.session = requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.timeout = 30
        
        # If-Modified-Since HTTP 캐시 관리를 위한 로컬 파일 캐시 설정
        import json
        self.cache_file = os.path.join(os.path.dirname(__file__), "sec_last_modified_cache.json")
        self.last_modified_cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    self.last_modified_cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load SEC Last-Modified cache: {e}")

    def _enforce_rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def get_master_index(self) -> dict[str, dict[str, str]]:
        """
        company_tickers.json을 호출하여 CIK를 키로 하는 정보 반환.
        Returns:
            {
                "0000320193": {"ticker": "AAPL", "name": "Apple Inc."},
                ...
            }
        """
        raw = self.get_company_tickers()
        result = {}
        for _, val in raw.items():
            cik_str = str(val['cik_str']).zfill(10)
            result[cik_str] = {
                'ticker': val['ticker'],
                'name': val['title']
            }
        return result

    def get_company_tickers(self) -> dict[str, dict[str, Any]]:
        """www.sec.gov/files/company_tickers.json 호출 Raw 반환"""
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ReadTimeout:
            logger.error(f"Read timeout fetching company_tickers.json from {url}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch company_tickers.json: {e}")
            raise

    def get_company_facts(self, cik: str) -> Optional[dict[str, Any]]:
        """
        특정 CIK의 XBRL company facts raw 데이터를 조회합니다.
        URL: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_10digit}.json
        If-Modified-Since 헤더를 지원하여 변경 사항이 없을 때는 None을 반환(304 Not Modified).
        """
        padded_cik = str(cik).zfill(10)
        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{padded_cik}.json"
        
        headers = self.headers.copy()
        last_mod = self.last_modified_cache.get(padded_cik)
        if last_mod:
            headers["If-Modified-Since"] = last_mod
            
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 304:
                logger.info(f"CIK {cik} facts data not modified (304). Skipping fetch.")
                return None
                
            resp.raise_for_status()
            
            # Last-Modified 헤더 갱신 및 캐시 저장
            new_last_mod = resp.headers.get("Last-Modified")
            if new_last_mod:
                self.last_modified_cache[padded_cik] = new_last_mod
                try:
                    import json
                    with open(self.cache_file, "w") as f:
                        json.dump(self.last_modified_cache, f)
                except Exception as cache_err:
                    logger.warning(f"Failed to save SEC Last-Modified cache to file: {cache_err}")
                    
            return resp.json()
        except requests.exceptions.ReadTimeout:
            logger.error(f"Read timeout fetching facts for CIK {cik} from {url}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch facts for CIK {cik}: {e}")
            raise

    def get_tickers_exchange(self) -> dict[str, str]:
        """
        company_tickers_exchange.json 호출 및 파싱.
        Returns:
            {
                "AAPL": "NASDAQ",
                "MSFT": "NASDAQ",
                ...
            }
        """
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data_json = resp.json()
            
            fields = data_json['fields']
            exch_idx = fields.index('exchange')
            ticker_idx = fields.index('ticker')
            
            result = {}
            for row in data_json['data']:
                exchange = row[exch_idx]
                ticker = row[ticker_idx]
                result[ticker] = exchange
            return result
        except Exception as e:
            logger.error(f"Failed to fetch company_tickers_exchange.json: {e}")
            raise

    def get_filings_by_date(self, target_date: Any) -> list[dict[str, Any]]:
        """
        SEC Daily Index (.idx) 파일 파싱.
        Returns:
            [
                {"cik": 320193, "form_type": "10-K", "accession": "edgar/data/..."},
                ...
            ]
        """
        if isinstance(target_date, str):
            try:
                if '-' in target_date:
                    target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
                else:
                    target_date = datetime.strptime(target_date, '%Y%m%d').date()
            except ValueError:
                logger.error(f"Invalid date format: {target_date}")
                return []
                
        year = target_date.year
        qtr = (target_date.month - 1) // 3 + 1
        date_str = target_date.strftime('%Y%m%d')
        
        url = f"{self.ARCHIVE_URL}/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout + 10)
            if resp.status_code == 403:
                if target_date == datetime.now().date():
                    logger.warning(f"Got 403 for Today's Index ({target_date}). Assuming file not generated yet.")
                    return []
                else:
                    logger.warning(f"Got 403 for Past Date ({target_date}). possibly file missing or blocked.")
                    return []
            if resp.status_code == 404:
                logger.warning(f"No daily index found for {target_date} (404). Possibly holiday or weekend.")
                return []
                
            resp.raise_for_status()
            
            lines = resp.text.splitlines()
            records = []
            
            start_parsing = False
            for line in lines:
                if line.startswith("---"):
                    start_parsing = True
                    continue
                if not start_parsing: 
                    continue
                    
                parts = line.strip().split()
                if len(parts) < 5: 
                    continue
                
                cik_str = parts[-3]
                form_type = parts[-4]
                filename = parts[-1]
                
                if cik_str.isdigit():
                    records.append({
                        'cik': int(cik_str),
                        'form_type': form_type,
                        'accession': filename
                    })
            return records
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                 logger.warning(f"403 Forbidden during request: {e}. Treating as empty.")
                 return []
            logger.error(f"HTTP Error failed to fetch daily index using {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch daily index for {target_date}: {e}")
            raise
