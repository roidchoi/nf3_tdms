# collectors/kis_rest.py

import requests
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv
import os

LOG_FILE = 'kis_api.log'

class KisAPIError(Exception):
    """한국투자증권 API 응답 에러를 위한 커스텀 예외 클래스"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class TokenManager:
    """접근 토큰 관리를 담당하는 클래스"""
    
    def __init__(self, app_key: str, app_secret: str, base_url: str, 
                 cache_file: str, logger: logging.Logger):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.cache_file = cache_file
        self.logger = logger
        
        self.access_token = ""
        self.token_expires_at = datetime.now()
        
        # 캐시 디렉토리 생성
        Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
    
    def get_valid_token(self) -> str:
        """유효한 토큰을 반환합니다. 없거나 만료되었으면 새로 발급합니다."""
        if self._is_valid():
            return self.access_token
        
        # 캐시에서 로드 시도
        if self._load_from_cache():
            if self._is_valid():
                return self.access_token
        
        # 새로 발급
        self._issue_new_token()
        return self.access_token
    
    def _is_valid(self) -> bool:
        """현재 토큰이 유효한지 확인 (2시간 여유)"""
        return (self.access_token and 
                datetime.now() < self.token_expires_at - timedelta(hours=2))
    
    def _load_from_cache(self) -> bool:
        """캐시 파일에서 토큰 로드"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            
            if cached.get('app_key') != self.app_key:
                return False
            
            self.access_token = cached.get('access_token', '')
            expires_str = cached.get('expires_at', '')
            self.token_expires_at = datetime.fromisoformat(expires_str)
            
            if self._is_valid():
                remaining = self.token_expires_at - datetime.now()
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                self.logger.info(f"✅ 캐시 토큰 로드 (유효시간: {hours}h {minutes}m)")
                return True
            
            return False
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"⚠️ 캐시 로드 실패: {e}")
            return False
    
    def _issue_new_token(self):
        """새로운 토큰 발급"""
        endpoint = '/oauth2/tokenP'
        url = self.base_url + endpoint
        
        headers = {'Content-Type': 'application/json; charset=UTF-8'}
        data = {
            'grant_type': 'client_credentials',
            'appkey': self.app_key,
            'appsecret': self.app_secret
        }
        
        try:
            self.logger.info("🔑 새 토큰 발급 요청...")
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            self.access_token = result.get('access_token')
            expires_in = result.get('expires_in', 86400)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
            
            self._save_to_cache()
            self.logger.info(f"✅ 토큰 발급 성공 ({expires_in // 3600}h)")
            
        except requests.exceptions.RequestException as e:
            self.logger.critical(f"❌ 토큰 발급 실패: {e}")
            raise
    
    def _save_to_cache(self):
        """토큰을 캐시에 저장"""
        cache_data = {
            'access_token': self.access_token,
            'expires_at': self.token_expires_at.isoformat(),
            'app_key': self.app_key,
            'issued_at': datetime.now().isoformat()
        }
        
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"💾 토큰 캐시 저장: {self.cache_file}")
        except Exception as e:
            self.logger.warning(f"⚠️ 캐시 저장 실패: {e}")
    
    def revoke(self) -> bool:
        """토큰 폐기"""
        if not self.access_token:
            return False
        
        endpoint = '/oauth2/revokeP'
        url = self.base_url + endpoint
        
        headers = {'Content-Type': 'application/json; charset=UTF-8'}
        data = {
            'appkey': self.app_key,
            'appsecret': self.app_secret,
            'token': self.access_token
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            self.access_token = ""
            self.token_expires_at = datetime.now()
            
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            
            self.logger.info("✅ 토큰 폐기 성공")
            return True
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ 토큰 폐기 실패: {e}")
            return False
    
    def get_info(self) -> Dict[str, Any]:
        """토큰 정보 반환"""
        remaining = self.token_expires_at - datetime.now()
        is_valid = remaining.total_seconds() > 0
        
        return {
            'valid': is_valid,
            'expires_at': self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S'),
            'remaining_hours': int(remaining.total_seconds() // 3600) if is_valid else 0,
            'remaining_minutes': int((remaining.total_seconds() % 3600) // 60) if is_valid else 0
        }


class RateLimiter:
    """API 호출 제한을 관리하는 클래스"""
    
    def __init__(self, calls_per_second: int):
        self.interval = 1.0 / calls_per_second
        self.last_call = 0.0
    
    def wait(self):
        """필요한 만큼 대기"""
        elapsed = time.time() - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()


class KisREST:
    """한국투자증권 REST API 래퍼 클래스"""
    
    # API 설정 상수
    REAL_BASE_URL = 'https://openapi.koreainvestment.com:9443'
    MOCK_BASE_URL = 'https://openapivts.koreainvestment.com:29443'
    REAL_RATE_LIMIT = 20  # 초당 20건
    MOCK_RATE_LIMIT = 2   # 초당 2건
    
    def __init__(self, mock: bool = False, log_level: int = 3, 
                 retry_count: int = 3, retry_delay: float = 2.0,
                 token_cache_dir: str = './.token_cache'):
        """
        KisREST 초기화
        
        :param mock: 모의투자 모드 여부
        :param log_level: 로그 상세도 (0~4)
        :param retry_count: 재시도 횟수
        :param retry_delay: 재시도 대기 시간
        :param token_cache_dir: 토큰 캐시 디렉토리
        """
        self.mock = mock
        self.log_level = log_level
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # 로거 설정
        self.logger = self._setup_logger()
        
        # 환경 변수 로드
        load_dotenv()
        self.app_key, self.app_secret = self._load_credentials()
        
        # 모드별 설정
        self.mode_name = '모의투자' if mock else '실전투자'
        self.base_url = self.MOCK_BASE_URL if mock else self.REAL_BASE_URL
        rate_limit = self.MOCK_RATE_LIMIT if mock else self.REAL_RATE_LIMIT
        
        # 토큰 관리자
        cache_file = f"{token_cache_dir}/token_{'mock' if mock else 'real'}.json"
        self.token_manager = TokenManager(
            self.app_key, self.app_secret, self.base_url, cache_file, self.logger
        )
        
        # Rate Limiter
        self.rate_limiter = RateLimiter(rate_limit)
        
        # 초기 토큰 로드
        self.token_manager.get_valid_token()
        
        self.logger.info(f"✅ [{self.mode_name}] 초기화 완료 (Rate: {rate_limit}/s)")
    
    def _setup_logger(self) -> logging.Logger:
        """로거 설정"""
        logger = logging.getLogger("KisREST")
        logger.setLevel(logging.INFO)
        
        if logger.hasHandlers():
            return logger
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # 파일 핸들러
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        # 콘솔 핸들러
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        return logger
    
    def _load_credentials(self) -> Tuple[str, str]:
        """환경 변수에서 자격 증명 로드"""
        if self.mock:
            app_key = os.getenv('MOCK_KIS_APP_KEY')
            app_secret = os.getenv('MOCK_KIS_APP_SECRET')
        else:
            app_key = os.getenv('KIS_APP_KEY')
            app_secret = os.getenv('KIS_APP_SECRET')
        
        if not app_key or not app_secret:
            raise ValueError(f"{self.mode_name} 환경변수 미설정. .env 파일을 확인하세요.")
        
        return app_key, app_secret
    
    def _format_response_log(self, response: requests.Response) -> Optional[str]:
        """응답 로그 포맷팅"""
        if self.log_level == 0:
            return None
        
        headers = response.headers
        log_parts = [f"Status={response.status_code}"]
        
        if self.log_level >= 1:
            log_parts.append(f"tr_cont={headers.get('tr_cont')}")
        
        if self.log_level >= 2:
            try:
                body_keys = list(response.json().keys())
                log_parts.append(f"keys={body_keys}")
            except:
                pass
        
        if self.log_level >= 3:
            text = response.text
            if len(text) > 200:
                log_parts.append(f"body={text[:100]}...{text[-100:]}")
            else:
                log_parts.append(f"body={text}")
        
        return ", ".join(log_parts)
    
    def _request(self, method: str, endpoint: str, tr_id: str, 
                 params: Optional[Dict] = None, data: Optional[Dict] = None,
                 extra_headers: Optional[Dict] = None) -> requests.Response:
        """
        중앙 API 요청 메소드
        
        :param method: HTTP 메소드 (GET/POST)
        :param endpoint: API 엔드포인트
        :param tr_id: 거래 ID
        :param params: 쿼리 파라미터
        :param data: Body 데이터
        :param extra_headers: 추가 헤더
        :return: Response 객체
        """
        # 헤더 구성
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'appkey': self.app_key,
            'appsecret': self.app_secret,
            'tr_id': tr_id,
            'custtype': 'P',
            'authorization': f'Bearer {self.token_manager.get_valid_token()}'
        }
        
        if extra_headers:
            headers.update(extra_headers)
        
        url = self.base_url + endpoint
        
        # 재시도 로직
        for attempt in range(self.retry_count):
            try:
                self.rate_limiter.wait()
                
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, params=params)
                else:
                    response = requests.post(url, headers=headers, json=data)
                
                # 로그
                log_msg = self._format_response_log(response)
                if log_msg:
                    self.logger.debug(f"API: {tr_id}, {log_msg}")
                
                response.raise_for_status()
                
                # 응답 검증
                result = response.json()
                rt_cd = result.get('rt_cd', '0')
                
                if rt_cd != '0':
                    msg = result.get('msg1', 'Unknown error')
                    raise KisAPIError(f"{msg} (rt_cd={rt_cd})", error_code=rt_cd)
                
                return response
                
            except requests.exceptions.HTTPError as e:
                self.logger.warning(f"HTTP 에러: {e} (시도 {attempt + 1}/{self.retry_count})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"네트워크 에러: {e} (시도 {attempt + 1}/{self.retry_count})")
            except KisAPIError:
                raise
            
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay)
        
        raise requests.exceptions.RequestException(f"API 요청 실패: {tr_id}")
    
    def _check_mock_support(self, api_name: str):
        """모의투자 미지원 API 체크"""
        if self.mock:
            raise NotImplementedError(f"{api_name}은(는) 모의투자 미지원")
    
    def _get_endpoint_config(self, api_type: str) -> Tuple[str, str]:
        """API 타입별 엔드포인트와 TR_ID 반환"""
        configs = {
            'daily_price': ('/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice', 'FHKST03010100'),
            'minute_price': ('/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice', 'FHKST03010230'),
            'holiday': ('/uapi/domestic-stock/v1/quotations/chk-holiday', 'CTCA0903R'),
            'disclosures': ('/uapi/domestic-stock/v1/quotations/news-title', 'FHKST01011800'),
            'dividend': ('/uapi/domestic-stock/v1/ksdinfo/dividend', 'HHKDB669102C0'),
            'paidin_capital': ('/uapi/domestic-stock/v1/ksdinfo/paidin-capin', 'HHKDB669100C0'),
            'bonus_issue': ('/uapi/domestic-stock/v1/ksdinfo/bonus-issue', 'HHKDB669101C0'),
            'merger_split': ('/uapi/domestic-stock/v1/ksdinfo/merger-split', 'HHKDB669104C0'),
            'capital_decrease': ('/uapi/domestic-stock/v1/ksdinfo/cap-dcrs', 'HHKDB669106C0'),
            # 재무정보 API
            'balance_sheet': ('/uapi/domestic-stock/v1/finance/balance-sheet', 'FHKST66430100'),
            'income_statement': ('/uapi/domestic-stock/v1/finance/income-statement', 'FHKST66430200'),
            'financial_ratio': ('/uapi/domestic-stock/v1/finance/financial-ratio', 'FHKST66430300'),
            'profit_ratio': ('/uapi/domestic-stock/v1/finance/profit-ratio', 'FHKST66430400'),
            'other_major_ratios': ('/uapi/domestic-stock/v1/finance/other-major-ratios', 'FHKST66430500'),
            'stability_ratio': ('/uapi/domestic-stock/v1/finance/stability-ratio', 'FHKST66430600'),
            'growth_ratio': ('/uapi/domestic-stock/v1/finance/growth-ratio', 'FHKST66430800')
        }
        return configs.get(api_type, ('', ''))
    
    # ==================== 인증 관련 ====================
    
    def revoke_token(self) -> bool:
        """토큰 폐기"""
        return self.token_manager.revoke()
    
    def get_token_info(self) -> Dict[str, Any]:
        """토큰 정보 조회"""
        info = self.token_manager.get_info()
        info['mode'] = self.mode_name
        return info
    
    # ==================== 시세 조회 ====================
    
    def fetch_daily_price(self, stock_code: str, start_date: str, end_date: str,
                         adj_price: str = '0', period_code: str = 'D') -> List[Dict]:
        """일봉/주봉/월봉/년봉 조회"""
        endpoint, tr_id = self._get_endpoint_config('daily_price')
        
        params = {
            'FID_COND_MRKT_DIV_CODE': 'J',
            'FID_INPUT_ISCD': stock_code,
            'FID_INPUT_DATE_1': start_date,
            'FID_INPUT_DATE_2': end_date,
            'FID_PERIOD_DIV_CODE': period_code,
            'FID_ORG_ADJ_PRC': adj_price
        }
        
        response = self._request('GET', endpoint, tr_id, params=params)
        return response.json().get('output2', [])
    
    def fetch_minute_price(self, stock_code: str, target_date: str, 
                          target_time: str = '150000') -> List[Dict]:
        """분봉 조회 (실전 전용)"""
        self._check_mock_support("분봉조회")
        endpoint, tr_id = self._get_endpoint_config('minute_price')
        
        params = {
            'FID_COND_MRKT_DIV_CODE': 'J',
            'FID_INPUT_ISCD': stock_code,
            'FID_INPUT_HOUR_1': target_time,
            'FID_INPUT_DATE_1': target_date,
            'FID_PW_DATA_INCU_YN': 'Y',
            'FID_FAKE_TICK_INCU_YN': ''
        }
        
        response = self._request('GET', endpoint, tr_id, params=params)
        return response.json().get('output2', [])
    
    # ==================== 휴장일/공시 ====================
    
    def check_holiday(self, bass_dt: str) -> Dict:
        """휴장일 조회 (실전 전용)"""
        self._check_mock_support("휴장일조회")
        endpoint, tr_id = self._get_endpoint_config('holiday')
        
        params = {
            'BASS_DT': bass_dt,
            'CTX_AREA_NK': '',
            'CTX_AREA_FK': ''
        }
        
        response = self._request('GET', endpoint, tr_id, params=params)
        return response.json()
    
    def fetch_disclosures(self, stock_code: str = '', target_date: str = '', 
                         target_time: str = '') -> List[Dict]:
        """공시 조회 (실전 전용)"""
        self._check_mock_support("공시조회")
        endpoint, tr_id = self._get_endpoint_config('disclosures')
        
        params = {
            'FID_NEWS_OFER_ENTP_CODE': '',
            'FID_COND_MRKT_CLS_CODE': '',
            'FID_INPUT_ISCD': stock_code,
            'FID_TITL_CNTT': '',
            'FID_INPUT_DATE_1': target_date,
            'FID_INPUT_HOUR_1': target_time,
            'FID_RANK_SORT_CLS_CODE': '',
            'FID_INPUT_SRNO': ''
        }
        
        response = self._request('GET', endpoint, tr_id, params=params)
        return response.json().get('output', [])
    
    # ==================== 예탁원 정보 ====================
    
    def _fetch_ksd_schedule(self, api_type: str, start_date: str, end_date: str,
                           stock_code: str = '', extra_params: Optional[Dict] = None) -> List[Dict]:
        """예탁원 일정 조회 공통 메소드"""
        self._check_mock_support(f"예탁원_{api_type}")
        endpoint, tr_id = self._get_endpoint_config(api_type)
        
        params = {
            'CTS': '',
            'F_DT': start_date,
            'T_DT': end_date,
            'SHT_CD': stock_code
        }
        
        if extra_params:
            params.update(extra_params)
        
        response = self._request('GET', endpoint, tr_id, params=params)
        result = response.json()
        
        # output 또는 output1 반환
        return result.get('output', result.get('output1', []))
    
    def fetch_dividend_schedule(self, start_date: str, end_date: str,
                               stock_code: str = '', div_type: str = '0') -> List[Dict]:
        """배당일정 조회"""
        return self._fetch_ksd_schedule(
            'dividend', start_date, end_date, stock_code,
            extra_params={'GB1': div_type, 'HIGH_GB': ''}
        )
    
    def fetch_paidin_capital_schedule(self, start_date: str, end_date: str,
                                     stock_code: str = '', query_type: str = '1') -> List[Dict]:
        """유상증자일정 조회"""
        return self._fetch_ksd_schedule(
            'paidin_capital', start_date, end_date, stock_code,
            extra_params={'GB1': query_type}
        )
    
    def fetch_bonus_issue_schedule(self, start_date: str, end_date: str,
                                   stock_code: str = '') -> List[Dict]:
        """무상증자일정 조회"""
        return self._fetch_ksd_schedule(
            'bonus_issue', start_date, end_date, stock_code
        )
    
    def fetch_merger_split_schedule(self, start_date: str, end_date: str,
                                    stock_code: str = '') -> List[Dict]:
        """합병/분할일정 조회"""
        return self._fetch_ksd_schedule(
            'merger_split', start_date, end_date, stock_code
        )
    
    def fetch_capital_decrease_schedule(self, start_date: str, end_date: str,
                                       stock_code: str = '') -> List[Dict]:
        """자본감소일정 조회"""
        return self._fetch_ksd_schedule(
            'capital_decrease', start_date, end_date, stock_code
        )
    
    # ==================== 재무정보 조회 ====================
    
    def _fetch_financial_data(self, api_type: str, stock_code: str, 
                             div_cls_code: str = '0') -> List[Dict]:
        """
        재무정보 조회 공통 메소드
        
        :param api_type: API 타입
        :param stock_code: 종목코드
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 재무정보 리스트
        """
        self._check_mock_support(f"재무정보_{api_type}")
        endpoint, tr_id = self._get_endpoint_config(api_type)
        
        params = {
            'FID_DIV_CLS_CODE': div_cls_code,
            'fid_cond_mrkt_div_code': 'J',
            'fid_input_iscd': stock_code
        }
        
        response = self._request('GET', endpoint, tr_id, params=params)
        return response.json().get('output', [])
    
    def fetch_balance_sheet(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        대차대조표 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 대차대조표 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - cras: 유동자산
        - fxas: 고정자산
        - total_aset: 자산총계
        - flow_lblt: 유동부채
        - fix_lblt: 고정부채
        - total_lblt: 부채총계
        - cpfn: 자본금
        - total_cptl: 자본총계
        """
        return self._fetch_financial_data('balance_sheet', stock_code, div_cls_code)
    
    def fetch_income_statement(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        손익계산서 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기, 분기는 연단위 누적합산)
        :return: 손익계산서 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - sale_account: 매출액
        - sale_cost: 매출원가
        - sale_totl_prfi: 매출총이익
        - bsop_prti: 영업이익
        - op_prfi: 경상이익
        - spec_prfi: 특별이익
        - spec_loss: 특별손실
        - thtr_ntin: 당기순이익
        """
        return self._fetch_financial_data('income_statement', stock_code, div_cls_code)
    
    def fetch_financial_ratio(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        재무비율 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 재무비율 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - grs: 매출액증가율
        - bsop_prfi_inrt: 영업이익증가율
        - ntin_inrt: 순이익증가율
        - roe_val: ROE
        - eps: EPS
        - sps: 주당매출액
        - bps: BPS
        - rsrv_rate: 유보율
        - lblt_rate: 부채비율
        """
        return self._fetch_financial_data('financial_ratio', stock_code, div_cls_code)
    
    def fetch_profit_ratio(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        수익성비율 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 수익성비율 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - cptl_ntin_rate: 총자본순이익율
        - self_cptl_ntin_inrt: 자기자본순이익율
        - sale_ntin_rate: 매출액순이익율
        - sale_totl_rate: 매출액총이익율
        """
        return self._fetch_financial_data('profit_ratio', stock_code, div_cls_code)
    
    def fetch_other_major_ratios(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        기타주요비율 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 기타주요비율 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - payout_rate: 배당성향 (비정상 데이터로 무시 권장)
        - eva: EVA
        - ebitda: EBITDA
        - ev_ebitda: EV/EBITDA
        """
        return self._fetch_financial_data('other_major_ratios', stock_code, div_cls_code)
    
    def fetch_stability_ratio(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        안정성비율 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 안정성비율 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - lblt_rate: 부채비율
        - bram_depn: 차입금의존도
        - crnt_rate: 유동비율
        - quck_rate: 당좌비율
        """
        return self._fetch_financial_data('stability_ratio', stock_code, div_cls_code)
    
    def fetch_growth_ratio(self, stock_code: str, div_cls_code: str = '0') -> List[Dict]:
        """
        성장성비율 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 성장성비율 정보 리스트
        
        응답 필드:
        - stac_yymm: 결산년월
        - grs: 매출액증가율
        - bsop_prfi_inrt: 영업이익증가율
        - equt_inrt: 자기자본증가율
        - totl_aset_inrt: 총자산증가율
        """
        return self._fetch_financial_data('growth_ratio', stock_code, div_cls_code)
    
    def fetch_all_financial_data(self, stock_code: str, div_cls_code: str = '0') -> Dict[str, List[Dict]]:
        """
        모든 재무정보를 한번에 조회 (실전 전용)
        
        :param stock_code: 종목코드 (예: '005930')
        :param div_cls_code: 분류구분 ('0': 년, '1': 분기)
        :return: 모든 재무정보를 담은 딕셔너리
        """
        self._check_mock_support("종합재무정보")
        
        return {
            'balance_sheet': self.fetch_balance_sheet(stock_code, div_cls_code),
            'income_statement': self.fetch_income_statement(stock_code, div_cls_code),
            'financial_ratio': self.fetch_financial_ratio(stock_code, div_cls_code),
            'profit_ratio': self.fetch_profit_ratio(stock_code, div_cls_code),
            'other_major_ratios': self.fetch_other_major_ratios(stock_code, div_cls_code),
            'stability_ratio': self.fetch_stability_ratio(stock_code, div_cls_code),
            'growth_ratio': self.fetch_growth_ratio(stock_code, div_cls_code)
        }


# ==================== 사용 예시 ====================
if __name__ == "__main__":
    # 실전 모드 초기화
    kis = KisREST(mock=False)
    
    # 토큰 정보 확인
    token_info = kis.get_token_info()
    print(f"토큰 상태: {'유효' if token_info['valid'] else '만료'}")
    print(f"남은 시간: {token_info['remaining_hours']}시간 {token_info['remaining_minutes']}분")
    
    # API 호출 예시
    try:
        daily_data = kis.fetch_daily_price('005930', '20250101', '20250131')
        print(f"✅ 일봉 데이터 {len(daily_data)}건 조회")
    except Exception as e:
        print(f"❌ 에러: {e}")