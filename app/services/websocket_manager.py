"""
WebSocket Manager

Manages WebSocket connections for real-time task notifications.
"""
import asyncio
import json
import logging
from typing import Dict, Set, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """WebSocket connection metadata"""
    websocket: WebSocket
    user_id: int
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subscriptions: Set[str] = field(default_factory=set)


class WebSocketManager:
    """
    Manages WebSocket connections and message broadcasting.

    Features:
    - User-based connection grouping (multiple connections per user)
    - Task-specific subscriptions
    - Automatic reconnection handling
    - Connection health monitoring
    - Connection limit enforcement
    """

    def __init__(self, max_connections: int = 50):
        self._connections: Dict[int, List[ConnectionInfo]] = {}
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
            current_count = sum(len(conns) for conns in self._connections.values())

            if current_count >= self._max_connections:
                logger.warning(
                    f"WebSocket connection rejected: limit reached | "
                    f"user_id={user_id} | current={current_count} | max={self._max_connections}"
                )
                await websocket.close(code=1013, reason="Connection limit reached")
                raise WebSocketDisconnect(code=1013, reason="Connection limit reached")

            await websocket.accept()
            conn_info = ConnectionInfo(websocket=websocket, user_id=user_id)

            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(conn_info)

        logger.info(f"WebSocket connected: user_id={user_id} | total={current_count + 1}")

    async def disconnect(self, user_id: int, websocket: Optional[WebSocket] = None):
        """
        Remove WebSocket connection.

        Args:
            user_id: User identifier
            websocket: Specific WebSocket to remove (if None, remove all for user)
        """
        async with self._lock:
            if user_id not in self._connections:
                return

            if websocket is None:
                # Remove all connections for user
                del self._connections[user_id]
                logger.info(f"WebSocket disconnected: user_id={user_id} (all connections)")
            else:
                # Remove specific connection
                self._connections[user_id] = [
                    conn for conn in self._connections[user_id]
                    if conn.websocket != websocket
                ]
                if not self._connections[user_id]:
                    del self._connections[user_id]
                logger.info(f"WebSocket disconnected: user_id={user_id} (specific connection)")

    async def send_personal_message(self, user_id: int, message: dict):
        """
        Send message to all of user's connections.

        Args:
            user_id: User identifier
            message: Message data (will be JSON serialized)
        """
        async with self._lock:
            conn_list = self._connections.get(user_id, [])

        if not conn_list:
            logger.warning(f"Cannot send message to user {user_id}: no connection")
            return

        failed_connections = []
        for conn_info in conn_list:
            try:
                await conn_info.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                failed_connections.append(conn_info)

        # Clean up failed connections
        if failed_connections:
            async with self._lock:
                if user_id in self._connections:
                    self._connections[user_id] = [
                        conn for conn in self._connections[user_id]
                        if conn not in failed_connections
                    ]
                    if not self._connections[user_id]:
                        del self._connections[user_id]

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
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.send_personal_message(user_id, message)

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected users.

        Args:
            message: Message data (will be JSON serialized)
        """
        async with self._lock:
            all_connections = []
            for conn_list in self._connections.values():
                all_connections.extend(conn_list)

        for conn_info in all_connections:
            try:
                await conn_info.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {conn_info.user_id}: {e}")

    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return sum(len(conns) for conns in self._connections.values())

    def get_user_count(self) -> int:
        """Get number of connected users."""
        return len(self._connections)

    def is_connected(self, user_id: int) -> bool:
        """Check if user has any active connections."""
        return user_id in self._connections and len(self._connections[user_id]) > 0


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    """获取全局 WebSocket 管理器实例"""
    return ws_manager
