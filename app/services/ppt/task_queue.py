"""
PPT 任务队列服务（Redis 支持）

提供基于 Redis 的任务队列管理，支持：
- 任务状态持久化
- 服务重启后恢复
- 分布式部署
- 降级至内存队列
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PPTTask:
    """PPT 任务数据模型"""
    task_id: str
    user_id: str
    status: str = TaskStatus.PENDING
    topic: str = ""
    template_id: str = "modern"
    slide_count: int = 10
    progress: float = 0.0
    current_step: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    output_format: str = "pptx"
    enable_animation: bool = True
    auto_images: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "status": self.status,
            "topic": self.topic,
            "template_id": self.template_id,
            "slide_count": self.slide_count,
            "progress": self.progress,
            "current_step": self.current_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "output_format": self.output_format,
            "enable_animation": self.enable_animation,
            "auto_images": self.auto_images,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PPTTask":
        """从字典创建"""
        return cls(
            task_id=data["task_id"],
            user_id=data["user_id"],
            status=data.get("status", TaskStatus.PENDING),
            topic=data.get("topic", ""),
            template_id=data.get("template_id", "modern"),
            slide_count=data.get("slide_count", 10),
            progress=data.get("progress", 0.0),
            current_step=data.get("current_step", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            output_format=data.get("output_format", "pptx"),
            enable_animation=data.get("enable_animation", True),
            auto_images=data.get("auto_images", True),
        )


class PPTTaskQueueError(Exception):
    """任务队列异常"""
    pass


class PPTTaskQueue:
    """
    PPT 任务队列服务
    
    优先使用 Redis 作为后端存储，如果 Redis 不可用则降级到内存存储。
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        初始化任务队列
        
        Args:
            redis_url: Redis 连接 URL，为空则使用内存模式
            max_retries: Redis 操作最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self._redis_url = redis_url
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._redis = None
        self._use_memory = True
        self._memory_tasks: Dict[str, PPTTask] = {}
        self._memory_user_index: Dict[str, List[str]] = {}

    async def initialize(self) -> bool:
        """
        初始化队列后端
        
        Returns:
            是否成功连接
        """
        if not self._redis_url:
            logger.info("未提供 Redis URL，使用内存模式")
            self._use_memory = True
            return True

        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                encoding="utf-8",
            )

            # 测试连接
            await self._redis.ping()

            self._use_memory = False
            logger.info("Redis 连接成功")
            return True

        except Exception as e:
            logger.warning(f"Redis 连接失败，使用内存模式：{e}")
            self._use_memory = True
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            await self._redis.aclose()
            logger.info("Redis 连接已关闭")

    async def create_task(self, task: PPTTask) -> bool:
        """
        创建任务
        
        Args:
            task: 任务对象
            
        Returns:
            是否创建成功
        """
        if self._use_memory:
            return self._create_task_memory(task)
        else:
            return await self._create_task_redis(task)

    async def get_task(self, task_id: str) -> Optional[PPTTask]:
        """
        获取任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务对象，不存在时返回 None
        """
        if self._use_memory:
            return self._memory_tasks.get(task_id)
        else:
            return await self._get_task_redis(task_id)

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新任务
        
        Args:
            task_id: 任务 ID
            updates: 要更新的字段
            
        Returns:
            是否更新成功
        """
        if self._use_memory:
            return self._update_task_memory(task_id, updates)
        else:
            return await self._update_task_redis(task_id, updates)

    async def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否删除成功
        """
        if self._use_memory:
            return self._delete_task_memory(task_id)
        else:
            return await self._delete_task_redis(task_id)

    async def list_user_tasks(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        列出用户的任务
        
        Args:
            user_id: 用户 ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            包含 tasks 和 pagination 的字典
        """
        if self._use_memory:
            return self._list_user_tasks_memory(user_id, page, page_size)
        else:
            return await self._list_user_tasks_redis(user_id, page, page_size)

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户任务统计
        
        Args:
            user_id: 用户 ID
            
        Returns:
            统计信息
        """
        if self._use_memory:
            return self._get_user_stats_memory(user_id)
        else:
            return await self._get_user_stats_redis(user_id)

    # === 内存模式实现 ===

    def _create_task_memory(self, task: PPTTask) -> bool:
        """内存模式创建任务"""
        if task.task_id in self._memory_tasks:
            logger.warning(f"任务已存在：{task.task_id}")
            return False

        if not task.created_at:
            task.created_at = datetime.now(timezone.utc).isoformat()
        if not task.updated_at:
            task.updated_at = datetime.now(timezone.utc).isoformat()

        self._memory_tasks[task.task_id] = task

        if task.user_id not in self._memory_user_index:
            self._memory_user_index[task.user_id] = []
        self._memory_user_index[task.user_id].append(task.task_id)

        logger.info(f"创建任务（内存）：{task.task_id}")
        return True

    def _update_task_memory(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """内存模式更新任务"""
        if task_id not in self._memory_tasks:
            return False

        task = self._memory_tasks[task_id]
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.now(timezone.utc).isoformat()

        if updates.get("status") in ("completed", "failed", "cancelled"):
            task.completed_at = datetime.now(timezone.utc).isoformat()

        logger.info(f"更新任务（内存）：{task_id}")
        return True

    def _delete_task_memory(self, task_id: str) -> bool:
        """内存模式删除任务"""
        if task_id not in self._memory_tasks:
            return False

        task = self._memory_tasks[task_id]
        user_id = task.user_id

        del self._memory_tasks[task_id]

        if user_id in self._memory_user_index:
            if task_id in self._memory_user_index[user_id]:
                self._memory_user_index[user_id].remove(task_id)

        logger.info(f"删除任务（内存）：{task_id}")
        return True

    def _list_user_tasks_memory(
        self, user_id: str, page: int, page_size: int
    ) -> Dict[str, Any]:
        """内存模式列出用户任务"""
        task_ids = self._memory_user_index.get(user_id, [])
        tasks = []

        for task_id in task_ids:
            task = self._memory_tasks.get(task_id)
            if task:
                tasks.append(task)

        # 按创建时间倒序
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        # 分页
        total = len(tasks)
        start = (page - 1) * page_size
        end = start + page_size
        page_tasks = tasks[start:end]

        return {
            "tasks": page_tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    def _get_user_stats_memory(self, user_id: str) -> Dict[str, Any]:
        """内存模式获取用户统计"""
        task_ids = self._memory_user_index.get(user_id, [])
        tasks = []
        for task_id in task_ids:
            task = self._memory_tasks.get(task_id)
            if task:
                tasks.append(task)

        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        running = sum(1 for t in tasks if t.status == TaskStatus.RUNNING)
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)

        avg_progress = (
            sum(t.progress for t in tasks) / total if total > 0 else 0
        )

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "avg_progress": round(avg_progress, 2),
        }

    # === Redis 模式实现 ===

    async def _create_task_redis(self, task: PPTTask) -> bool:
        """Redis 模式创建任务"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            if not task.created_at:
                task.created_at = now
            if not task.updated_at:
                task.updated_at = now

            key = f"ppt:task:{task.task_id}"
            user_key = f"ppt:user:{task.user_id}:tasks"

            # 使用事务确保原子性
            async with self._redis.pipeline() as pipe:
                await pipe.set(key, json.dumps(task.to_dict()))
                await pipe.rpush(user_key, task.task_id)
                await pipe.execute()

            logger.info(f"创建任务（Redis）：{task.task_id}")
            return True

        except Exception as e:
            logger.error(f"Redis 创建任务失败：{e}")
            return False

    async def _get_task_redis(self, task_id: str) -> Optional[PPTTask]:
        """Redis 模式获取任务"""
        try:
            key = f"ppt:task:{task_id}"
            data = await self._redis.get(key)

            if data is None:
                return None

            return PPTTask.from_dict(json.loads(data))

        except Exception as e:
            logger.error(f"Redis 获取任务失败：{e}")
            return None

    async def _update_task_redis(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Redis 模式更新任务"""
        try:
            key = f"ppt:task:{task_id}"
            data = await self._redis.get(key)

            if data is None:
                return False

            task_data = json.loads(data)
            task_data.update(updates)
            task_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            if updates.get("status") in ("completed", "failed", "cancelled"):
                task_data["completed_at"] = datetime.now(timezone.utc).isoformat()

            await self._redis.set(key, json.dumps(task_data))

            logger.info(f"更新任务（Redis）：{task_id}")
            return True

        except Exception as e:
            logger.error(f"Redis 更新任务失败：{e}")
            return False

    async def _delete_task_redis(self, task_id: str) -> bool:
        """Redis 模式删除任务"""
        try:
            key = f"ppt:task:{task_id}"
            data = await self._redis.get(key)

            if data is None:
                return False

            task_data = json.loads(data)
            user_id = task_data["user_id"]
            user_key = f"ppt:user:{user_id}:tasks"

            async with self._redis.pipeline() as pipe:
                await pipe.delete(key)
                await pipe.lrem(user_key, 0, task_id)
                await pipe.execute()

            logger.info(f"删除任务（Redis）：{task_id}")
            return True

        except Exception as e:
            logger.error(f"Redis 删除任务失败：{e}")
            return False

    async def _list_user_tasks_redis(
        self, user_id: str, page: int, page_size: int
    ) -> Dict[str, Any]:
        """Redis 模式列出用户任务"""
        try:
            user_key = f"ppt:user:{user_id}:tasks"
            task_ids = await self._redis.lrange(user_key, 0, -1)

            tasks = []
            for task_id in task_ids:
                key = f"ppt:task:{task_id}"
                data = await self._redis.get(key)
                if data:
                    tasks.append(PPTTask.from_dict(json.loads(data)))

            # 按创建时间倒序
            tasks.sort(key=lambda t: t.created_at, reverse=True)

            # 分页
            total = len(tasks)
            start = (page - 1) * page_size
            end = start + page_size
            page_tasks = tasks[start:end]

            return {
                "tasks": page_tasks,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            }

        except Exception as e:
            logger.error(f"Redis 列出用户任务失败：{e}")
            return {"tasks": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    async def _get_user_stats_redis(self, user_id: str) -> Dict[str, Any]:
        """Redis 模式获取用户统计"""
        try:
            user_key = f"ppt:user:{user_id}:tasks"
            task_ids = await self._redis.lrange(user_key, 0, -1)

            total = len(task_ids)
            completed = 0
            failed = 0
            running = 0
            pending = 0
            total_progress = 0.0

            for task_id in task_ids:
                key = f"ppt:task:{task_id}"
                data = await self._redis.get(key)
                if data:
                    task_data = json.loads(data)
                    status = task_data.get("status", "")
                    progress = task_data.get("progress", 0.0)

                    if status == TaskStatus.COMPLETED:
                        completed += 1
                    elif status == TaskStatus.FAILED:
                        failed += 1
                    elif status == TaskStatus.RUNNING:
                        running += 1
                    elif status == TaskStatus.PENDING:
                        pending += 1

                    total_progress += progress

            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": pending,
                "avg_progress": round(total_progress / total, 2) if total > 0 else 0,
            }

        except Exception as e:
            logger.error(f"Redis 获取用户统计失败：{e}")
            return {"total": 0, "completed": 0, "failed": 0, "running": 0, "pending": 0}


# 全局单例
ppt_task_queue = PPTTaskQueue()
