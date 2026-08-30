"""
异步任务队列管理

使用 Redis 存储任务状态，支持多 worker 共享
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any
from enum import Enum

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://localhost:6379/0"
TASK_PREFIX = "task:"
TASK_TTL = 86400 * 7  # 任务状态保留 7 天


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskManager:
    """
    任务管理器（单例）

    功能:
    - 任务提交
    - 任务状态查询
    - 任务取消
    - 进度更新
    - 自动清理过期任务
    """

    _instance: Optional['TaskManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._redis: Optional[redis.Redis] = None
            cls._instance._tasks: Dict[str, dict] = {}  # 仅保留运行中的任务
            cls._instance._running_tasks: Dict[str, asyncio.Task] = {}
            cls._instance._cleanup_task: Optional[asyncio.Task] = None
        return cls._instance

    async def _get_redis(self) -> redis.Redis:
        """获取 Redis 连接（懒加载）"""
        if self._redis is None:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    async def _ensure_started(self):
        """确保后台清理任务已启动"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """定期清理过期任务"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                await self.cleanup_old_tasks(days=7)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务失败: {e}")

    async def create_task(
        self,
        task_type: str,
        user_id: int,
        func: Callable,
        params: dict = None,
        input_file_id: int = None
    ) -> str:
        """
        创建任务

        Args:
            task_type: 任务类型
            user_id: 用户 ID
            func: 异步函数
            params: 函数参数
            input_file_id: 输入文件 ID

        Returns:
            task_id: 任务 ID
        """
        await self._ensure_started()
        task_id = str(uuid.uuid4())

        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "user_id": user_id,
            "status": TaskStatus.PENDING.value,
            "params": params or {},
            "input_file_id": input_file_id,
            "result": {},
            "error_message": None,
            "progress": 0,
            "progress_message": "等待中...",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None
        }

        await self._persist_sql_create(task_info)

        # 存储到 Redis
        try:
            r = await self._get_redis()
            await r.set(f"{TASK_PREFIX}{task_id}", json.dumps(task_info, default=str), ex=TASK_TTL)
            # 同时更新用户的任务列表
            await r.sadd(f"user_tasks:{user_id}", task_id)
            await r.expire(f"user_tasks:{user_id}", TASK_TTL)
        except Exception as e:
            logger.warning(f"Redis 存储失败，使用内存: {e}")
            self._tasks[task_id] = task_info

        # 保留在内存用于 asyncio 取消
        asyncio_task = asyncio.create_task(
            self._execute_task(task_id, func, params or {})
        )
        self._running_tasks[task_id] = asyncio_task

        logger.info(f"创建任务 | task_id={task_id} | type={task_type} | user_id={user_id}")

        return task_id

    async def _execute_task(self, task_id: str, func: Callable, params: dict):
        """执行任务"""
        # 从 Redis 读取任务状态
        task_info = await self._get_task_from_redis(task_id)

        async def _update_status(status: str, **kwargs):
            task_info["status"] = status
            for k, v in kwargs.items():
                task_info[k] = v
            await self._save_task_to_redis(task_id, task_info)
            await self._persist_sql_update(task_info)

        try:
            await _update_status(
                TaskStatus.RUNNING.value,
                started_at=datetime.utcnow().isoformat(),
                progress_message="执行中..."
            )

            result = await func(task_id=task_id, **params)
            latest_task_info = await self._get_task_from_redis(task_id) or task_info
            terminal_statuses = {
                TaskStatus.SUCCESS.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            }
            if latest_task_info.get("status") in terminal_statuses:
                task_info = latest_task_info
                if not task_info.get("completed_at"):
                    await _update_status(
                        task_info["status"],
                        completed_at=datetime.utcnow().isoformat(),
                    )
                logger.info(f"任务完成 | task_id={task_id} | status={task_info['status']}")
            else:
                await _update_status(
                    TaskStatus.SUCCESS.value,
                    result=result or {},
                    progress=100,
                    progress_message="完成",
                    completed_at=datetime.utcnow().isoformat()
                )
                logger.info(f"任务完成 | task_id={task_id} | status=success")

        except asyncio.CancelledError:
            await _update_status(
                TaskStatus.CANCELLED.value,
                completed_at=datetime.utcnow().isoformat()
            )
            logger.info(f"任务取消 | task_id={task_id}")

        except Exception as e:
            await _update_status(
                TaskStatus.FAILED.value,
                error_message=str(e),
                progress_message=f"失败：{str(e)}",
                completed_at=datetime.utcnow().isoformat()
            )
            logger.error(f"任务失败 | task_id={task_id} | error={str(e)}", exc_info=True)

        finally:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

    async def _get_task_from_redis(self, task_id: str) -> Optional[dict]:
        """从 Redis 获取任务状态"""
        try:
            r = await self._get_redis()
            data = await r.get(f"{TASK_PREFIX}{task_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis 读取失败: {e}")
            if task_id in self._tasks:
                return self._tasks[task_id]
        return None

    async def _save_task_to_redis(self, task_id: str, task_info: dict):
        """保存任务状态到 Redis"""
        try:
            r = await self._get_redis()
            await r.set(f"{TASK_PREFIX}{task_id}", json.dumps(task_info, default=str), ex=TASK_TTL)
            await r.publish(f"task_events:{task_id}", json.dumps(task_info, default=str))
        except Exception as e:
            logger.warning(f"Redis 保存失败: {e}")
            self._tasks[task_id] = task_info

    async def _persist_sql_create(self, task_info: dict):
        """双写统一 SQL 状态；数据库异常不影响旧任务执行。"""
        try:
            from app.db.database import async_session
            from app.services.unified_state_service import create_task

            async with async_session() as db:
                await create_task(
                    db,
                    int(task_info["user_id"]),
                    task_info["task_type"],
                    task_id=task_info["task_id"],
                    session_id=task_info.get("session_id"),
                    idempotency_key=task_info.get("idempotency_key"),
                    params=task_info.get("params") or {},
                    input_file_id=task_info.get("input_file_id"),
                )
                await db.commit()
        except Exception as error:
            logger.warning("统一任务 SQL 创建失败 | task_id=%s | error=%s", task_info["task_id"], error)

    async def _persist_sql_update(self, task_info: dict):
        """把 Redis/内存任务快照同步到 SQL，并追加可重放事件。"""
        try:
            from app.db.database import async_session
            from app.services.unified_state_service import append_task_event, transition_task

            async with async_session() as db:
                await transition_task(
                    db,
                    task_info["task_id"],
                    int(task_info["user_id"]),
                    task_info["status"],
                    progress=task_info.get("progress"),
                    stage=task_info.get("progress_message"),
                    result=task_info.get("result") or None,
                    error_message=task_info.get("error_message"),
                )
                await append_task_event(
                    db,
                    task_info["task_id"],
                    int(task_info["user_id"]),
                    "task.updated",
                    payload={
                        "progress_message": task_info.get("progress_message"),
                        "result": task_info.get("result") or {},
                        "error_message": task_info.get("error_message"),
                    },
                    status=task_info["status"],
                    progress=task_info.get("progress"),
                )
                await db.commit()
        except Exception as error:
            logger.warning("统一任务 SQL 更新失败 | task_id=%s | error=%s", task_info["task_id"], error)

    def get_task_info(self, task_id: str) -> Optional[dict]:
        """获取任务信息（同步）"""
        # 尝试从内存读取（运行中的任务）
        if task_id in self._running_tasks:
            if task_id in self._tasks:
                return self._tasks[task_id]
        return None

    async def get_task_info_async(self, task_id: str) -> Optional[dict]:
        """获取任务信息（异步，从 Redis）"""
        task_info = await self._get_task_from_redis(task_id)
        if task_info:
            # 恢复 datetime 字符串
            for field in ["created_at", "started_at", "completed_at"]:
                if task_info.get(field):
                    try:
                        task_info[field] = datetime.fromisoformat(task_info[field])
                    except:
                        pass
        return task_info

    async def update_progress(
        self,
        task_id: str,
        progress: int,
        message: str = "",
        status: str = None,
        result_data: Any = None,
        error_message: str = None,
    ):
        """
        更新任务进度

        Args:
            task_id: 任务 ID
            progress: 进度百分比 (0-100)
            message: 进度描述
            status: 可选任务状态
            result_data: 可选任务结果
            error_message: 可选错误信息
        """
        task_info = await self._get_task_from_redis(task_id)
        if task_info and task_info["status"] == TaskStatus.RUNNING.value:
            task_info["progress"] = min(max(0, progress), 100)
            task_info["progress_message"] = message
            if status:
                task_info["status"] = TaskStatus.SUCCESS.value if status == "completed" else status
            if result_data is not None:
                try:
                    task_info["result"] = json.loads(result_data) if isinstance(result_data, str) else result_data
                except (TypeError, ValueError):
                    task_info["result"] = result_data
            if error_message:
                task_info["error_message"] = error_message
            await self._save_task_to_redis(task_id, task_info)
            logger.debug(f"更新进度 | task_id={task_id} | progress={progress}% | message={message}")

    async def reconcile_task(self, task_id: str) -> Optional[dict]:
        """核对 Redis/内存快照与 SQL 状态，返回差异报告。"""
        snapshot = await self._get_task_from_redis(task_id)
        if not snapshot:
            return None
        try:
            from app.db.database import async_session
            from app.services.unified_state_service import compare_task_snapshot

            async with async_session() as db:
                report = await compare_task_snapshot(db, task_id, int(snapshot["user_id"]), snapshot)
                await db.commit()
                return report
        except Exception as error:
            logger.warning("统一任务状态核对失败 | task_id=%s | error=%s", task_id, error)
            return {"task_id": task_id, "consistent": False, "error": str(error)}

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否成功取消
        """
        if task_id in self._running_tasks:
            asyncio_task = self._running_tasks[task_id]
            asyncio_task.cancel()
            logger.info(f"取消任务 | task_id={task_id}")
            return True
        return False

    async def get_user_tasks(
        self,
        user_id: int,
        status: str = None,
        limit: int = 50
    ) -> list:
        """
        获取用户的任务列表

        Args:
            user_id: 用户 ID
            status: 状态筛选
            limit: 数量限制

        Returns:
            任务列表
        """
        try:
            r = await self._get_redis()
            task_ids = await r.smembers(f"user_tasks:{user_id}")

            tasks = []
            for task_id in task_ids:
                task_info = await self._get_task_from_redis(task_id)
                if task_info and (not status or task_info["status"] == status):
                    tasks.append(task_info)

            # 按创建时间排序
            tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return tasks[:limit]
        except Exception as e:
            logger.error(f"获取用户任务列表失败: {e}")
            return []

    async def cleanup_old_tasks(self, days: int = 7):
        """清理旧任务"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        try:
            r = await self._get_redis()
            # 遍历所有任务键
            keys = await r.keys(f"{TASK_PREFIX}*")
            for key in keys:
                if key.startswith(f"{TASK_PREFIX}"):
                    task_id = key.replace(TASK_PREFIX, "")
                    data = await r.get(key)
                    if data:
                        task_info = json.loads(data)
                        completed_at = task_info.get("completed_at")
                        if completed_at:
                            try:
                                completed_time = datetime.fromisoformat(completed_at)
                                if completed_time < cutoff:
                                    await r.delete(key)
                                    # 从用户任务列表中移除
                                    user_id = task_info.get("user_id")
                                    if user_id:
                                        await r.srem(f"user_tasks:{user_id}", task_id)
                                    logger.info(f"清理过期任务 | task_id={task_id}")
                            except:
                                pass
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")


# 全局单例
task_manager = TaskManager()
