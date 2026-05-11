"""
Celery Application Configuration

Task Queue System - Powered by Celery + Redis
"""
import os
import asyncio
import logging
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure, task_retry, task_revoked

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "codingmatrix",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.project_tasks",
        "app.tasks.code_tasks",
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=int(os.getenv("TASK_TIME_LIMIT", "300")),
    task_soft_time_limit=int(os.getenv("TASK_SOFT_TIME_LIMIT", "270")),
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=604800,
    task_default_priority=5,
    task_create_missing_queues=True,
    task_routes={
        "app.tasks.project_tasks.*": {"queue": "tasks"},
        "app.tasks.code_tasks.*": {"queue": "tasks"},
    },
    task_annotations={
        "app.tasks.project_tasks.*": {"rate_limit": "10/m"},
        "app.tasks.code_tasks.*": {"rate_limit": "60/m"},
    },
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "1")),
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "50")),
    worker_disable_rate_limits=False,
    broker_connection_retry_on_startup=True,
)


def setup_celery_signals():
    """Setup Celery signal handlers for WebSocket notifications"""

    @task_prerun.connect
    def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
        """任务开始执行"""
        logger.debug(f"Task prerun: {task_id}")
        asyncio.create_task(_async_update_task_status(task_id, "running"))

    @task_postrun.connect
    def task_postrun_handler(sender=None, task_id=None, task=None, state=None, **kwargs):
        """任务执行完成"""
        logger.debug(f"Task postrun: {task_id} state={state}")
        asyncio.create_task(_async_update_task_status(task_id, state.lower() if state else "unknown"))

    @task_failure.connect
    def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
        """任务失败"""
        logger.error(f"Task failure: {task_id} error={exception}")
        asyncio.create_task(_async_notify_failure(task_id, str(exception)))

    @task_retry.connect
    def task_retry_handler(sender=None, task_id=None, exception=None, **kwargs):
        """任务重试"""
        logger.warning(f"Task retry: {task_id} error={exception}")
        asyncio.create_task(_async_notify_retry(task_id, str(exception)))

    @task_revoked.connect
    def task_revoked_handler(sender=None, task_id=None, task=None, terminated=None, signum=None, **kwargs):
        """任务被撤销"""
        logger.info(f"Task revoked: {task_id}")
        asyncio.create_task(_async_update_task_status(task_id, "cancelled"))


async def _async_update_task_status(task_id: str, status: str):
    """异步更新任务状态到数据库"""
    try:
        from app.db.database import async_session
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.task_id == task_id))
            task = result.scalar_one_or_none()

            if task:
                task.status = status
                if status == "running":
                    from datetime import datetime
                    task.started_at = datetime.utcnow()
                await db.commit()

                from app.services.websocket_manager import ws_manager
                if task.user_id:
                    await ws_manager.send_task_update(
                        task.user_id,
                        task_id,
                        {"status": status, "progress": task.progress}
                    )
    except Exception as e:
        logger.error(f"Failed to update task status: {e}")


async def _async_notify_failure(task_id: str, error: str):
    """异步发送失败通知"""
    try:
        from app.db.database import async_session
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.task_id == task_id))
            task = result.scalar_one_or_none()

            if task:
                task.status = "failed"
                task.error_message = error
                await db.commit()

                from app.services.websocket_manager import ws_manager
                if task.user_id:
                    await ws_manager.send_task_update(
                        task.user_id,
                        task_id,
                        {"status": "failed", "error": error}
                    )
    except Exception as e:
        logger.error(f"Failed to notify failure: {e}")


async def _async_notify_retry(task_id: str, error: str):
    """异步发送重试通知"""
    try:
        from app.db.database import async_session
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.task_id == task_id))
            task = result.scalar_one_or_none()

            if task:
                task.status = "retrying"
                task.retry_count = (task.retry_count or 0) + 1
                await db.commit()

                from app.services.websocket_manager import ws_manager
                if task.user_id:
                    await ws_manager.send_task_update(
                        task.user_id,
                        task_id,
                        {
                            "status": "retrying",
                            "retry_count": task.retry_count,
                            "error": error
                        }
                    )
    except Exception as e:
        logger.error(f"Failed to notify retry: {e}")


setup_celery_signals()
celery_app.autodiscover_tasks(["app.tasks"], force=True)