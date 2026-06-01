"""
PPT 历史记录服务

管理 PPT 生成历史记录，支持：
- 创建记录
- 查询用户历史（分页）
- 获取单条记录
- 删除记录
- 自动清理过期记录
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class PPTHistoryRecord:
    """PPT 历史记录数据模型"""
    id: int
    user_id: str
    task_id: str
    topic: str
    template_id: str
    slide_count: int
    file_id: str
    status: str  # completed, failed, cancelled
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class HistoryServiceError(Exception):
    """历史记录服务异常"""
    pass


class PPTHistoryService:
    """
    PPT 历史记录服务
    
    负责管理 PPT 生成历史记录的 CRUD 操作和自动清理。
    """
    
    def __init__(self):
        """初始化历史记录服务"""
        self._records: Dict[str, PPTHistoryRecord] = {}
        self._next_id = 1
    
    async def create_record(
        self,
        user_id: str,
        task_id: str,
        topic: str,
        template_id: str,
        slide_count: int,
        file_id: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> PPTHistoryRecord:
        """
        创建历史记录
        
        Args:
            user_id: 用户 ID
            task_id: 任务 ID
            topic: PPT 主题
            template_id: 模板 ID
            slide_count: 幻灯片数量
            file_id: 文件 ID
            status: 状态（completed, failed, cancelled）
            error_message: 错误信息（失败时）
            
        Returns:
            创建的历史记录
        """
        record = PPTHistoryRecord(
            id=self._next_id,
            user_id=user_id,
            task_id=task_id,
            topic=topic,
            template_id=template_id,
            slide_count=slide_count,
            file_id=file_id,
            status=status,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc) if status != "pending" else None,
            error_message=error_message,
        )
        
        self._records[task_id] = record
        self._next_id += 1
        
        logger.info(f"创建历史记录 | task_id={task_id} | user_id={user_id} | status={status}")
        
        return record
    
    async def get_user_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        获取用户历史（分页）
        
        Args:
            user_id: 用户 ID
            page: 页码（从 1 开始）
            page_size: 每页数量
            
        Returns:
            包含 records, total, page, page_size 的字典
        """
        # 获取用户的所有记录
        user_records = [
            r for r in self._records.values()
            if r.user_id == user_id
        ]
        
        # 按创建时间倒序
        user_records.sort(key=lambda r: r.created_at, reverse=True)
        
        # 计算分页
        total = len(user_records)
        start = (page - 1) * page_size
        end = start + page_size
        
        # 获取当前页
        page_records = user_records[start:end]
        
        return {
            "records": page_records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }
    
    async def get_record(self, task_id: str) -> Optional[PPTHistoryRecord]:
        """
        获取单条记录
        
        Args:
            task_id: 任务 ID
            
        Returns:
            历史记录，不存在时返回 None
        """
        return self._records.get(task_id)
    
    async def delete_record(self, task_id: str) -> bool:
        """
        删除记录
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否删除成功
        """
        if task_id in self._records:
            del self._records[task_id]
            logger.info(f"删除历史记录 | task_id={task_id}")
            return True
        
        logger.warning(f"删除不存在的历史记录 | task_id={task_id}")
        return False
    
    async def update_record(
        self,
        task_id: str,
        updates: Dict[str, Any],
    ) -> Optional[PPTHistoryRecord]:
        """
        更新记录
        
        Args:
            task_id: 任务 ID
            updates: 要更新的字段
            
        Returns:
            更新后的记录，不存在时返回 None
        """
        record = self._records.get(task_id)
        
        if record is None:
            logger.warning(f"更新不存在的历史记录 | task_id={task_id}")
            return None
        
        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)
        
        logger.info(f"更新历史记录 | task_id={task_id} | updates={list(updates.keys())}")
        
        return record
    
    async def cleanup_expired(
        self,
        retention_days: int = 30,
    ) -> int:
        """
        清理过期记录
        
        Args:
            retention_days: 保留天数
            
        Returns:
            清理的记录数量
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        expired_ids = [
            task_id
            for task_id, record in self._records.items()
            if record.created_at < cutoff
        ]
        
        for task_id in expired_ids:
            del self._records[task_id]
        
        if expired_ids:
            logger.info(f"清理过期历史记录 | count={len(expired_ids)} | retention_days={retention_days}")
        
        return len(expired_ids)
    
    async def get_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计信息
        
        Args:
            user_id: 用户 ID
            
        Returns:
            统计信息字典
        """
        user_records = [
            r for r in self._records.values()
            if r.user_id == user_id
        ]
        
        total = len(user_records)
        completed = sum(1 for r in user_records if r.status == "completed")
        failed = sum(1 for r in user_records if r.status == "failed")
        cancelled = sum(1 for r in user_records if r.status == "cancelled")
        
        avg_slides = (
            sum(r.slide_count for r in user_records) / total
            if total > 0
            else 0
        )
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "avg_slides_per_ppt": round(avg_slides, 1),
        }


# 全局单例
history_service = PPTHistoryService()
