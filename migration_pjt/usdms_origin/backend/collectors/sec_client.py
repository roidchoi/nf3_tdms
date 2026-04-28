import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class SECClient:
    """
    SEC EDGAR API Client with Rate Limiting and User-Agent compliance.
    """
    BASE_URL = "https://data.sec.gov"
    ARCHIVE_URL = "https://www.sec.gov/Archives"
    
    def __init__(self):
        self.user_agent = os.getenv("SEC_USER_AGENT", "Name (email@example.com)")
        if not self.user_agent or "sample" in self.user_agent.lower():
            logger.warning("SEC_USER_AGENT is not set properly. Using fallback.")
            self.user_agent = "MyDailyRoutine/1.0 (admin@example.com)"
        
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov" # Default, overridden in specific methods
        }
        self.last_request_time = 0
        self.rate_limit_delay = 0.15  # ~6.6 requests per second (Limit is 10)

        # Robust Session with Retry
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
        self.timeout = 30 # Increased to 30s

    def get_master_index(self) -> Dict[str, Any]:
        """
        Alias for get_company_tickers to satisfy MasterSync interface.
        Returns: {cik: {ticker, title, ...}}
        Note: company_tickers.json returns a dict index by "0", "1"... 
        We might need to reshape it if MasterSync expects CIK as key.
        Let's check company_tickers structure: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
        """
        raw = self.get_company_tickers()
        # Transform to {cik: {ticker, name}} map for easy lookup
        # MasterSync expects: {cik: {'ticker': ..., 'name': ...}}
        result = {}
        for _, val in raw.items():
            cik_str = str(val['cik_str']).zfill(10)
            result[cik_str] = {
                'ticker': val['ticker'],
                'name': val['title']
            }
        return result

    def _enforce_rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def get_company_tickers(self) -> Dict[str, Any]:
        """
        Fetch company_tickers.json (CIK, Ticker, Title)
        URL: https://www.sec.gov/files/company_tickers.json
        Note: This file is on www.sec.gov, not data.sec.gov
        """
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

    def get_company_facts(self, cik: str) -> Dict[str, Any]:
        """
        Fetch company facts (XBRL data) for a specific CIK.
        """
        padded_cik = str(cik).zfill(10)
        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{padded_cik}.json"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ReadTimeout:
            logger.error(f"Read timeout fetching facts for CIK {cik} from {url}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch facts for CIK {cik}: {e}")
            raise

    def get_tickers_exchange(self) -> Dict[int, str]:
        """
        Fetch company_tickers_exchange.json
        URL: https://www.sec.gov/files/company_tickers_exchange.json
        Returns: {cik: exchange_name}
        """
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data_json = resp.json()
            
            # Structure: {'fields': ['cik', 'name', 'ticker', 'exchange'], 'data': [[...], ...]}
            fields = data_json['fields']
            cik_idx = fields.index('cik')
            exch_idx = fields.index('exchange')
            ticker_idx = fields.index('ticker')
            
            result = {}
            for row in data_json['data']:
                cik = row[cik_idx] # Keep for reference if needed, but key is ticker
                exchange = row[exch_idx]
                ticker = row[ticker_idx]
                result[ticker] = exchange
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch company_tickers_exchange.json: {e}")
            raise

    def get_filings_by_date(self, target_date) -> list:
        """
        Fetch SEC Daily Index for a specific date and parse it.
        URL Format: https://www.sec.gov/Archives/edgar/daily-index/YYYY/QTRx/company.YYYYMMDD.idx
        Returns list of dict: [{'cik': int, 'form_type': str, 'accession': str}, ...]
        """
        # Convert date to YYYY, QTR, YYYYMMDD
        if isinstance(target_date, str):
            # Try parsing YYYYMMDD or YYYY-MM-DD
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
        
        # NOTE: SEC Archives often return 403 Forbidden instead of 404 Not Found 
        # when the file hasn't been generated yet (especially for today's date).
        url = f"{self.ARCHIVE_URL}/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"
        
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout + 10) # 40s generous for Index
            
            # Special Handling for 403 on 'Today'
            if resp.status_code == 403:
                # If target is today, it's likely just not ready yet.
                if target_date == datetime.now().date():
                    logger.warning(f"Got 403 for Today's Index ({target_date}). Assuming file not generated yet.")
                    return []
                else:
                    # Generic 403 for past date - likely blocked or missing
                    logger.warning(f"Got 403 for Past Date ({target_date}). possibly file missing or blocked.")
                    # We usually want to stop if confirmed blocked, but let's return empty to keep pipeline alive.
                    return []

            if resp.status_code == 404:
                logger.warning(f"No daily index found for {target_date} (404). Possibly holiday or weekend.")
                return []
                
            resp.raise_for_status()
            
            # Parse .idx file
            lines = resp.text.splitlines()
            records = []
            
            # Find start of data (after separator line)
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
                
                # Heuristic parsing
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
