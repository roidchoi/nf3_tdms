import requests
import os
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
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.is_mock = is_mock
        
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
        KIS API 요청 실행. 401 응답 시 토큰 자동 갱신 후 1회 재시도.
        """
        if params is None:
            params = {}
        if body is None:
            body = {}
            
        url = f"{self.base_url}{path}"
        
        def _make_request():
            # tr_id는 각 API 호출 시마다 다르므로 params, body 대신 필요 시 request signature에서 받거나 생략할 수 있으나,
            # 스펙에서는 request() 인자에 tr_id가 없음. 내부에서 get_headers()를 호출하려면 tr_id가 필수.
            # 테스트 케이스를 보면 core.request("GET", "/some/path") 형식으로 호출함.
            # 테스트에서는 tr_id가 필요없는 경우가 있으므로, 임시로 처리.
            # wait, test_request_returns_response_json_on_success does not pass tr_id!
            # so how does request() get headers? 
            # Let's add kwargs or just pass empty tr_id for headers if not provided.
            headers = self.get_headers(tr_id=tr_id, extra=extra_headers)
            return requests.request(method, url, headers=headers, params=params, json=body)

        try:
            res = _make_request()
            res.raise_for_status()
        except requests.HTTPError as e:
            if res.status_code == 401:
                self._issue_new_token()
                res = _make_request()
                res.raise_for_status()
            else:
                raise e
                
        return res.json()
