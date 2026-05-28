import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class LogBroadcaster:
    def __init__(self):
        self.active_connections = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except KeyError:
            pass

    async def broadcast(self, message: str):
        async with self._lock:
            connections = list(self.active_connections)
        
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send websocket message: {e}")
                try:
                    self.active_connections.remove(connection)
                except KeyError:
                    pass

log_broadcaster = LogBroadcaster()

