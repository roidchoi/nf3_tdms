#
# log_utils.py
#
"""
PRD 4.1.4: 실시간 로그 스트리밍을 위한 WebSocket 핸들러

- 로그 레코드를 비동기 큐(asyncio.Queue)에 저장
- FastAPI의 WebSocket 엔드포인트에서 이 큐를 구독하여 로그를 클라이언트로 전송
"""
import logging
import asyncio
from typing import List

class PollingLogFilter(logging.Filter):
    """
    /tasks/status 엔드포인트의 200 OK 로그(Polling)를 필터링하여
    콘솔 노이즈를 줄이는 필터
    """
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        
        # 해당 경로가 포함된 모든 로그를 출력하지 않음 (False 반환)
        if "/api/v1/admin/tasks/status" in msg:
            return False
            
        return True

class WebSocketQueueHandler(logging.Handler):
    """
    로그 레코드를 asyncio.Queue에 넣는 커스텀 로깅 핸들러입니다.
    """
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        """ 로그 레코드를 포맷하여 큐에 삽입 """
        log_entry = self.format(record)
        try:
            # 비동기 이벤트 루프가 실행 중이지 않을 때를 대비
            asyncio.get_running_loop().call_soon_threadsafe(
                self.queue.put_nowait, log_entry
            )
        except RuntimeError:
            try:
                self.queue.put_nowait(log_entry)
            except asyncio.QueueFull:
                print(f"Log queue is full. Dropping log: {log_entry}")
            except Exception as e:
                print(f"Failed to put log in queue: {e}")
        except asyncio.QueueFull:
             # 큐가 가득 찼을 경우 로그 유실 (비-블로킹)
            print(f"Log queue is full. Dropping log: {log_entry}")


def setup_websocket_logging(log_queue: asyncio.Queue):
    """
    루트 로거에 WebSocket 핸들러를 설정합니다.
    main.py의 lifespan에서 호출됩니다.
    
    :param log_queue: 로그를 수신할 asyncio.Queue
    """
    formatter = logging.Formatter(
        "[%(asctime)s | %(levelname)s | %(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    queue_handler = WebSocketQueueHandler(log_queue)
    queue_handler.setLevel(logging.INFO)
    queue_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    if not any(isinstance(h, WebSocketQueueHandler) for h in root_logger.handlers):
        root_logger.addHandler(queue_handler)
        root_logger.info("--- WebSocket 로깅 핸들러 설정 완료 ---")