"""aicloud 核心路由与审计回归测试

覆盖已建档缺陷：
- ADT1 audit details 以 Python repr 字符串落库，无法结构化使用
- PR1 route() 前缀模糊匹配把未知模型误路由到官方供应商
- DP2 fetch_models_openai 向用户可控 base_url 发请求时无 SSRF 校验
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.aicloud.audit_logger import log_operation
from app.utils.aicloud.dynamic_provider import DynamicProvider, Protocol, fetch_models_openai
from app.utils.aicloud.provider_router import ProviderRouter, MODEL_PROVIDER_MAP
from app.utils.aicloud.providers import ModelProvider


async def test_log_operation_serializes_details_as_json():
    """ADT1：details 落库为合法 JSON，而非 Python repr 单引号字符串。"""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    log = await log_operation(
        db=db,
        user_id=1,
        operation="file_read",
        status="success",
        details={"action": "read", "path": "/tmp/中文.txt"},
    )

    parsed = json.loads(log.details)
    assert parsed == {"action": "read", "path": "/tmp/中文.txt"}


def test_route_does_not_prefix_match_unknown_model():
    """PR1：带后缀的未知模型不再前缀命中已映射供应商。"""
    ProviderRouter.clear_cache()
    router = ProviderRouter.get_instance()

    # 精确名仍正常路由
    assert MODEL_PROVIDER_MAP.get("deepseek-chat") is ModelProvider.DEEPSEEK
    assert router.route("deepseek-chat") == ModelProvider.DEEPSEEK

    # 未精确映射的变体不得再被前缀命中到 DEEPSEEK
    assert router.route("deepseek-chat-v9-unknown") == ModelProvider.SILICONFLOW


async def test_fetch_models_openai_blocks_internal_base_url(monkeypatch):
    """DP2：库函数层拒绝向内网 base_url 发请求。"""
    provider = DynamicProvider(
        id="p1",
        name="internal",
        base_url="http://127.0.0.1:8000",
        protocol=Protocol.OPENAI,
        api_key="sk-test",
    )

    def _no_network(*args, **kwargs):
        raise AssertionError("不应向非公网地址发起请求")

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.httpx.AsyncClient", _no_network
    )

    with pytest.raises(ValueError, match="不安全"):
        await fetch_models_openai(provider)
