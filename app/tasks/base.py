"""
Base Task Classes

Provides reusable task functionality with progress tracking and error handling.
"""
import asyncio
import logging
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded, Reject
from typing import Optional, Callable, Any
import json
import os

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


class ProgressCallback:
    """Callback for task progress updates"""

    def __init__(self, task_id: str, user_id: int, ws_manager=None):
        self.task_id = task_id
        self.user_id = user_id
        self.ws_manager = ws_manager
        self._last_progress = 0

    async def update(self, progress: int, message: str = ""):
        """Update task progress and send WebSocket notification"""
        # 进度契约：任意调用方都可能传入越界值，这里统一夹到 [0, 100]
        progress = max(0, min(100, progress))
        self._last_progress = progress
        if self.ws_manager and self.user_id:
            await self.ws_manager.send_task_update(
                self.user_id,
                self.task_id,
                {
                    "status": "PROGRESS",
                    "progress": progress,
                    "message": message
                }
            )
        logger.debug(f"Task {self.task_id} progress: {progress}% - {message}")


def _run_coroutine_sync(coro):
    """在同步 Celery 回调中执行协程。

    Celery 回调通常没有运行中的事件循环，此时直接 ``asyncio.run``。若调用方
    本身处于异步上下文（异步 worker、内联测试），``asyncio.run`` 会抛
    running-loop 错误并被回调吞掉，通知静默丢失；这种情况下改到独立线程
    执行，让通知仍能送达。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class BaseTask(Task):
    """Base task class with retry, timeout, and progress tracking"""

    abstract = True
    _ws_manager = None

    @property
    def ws_manager(self):
        """Get WebSocket manager instance"""
        if self._ws_manager is None:
            from app.services.websocket_manager import ws_manager
            self._ws_manager = ws_manager
        return self._ws_manager

    def _get_progress_callback(self, task_id: str, user_id: int) -> ProgressCallback:
        """Create the shared progress publisher used by worker tasks."""
        return ProgressCallback(task_id, int(user_id), self.ws_manager)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error(f"Task {task_id} failed: {exc}", exc_info=einfo)
        user_id = kwargs.get("user_id", 0) if kwargs else 0
        try:
            _run_coroutine_sync(self._notify_failure(task_id, user_id, str(exc)))
        except Exception as e:
            logger.error(f"WebSocket 通知失败: {e}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        logger.warning(f"Task {task_id} retrying: {exc}")
        self.update_state(
            state="RETRYING",
            meta={
                "error": str(exc),
                "retry_count": self.request.retries,
                "max_retries": self.max_retries
            }
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        logger.info(f"Task {task_id} succeeded")
        user_id = kwargs.get("user_id", 0) if kwargs else 0
        try:
            _run_coroutine_sync(self._notify_success(task_id, user_id, retval))
        except Exception as e:
            logger.error(f"WebSocket 通知失败: {e}")

    def on_timeout(self, soft, timeout):
        """Handle task timeout"""
        task_id = self.request.id
        logger.warning(f"Task {task_id} timeout (soft={soft}, timeout={timeout})")
        try:
            _run_coroutine_sync(self._notify_timeout(task_id))
        except Exception as e:
            logger.error(f"WebSocket 通知失败: {e}")

    async def _notify_failure(self, task_id: str, user_id: int, error: str):
        """Send failure notification via WebSocket"""
        if self.ws_manager and user_id:
            await self.ws_manager.send_task_update(
                user_id,
                task_id,
                {
                    "status": "FAILURE",
                    "error": error
                }
            )

    async def _notify_success(self, task_id: str, user_id: int, result: Any):
        """Send success notification via WebSocket"""
        if self.ws_manager and user_id:
            await self.ws_manager.send_task_update(
                user_id,
                task_id,
                {
                    "status": "SUCCESS",
                    "result": result
                }
            )

    async def _notify_timeout(self, task_id: str):
        """Send timeout notification via WebSocket"""
        logger.info(f"Task {task_id} timed out")


def handle_task_result(result: Any, max_size: int = 1024 * 1024) -> dict:
    """
    Handle task result, storing large results in filesystem.

    Args:
        result: Task result data
        max_size: Maximum size in bytes (default 1MB)

    Returns:
        dict with result or file path reference
    """
    result_str = json.dumps(result, ensure_ascii=False, default=str)

    if len(result_str.encode('utf-8')) > max_size:
        import re
        raw_task_id = result.get('task_id', 'unknown') if isinstance(result, dict) else 'unknown'
        safe_task_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(raw_task_id))
        if not safe_task_id:
            safe_task_id = 'unknown'
        file_path = f"/tmp/task_results/{safe_task_id}.json"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, default=str)
        return {
            "stored": "file",
            "path": file_path,
            "size": len(result_str.encode('utf-8'))
        }

    return {"stored": "inline", "data": result}


def parse_priority(priority: str) -> int:
    """
    Parse priority string to integer value.

    Args:
        priority: "high", "medium", or "low"

    Returns:
        Integer priority (1-10, 10 is highest)
    """
    priority_map = {
        "high": 8,
        "medium": 5,
        "low": 2
    }
    # Celery 重放/直连调用可能绕过 API 的 Enum 约束，非字符串一律落默认档
    if not isinstance(priority, str):
        return priority_map["medium"]
    return priority_map.get(priority.lower(), 5)


def parse_timeout(timeout: Optional[int], default: int = 300) -> int:
    """
    Parse and validate timeout value.

    Args:
        timeout: Timeout in seconds or None
        default: Default timeout if None

    Returns:
        Valid timeout in seconds
    """
    if timeout is None:
        return default
    return max(30, min(timeout, 3600))
