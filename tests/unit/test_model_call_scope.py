"""Wiring tests: the budgeted ModelGateway scope reaches shared LLM clients."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.llm_client import LLMClient
from app.agent.model_call_scope import (
    ModelCallScope,
    current_model_call_scope,
    model_call_scope,
)
from app.agent.orchestration import ExecutionBudget, ModelGateway


class FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> str:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:
        self.closed = True


def make_budget() -> ExecutionBudget:
    return ExecutionBudget(
        task_seconds=5.0,
        stage_seconds=4.0,
        file_seconds=3.0,
        model_call_seconds=2.0,
    )


@pytest.mark.asyncio
async def test_scope_is_isolated_between_concurrent_tasks() -> None:
    assert current_model_call_scope() is None
    seen: dict[str, str] = {}

    async def worker(name: str, delay: float) -> None:
        scope = ModelCallScope(
            gateway=object(), budget=object(), task_id=name, stage_id="stage"
        )
        with model_call_scope(scope):
            await asyncio.sleep(delay)
            seen[name] = current_model_call_scope().task_id

    await asyncio.gather(worker("a", 0.01), worker("b", 0.02))

    assert seen == {"a": "a", "b": "b"}
    assert current_model_call_scope() is None


@pytest.mark.asyncio
@patch("app.agent.llm_client.LayeredModelRouter")
@patch("app.agent.llm_client.get_dynamic_router")
async def test_gateway_scope_routes_client_call_through_gateway(
    mock_get_router, mock_router_cls
) -> None:
    mock_router_cls.get_model_config.return_value = {
        "max_tokens": 4096,
        "thinking_budget": 0,
        "temperature": 0.7,
        "timeout": 300,
    }
    mock_get_router.return_value = AsyncMock()

    calls: list[dict] = []

    async def caller(**kwargs):
        calls.append(kwargs)
        return {
            "choices": [{"message": {"content": "generated"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }

    gateway = ModelGateway(caller)
    client = LLMClient(model_name="test-model")
    scope = ModelCallScope(
        gateway=gateway,
        budget=make_budget(),
        task_id="task-1",
        stage_id="stage-1",
        file_path="main.py",
    )

    with model_call_scope(scope):
        result = await client.call("Hi", "system")

    assert result == "generated"
    assert len(calls) == 1
    assert calls[0]["model"] == "test-model"
    assert calls[0]["prompt"] == "Hi"
    assert calls[0]["stream"] is False
    assert calls[0]["timeout"] > 0
    assert calls[0]["_skip_semaphore"] is True

    telemetry = list(gateway.telemetry_snapshot().values())[0]
    assert telemetry.prompt_tokens == 7
    assert telemetry.completion_tokens == 3
    assert telemetry.total_tokens == 10
    assert telemetry.finish_reason == "stop"
    assert telemetry.max_tokens == 4096


@pytest.mark.asyncio
@patch("app.agent.llm_client.LayeredModelRouter")
@patch("app.agent.llm_client.get_dynamic_router")
async def test_gateway_scope_routes_streaming_client_through_gateway(
    mock_get_router, mock_router_cls
) -> None:
    mock_router_cls.get_model_config.return_value = {
        "max_tokens": 4096,
        "thinking_budget": 0,
        "temperature": 0.7,
        "timeout": 300,
    }
    mock_get_router.return_value = AsyncMock()

    async def caller(**kwargs):
        if kwargs.get("stream"):
            return FakeStream([
                'data: {"choices":[{"delta":{"content":"hi"}}]}',
                'data: {"choices":[{"delta":{"content":"!"}}],"usage":'
                '{"prompt_tokens":2,"completion_tokens":2}}',
            ])
        return {"choices": [{"message": {"content": "unexpected"}}]}

    gateway = ModelGateway(caller)
    client = LLMClient(model_name="test-model")
    scope = ModelCallScope(
        gateway=gateway,
        budget=make_budget(),
        task_id="task-1",
        stage_id="stage-1",
        file_path="main.py",
    )
    deltas: list[str] = []

    async def on_chunk(content: str, reasoning: str) -> None:
        deltas.append(content)

    with model_call_scope(scope):
        result = await client.call_stream("Hi", "system", on_chunk=on_chunk)

    assert result == "hi!"
    assert deltas == ["hi", "!"]
    telemetry = list(gateway.telemetry_snapshot().values())[0]
    assert telemetry.completion_tokens == 2


@pytest.mark.asyncio
@patch("app.agent.llm_client.LayeredModelRouter")
@patch("app.agent.llm_client.get_dynamic_router")
async def test_gateway_cancellation_surfaces_as_cancelled_error(
    mock_get_router, mock_router_cls
) -> None:
    mock_router_cls.get_model_config.return_value = {
        "max_tokens": 4096,
        "thinking_budget": 0,
        "temperature": 0.7,
        "timeout": 300,
    }
    mock_get_router.return_value = AsyncMock()

    async def caller(**kwargs):
        return {"choices": [{"message": {"content": "never"}}]}

    gateway = ModelGateway(caller)
    client = LLMClient(model_name="test-model")
    scope = ModelCallScope(
        gateway=gateway,
        budget=make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )
    cancel_event = asyncio.Event()
    cancel_event.set()
    client._cancel_event = cancel_event

    with model_call_scope(scope):
        with pytest.raises(asyncio.CancelledError):
            await client.call("Hi")
