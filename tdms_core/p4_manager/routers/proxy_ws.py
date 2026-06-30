# tdms_core/p4_manager/routers/proxy_ws.py
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query
import websockets
from websockets.exceptions import ConnectionClosed
from p1_shared.utils.env_detector import EnvDetector

logger = logging.getLogger("p4_manager.proxy_ws")

router = APIRouter()
detector = EnvDetector()

@router.websocket("/ws/logs/{market}")
async def websocket_proxy_endpoint(
    websocket: WebSocket,
    market: str,
    log_file: Optional[str] = Query(None)
):
    """
    [목적] 클라이언트의 WebSocket 연결을 받아, market 인자에 따라
          대상 백엔드의 웹소켓 서버에 비동기 연결하여 양방향 프록시 터널링을 구성합니다.
    """
    if market not in ("kr", "us"):
        logger.warning(f"Invalid market request for logs proxy: {market}")
        # 400 Bad Request에 해당하는 WebSocket Close Code 1008 사용
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # 타겟 백엔드 WebSocket 주소 수립 (DNS 장애 대비 get_service_host 사용)
    if market == "kr":
        host = detector.get_service_host("p2_kdms")
        target_url = f"ws://{host}:8000/ws/logs"
    else:
        host = detector.get_service_host("p3_usdms")
        target_url = f"ws://{host}:8005/api/admin/ws/logs"
        if log_file:
            target_url += f"?log_file={log_file}"

    logger.info(f"Connecting to upstream WebSocket: {target_url}")

    upstream_conn = None
    try:
        upstream_conn = await websockets.connect(target_url)
    except Exception as e:
        logger.error(f"Failed to connect to upstream WebSocket {target_url}: {e}")
        try:
            await websocket.send_text(f"[SYSTEM ERROR] {market} backend log service offline: {str(e)}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
        return

    # 업스트림 데이터 중계 태스크 및 클라이언트 상태 감시 태스크 동시 기동
    async def recv_from_upstream():
        try:
            while True:
                message = await upstream_conn.recv()
                # websockets.recv는 bytes 또는 str을 반환
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                await websocket.send_text(message)
        except (ConnectionClosed, asyncio.CancelledError):
            logger.info("Upstream WebSocket connection closed or task cancelled.")
        except Exception as e:
            logger.error(f"Error reading from upstream: {e}")

    async def monitor_client():
        try:
            while True:
                # 클라이언트의 명시적 종료 감시
                await websocket.receive_text()
        except (WebSocketDisconnect, asyncio.CancelledError):
            logger.info("Client WebSocket disconnected or task cancelled.")
        except Exception as e:
            logger.error(f"Error reading from client: {e}")

    # 두 비동기 태스크를 태스크 그룹 또는 gather로 구동하여 한쪽이 종료되면 다른 쪽도 함께 취소 처리
    try:
        await asyncio.gather(
            recv_from_upstream(),
            monitor_client(),
            return_exceptions=True
        )
    finally:
        # 리소스 누수 방지를 위한 upstream 커넥션 강제 종료 보장
        if upstream_conn:
            logger.info(f"Closing upstream WebSocket for market {market}")
            await upstream_conn.close()
