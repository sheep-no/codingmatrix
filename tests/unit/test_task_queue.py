"""
任务队列单元测试

测试 Celery 任务、WebSocket 管理器、优先级解析等功能。
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestParsePriority:
    """测试优先级解析"""

    def test_parse_priority_high(self):
        """高优先级返回正确值"""
        from app.tasks.base import parse_priority
        assert parse_priority("high") == 8

    def test_parse_priority_medium(self):
        """中优先级返回正确值"""
        from app.tasks.base import parse_priority
        assert parse_priority("medium") == 5

    def test_parse_priority_low(self):
        """低优先级返回正确值"""
        from app.tasks.base import parse_priority
        assert parse_priority("low") == 2

    def test_parse_priority_case_insensitive(self):
        """优先级解析不区分大小写"""
        from app.tasks.base import parse_priority
        assert parse_priority("HIGH") == 8
        assert parse_priority("Medium") == 5
        assert parse_priority("Low") == 2

    def test_parse_priority_unknown_returns_medium(self):
        """未知优先级返回默认值"""
        from app.tasks.base import parse_priority
        assert parse_priority("unknown") == 5
        assert parse_priority("") == 5


class TestParseTimeout:
    """测试超时解析"""

    def test_parse_timeout_default(self):
        """None 返回默认值"""
        from app.tasks.base import parse_timeout
        assert parse_timeout(None) == 300

    def test_parse_timeout_valid(self):
        """有效超时值"""
        from app.tasks.base import parse_timeout
        assert parse_timeout(60) == 60
        assert parse_timeout(600) == 600

    def test_parse_timeout_minimum(self):
        """超时值最小为 30 秒"""
        from app.tasks.base import parse_timeout
        assert parse_timeout(10) == 30
        assert parse_timeout(29) == 30

    def test_parse_timeout_maximum(self):
        """超时值最大为 3600 秒"""
        from app.tasks.base import parse_timeout
        assert parse_timeout(4000) == 3600
        assert parse_timeout(3601) == 3600


class TestTaskStatus:
    """测试任务状态枚举"""

    def test_task_status_values(self):
        """任务状态枚举值正确"""
        from app.models.task import TaskStatus
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.SUCCESS.value == "success"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_task_type_values(self):
        """任务类型枚举值正确"""
        from app.models.task import TaskType
        assert TaskType.PROJECT_GENERATE.value == "project_generate"
        assert TaskType.CODE_GENERATE.value == "code_generate"
        assert TaskType.PPT_GENERATE.value == "ppt_generate"
        assert TaskType.FILE_PROCESS.value == "file_process"

    def test_task_priority_values(self):
        """任务优先级枚举值正确"""
        from app.models.task import TaskPriority
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.MEDIUM.value == "medium"
        assert TaskPriority.LOW.value == "low"


class TestTaskSchema:
    """测试任务 Schema"""

    def test_task_create_request_defaults(self):
        """创建任务请求默认值"""
        from app.schema.task_schema import TaskCreateRequest, TaskPriorityEnum, TaskTypeEnum

        request = TaskCreateRequest(task_type=TaskTypeEnum.PROJECT_GENERATE)
        assert request.priority == TaskPriorityEnum.MEDIUM
        assert request.timeout == 300
        assert request.params == {}
        assert request.input_file_id is None

    def test_task_response_fields(self):
        """任务响应包含所有必要字段"""
        from app.schema.task_schema import TaskResponse

        response = TaskResponse(
            task_id="test_123",
            task_type="project_generate",
            status="pending",
            progress=0,
            progress_message="等待中",
            result=None,
            error_message=None,
            created_at="2026-04-25T12:00:00"
        )

        assert response.task_id == "test_123"
        assert response.priority == 5
        assert response.celery_task_id is None
        assert response.retry_count == 0
        assert response.max_retries == 3


class TestWebSocketManager:
    """测试 WebSocket 管理器"""

    @pytest.mark.asyncio
    async def test_connect_creates_connection(self):
        """连接创建连接记录"""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(user_id=1, websocket=mock_ws)

        assert await manager.get_connection_count() == 1
        conn_info = await manager.get_user_connection(1)
        assert conn_info is not None
        assert conn_info.user_id == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """断开连接移除记录"""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(user_id=1, websocket=mock_ws)
        assert await manager.get_connection_count() == 1

        await manager.disconnect(user_id=1)
        assert await manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        """发送个人消息"""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(user_id=1, websocket=mock_ws)
        await manager.send_personal_message(user_id=1, message={"type": "test"})

        mock_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_task_update_format(self):
        """任务更新消息格式正确"""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(user_id=1, websocket=mock_ws)

        sent_data = None
        original_send_json = mock_ws.send_json
        async def capture_json(data):
            nonlocal sent_data
            sent_data = data
            await original_send_json(data)
        mock_ws.send_json = capture_json

        await manager.send_task_update(
            user_id=1,
            task_id="task_123",
            data={"status": "running", "progress": 50}
        )

        assert sent_data["type"] == "task_update"
        assert sent_data["task_id"] == "task_123"
        assert sent_data["data"]["status"] == "running"
        assert sent_data["data"]["progress"] == 50
        assert "timestamp" in sent_data

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_user(self):
        """发送给不存在的用户不抛出异常"""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()

        await manager.send_personal_message(user_id=999, message={"type": "test"})


class TestProgressCallback:
    """测试进度回调"""

    @pytest.mark.asyncio
    async def test_progress_callback_initial(self):
        """进度回调初始状态"""
        from app.tasks.base import ProgressCallback

        callback = ProgressCallback(task_id="test_123", user_id=1)
        assert callback.task_id == "test_123"
        assert callback.user_id == 1
        assert callback._last_progress == 0


class TestHandleTaskResult:
    """测试任务结果处理"""

    def test_small_result_inline(self):
        """小结果直接存储"""
        from app.tasks.base import handle_task_result

        result = {"data": "test", "value": 123}
        processed = handle_task_result(result, max_size=1024)

        assert processed["stored"] == "inline"
        assert processed["data"] == result

    def test_large_result_stored_in_file(self):
        """大结果存储到文件"""
        from app.tasks.base import handle_task_result
        import os

        large_data = {"data": "x" * 2000}
        processed = handle_task_result(large_data, max_size=100)

        assert processed["stored"] == "file"
        assert "path" in processed
        assert processed["size"] > 100

        if os.path.exists(processed["path"]):
            os.remove(processed["path"])


class TestCeleryApp:
    """测试 Celery 应用配置"""

    def test_celery_app_configured(self):
        """Celery 应用已正确配置"""
        from app.celery_app import celery_app

        assert celery_app.main == "codingmatrix"
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert celery_app.conf.task_time_limit == 300
        assert celery_app.conf.task_max_retries == 3

    def test_celery_tasks_registered(self):
        """Celery 任务已注册"""
        from app.tasks import project_tasks, code_tasks

        assert hasattr(project_tasks, 'generate_project')
        assert hasattr(code_tasks, 'generate_code')
        assert hasattr(code_tasks, 'execute_code')


class TestCeleryTasks:
    """测试 Celery 任务定义"""

    def test_project_generate_task_exists(self):
        """项目生成任务已定义"""
        from app.tasks.project_tasks import generate_project

        assert generate_project.name == "app.tasks.project_tasks.generate_project"
        assert generate_project.max_retries == 3
        assert generate_project.default_retry_delay == 60

    def test_code_generate_task_exists(self):
        """代码生成任务已定义"""
        from app.tasks.code_tasks import generate_code

        assert generate_code.name == "app.tasks.code_tasks.generate_code"
        assert generate_code.max_retries == 3
        assert generate_code.default_retry_delay == 30

    def test_execute_code_task_exists(self):
        """代码执行任务已定义"""
        from app.tasks.code_tasks import execute_code

        assert execute_code.name == "app.tasks.code_tasks.execute_code"
        assert execute_code.max_retries == 2
