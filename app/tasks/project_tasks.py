"""
Project Generation Tasks

Celery tasks for AI project code generation.
"""
import asyncio
import logging
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import BaseTask, parse_priority, parse_timeout

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.project_tasks.generate_project",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True
)
def generate_project(self, task_id: str, requirement: str, user_id: int, **kwargs):
    """
    Generate project code based on requirements.

    Args:
        task_id: Unique task identifier
        requirement: Project requirement description
        user_id: User ID for WebSocket notifications
        **kwargs: Additional parameters

    Returns:
        dict with generated project data
    """
    async def _execute():
        from app.api.v1.AiProjectCode import ProjectGeneratorAgent
        from app.db.database import async_session

        progress_cb = self._get_progress_callback(task_id, user_id)

        await progress_cb.update(10, "分析需求...")

        agent = ProjectGeneratorAgent()
        await progress_cb.update(30, "生成代码...")

        result = await agent.generate_project(
            requirement=requirement,
            task_id=task_id,
            user_id=user_id,
            progress_callback=progress_cb.update
        )

        await progress_cb.update(100, "完成")
        return result

    try:
        return asyncio.run(_execute())
    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        raise Exception("任务执行超时")


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.project_tasks.validate_project",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True
)
def validate_project(self, task_id: str, project_path: str, user_id: int, **kwargs):
    """
    Validate generated project using Docker sandbox.

    Args:
        task_id: Unique task identifier
        project_path: Path to generated project
        user_id: User ID for WebSocket notifications
        **kwargs: Additional parameters

    Returns:
        dict with validation result
    """
    async def _execute():
        from app.utils.docker_runner import DockerRunner
        from app.db.database import async_session

        progress_cb = self._get_progress_callback(task_id, user_id)

        await progress_cb.update(10, "准备验证环境...")

        runner = DockerRunner()
        await progress_cb.update(30, "安装依赖...")

        await progress_cb.update(60, "运行测试...")

        await progress_cb.update(100, "验证完成")
        return {"status": "success", "project_path": project_path}

    try:
        return asyncio.run(_execute())
    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        raise Exception("验证任务超时")
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise
