"""
PPT 历史记录服务单元测试

测试历史记录服务的核心功能：
- 创建记录
- 获取用户历史（分页）
- 更新和删除记录
- 清理过期记录
- 统计信息
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.ppt.history_service import (
    PPTHistoryService,
    PPTHistoryRecord,
    HistoryServiceError,
)


@pytest.fixture
def service():
    """创建历史记录服务实例"""
    return PPTHistoryService()


@pytest.fixture
def sample_records(service):
    """创建示例记录"""
    records = []
    
    for i in range(5):
        record = service._next_id
        records.append({
            "user_id": "user_1",
            "task_id": f"task_{i}",
            "topic": f"测试主题 {i}",
            "template_id": "modern",
            "slide_count": 8 + i,
            "file_id": f"file_{i}",
            "status": "completed" if i < 4 else "failed",
        })
        
        # 让每条记录时间不同
        service._next_id = record + 1
    
    return records


class TestPPTHistoryService:
    """历史记录服务测试"""
    
    @pytest.mark.asyncio
    async def test_create_record(self, service):
        """测试创建记录"""
        record = await service.create_record(
            user_id="user_1",
            task_id="task_001",
            topic="AI 发展趋势",
            template_id="modern",
            slide_count=10,
            file_id="file_001",
        )
        
        assert record.id == 1
        assert record.user_id == "user_1"
        assert record.task_id == "task_001"
        assert record.topic == "AI 发展趋势"
        assert record.template_id == "modern"
        assert record.slide_count == 10
        assert record.file_id == "file_001"
        assert record.status == "completed"
        assert record.created_at is not None
    
    @pytest.mark.asyncio
    async def test_create_record_with_error(self, service):
        """测试创建带错误信息的记录"""
        record = await service.create_record(
            user_id="user_1",
            task_id="task_002",
            topic="测试主题",
            template_id="modern",
            slide_count=5,
            file_id="file_002",
            status="failed",
            error_message="AI 服务调用失败",
        )
        
        assert record.status == "failed"
        assert record.error_message == "AI 服务调用失败"
    
    @pytest.mark.asyncio
    async def test_get_user_history_pagination(self, service):
        """测试获取用户历史（分页）"""
        # 创建 10 条记录
        for i in range(10):
            await service.create_record(
                user_id="user_1",
                task_id=f"task_{i}",
                topic=f"主题 {i}",
                template_id="modern",
                slide_count=8,
                file_id=f"file_{i}",
            )
        
        # 获取第一页（每页 3 条）
        result = await service.get_user_history("user_1", page=1, page_size=3)
        
        assert result["total"] == 10
        assert result["page"] == 1
        assert result["page_size"] == 3
        assert result["total_pages"] == 4
        assert len(result["records"]) == 3
        
        # 获取第二页
        result2 = await service.get_user_history("user_1", page=2, page_size=3)
        assert result2["page"] == 2
        assert len(result2["records"]) == 3
        
        # 获取最后一页
        result3 = await service.get_user_history("user_1", page=4, page_size=3)
        assert result3["page"] == 4
        assert len(result3["records"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_user_history_empty(self, service):
        """测试获取空历史"""
        result = await service.get_user_history("user_nonexistent")
        
        assert result["total"] == 0
        assert result["records"] == []
    
    @pytest.mark.asyncio
    async def test_get_record_exists(self, service):
        """测试获取存在的记录"""
        await service.create_record(
            user_id="user_1",
            task_id="task_001",
            topic="测试主题",
            template_id="modern",
            slide_count=10,
            file_id="file_001",
        )
        
        record = await service.get_record("task_001")
        assert record is not None
        assert record.task_id == "task_001"
    
    @pytest.mark.asyncio
    async def test_get_record_not_exists(self, service):
        """测试获取不存在的记录"""
        record = await service.get_record("nonexistent")
        assert record is None
    
    @pytest.mark.asyncio
    async def test_delete_record_success(self, service):
        """测试删除记录成功"""
        await service.create_record(
            user_id="user_1",
            task_id="task_001",
            topic="测试主题",
            template_id="modern",
            slide_count=10,
            file_id="file_001",
        )
        
        result = await service.delete_record("task_001")
        assert result is True
        
        record = await service.get_record("task_001")
        assert record is None
    
    @pytest.mark.asyncio
    async def test_delete_record_not_exists(self, service):
        """测试删除不存在的记录"""
        result = await service.delete_record("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_update_record(self, service):
        """测试更新记录"""
        await service.create_record(
            user_id="user_1",
            task_id="task_001",
            topic="测试主题",
            template_id="modern",
            slide_count=10,
            file_id="file_001",
            status="pending",
        )
        
        # 更新状态
        updated = await service.update_record(
            "task_001",
            {"status": "completed", "completed_at": datetime.now(timezone.utc)},
        )
        
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_update_record_not_exists(self, service):
        """测试更新不存在的记录"""
        result = await service.update_record(
            "nonexistent",
            {"status": "completed"},
        )
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self, service):
        """测试清理过期记录"""
        # 创建过期记录
        old_record = await service.create_record(
            user_id="user_1",
            task_id="old_task",
            topic="旧主题",
            template_id="modern",
            slide_count=5,
            file_id="old_file",
        )
        old_record.created_at = datetime.now(timezone.utc) - timedelta(days=31)
        
        # 创建新记录
        new_record = await service.create_record(
            user_id="user_1",
            task_id="new_task",
            topic="新主题",
            template_id="modern",
            slide_count=8,
            file_id="new_file",
        )
        
        # 清理
        cleaned = await service.cleanup_expired(retention_days=30)
        
        assert cleaned == 1
        assert await service.get_record("old_task") is None
        assert await service.get_record("new_task") is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_no_expired(self, service):
        """测试无过期记录时不清理"""
        await service.create_record(
            user_id="user_1",
            task_id="task_001",
            topic="测试主题",
            template_id="modern",
            slide_count=10,
            file_id="file_001",
        )
        
        cleaned = await service.cleanup_expired(retention_days=30)
        assert cleaned == 0
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, service):
        """测试获取统计信息"""
        # 创建不同类型记录
        await service.create_record(
            user_id="user_1",
            task_id="task_1",
            topic="主题 1",
            template_id="modern",
            slide_count=10,
            file_id="file_1",
            status="completed",
        )
        
        await service.create_record(
            user_id="user_1",
            task_id="task_2",
            topic="主题 2",
            template_id="business",
            slide_count=8,
            file_id="file_2",
            status="completed",
        )
        
        await service.create_record(
            user_id="user_1",
            task_id="task_3",
            topic="主题 3",
            template_id="modern",
            slide_count=5,
            file_id="file_3",
            status="failed",
        )
        
        stats = await service.get_statistics("user_1")
        
        assert stats["total"] == 3
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["cancelled"] == 0
        assert stats["avg_slides_per_ppt"] == pytest.approx(7.7, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_get_statistics_empty(self, service):
        """测试空用户统计"""
        stats = await service.get_statistics("nonexistent")
        
        assert stats["total"] == 0
        assert stats["avg_slides_per_ppt"] == 0
    
    @pytest.mark.asyncio
    async def test_record_id_auto_increment(self, service):
        """测试记录 ID 自动递增"""
        record1 = await service.create_record(
            user_id="user_1", task_id="task_1", topic="t1",
            template_id="m", slide_count=5, file_id="f1",
        )
        
        record2 = await service.create_record(
            user_id="user_1", task_id="task_2", topic="t2",
            template_id="m", slide_count=5, file_id="f2",
        )
        
        assert record2.id == record1.id + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
