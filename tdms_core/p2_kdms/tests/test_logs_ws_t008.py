import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from utils.log_broadcaster import LogBroadcaster

@pytest.mark.asyncio
async def test_ws_logs_broadcast_to_multiple_clients():
    """
    TC-10: 2개 이상의 WebSocket 클라이언트가 동시 접속했을 때 경쟁 없이 모든 클라이언트에 로그가 전달되는지 검증
    """
    broadcaster = LogBroadcaster()
    
    # 2개의 Mock WebSocket 객체 생성 (AsyncMock 사용)
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    
    # 연결 수립
    await broadcaster.connect(ws1)
    await broadcaster.connect(ws2)
    
    assert len(broadcaster.active_connections) == 2
    
    # 브로드캐스트 호출
    test_message = "Test log message"
    await broadcaster.broadcast(test_message)
    
    # 두 WebSocket 객체 모두 send_text가 해당 메시지로 호출되었는지 확인
    ws1.send_text.assert_called_once_with(test_message)
    ws2.send_text.assert_called_once_with(test_message)
    
    # 연결 끊기
    broadcaster.disconnect(ws1)
    assert len(broadcaster.active_connections) == 1
    assert ws1 not in broadcaster.active_connections
    assert ws2 in broadcaster.active_connections
