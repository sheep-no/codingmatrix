"""适配器 P2 缺陷回归测试（adapters.md）。
覆盖：
- 每个请求都带上适配器自身的 timeout（此前 Timeout 构造后从不使用，
  所有请求落到共享客户端的 300s 超时）。
- Anthropic 流式事件转换为 OpenAI 兼容 chunk（此前原样透传，下游
  choices[0].delta.content 恒空）。
- Anthropic 供应商 base_url 带 /v1（此前缺 /v1 → 用户自带 Key 404）。
- 非标准字段注入按供应商收敛（此前给 OpenAI/DeepSeek 注入
  enable_thinking/extra_body 等非标准字段）。
"""

import pytest

from app.utils.aicloud.providers import ModelProvider, ProviderConfig


class _FakeResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

    def raise_for_status(self):
        return None


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, lines):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aclose(self):
        return None


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


class _FakeErrorStreamResponse:
    """非 200 流式响应：既提供 aiter_bytes（读错误体），也提供 aiter_lines
    （模拟未做状态检查的适配器把错误体当作 SSE 行消费）。"""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body.encode()

    async def aiter_bytes(self):
        yield self._body

    async def aiter_lines(self):
        for line in self._body.decode(errors="replace").splitlines():
            yield line

    async def aclose(self):
        return None


class _SequencedStreamClient:
    """按调用次序返回预设流式响应，用于验证 stream_options 回退重试。"""

    def __init__(self, responses):
        self.calls = []
        self._responses = list(responses)

    async def post(self, url, **kwargs):  # pragma: no cover - 流式路径不应走此分支
        raise AssertionError("流式路径不应调用 post")

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _FakeStreamContext(self._responses.pop(0))


class _FakeClient:
    def __init__(self, lines=None):
        self.calls = []
        self._lines = lines or []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _FakeResponse()

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _FakeStreamContext(_FakeStreamResponse(self._lines))


def _patch_client(monkeypatch, module, client):
    async def _get_client():
        return client

    monkeypatch.setattr(module, "get_http_client", _get_client)


def _openai_config(provider=ModelProvider.OPENAI, timeout=42.0):
    return ProviderConfig(
        provider=provider,
        api_key="test-key",
        base_url="https://example.com/v1",
        timeout=timeout,
    )


@pytest.mark.asyncio
async def test_openai_adapter_passes_timeout(monkeypatch):
    from app.utils.aicloud.adapters import openai as openai_module
    from app.utils.aicloud.adapters.openai import OpenAIAdapter

    client = _FakeClient()
    _patch_client(monkeypatch, openai_module, client)
    adapter = OpenAIAdapter(_openai_config(timeout=42.0))

    await adapter.call_llm(model="gpt-4o", prompt="hi")
    method, url, kwargs = client.calls[-1]
    assert method == "POST"
    assert kwargs["timeout"].read == 42.0

    await adapter.call_llm(model="gpt-4o", prompt="hi", stream=True)
    method, url, kwargs = client.calls[-1]
    assert kwargs["timeout"].read == 42.0


@pytest.mark.asyncio
async def test_anthropic_adapter_passes_timeout_and_converts_stream(monkeypatch):
    from app.utils.aicloud.adapters import anthropic as anthropic_module
    from app.utils.aicloud.adapters.anthropic import AnthropicAdapter

    lines = [
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{}}',
        'data: {"type":"ping"}',
    ]
    client = _FakeClient(lines=lines)
    _patch_client(monkeypatch, anthropic_module, client)
    adapter = AnthropicAdapter(_openai_config(ModelProvider.ANTHROPIC, timeout=55.0))

    stream = await adapter.call_llm(model="claude-3", prompt="hi", stream=True)
    chunks = [chunk async for chunk in stream]

    assert any('"Hello"' in chunk for chunk in chunks)
    assert any('" world"' in chunk for chunk in chunks)
    assert any('"finish_reason": "end_turn"' in chunk for chunk in chunks)
    # ping 事件不应产出 chunk
    assert all("ping" not in chunk for chunk in chunks)
    assert client.calls[-1][2]["timeout"].read == 55.0


@pytest.mark.asyncio
async def test_dynamic_anthropic_adapter_converts_stream(monkeypatch):
    from app.utils.aicloud.adapters import dynamic as dynamic_module
    from app.utils.aicloud.adapters.dynamic import DynamicAdapter
    from app.utils.aicloud.dynamic_provider import DynamicProvider, Protocol

    lines = [
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}',
    ]
    client = _FakeClient(lines=lines)
    _patch_client(monkeypatch, dynamic_module, client)
    adapter = DynamicAdapter(
        DynamicProvider(
            id="dyn",
            name="dyn",
            base_url="https://example.com",
            api_key="test-key",
            protocol=Protocol.ANTHROPIC,
        )
    )

    stream = await adapter.call_llm(model="claude-3", prompt="hi", stream=True)
    chunks = [chunk async for chunk in stream]

    assert any('"Hi"' in chunk for chunk in chunks)
    assert client.calls[-1][2]["timeout"].read == adapter.timeout


def test_anthropic_sse_converter_ignores_non_text_events():
    from app.utils.aicloud.adapters.base import anthropic_sse_to_openai_chunk

    assert anthropic_sse_to_openai_chunk({"type": "message_start"}) is None
    assert anthropic_sse_to_openai_chunk({"type": "ping"}) is None
    assert anthropic_sse_to_openai_chunk(
        {"type": "content_block_delta", "delta": {"type": "input_json_delta"}}
    ) is None
    converted = anthropic_sse_to_openai_chunk(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}}
    )
    assert converted is not None and '"x"' in converted


def test_anthropic_provider_base_url_has_v1():
    from app.utils.aicloud.llm_caller import _get_provider_base_url

    assert _get_provider_base_url(ModelProvider.ANTHROPIC).endswith("/v1")


def test_request_body_only_injects_thinking_fields_for_supporting_providers():
    from app.utils.aicloud.adapters.dashscope import DashScopeAdapter
    from app.utils.aicloud.adapters.openai import OpenAIAdapter
    from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter

    messages = [{"role": "user", "content": "hi"}]

    official = OpenAIAdapter(_openai_config())._build_request_body(
        model="gpt-4o", messages=messages
    )
    assert "enable_thinking" not in official
    assert "extra_body" not in official

    official_reasoning = OpenAIAdapter(_openai_config())._build_request_body(
        model="o1-reasoner", messages=messages
    )
    assert "extra_body" not in official_reasoning

    dashscope = DashScopeAdapter(
        _openai_config(ModelProvider.DASHSCOPE)
    )._build_request_body(model="qwen3-8b", messages=messages)
    assert dashscope["enable_thinking"] is False

    siliconflow = SiliconFlowAdapter(
        _openai_config(ModelProvider.SILICONFLOW)
    )._build_request_body(model="Qwen/Qwen3.5-4B", messages=messages)
    assert siliconflow["enable_thinking"] is False


@pytest.mark.asyncio
async def test_siliconflow_stream_requests_usage(monkeypatch):
    """LC4：流式请求应带 stream_options.include_usage，末端才会返回 usage。"""
    from app.utils.aicloud.adapters import siliconflow as siliconflow_module
    from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter

    client = _SequencedStreamClient([
        _FakeStreamResponse([
            'data: {"choices":[{"delta":{"content":"hi"}}]}',
            "data: [DONE]",
        ]),
    ])
    _patch_client(monkeypatch, siliconflow_module, client)
    adapter = SiliconFlowAdapter(_openai_config(ModelProvider.SILICONFLOW))

    stream = await adapter.call_llm(model="Qwen/Qwen3.5-4B", prompt="hi", stream=True)
    chunks = [chunk async for chunk in stream]

    assert chunks == ['{"choices":[{"delta":{"content":"hi"}}]}\n']
    assert client.calls[-1][2]["json"]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_siliconflow_stream_retries_without_stream_options_on_400(monkeypatch):
    """LC4：供应商拒收 stream_options 时去掉后重试一次，并记忆为不支持。"""
    from app.utils.aicloud.adapters import siliconflow as siliconflow_module
    from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter

    client = _SequencedStreamClient([
        _FakeErrorStreamResponse(400, '{"error":"unknown field stream_options"}'),
        _FakeStreamResponse([
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]),
    ])
    _patch_client(monkeypatch, siliconflow_module, client)
    adapter = SiliconFlowAdapter(_openai_config(ModelProvider.SILICONFLOW))

    stream = await adapter.call_llm(model="Qwen/Qwen3.5-4B", prompt="hi", stream=True)
    chunks = [chunk async for chunk in stream]

    assert any("ok" in chunk for chunk in chunks)
    assert adapter._stream_usage_supported is False
    assert "stream_options" in client.calls[0][2]["json"]
    assert "stream_options" not in client.calls[1][2]["json"]


@pytest.mark.parametrize(
    "module_name,adapter_name,provider,model",
    [
        ("openai", "OpenAIAdapter", ModelProvider.OPENAI, "gpt-4o-mini"),
        ("deepseek", "DeepSeekAdapter", ModelProvider.DEEPSEEK, "deepseek-chat"),
        ("dashscope", "DashScopeAdapter", ModelProvider.DASHSCOPE, "qwen-plus"),
        ("zhipu", "ZhipuAdapter", ModelProvider.ZHIPU, "glm-4-flash"),
    ],
)
@pytest.mark.asyncio
async def test_official_adapter_stream_raises_on_non_200(
    monkeypatch, module_name, adapter_name, provider, model
):
    """ADP11：非 200 流式响应必须抛错，而非把错误 JSON 当 SSE 逐行产出。"""
    import importlib

    import httpx

    module = importlib.import_module(f"app.utils.aicloud.adapters.{module_name}")
    adapter_cls = getattr(module, adapter_name)

    client = _SequencedStreamClient(
        [_FakeErrorStreamResponse(401, '{"error":"invalid api key"}')]
    )
    _patch_client(monkeypatch, module, client)
    adapter = adapter_cls(_openai_config(provider))

    stream = await adapter.call_llm(model=model, prompt="hi", stream=True)
    with pytest.raises(httpx.HTTPStatusError, match="401"):
        async for _ in stream:
            pass


@pytest.mark.asyncio
async def test_official_adapter_stream_200_still_yields(monkeypatch):
    """非 200 检查不得误伤正常的 200 流式响应。"""
    from app.utils.aicloud.adapters import openai as openai_module
    from app.utils.aicloud.adapters.openai import OpenAIAdapter

    client = _SequencedStreamClient([
        _FakeStreamResponse([
            'data: {"choices":[{"delta":{"content":"hi"}}]}',
            "data: [DONE]",
        ]),
    ])
    _patch_client(monkeypatch, openai_module, client)
    adapter = OpenAIAdapter(_openai_config(ModelProvider.OPENAI))

    stream = await adapter.call_llm(model="gpt-4o-mini", prompt="hi", stream=True)
    chunks = [chunk async for chunk in stream]

    assert chunks == ['{"choices":[{"delta":{"content":"hi"}}]}\n']
