import requests
import os
import time
from datetime import datetime, timezone, timedelta
from p1_shared.api.token_manager import TokenManager

class KiwoomApiCore:
    """
    Kiwoom REST API 클라이언트 (한국 시장 전용).
    TokenManager를 통해 토큰 캐시를 관리하며, 요청 시 자동으로 유효한 헤더를 구성한다.
    """

    BASE_URL = "https://api.kiwoom.com"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        token_cache_path: str = "~/.cache/tdms/kiwoom_token.json",
        throttle_delay: float = 0.25,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.throttle_delay = throttle_delay
        expanded_path = os.path.expanduser(token_cache_path)
        self.token_manager = TokenManager(expanded_path, "kiwoom")

    def get_headers(self) -> dict:
        """
        유효한 토큰이 포함된 요청 헤더 반환.
        토큰이 없거나 만료 시 자동으로 신규 발급 후 캐시 저장.
        """
        token = self.token_manager.get_valid_token()
        if not token:
            token = self._issue_new_token()
            
        return {
            "Authorization": token
        }

    def _issue_new_token(self) -> str:
        """Kiwoom API에서 신규 토큰을 발급받고 저장한다."""
        url = f"{self.BASE_URL}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret
        }
        
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"토큰 발급 실패: {e}")
            
        data = res.json()
        token_str = data.get("access_token") or data.get("token")
        expires_dt_str = data.get("expires_dt")
        
        # Kiwoom은 한국 시간이므로 KST(UTC+9) 처리
        expires_at = datetime.strptime(expires_dt_str, "%Y%m%d%H%M%S")
        kst = timezone(timedelta(hours=9))
        expires_at = expires_at.replace(tzinfo=kst)
        
        # 만약 Bearer가 이미 포함되어 있지 않다면 추가
        bearer_token = token_str if token_str.startswith("Bearer") else f"Bearer {token_str}"
        self.token_manager.save_token(bearer_token, expires_at)
        
        return bearer_token

    def request(
        self,
        method: str,
        path: str,
        params: dict = {},
    ) -> dict:
        """Kiwoom API 요청 실행."""
        url = f"{self.BASE_URL}{path}"
        headers = self.get_headers()
        
        res = requests.request(method, url, headers=headers, params=params)
        res.raise_for_status()
        
        if self.throttle_delay > 0:
            time.sleep(self.throttle_delay)
            
        return res.json()
