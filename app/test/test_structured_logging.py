"""
测试结构化日志
"""
import pytest
from app.utils.structured_logging import (
    StructuredLogger,
    RequestContextLogger,
    get_request_id,
    generate_request_id,
    setup_request_context,
    clear_request_context,
    log_with_context
)


class TestRequestId:
    """测试 request_id 功能"""

    def test_generate_request_id(self):
        """测试生成 request_id"""
        rid = generate_request_id()
        assert len(rid) == 16
        assert isinstance(rid, str)

    def test_generate_unique_ids(self):
        """测试生成的 ID 是唯一的"""
        ids = [generate_request_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_get_request_id_default_none(self):
        """测试默认返回 None"""
        clear_request_context()
        assert get_request_id() is None

    def test_set_and_get_request_id(self):
        """测试设置和获取"""
        clear_request_context()
        setup_request_context("test-123")
        assert get_request_id() == "test-123"
        clear_request_context()


class TestStructuredLogger:
    """测试结构化日志"""

    def test_create_logger(self):
        """测试创建日志器"""
        logger = StructuredLogger("test.module")
        assert logger.logger.name == "test.module"

    def test_info_log(self):
        """测试 info 日志"""
        logger = StructuredLogger("test.info")
        logger.info("test message")


class TestRequestContextLogger:
    """测试请求上下文日志"""

    def test_create_logger(self):
        """测试创建日志器"""
        logger = RequestContextLogger("test.context")
        assert logger.logger.name == "test.context"

    def test_log_with_context(self):
        """测试带上下文的日志"""
        setup_request_context("ctx-123")
        logger = RequestContextLogger("test.context")
        logger.info("test message", user_id=1, action="test")
        clear_request_context()


class TestLogWithContextDecorator:
    """测试上下文装饰器"""

    @pytest.mark.asyncio
    async def test_decorator(self):
        """测试装饰器"""
        call_count = 0

        @log_with_context("test.decorated")
        async def my_func():
            nonlocal call_count
            call_count += 1
            return get_request_id()

        clear_request_context()
        rid = await my_func()
        assert rid is not None
        assert call_count == 1
