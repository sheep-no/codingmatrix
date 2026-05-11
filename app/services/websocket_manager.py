"""
WebSocket Manager

Manages WebSocket connections for real-time task notifications.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """WebSocket connection metadata"""
    websocket: WebSocket
    user_id: int
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Set[str] = field(default_factory=set)


class WebSocketManager:
    """
    Manages WebSocket connections and message broadcasting.

    Features:
    - User-based connection grouping
    - Task-specific subscriptions
    - Automatic reconnection handling
    - Connection health monitoring
    - Connection limit enforcement
    """

    def __init__(self, max_connections: int = 50):
        self._connections: Dict[int, ConnectionInfo] = {}
        self._lock = asyncio.Lock()
        self._max_connections = max_connections

    async def connect(self, user_id: int, websocket: WebSocket):
        """
        Accept and register a new WebSocket connection.

        Args:
            user_id: User identifier
            websocket: FastAPI WebSocket instance

        Raises:
            WebSocketDisconnect: If connection limit is reached
        """
        async with self._lock:
            current_count = len(self._connections)

            if current_count >= self._max_connections:
                logger.warning(
                    f"WebSocket connection rejected: limit reached | "
                    f"user_id={user_id} | current={current_count} | max={self._max_connections}"
                )
                await websocket.close(code=1013, reason="Connection limit reached")
                raise WebSocketDisconnect(code=1013, reason="Connection limit reached")

            await websocket.accept()
            conn_info = ConnectionInfo(websocket=websocket, user_id=user_id)
            self._connections[user_id] = conn_info

        logger.info(f"WebSocket connected: user_id={user_id} | total={current_count + 1}")

    async def disconnect(self, user_id: int):
        """
        Remove WebSocket connection.

        Args:
            user_id: User identifier
        """
        async with self._lock:
            if user_id in self._connections:
                del self._connections[user_id]
                logger.info(f"WebSocket disconnected: user_id={user_id}")

    async def send_personal_message(self, user_id: int, message: dict):
        """
        Send message to specific user's connection.

        Args:
            user_id: User identifier
            message: Message data (will be JSON serialized)
        """
        async with self._lock:
            conn_info = self._connections.get(user_id)

        if conn_info is None:
            logger.warning(f"Cannot send message to user {user_id}: no connection")
            return

        try:
            await conn_info.websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to user {user_id}: {e}")
            self.disconnect(user_id)

    async def send_task_update(
        self,
        user_id: int,
        task_id: str,
        data: dict
    ):
        """
        Send task status update to user.

        Args:
            user_id: User identifier
            task_id: Task identifier
            data: Task status data
        """
        message = {
            "type": "task_update",
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        await self.send_personal_message(user_id, message)

    async def send_progress(
        self,
        user_id: int,
        task_id: str,
        progress: int,
        message: str = ""
    ):
        """
        Send task progress update.

        Args:
            user_id: User identifier
            task_id: Task identifier
            progress: Progress percentage (0-100)
            message: Progress description
        """
        await self.send_task_update(
            user_id,
            task_id,
            {
                "status": "PROGRESS",
                "progress": progress,
                "message": message
            }
        )

    async def broadcast(self, message: dict, exclude_users: set = None):
        """
        Broadcast message to all connected users.

        Args:
            message: Message data
            exclude_users: User IDs to exclude from broadcast
        """
        exclude_users = exclude_users or set()

        async with self._lock:
            connections = list(self._connections.items())

        for user_id, conn_info in connections:
            if user_id in exclude_users:
                continue

            try:
                await conn_info.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                self.disconnect(user_id)

    async def get_connection_count(self) -> int:
        """Get number of active connections (thread-safe)."""
        async with self._lock:
            return len(self._connections)

    async def get_connection_info(self) -> dict:
        """Get connection statistics (thread-safe)."""
        async with self._lock:
            return {
                "current": len(self._connections),
                "max": self._max_connections,
                "available": self._max_connections - len(self._connections)
            }

    async def set_max_connections(self, max_connections: int):
        """Update max connections limit dynamically."""
        async with self._lock:
            self._max_connections = max_connections
        logger.info(f"WebSocket max connections updated: {max_connections}")

    async def get_user_connection(self, user_id: int) -> Optional[ConnectionInfo]:
        """Get connection info for a user (thread-safe)."""
        async with self._lock:
            return self._connections.get(user_id)


def _get_max_connections() -> int:
    """Get max connections from config, with fallback."""
    try:
        from app.core.config import settings
        return getattr(settings, 'WS_MAX_CONNECTIONS', 50)
    except Exception:
        return 50


# Lazy initialization singleton
_ws_manager_instance: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    """Get or create WebSocketManager singleton."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = WebSocketManager(max_connections=_get_max_connections())
    return _ws_manager_instance


# Backward compatible module-level access (lazy)
class _WsManagerProxy:
    """Proxy for backward compatible ws_manager access."""
    _instance: Optional[WebSocketManager] = None

    def __getattr__(self, name):
        return getattr(get_ws_manager(), name)


ws_manager = _WsManagerProxy()