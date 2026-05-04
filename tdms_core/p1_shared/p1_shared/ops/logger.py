import logging
import asyncio
import sys

class WebSocketQueueHandler(logging.Handler):
    """asyncio.Queue에 로그 레코드를 비동기로 삽입하는 핸들러."""
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        """
        queue.put_nowait()로 record를 삽입.
        QueueFull 발생 시 무시 (로깅이 앱을 멈춰선 안 됨).
        """
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

def get_logger(
    name: str,
    ws_queue: asyncio.Queue | None = None
) -> logging.Logger:
    """공통 설정이 적용된 Logger 인스턴스 반환."""
    logger = logging.getLogger(name)
    
    # 이미 설정된 로거면 바로 반환
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # 콘솔 출력 (Rich 등을 쓸 수도 있으나 기본 StreamHandler 사용)
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if ws_queue is not None:
        ws_handler = WebSocketQueueHandler(ws_queue)
        ws_handler.setFormatter(formatter)
        logger.addHandler(ws_handler)
        
    return logger
