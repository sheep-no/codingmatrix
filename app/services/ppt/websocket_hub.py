"""
PPT WebSocket 进度中心

实时推送 PPT 生成任务进度到前端客户端。

功能：
- 按 task_id 管理连接
- 推送进度、完成、错误消息
- 支持历史消息重放（连接时推送当前状态）
- 自动清理过期连接
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from fastapi import WebSocket
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


@dataclass
class TaskProgressState:
    """任务进度状态"""
    task_id: str
    user_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    progress: float = 0.0
    current_step: str = ""
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WebSocketProgressHub:
    """
    PPT 任务进度 WebSocket 中心
    
    负责管理 PPT 生成任务的实时进度推送，支持：
    - 按 task_id 连接和订阅
    - 推送进度更新、完成通知、错误消息
    - 连接时重放当前任务状态
    """
    
    def __init__(self):
        """初始化进度中心"""
        # task_id -> TaskProgressState
        self._task_states: Dict[str, TaskProgressState] = {}
        
        # task_id -> set of user_ids (追踪哪些用户订阅了任务)
        self._task_subscriptions: Dict[str, set] = {}
        
        # 历史消息缓存（最近 N 条）
        self._message_history: Dict[str, list] = {}
        self._max_history_size = 10
    
    async def connect(
        self,
        websocket: WebSocket,
        task_id: str,
        user_id: str,
    ) -> bool:
        """
        连接 WebSocket 并订阅任务进度
        
        Args:
            websocket: FastAPI WebSocket 实例
            task_id: 任务 ID
            user_id: 用户 ID
            
        Returns:
            是否连接成功
        """
        try:
            # 接受 WebSocket 连接
            await websocket.accept()
            
            # 注册到全局 WebSocket 管理器
            numeric_user_id = self._parse_user_id(user_id)
            await ws_manager.connect(numeric_user_id, websocket)
            
            # 订阅任务
            self._subscribe_task(task_id, user_id)
            
            # 推送当前任务状态（如果存在）
            state = self._task_states.get(task_id)
            if state:
                await self._send_status(websocket, state)
                logger.info(f"重放任务状态 | task_id={task_id} | status={state.status}")
            
            # 推送历史消息（最近几条）
            history = self._message_history.get(task_id, [])
            for msg in history:
                await websocket.send_json(msg)
            
            logger.info(f"WebSocket 连接成功 | task_id={task_id} | user_id={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket 连接失败 | task_id={task_id} | error={e}")
            return False
    
    async def disconnect(self, task_id: str, user_id: str) -> None:
        """
        断开 WebSocket 连接
        
        Args:
            task_id: 任务 ID
            user_id: 用户 ID
        """
        self._unsubscribe_task(task_id, user_id)
        
        # 从全局管理器断开
        numeric_user_id = self._parse_user_id(user_id)
        await ws_manager.disconnect(numeric_user_id)
        
        logger.info(f"WebSocket 断开连接 | task_id={task_id} | user_id={user_id}")
    
    async def push_progress(
        self,
        task_id: str,
        progress: float,
        step: str,
        message: str = "",
        user_id: Optional[str] = None,
    ) -> None:
        """
        推送任务进度更新
        
        Args:
            task_id: 任务 ID
            progress: 进度 (0.0 - 1.0)
            step: 当前步骤
            message: 用户可见的消息
            user_id: 特定用户 ID（可选，为空则推送给所有订阅者）
        """
        # 更新任务状态
        state = self._task_states.get(task_id)
        if state is None:
            state = TaskProgressState(task_id=task_id, user_id=user_id or "unknown")
            self._task_states[task_id] = state
        
        state.status = "running"
        state.progress = max(0.0, min(1.0, progress))
        state.current_step = step
        state.message = message
        state.updated_at = datetime.now(timezone.utc)
        
        # 构建消息
        msg = {
            "type": "progress",
            "task_id": task_id,
            "progress": state.progress,
            "step": step,
            "message": message,
            "status": "running",
            "timestamp": state.updated_at.isoformat(),
        }
        
        # 缓存历史消息
        self._cache_message(task_id, msg)
        
        # 推送给订阅者
        await self._broadcast_to_task(task_id, msg)
        
        logger.debug(
            f"推送进度 | task_id={task_id} | progress={progress:.1%} | step={step}"
        )
    
    async def push_complete(
        self,
        task_id: str,
        result: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> None:
        """
        推送任务完成消息
        
        Args:
            task_id: 任务 ID
            result: 任务结果数据
            user_id: 特定用户 ID（可选）
        """
        # 更新任务状态
        state = self._task_states.get(task_id)
        if state is None:
            state = TaskProgressState(task_id=task_id, user_id=user_id or "unknown")
            self._task_states[task_id] = state
        
        state.status = "completed"
        state.progress = 1.0
        state.current_step = "completed"
        state.message = "任务完成"
        state.result = result
        state.updated_at = datetime.now(timezone.utc)
        
        # 构建消息
        msg = {
            "type": "complete",
            "task_id": task_id,
            "progress": 1.0,
            "step": "completed",
            "message": "任务完成",
            "status": "completed",
            "result": result,
            "timestamp": state.updated_at.isoformat(),
        }
        
        # 缓存历史消息
        self._cache_message(task_id, msg)
        
        # 推送给订阅者
        await self._broadcast_to_task(task_id, msg)
        
        logger.info(f"任务完成 | task_id={task_id} | result_keys={list(result.keys())}")
    
    async def push_error(
        self,
        task_id: str,
        error: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        推送任务错误消息
        
        Args:
            task_id: 任务 ID
            error: 错误信息
            user_id: 特定用户 ID（可选）
        """
        # 更新任务状态
        state = self._task_states.get(task_id)
        if state is None:
            state = TaskProgressState(task_id=task_id, user_id=user_id or "unknown")
            self._task_states[task_id] = state
        
        state.status = "failed"
        state.error = error
        state.message = f"任务失败：{error}"
        state.updated_at = datetime.now(timezone.utc)
        
        # 构建消息
        msg = {
            "type": "error",
            "task_id": task_id,
            "progress": state.progress,
            "step": state.current_step,
            "message": state.message,
            "status": "failed",
            "error": error,
            "timestamp": state.updated_at.isoformat(),
        }
        
        # 缓存历史消息
        self._cache_message(task_id, msg)
        
        # 推送给订阅者
        await self._broadcast_to_task(task_id, msg)
        
        logger.warning(f"任务错误 | task_id={task_id} | error={error}")
    
    async def push_cancelled(
        self,
        task_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        推送任务取消消息
        
        Args:
            task_id: 任务 ID
            user_id: 用户 ID
        """
        state = self._task_states.get(task_id)
        if state is None:
            state = TaskProgressState(task_id=task_id, user_id=user_id or "unknown")
            self._task_states[task_id] = state
        
        state.status = "cancelled"
        state.message = "任务已取消"
        state.updated_at = datetime.now(timezone.utc)
        
        msg = {
            "type": "cancelled",
            "task_id": task_id,
            "progress": state.progress,
            "message": "任务已取消",
            "status": "cancelled",
            "timestamp": state.updated_at.isoformat(),
        }
        
        self._cache_message(task_id, msg)
        await self._broadcast_to_task(task_id, msg)
        
        logger.info(f"任务取消 | task_id={task_id}")
    
    def get_task_state(self, task_id: str) -> Optional[TaskProgressState]:
        """
        获取任务当前状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务状态，不存在时返回 None
        """
        return self._task_states.get(task_id)
    
    def create_task_state(
        self,
        task_id: str,
        user_id: str,
        topic: str = "",
    ) -> TaskProgressState:
        """
        创建新的任务状态记录
        
        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            topic: 任务主题
            
        Returns:
            创建的任务状态
        """
        state = TaskProgressState(
            task_id=task_id,
            user_id=user_id,
            message=f"正在生成：{topic}" if topic else "任务已开始",
        )
        self._task_states[task_id] = state
        
        logger.info(f"创建任务状态 | task_id={task_id} | user_id={user_id}")
        return state
    
    def cleanup_finished_tasks(
        self,
        max_age_minutes: int = 30,
    ) -> int:
        """
        清理已完成的任务状态
        
        Args:
            max_age_minutes: 最大保留时间（分钟）
            
        Returns:
            清理的任务数
        """
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=max_age_minutes)
        
        cleaned = 0
        task_ids_to_remove = []
        
        for task_id, state in self._task_states.items():
            if state.status in ("completed", "failed", "cancelled"):
                if state.updated_at < cutoff:
                    task_ids_to_remove.append(task_id)
        
        for task_id in task_ids_to_remove:
            del self._task_states[task_id]
            self._message_history.pop(task_id, None)
            self._task_subscriptions.pop(task_id, None)
            cleaned += 1
        
        if cleaned > 0:
            logger.info(f"清理过期任务 | cleaned={cleaned}")
        
        return cleaned
    
    def _subscribe_task(self, task_id: str, user_id: str) -> None:
        """订阅任务进度"""
        if task_id not in self._task_subscriptions:
            self._task_subscriptions[task_id] = set()
        self._task_subscriptions[task_id].add(user_id)
    
    def _unsubscribe_task(self, task_id: str, user_id: str) -> None:
        """取消订阅任务进度"""
        if task_id in self._task_subscriptions:
            self._task_subscriptions[task_id].discard(user_id)
            if not self._task_subscriptions[task_id]:
                del self._task_subscriptions[task_id]
    
    async def _broadcast_to_task(self, task_id: str, message: dict) -> None:
        """广播消息给任务的所有订阅者"""
        subscribers = self._task_subscriptions.get(task_id, set())
        
        for user_id in subscribers:
            numeric_user_id = self._parse_user_id(user_id)
            try:
                await ws_manager.send_personal_message(numeric_user_id, message)
            except Exception as e:
                logger.warning(f"推送消息失败 | user_id={user_id} | error={e}")
    
    async def _send_status(self, websocket: WebSocket, state: TaskProgressState) -> None:
        """发送当前任务状态"""
        status_msg = {
            "type": "status",
            "task_id": state.task_id,
            "status": state.status,
            "progress": state.progress,
            "step": state.current_step,
            "message": state.message,
            "result": state.result,
            "error": state.error,
            "timestamp": state.updated_at.isoformat(),
        }
        await websocket.send_json(status_msg)
    
    def _cache_message(self, task_id: str, message: dict) -> None:
        """缓存消息到历史"""
        if task_id not in self._message_history:
            self._message_history[task_id] = []
        
        self._message_history[task_id].append(message)
        
        # 限制历史大小
        if len(self._message_history[task_id]) > self._max_history_size:
            self._message_history[task_id] = self._message_history[task_id][-self._max_history_size:]
    
    @staticmethod
    def _parse_user_id(user_id: str) -> int:
        """将用户 ID 转换为整数"""
        try:
            if user_id.startswith("user_"):
                return int(user_id[5:])
            return int(user_id)
        except (ValueError, IndexError):
            return 0


# 全局单例
progress_hub = WebSocketProgressHub()
