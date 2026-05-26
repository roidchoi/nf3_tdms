from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

class TokenManager:
    """
    파일 기반 API 토큰 캐시 관리자.
    토큰을 JSON 파일로 저장하고, 만료 여부를 판단하여 반환한다.
    """

    def __init__(self, cache_path: str, token_type: str, min_buffer_hours: float = 5.0) -> None:
        self.cache_path = Path(cache_path)
        self.token_type = token_type
        self.min_buffer = timedelta(hours=min_buffer_hours)

    def get_valid_token(self) -> str | None:
        """
        유효한 토큰 반환. 캐시 파일이 없거나 만료 시 None 반환.
        """
        if not self.is_valid():
            return None
            
        try:
            data = json.loads(self.cache_path.read_text())
            return data["token"]
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    def save_token(self, token: str, expires_at: datetime) -> None:
        """
        토큰과 만료 시각을 JSON 파일로 저장.
        부모 디렉토리가 없으면 자동 생성(mkdir -p).
        """
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": token,
            "expires_at": expires_at.isoformat()
        }
        self.cache_path.write_text(json.dumps(data))

    def is_valid(self) -> bool:
        """
        현재 캐시된 토큰의 유효성 확인.
        설정된 버퍼(기본 5시간) 이상 남아있을 때만 유효함.
        """
        if not self.cache_path.exists():
            return False
            
        try:
            data = json.loads(self.cache_path.read_text())
            expires_at = datetime.fromisoformat(data["expires_at"])
            now = datetime.now(timezone.utc)
            return (expires_at - now) > self.min_buffer
        except (json.JSONDecodeError, KeyError, ValueError):
            return False
