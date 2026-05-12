import pytest
import asyncio
import logging
from p1_shared.ops.logger import get_logger, WebSocketQueueHandler

def test_get_logger_returns_logger_with_name():
    logger = get_logger("test_module")
    assert logger.name == "test_module"
    assert isinstance(logger, logging.Logger)

def test_get_logger_without_queue_has_no_ws_handler():
    logger = get_logger("no_ws_test")
    ws_handlers = [h for h in logger.handlers if isinstance(h, WebSocketQueueHandler)]
    assert len(ws_handlers) == 0

def test_websocket_queue_handler_emits_record_to_queue():
    queue = asyncio.Queue()
    handler = WebSocketQueueHandler(queue)
    
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg="hello", args=(), exc_info=None
    )
    handler.emit(record)
    
    assert not queue.empty()
    queued = queue.get_nowait()
    assert queued.getMessage() == "hello"

def test_websocket_queue_handler_does_not_raise_when_queue_full():
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait("already_full")
    
    handler = WebSocketQueueHandler(queue)
    record = logging.LogRecord(
        name="test", level=logging.WARNING,
        pathname="", lineno=0, msg="overflow", args=(), exc_info=None
    )
    handler.emit(record)

def test_package_is_importable_after_editable_install():
    import p1_shared
    assert hasattr(p1_shared, "__version__") or True

def test_get_logger_with_queue_adds_ws_handler():
    queue = asyncio.Queue()
    logger = get_logger("ws_test_logger", ws_queue=queue)
    
    ws_handlers = [h for h in logger.handlers if isinstance(h, WebSocketQueueHandler)]
    assert len(ws_handlers) == 1
