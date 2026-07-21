"""E2E 测试共享 fixtures"""
import pytest


@pytest.fixture(autouse=True)
async def _reset_http_client():
    """每次测试后重置共享 HTTP 客户端，避免 Event loop is closed"""
    yield
    from app.utils.aicloud.http_client import close_http_client
    await close_http_client()
