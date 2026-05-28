import requests
import os
import time
import random
from datetime import datetime, timezone, timedelta
from p1_shared.api.token_manager import TokenManager

class KisApiCore:
    """
    KIS REST API 클라이언트 기반 클래스.
    """

    REAL_URL = "https://openapi.koreainvestment.com:9443"
    MOCK_URL = "https://openapivts.koreainvestment.com:29443"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_mock: bool = False,
        token_cache_path: str = "~/.cache/tdms/kis_token.json",
        throttle_delay: float = None,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.is_mock = is_mock
        
        # 안전 마진이 적용된 속도 제한 지연 설정
        if throttle_delay is not None:
            self.throttle_delay = throttle_delay
        else:
            self.throttle_delay = 0.4 if is_mock else 0.08
            
        expanded_path = os.path.expanduser(token_cache_path)
        self.token_manager = TokenManager(expanded_path, "kis")

    @property
    def base_url(self) -> str:
        """is_mock 플래그에 따라 실전/모의 투자 URL 반환."""
        return self.MOCK_URL if self.is_mock else self.REAL_URL

    def get_headers(self, tr_id: str, extra: dict = None) -> dict:
        """
        유효한 토큰이 포함된 KIS 요청 헤더 반환.
        """
        if extra is None:
            extra = {}
            
        token = self.token_manager.get_valid_token()
        if not token:
            token = self._issue_new_token()
            
        headers = {
            "Authorization": token,
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        headers.update(extra)
        return headers

    def _issue_new_token(self) -> str:
        """KIS API에서 신규 토큰을 발급받고 저장한다."""
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"토큰 발급 실패: {e}")
            
        data = res.json()
        token_str = data.get("access_token")
        expires_dt_str = data.get("access_token_token_expired")
        
        if expires_dt_str:
            expires_at = datetime.strptime(expires_dt_str, "%Y-%m-%d %H:%M:%S")
            # KIS 시간은 기본적으로 KST 기준(UTC+9)이므로 타임존 오프셋을 KST로 설정합니다.
            kst = timezone(timedelta(hours=9))
            expires_at = expires_at.replace(tzinfo=kst)
        else:
            # Fallback if expires_dt is missing
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            
        # Ensure Bearer prefix
        bearer_token = token_str if token_str.startswith("Bearer") else f"Bearer {token_str}"
        self.token_manager.save_token(bearer_token, expires_at)
        
        return bearer_token

    def request(
        self,
        method: str,
        path: str,
        params: dict = None,
        body: dict = None,
        tr_id: str = "",
        extra_headers: dict = None,
    ) -> dict:
        """
        KIS API 요청 실행.
        - 401 응답 시: 토큰 자동 갱신 후 즉시 재시도.
        - 429(Rate Limit), 5xx(서버 오류) 또는 네트워크 장애 발생 시: 지수 백오프 기반 최대 3회 재시도.
        """
        if params is None:
            params = {}
        if body is None:
            body = {}
            
        url = f"{self.base_url}{path}"
        
        max_retries = 3
        base_delay = 2.0
        
        def _make_request():
            headers = self.get_headers(tr_id=tr_id, extra=extra_headers)
            return requests.request(method, url, headers=headers, params=params, json=body)

        for attempt in range(max_retries + 1):
            try:
                res = _make_request()
                res.raise_for_status()
                if self.throttle_delay > 0:
                    time.sleep(self.throttle_delay)
                return res.json()
            except requests.exceptions.RequestException as e:
                # HTTP 에러인 경우 상태 코드로 판단
                status_code = None
                if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                    status_code = e.response.status_code
                
                # 401 Unauthorized인 경우 토큰을 갱신하고 즉시 1회 재시도 (재시도 카운트 미소모)
                if status_code == 401:
                    try:
                        self._issue_new_token()
                        res = _make_request()
                        res.raise_for_status()
                        if self.throttle_delay > 0:
                            time.sleep(self.throttle_delay)
                        return res.json()
                    except Exception as token_err:
                        # 토큰 갱신 후에도 실패한 경우 일반 백오프 로직에 태움
                        e = token_err
                        if isinstance(token_err, requests.exceptions.HTTPError) and token_err.response is not None:
                            status_code = token_err.response.status_code

                # 403, 404, 400 등 일반적인 클라이언트 에러는 재시도 없이 즉시 실패
                if status_code is not None and 400 <= status_code < 500 and status_code not in (401, 429):
                    raise e
                
                # 마지막 시도에서도 실패했으면 예외를 밖으로 던짐
                if attempt == max_retries:
                    raise e
                
                # 지수 백오프 시간 계산 (Jitter 포함)
                delay = (base_delay * (2 ** attempt)) + random.uniform(0.0, 1.0)
                print(f"⚠️ KIS API 요청 실패 (Error: {e}). {delay:.2f}초 후 재시도합니다... (시도 {attempt + 1}/{max_retries})")
                time.sleep(delay)
