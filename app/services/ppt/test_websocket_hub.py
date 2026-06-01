"""
PPT WebSocket 进度中心单元测试

测试 WebSocket 进度中心的核心功能：
- 连接和订阅管理
- 进度推送
- 完成/错误消息
- 状态查询和历史消息
- 清理过期任务
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ppt.websocket_hub import (
    WebSocketProgressHub,
    TaskProgressState,
    progress_hub,
)


@pytest.fixture
def hub():
    """创建进度中心实例"""
    return WebSocketProgressHub()


@pytest.fixture
def mock_websocket():
    """模拟 WebSocket"""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestTaskProgressState:
    """任务状态测试"""
    
    def test_default_state(self):
        """测试默认状态"""
        state = TaskProgressState(task_id="test_123", user_id="user_1")
        
        assert state.task_id == "test_123"
        assert state.user_id == "user_1"
        assert state.status == "pending"
        assert state.progress == 0.0
        assert state.current_step == ""
        assert state.result is None
        assert state.error is None
    
    def test_progress_bounds(self):
        """测试进度边界"""
        state = TaskProgressState(
            task_id="test",
            user_id="user_1",
            progress=1.0,
            status="completed",
        )
        
        assert state.progress == 1.0
        assert state.status == "completed"


class TestWebSocketProgressHub:
    """WebSocket 进度中心测试"""
    
    def test_create_task_state(self, hub):
        """测试创建任务状态"""
        state = hub.create_task_state(
            task_id="task_123",
            user_id="user_456",
            topic="AI 发展趋势",
        )
        
        assert state.task_id == "task_123"
        assert state.user_id == "user_456"
        assert "AI 发展趋势" in state.message
        assert state.status == "pending"
        assert state.progress == 0.0
    
    def test_get_task_state(self, hub):
        """测试获取任务状态"""
        hub.create_task_state("task_1", "user_1")
        
        state = hub.get_task_state("task_1")
        assert state is not None
        assert state.task_id == "task_1"
    
    def test_get_nonexistent_task_state(self, hub):
        """测试获取不存在的任务状态"""
        state = hub.get_task_state("nonexistent")
        assert state is None
    
    @pytest.mark.asyncio
    async def test_push_progress(self, hub):
        """测试推送进度"""
        hub.create_task_state("task_1", "user_1")
        hub._subscribe_task("task_1", "user_1")
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            await hub.push_progress(
                task_id="task_1",
                progress=0.5,
                step="generating_content",
                message="正在生成内容",
            )
            
            # 验证状态更新
            state = hub.get_task_state("task_1")
            assert state.progress == 0.5
            assert state.current_step == "generating_content"
            assert state.status == "running"
            
            # 验证消息发送
            mock_ws.send_personal_message.assert_called_once()
            call_args = mock_ws.send_personal_message.call_args
            assert call_args[0][1]["type"] == "progress"
            assert call_args[0][1]["progress"] == 0.5
    
    @pytest.mark.asyncio
    async def test_push_complete(self, hub):
        """测试推送完成消息"""
        hub.create_task_state("task_1", "user_1")
        hub._subscribe_task("task_1", "user_1")
        
        result = {
            "file_id": "file_123",
            "download_url": "/api/ppt/download/file_123",
            "slide_count": 8,
        }
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            await hub.push_complete("task_1", result)
            
            # 验证状态更新
            state = hub.get_task_state("task_1")
            assert state.status == "completed"
            assert state.progress == 1.0
            assert state.result == result
            
            # 验证消息发送
            call_args = mock_ws.send_personal_message.call_args
            assert call_args[0][1]["type"] == "complete"
            assert call_args[0][1]["result"] == result
    
    @pytest.mark.asyncio
    async def test_push_error(self, hub):
        """测试推送错误消息"""
        hub.create_task_state("task_1", "user_1")
        hub._subscribe_task("task_1", "user_1")
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            await hub.push_error("task_1", "AI 服务调用失败")
            
            # 验证状态更新
            state = hub.get_task_state("task_1")
            assert state.status == "failed"
            assert state.error == "AI 服务调用失败"
            
            # 验证消息发送
            call_args = mock_ws.send_personal_message.call_args
            assert call_args[0][1]["type"] == "error"
            assert call_args[0][1]["error"] == "AI 服务调用失败"
    
    @pytest.mark.asyncio
    async def test_push_cancelled(self, hub):
        """测试推送取消消息"""
        hub.create_task_state("task_1", "user_1")
        hub._subscribe_task("task_1", "user_1")
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            await hub.push_cancelled("task_1")
            
            # 验证状态更新
            state = hub.get_task_state("task_1")
            assert state.status == "cancelled"
            
            # 验证消息发送
            call_args = mock_ws.send_personal_message.call_args
            assert call_args[0][1]["type"] == "cancelled"
    
    @pytest.mark.asyncio
    async def test_message_history(self, hub):
        """测试消息历史"""
        hub.create_task_state("task_1", "user_1")
        
        # 推送多条消息
        await hub.push_progress("task_1", 0.2, "step_1")
        await hub.push_progress("task_1", 0.5, "step_2")
        await hub.push_progress("task_1", 0.8, "step_3")
        
        # 验证历史消息存在
        history = hub._message_history.get("task_1", [])
        assert len(history) == 3
        assert history[0]["step"] == "step_1"
        assert history[1]["step"] == "step_2"
        assert history[2]["step"] == "step_3"
    
    @pytest.mark.asyncio
    async def test_message_history_limit(self, hub):
        """测试消息历史大小限制"""
        hub.create_task_state("task_1", "user_1")
        
        # 推送超过限制的消息
        for i in range(15):
            await hub.push_progress("task_1", (i + 1) * 0.1, f"step_{i}")
        
        # 验证历史不超过最大限制
        history = hub._message_history.get("task_1", [])
        assert len(history) <= hub._max_history_size
        
        # 验证保留的是最新的消息
        assert history[-1]["step"] == "step_14"
    
    def test_cleanup_finished_tasks(self, hub):
        """测试清理过期任务"""
        # 创建过期任务
        old_state = hub.create_task_state("old_task", "user_1")
        old_state.status = "completed"
        old_state.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # 创建新任务
        new_state = hub.create_task_state("new_task", "user_1")
        new_state.status = "completed"
        # 新任务不更新时间
        
        # 清理
        cleaned = hub.cleanup_finished_tasks(max_age_minutes=30)
        
        assert cleaned == 1
        assert hub.get_task_state("old_task") is None
        assert hub.get_task_state("new_task") is not None
    
    def test_subscribe_unsubscribe(self, hub):
        """测试订阅和取消订阅"""
        hub._subscribe_task("task_1", "user_1")
        hub._subscribe_task("task_1", "user_2")
        
        assert "user_1" in hub._task_subscriptions["task_1"]
        assert "user_2" in hub._task_subscriptions["task_1"]
        
        hub._unsubscribe_task("task_1", "user_1")
        assert "user_1" not in hub._task_subscriptions["task_1"]
        assert "user_2" in hub._task_subscriptions["task_1"]
        
        hub._unsubscribe_task("task_1", "user_2")
        assert "task_1" not in hub._task_subscriptions
    
    def test_parse_user_id(self):
        """测试用户 ID 解析"""
        assert WebSocketProgressHub._parse_user_id("user_123") == 123
        assert WebSocketProgressHub._parse_user_id("456") == 456
        assert WebSocketProgressHub._parse_user_id("invalid") == 0
    
    @pytest.mark.asyncio
    async def test_progress_bounds_clamping(self, hub):
        """测试进度边界限制"""
        hub.create_task_state("task_1", "user_1")
        
        # 测试超过 1.0
        await hub.push_progress("task_1", 1.5, "step")
        state = hub.get_task_state("task_1")
        assert state.progress <= 1.0
        
        # 测试低于 0.0
        await hub.push_progress("task_1", -0.1, "step")
        state = hub.get_task_state("task_1")
        assert state.progress >= 0.0


class TestProgressHubIntegration:
    """进度中心集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, hub):
        """测试完整任务生命周期"""
        task_id = "lifecycle_test"
        user_id = "user_1"
        
        # 1. 创建任务
        hub.create_task_state(task_id, user_id, "测试主题")
        hub._subscribe_task(task_id, user_id)
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            # 2. 进度更新
            await hub.push_progress(task_id, 0.25, "generating_outline")
            state = hub.get_task_state(task_id)
            assert state.status == "running"
            assert state.progress == 0.25
            
            await hub.push_progress(task_id, 0.5, "fetching_images")
            assert state.progress == 0.5
            
            await hub.push_progress(task_id, 0.75, "rendering_slides")
            assert state.progress == 0.75
            
            # 3. 任务完成
            result = {"file_id": "file_123", "slide_count": 10}
            await hub.push_complete(task_id, result)
            
            state = hub.get_task_state(task_id)
            assert state.status == "completed"
            assert state.progress == 1.0
            assert state.result == result
            
            # 验证发送了 4 条消息（3 条进度 + 1 条完成）
            assert mock_ws.send_personal_message.call_count == 4
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, hub):
        """测试错误后状态"""
        task_id = "error_test"
        user_id = "user_1"
        
        hub.create_task_state(task_id, user_id)
        hub._subscribe_task(task_id, user_id)
        
        with patch("app.services.ppt.websocket_hub.ws_manager") as mock_ws:
            mock_ws.send_personal_message = AsyncMock()
            
            await hub.push_progress(task_id, 0.5, "processing")
            await hub.push_error(task_id, "网络超时")
            
            state = hub.get_task_state(task_id)
            assert state.status == "failed"
            assert state.error == "网络超时"
            assert state.progress == 0.5  # 保持最后进度


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
