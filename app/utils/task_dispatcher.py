"""
任务处理器注册表

用于注册和调用不同类型的任务处理函数
"""
import asyncio
import logging
from typing import Callable, Dict, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """任务分发器（单例）"""

    _instance: Optional['TaskDispatcher'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
        return cls._instance

    def register(self, task_type: str):
        """
        注册任务处理器装饰子

        用法:
        @task_dispatcher.register("ppt_generate")
        async def handle_ppt_generate(task_id: str, **kwargs):
            ...
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(task_id: str, **kwargs):
                logger.info(f"执行任务 | task_id={task_id} | type={task_type}")
                return await func(task_id=task_id, **kwargs)

            self._handlers[task_type] = wrapper
            logger.info(f"注册任务处理器 | type={task_type} | handler={func.__name__}")
            return wrapper

        return decorator

    def get_handler(self, task_type: str) -> Optional[Callable]:
        """获取任务处理器"""
        handler = self._handlers.get(task_type)
        if not handler:
            logger.warning(f"未找到任务处理器 | type={task_type}")
        return handler

    def list_handlers(self) -> list:
        """列出所有已注册的处理器"""
        return list(self._handlers.keys())


# 全局单例
task_dispatcher = TaskDispatcher()
