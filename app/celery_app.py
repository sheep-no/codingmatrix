"""
Celery Application Configuration

Task Queue System - Powered by Celery + Redis
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
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
        "app.tasks.ppt_tasks",
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
        "app.tasks.ppt_tasks.*": {"queue": "ppt"},
    },
    task_annotations={
        "app.tasks.project_tasks.*": {"rate_limit": "10/m"},
        "app.tasks.code_tasks.*": {"rate_limit": "60/m"},
        "app.tasks.ppt_tasks.*": {"rate_limit": "10/m"},
    },
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "1")),
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "50")),
    worker_disable_rate_limits=False,
    broker_connection_retry_on_startup=True,
)


def _sync_set_task_status(
    task_id: str,
    status: str,
    error_message: Optional[str] = None,
    increment_retry: bool = False,
):
    """将 Celery 状态归一化后写入任务表，并拒绝覆盖已落库的终态。

    Celery 的 `state`（FAILURE/RETRY/REVOKED）与任务表词表不同，直接落库会写入
    词表外取值，使 retry/recover/cancel 端点与终态判定失效；`acks_late` 重投递
    及迟到的信号也会把终态任务改回运行中，因此终态任务只允许保持原状态。
    """
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.models.task import CELERY_STATE_TO_TASK_STATUS, TERMINAL_TASK_STATUSES, Task

        normalized = CELERY_STATE_TO_TASK_STATUS.get(str(status or "").lower())
        if normalized is None:
            logger.warning(f"Skip unknown celery state | task_id={task_id} | state={status}")
            return

        db_url = os.getenv("DATABASE_URL", "sqlite:///app.db").replace("+aiosqlite", "")
        engine = create_engine(db_url)

        with Session(engine) as session:
            task = session.execute(select(Task).where(Task.task_id == task_id)).scalar_one_or_none()
            if not task:
                return
            if task.status in TERMINAL_TASK_STATUSES and normalized != task.status:
                logger.info(
                    f"Skip override on terminal task | task_id={task_id} "
                    f"| {task.status} -> {normalized}"
                )
                return
            task.status = normalized
            if normalized == "running" and task.started_at is None:
                task.started_at = datetime.now(timezone.utc)
            if error_message is not None:
                task.error_message = error_message
            if increment_retry:
                task.retry_count = (task.retry_count or 0) + 1
            if normalized in TERMINAL_TASK_STATUSES:
                task.completed_at = task.completed_at or datetime.now(timezone.utc)
            session.commit()
    except Exception as e:
        logger.error(f"Failed to sync task status: {e}")


def _sync_update_task_status(task_id: str, status: str):
    """同步更新任务状态到数据库（Celery worker 中使用）"""
    _sync_set_task_status(task_id, status)


def _sync_notify_failure(task_id: str, error: str):
    """同步发送失败通知"""
    _sync_set_task_status(task_id, "failure", error_message=error)


def _sync_notify_retry(task_id: str, error: str):
    """同步发送重试通知"""
    _sync_set_task_status(task_id, "retry", increment_retry=True)


def setup_celery_signals():
    """Setup Celery signal handlers for task status updates"""

    @task_prerun.connect
    def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
        """任务开始执行"""
        logger.debug(f"Task prerun: {task_id}")
        _sync_update_task_status(task_id, "running")

    @task_postrun.connect
    def task_postrun_handler(sender=None, task_id=None, task=None, state=None, **kwargs):
        """任务执行完成"""
        logger.debug(f"Task postrun: {task_id} state={state}")
        _sync_update_task_status(task_id, state.lower() if state else "unknown")

    @task_failure.connect
    def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
        """任务失败"""
        logger.error(f"Task failure: {task_id} error={exception}")
        _sync_notify_failure(task_id, str(exception))

    @task_retry.connect
    def task_retry_handler(sender=None, task_id=None, exception=None, **kwargs):
        """任务重试"""
        logger.warning(f"Task retry: {task_id} error={exception}")
        _sync_notify_retry(task_id, str(exception))

    @task_revoked.connect
    def task_revoked_handler(sender=None, task_id=None, task=None, terminated=None, signum=None, **kwargs):
        """任务被撤销"""
        logger.info(f"Task revoked: {task_id}")
        _sync_update_task_status(task_id, "cancelled")


setup_celery_signals()
celery_app.autodiscover_tasks(["app.tasks"], force=True)
