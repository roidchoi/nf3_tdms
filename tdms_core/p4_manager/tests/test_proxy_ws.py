import pytest
import asyncio
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from tdms_core.p4_manager.main import app

def test_proxy_ws_invalid_market_closes_connection():
    """
    [목적] 잘못된 market 코드(예: jp)로 요청 시 연결이 거부되거나 즉시 닫히는지 검증.
    """
    client = TestClient(app)
    # 잘못된 market 코드 'jp'
    with pytest.raises(Exception):
        with client.websocket_connect("/api/mgr/ws/logs/jp") as websocket:
            pass

@pytest.mark.asyncio
async def test_proxy_ws_client_disconnect_closes_upstream_connection(mocker):
    """
    [목적] 클라이언트(프론트엔드)가 연결을 끊었을 때, 업스트림 소켓으로의 비동기 연결 리소스가 누수 없이 닫히는지 검증.
    """
    import websockets
    
    # websockets.connect mock 정의
    mock_connection = AsyncMock()
    mock_connection.close = AsyncMock()
    mock_connection.recv = AsyncMock(side_effect=asyncio.CancelledError) # recv 루프를 강제로 멈추기 위함
    
    # patch 적용
    mock_connect = AsyncMock(return_value=mock_connection)
    mocker.patch("websockets.connect", mock_connect)
    
    # client websocket_connect mock
    client = TestClient(app)
    
    try:
        # 정상 마켓 'kr' 연결 시도 후 강제 Exception 발생하여 disconnect 모사
        with client.websocket_connect("/api/mgr/ws/logs/kr") as websocket:
            # 즉시 닫아서 WebSocketDisconnect 유도
            websocket.close()
    except Exception:
        pass
    
    # 약간의 비동기 작업 처리를 기다림
    await asyncio.sleep(0.1)
    
    # websockets.connect의 close가 결국 호출되는지 검증
    # (실제 백엔드 구현에서 finally 절에 close()가 안전하게 들어갔는지를 입증)
    assert mock_connection.close.called
