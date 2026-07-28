import logging
from typing import List

class SilentLoopContext:
    """
    고빈도 루프 실행 동안 특정 로거들의 레벨을 일시적으로 WARNING(또는 지정 레벨)으로 조정하여
    불필요한 반복 로그 노이즈를 억제하는 컨텍스트 매니저입니다.
    """
    def __init__(self, logger_names: List[str], target_level: int = logging.WARNING):
        self.logger_names = logger_names
        self.target_level = target_level
        self.original_levels = {}

    def __enter__(self):
        for name in self.logger_names:
            logger = logging.getLogger(name)
            self.original_levels[name] = logger.level
            # 0(NOTSET) 또는 지정된 레벨보다 하위 레벨인 경우에만 강제로 레벨 변경
            # 만약 이미 WARNING이나 ERROR 등으로 수동 설정되어 있다면 유지
            logger.setLevel(self.target_level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for name in self.logger_names:
            logger = logging.getLogger(name)
            original = self.original_levels.get(name)
            if original is not None:
                logger.setLevel(original)
