"""Cross-worker coordination for generation tasks.

Generation still keeps in-process asyncio primitives for low latency.  In a
multi-worker deployment Redis carries the signals that must cross process
boundaries: cancellation and the per-user creation lock.  Every Redis failure
falls back to the local implementation so a single-process deployment keeps
working without Redis.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from app.core.config import settings

try:  # pragma: no cover - exercised only when the optional dependency is absent
    import redis
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger(__name__)

_CANCEL_TTL_SECONDS = 24 * 60 * 60
_LOCK_TTL_MS = 60_000
_LOCK_WAIT_SECONDS = 120.0


class GenerationRuntime:
    """Small Redis-backed coordination layer with local fallbacks."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        enabled: bool | None = None,
        namespace: str = "generation_runtime",
        watch_interval: float = 1.0,
    ) -> None:
        if enabled is None:
            enabled = bool(settings.REDIS_URL) and settings.ENV == "production"
        self._enabled = bool(enabled)
        self._client = client
        self._client_resolved = client is not None or not self._enabled
        self._namespace = namespace
        self._watch_interval = watch_interval
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._watchers: dict[str, asyncio.Task] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_client(self) -> Any | None:
        if not self._enabled:
            return None
        if self._client_resolved:
            return self._client
        self._client_resolved = True
        if redis is None or not settings.REDIS_URL:
            return None
        try:
            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        except Exception:
            logger.warning("初始化生成运行态 Redis 失败，回退进程内状态", exc_info=True)
            self._client = None
        return self._client

    def _key(self, suffix: str) -> str:
        return f"{self._namespace}:{suffix}"

    def _cancel_key(self, session_id: str) -> str:
        return self._key(f"cancel:{session_id}")

    def request_cancel(self, session_id: str) -> None:
        """Set the local event and publish cancellation for other workers."""
        event = self._cancel_events.get(session_id)
        if event is not None:
            event.set()
        client = self._get_client()
        if client is None:
            return
        try:
            client.set(self._cancel_key(session_id), "1", ex=_CANCEL_TTL_SECONDS)
        except Exception:
            logger.warning(
                "写取消信号到 Redis 失败，仅本地取消 | session=%s",
                session_id,
                exc_info=True,
            )

    def is_cancel_requested(self, session_id: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            return bool(client.get(self._cancel_key(session_id)))
        except Exception:
            logger.warning(
                "读取 Redis 取消信号失败 | session=%s",
                session_id,
                exc_info=True,
            )
            return False

    def register_cancel_event(self, session_id: str, event: asyncio.Event) -> None:
        self._cancel_events[session_id] = event
        if not self._enabled or event.is_set() or session_id in self._watchers:
            return
        self._watchers[session_id] = asyncio.create_task(
            self._watch_remote_cancel(session_id, event)
        )

    def release_cancel_event(
        self, session_id: str, expected: asyncio.Event | None = None
    ) -> None:
        current = self._cancel_events.get(session_id)
        if expected is not None and current is not expected:
            return
        self._cancel_events.pop(session_id, None)
        watcher = self._watchers.pop(session_id, None)
        if watcher is not None and not watcher.done():
            watcher.cancel()
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete(self._cancel_key(session_id))
        except Exception:
            logger.warning(
                "清理 Redis 取消信号失败 | session=%s",
                session_id,
                exc_info=True,
            )

    async def _watch_remote_cancel(
        self, session_id: str, event: asyncio.Event
    ) -> None:
        try:
            while not event.is_set():
                if await asyncio.to_thread(self.is_cancel_requested, session_id):
                    event.set()
                    break
                await asyncio.sleep(self._watch_interval)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.warning(
                "监听 Redis 取消信号异常 | session=%s",
                session_id,
                exc_info=True,
            )

    @asynccontextmanager
    async def user_lock(self, user_id: str):
        """Serialize project creation for one user across workers."""
        client = self._get_client()
        if client is None:
            yield
            return

        key = self._key(f"user_lock:{user_id}")
        token = uuid.uuid4().hex
        deadline = time.monotonic() + _LOCK_WAIT_SECONDS
        acquired = False
        while time.monotonic() < deadline:
            try:
                acquired = bool(client.set(key, token, nx=True, px=_LOCK_TTL_MS))
            except Exception:
                logger.warning(
                    "获取 Redis 用户锁失败，回退本地锁 | user=%s",
                    user_id,
                    exc_info=True,
                )
                break
            if acquired:
                break
            await asyncio.sleep(0.05)

        if not acquired:
            # The caller already holds a process-local lock.  Failing open keeps
            # generation available when Redis is unhealthy.
            yield
            return

        try:
            yield
        finally:
            try:
                if client.get(key) == token:
                    client.delete(key)
            except Exception:
                logger.warning(
                    "释放 Redis 用户锁失败 | user=%s",
                    user_id,
                    exc_info=True,
                )


generation_runtime = GenerationRuntime()
