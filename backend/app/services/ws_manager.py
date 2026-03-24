"""WebSocket 连接管理器"""

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.utils.logger import logger

MAX_CONNECTIONS_PER_TASK = 10
MAX_TOTAL_CONNECTIONS = 500


class ConnectionLimitError(Exception):
    """Raised when connection limits are exceeded."""


class WebSocketManager:
    """维护 task_id → set[WebSocket] 映射，提供 connect/disconnect/broadcast。"""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._pending_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._pong_received: set[int] = set()

    def get_connections(self, task_id: str) -> set[WebSocket]:
        return self._connections.get(task_id, set())

    def _task_connection_count(self, task_id: str) -> int:
        return len(self._connections.get(task_id, set())) + len(
            self._pending_connections.get(task_id, set())
        )

    def _total_connection_count(self) -> int:
        return sum(len(s) for s in self._connections.values()) + sum(
            len(s) for s in self._pending_connections.values()
        )

    async def connect(self, task_id: str, ws: WebSocket, *, ready: bool = True) -> None:
        if self._task_connection_count(task_id) >= MAX_CONNECTIONS_PER_TASK:
            raise ConnectionLimitError(
                f"Max connections per task ({MAX_CONNECTIONS_PER_TASK}) exceeded"
            )
        if self._total_connection_count() >= MAX_TOTAL_CONNECTIONS:
            raise ConnectionLimitError(
                f"Max total connections ({MAX_TOTAL_CONNECTIONS}) exceeded"
            )
        if ready:
            self._connections[task_id].add(ws)
        else:
            self._pending_connections[task_id].add(ws)
        logger.bind(task_id=task_id).debug(
            "WS registered; ready={} total={}",
            ready,
            self._task_connection_count(task_id),
        )

    def activate(self, task_id: str, ws: WebSocket) -> None:
        if ws in self._pending_connections.get(task_id, set()):
            self._pending_connections[task_id].discard(ws)
            if not self._pending_connections[task_id]:
                self._pending_connections.pop(task_id, None)
            self._connections[task_id].add(ws)
            logger.bind(task_id=task_id).debug("WS activated")

    def disconnect(self, task_id: str, ws: WebSocket) -> None:
        self._pong_received.discard(id(ws))
        self._connections.get(task_id, set()).discard(ws)
        if task_id in self._connections and not self._connections[task_id]:
            del self._connections[task_id]
        self._pending_connections.get(task_id, set()).discard(ws)
        if task_id in self._pending_connections and not self._pending_connections[task_id]:
            del self._pending_connections[task_id]
        logger.bind(task_id=task_id).debug("WS disconnected")

    async def broadcast(self, task_id: str, message: dict[str, Any]) -> None:
        """Send JSON message to all connections for task_id; silently drop broken ones."""
        payload = json.dumps(message, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(task_id, set())):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.bind(task_id=task_id).warning(
                    "WS send failed, removing: {}", exc
                )
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)

    def record_pong(self, ws: WebSocket) -> None:
        """Called by the route handler when a pong message is received."""
        self._pong_received.add(id(ws))

    async def run_heartbeat(
        self,
        ws: WebSocket,
        task_id: str,
        ping_interval: float = 30.0,
        timeout: float = 60.0,
    ) -> None:
        """Send ping every ping_interval; close if no pong within timeout."""
        try:
            while True:
                await asyncio.sleep(ping_interval)
                self._pong_received.discard(id(ws))
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    return
                deadline = timeout - ping_interval
                start = asyncio.get_event_loop().time()
                step = min(0.05, deadline / 10)
                while (asyncio.get_event_loop().time() - start) < deadline:
                    if id(ws) in self._pong_received:
                        break
                    await asyncio.sleep(step)
                else:
                    logger.bind(task_id=task_id).warning(
                        "WS heartbeat timeout, closing"
                    )
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    return
        finally:
            self._pong_received.discard(id(ws))


# Singleton — shared across routers
ws_manager = WebSocketManager()
