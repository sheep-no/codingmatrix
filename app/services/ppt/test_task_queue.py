"""
PPT 任务队列单元测试

测试任务队列的核心功能：
- 内存模式创建/读取/更新/删除
- 任务状态管理
- 用户索引
- 统计信息
- 降级机制
"""

import pytest
import asyncio
from datetime import datetime, timezone

from app.services.ppt.task_queue import (
    PPTTaskQueue,
    PPTTask,
    TaskStatus,
    PPTTaskQueueError,
)


@pytest.fixture
def queue():
    """创建内存模式任务队列"""
    return PPTTaskQueue(redis_url=None)


@pytest.fixture
def sample_task():
    """创建示例任务"""
    return PPTTask(
        task_id="task_001",
        user_id="user_1",
        topic="AI 发展趋势",
        template_id="modern",
        slide_count=10,
    )


class TestPPTTask:
    """任务数据模型测试"""

    def test_to_dict(self, sample_task):
        """测试转换为字典"""
        d = sample_task.to_dict()
        
        assert d["task_id"] == "task_001"
        assert d["user_id"] == "user_1"
        assert d["topic"] == "AI 发展趋势"
        assert d["template_id"] == "modern"
        assert d["slide_count"] == 10
        assert d["status"] == TaskStatus.PENDING

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "task_id": "task_002",
            "user_id": "user_1",
            "status": "completed",
            "topic": "测试主题",
            "template_id": "business",
            "slide_count": 5,
            "progress": 1.0,
        }
        
        task = PPTTask.from_dict(data)
        
        assert task.task_id == "task_002"
        assert task.user_id == "user_1"
        assert task.status == "completed"
        assert task.topic == "测试主题"
        assert task.template_id == "business"


class TestPPTTaskQueueMemory:
    """内存模式任务队列测试"""

    @pytest.mark.asyncio
    async def test_initialize_memory(self, queue):
        """测试初始化内存模式"""
        result = await queue.initialize()
        
        assert result is True
        assert queue._use_memory is True

    @pytest.mark.asyncio
    async def test_create_task(self, queue, sample_task):
        """测试创建任务"""
        result = await queue.create_task(sample_task)
        
        assert result is True
        
        task = await queue.get_task("task_001")
        assert task is not None
        assert task.task_id == "task_001"

    @pytest.mark.asyncio
    async def test_create_task_duplicate(self, queue, sample_task):
        """测试创建重复任务"""
        await queue.create_task(sample_task)
        
        result = await queue.create_task(sample_task)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_task_exists(self, queue, sample_task):
        """测试获取存在任务"""
        await queue.create_task(sample_task)
        
        task = await queue.get_task("task_001")
        assert task is not None
        assert task.user_id == "user_1"

    @pytest.mark.asyncio
    async def test_get_task_not_exists(self, queue):
        """测试获取不存在任务"""
        task = await queue.get_task("nonexistent")
        assert task is None

    @pytest.mark.asyncio
    async def test_update_task(self, queue, sample_task):
        """测试更新任务"""
        await queue.create_task(sample_task)
        
        result = await queue.update_task(
            "task_001",
            {"status": TaskStatus.RUNNING, "progress": 0.5},
        )
        
        assert result is True
        
        task = await queue.get_task("task_001")
        assert task.status == TaskStatus.RUNNING
        assert task.progress == 0.5

    @pytest.mark.asyncio
    async def test_update_task_not_exists(self, queue):
        """测试更新不存在任务"""
        result = await queue.update_task(
            "nonexistent",
            {"status": TaskStatus.COMPLETED},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_task(self, queue, sample_task):
        """测试删除任务"""
        await queue.create_task(sample_task)
        
        result = await queue.delete_task("task_001")
        assert result is True
        
        task = await queue.get_task("task_001")
        assert task is None

    @pytest.mark.asyncio
    async def test_delete_task_not_exists(self, queue):
        """测试删除不存在任务"""
        result = await queue.delete_task("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_user_tasks(self, queue):
        """测试列出用户任务"""
        # 创建多个任务
        for i in range(5):
            task = PPTTask(
                task_id=f"task_{i}",
                user_id="user_1",
                topic=f"主题 {i}",
            )
            await queue.create_task(task)
        
        # 创建其他用户任务
        other_task = PPTTask(
            task_id="other_task",
            user_id="user_2",
            topic="其他用户任务",
        )
        await queue.create_task(other_task)
        
        # 列出用户 1 的任务
        result = await queue.list_user_tasks("user_1", page=1, page_size=10)
        
        assert result["total"] == 5
        assert len(result["tasks"]) == 5
        assert all(t.user_id == "user_1" for t in result["tasks"])

    @pytest.mark.asyncio
    async def test_list_user_tasks_pagination(self, queue):
        """测试分页"""
        # 创建 10 个任务
        for i in range(10):
            task = PPTTask(
                task_id=f"task_{i}",
                user_id="user_1",
                topic=f"主题 {i}",
            )
            await queue.create_task(task)
        
        # 第一页
        result1 = await queue.list_user_tasks("user_1", page=1, page_size=3)
        assert result1["total"] == 10
        assert result1["page"] == 1
        assert len(result1["tasks"]) == 3
        assert result1["total_pages"] == 4
        
        # 第二页
        result2 = await queue.list_user_tasks("user_1", page=2, page_size=3)
        assert result2["page"] == 2
        assert len(result2["tasks"]) == 3
        
        # 最后一页
        result3 = await queue.list_user_tasks("user_1", page=4, page_size=3)
        assert result3["page"] == 4
        assert len(result3["tasks"]) == 1

    @pytest.mark.asyncio
    async def test_list_user_tasks_empty(self, queue):
        """测试空用户列表"""
        result = await queue.list_user_tasks("nonexistent")
        
        assert result["total"] == 0
        assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_user_stats(self, queue):
        """测试用户统计"""
        # 创建不同状态任务
        completed_task = PPTTask(
            task_id="task_1",
            user_id="user_1",
            status=TaskStatus.COMPLETED,
            progress=1.0,
        )
        await queue.create_task(completed_task)
        
        running_task = PPTTask(
            task_id="task_2",
            user_id="user_1",
            status=TaskStatus.RUNNING,
            progress=0.5,
        )
        await queue.create_task(running_task)
        
        failed_task = PPTTask(
            task_id="task_3",
            user_id="user_1",
            status=TaskStatus.FAILED,
        )
        await queue.create_task(failed_task)
        
        stats = await queue.get_user_stats("user_1")
        
        assert stats["total"] == 3
        assert stats["completed"] == 1
        assert stats["running"] == 1
        assert stats["failed"] == 1
        assert stats["avg_progress"] == pytest.approx(0.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_get_user_stats_empty(self, queue):
        """测试空用户统计"""
        stats = await queue.get_user_stats("nonexistent")
        
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_task_auto_timestamps(self, queue):
        """测试自动时间戳"""
        task = PPTTask(
            task_id="task_ts",
            user_id="user_1",
        )
        
        await queue.create_task(task)
        retrieved = await queue.get_task("task_ts")
        
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    @pytest.mark.asyncio
    async def test_task_status_transitions(self, queue):
        """测试任务状态流转"""
        task = PPTTask(
            task_id="task_flow",
            user_id="user_1",
            status=TaskStatus.PENDING,
        )
        await queue.create_task(task)
        
        # pending -> running
        await queue.update_task("task_flow", {"status": TaskStatus.RUNNING, "progress": 0.3})
        task = await queue.get_task("task_flow")
        assert task.status == TaskStatus.RUNNING
        
        # running -> completed
        await queue.update_task("task_flow", {"status": TaskStatus.COMPLETED, "progress": 1.0})
        task = await queue.get_task("task_flow")
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 1.0
        assert task.completed_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
