import os
import json
import logging

logger = logging.getLogger(__name__)

class FilePersistentDict(dict):
    """
    딕셔너리 데이터의 변경(설정, 업데이트, 팝, 클리어)이 발생할 때마다
    자동으로 로컬 JSON 파일에 상태를 직렬화하여 영구 보존하는 클래스.
    """
    def __init__(self, filepath: str, default_data: dict = None):
        self.filepath = filepath
        # 디렉토리 생성
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
            
        # 초기 파일 로드
        initial_data = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    initial_data = json.load(f)
                logger.info(f"Loaded persistent task statuses from {filepath}")
            except Exception as e:
                logger.error(f"Failed to load persistent task statuses: {e}")
                
        # 기본값 병합
        merged_data = default_data.copy() if default_data else {}
        merged_data.update(initial_data)
        
        # 안전장치: 비정상 종료(서버 다운/재시작)로 인해 'is_running' 상태로 남겨진 작업을 'interrupted'로 정정
        for k, v in merged_data.items():
            if isinstance(v, dict) and v.get("is_running") is True:
                v["is_running"] = False
                v["last_status"] = "interrupted"
                v["last_log"] = "서버 재시작으로 인해 이전 작업이 중단되었습니다."
                
        super().__init__(merged_data)
        self._save()

    def _save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(dict(self), f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save persistent task statuses: {e}")

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._save()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._save()

    def clear(self):
        super().clear()
        self._save()

    def pop(self, *args):
        res = super().pop(*args)
        self._save()
        return res
