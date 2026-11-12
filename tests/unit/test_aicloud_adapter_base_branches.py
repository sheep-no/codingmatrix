"""Branch coverage for app/utils/aicloud/adapters/base.py."""

import asyncio
import json

import httpx
import pytest

from app.utils.aicloud.adapters.base import (
    BaseProviderAdapter,
    anthropic_sse_to_openai_chunk,
)
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


class _ThinkingAdapter(BaseProviderAdapter):
    provider = ModelProvider.SILICONFLOW
    SUPPORTS_THINKING_TOGGLE = True

    async def call_llm(self, *_args, **_kwargs):
        return await super().call_llm(*_args, **_kwargs)

    async def call_embedding(self, *_args, **_kwargs):
        return await super().call_embedding(*_args, **_kwargs)

    def _get_headers(self):
        return super()._get_headers()


def _adapter():
    return _ThinkingAdapter(
        ProviderConfig(provider=ModelProvider.SILICONFLOW, api_key="k", base_url="u")
    )


class TestAbstractDefaults:
    async def test_abstract_call_llm_body_returns_none(self):
        assert await _adapter().call_llm("m", "p") is None

    async def test_abstract_call_embedding_body_returns_none(self):
        assert await _adapter().call_embedding("m", "t") is None

    def test_abstract_get_headers_returns_none(self):
        assert _adapter()._get_headers() is None


class TestThinkingToggle:
    def test_reasoning_model_positive_budget_gets_extra_body(self):
        body = _adapter()._build_request_body(
            model="deepseek-r1", messages=[], thinking_budget=1024
        )
        assert body["extra_body"] == {"thinking_budget": 1024}

    def test_reasoning_model_zero_budget_skips_field(self):
        body = _adapter()._build_request_body(
            model="deepseek-r1", messages=[], thinking_budget=0
        )
        assert "extra_body" not in body

    def test_non_reasoning_model_disables_thinking(self):
        body = _adapter()._build_request_body(
            model="qwen3", messages=[], thinking_budget=1024
        )
        assert body["enable_thinking"] is False

    def test_non_toggle_adapter_leaves_body_plain(self):
        class Plain(_ThinkingAdapter):
            SUPPORTS_THINKING_TOGGLE = False

        body = Plain(
            ProviderConfig(provider=ModelProvider.OPENAI, api_key="k", base_url="u")
        )._build_request_body(model="deepseek-r1", messages=[])
        assert "extra_body" not in body
        assert "enable_thinking" not in body


class TestStreamStatus:
    async def test_ok_status_returns_none(self):
        class Resp:
            status_code = 200

        assert await BaseProviderAdapter._raise_for_stream_status(Resp()) is None

    async def test_error_body_is_bounded_and_embedded(self):
        class Resp:
            status_code = 500
            request = None

            async def aiter_bytes(self):
                yield b"x" * 3000

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await BaseProviderAdapter._raise_for_stream_status(Resp())

        assert "HTTP 500" in str(exc_info.value)
        assert len(str(exc_info.value).split(": ", 1)[1]) <= 500

    async def test_empty_error_stream_still_raises(self):
        class Resp:
            status_code = 502
            request = None

            async def aiter_bytes(self):
                return
                yield b""

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await BaseProviderAdapter._raise_for_stream_status(Resp())

        assert exc_info.value.response.status_code == 502

    async def test_multiple_small_chunks_accumulate(self):
        class Resp:
            status_code = 500
            request = None

            async def aiter_bytes(self):
                yield b"first"
                yield b"second"

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await BaseProviderAdapter._raise_for_stream_status(Resp())

        assert "firstsecond" in str(exc_info.value)

    async def test_read_error_is_swallowed(self):
        class Resp:
            status_code = 503
            request = None

            async def aiter_bytes(self):
                raise RuntimeError("socket broken")
                yield b""

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await BaseProviderAdapter._raise_for_stream_status(Resp())

        assert exc_info.value.response.status_code == 503


class TestAnthropicSse:
    def test_text_delta_is_converted(self):
        converted = anthropic_sse_to_openai_chunk(
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
        )
        assert json.loads(converted)["choices"][0]["delta"]["content"] == "hi"

    def test_empty_text_delta_returns_none(self):
        assert (
            anthropic_sse_to_openai_chunk(
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": ""}}
            )
            is None
        )

    def test_non_text_delta_returns_none(self):
        assert (
            anthropic_sse_to_openai_chunk(
                {"type": "content_block_delta", "delta": {"type": "input_json_delta"}}
            )
            is None
        )

    def test_message_delta_stop_reason_converted(self):
        converted = anthropic_sse_to_openai_chunk(
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}
        )
        assert json.loads(converted)["choices"][0]["finish_reason"] == "end_turn"

    def test_message_delta_without_stop_reason_returns_none(self):
        assert anthropic_sse_to_openai_chunk({"type": "message_delta", "delta": {}}) is None

    def test_unrelated_event_returns_none(self):
        assert anthropic_sse_to_openai_chunk({"type": "message_start"}) is None


class TestHelpers:
    def test_parse_response_content_choices(self):
        assert _adapter()._parse_response_content(
            {"choices": [{"message": {"content": "from-choices"}}]}
        ) == "from-choices"

    def test_parse_response_content_direct_content(self):
        assert _adapter()._parse_response_content({"content": "x"}) == "x"

    def test_parse_response_content_rejects_unknown(self):
        with pytest.raises(ValueError):
            _adapter()._parse_response_content({"error": "e"})

    def test_build_messages_without_system_prompt(self):
        assert _adapter()._build_messages("hello") == [
            {"role": "user", "content": "hello"}
        ]

    def test_build_messages_with_system_prompt(self):
        assert _adapter()._build_messages("hello", "sys") == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
