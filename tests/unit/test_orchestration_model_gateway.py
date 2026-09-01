"""Wall-clock budget and cancellation tests for Orchestrator ModelGateway."""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.agent.orchestration import (
    ExecutionBudget,
    ExecutionBudgetExhausted,
    ModelCallCancelled,
    ModelCallContext,
    ModelCallTimeout,
    ModelGateway,
    ModelStreamDataKind,
)
from app.agent.orchestration.models import utc_now
from app.utils.aicloud.llm_caller import _SemaphoreWrappedAsyncIterator


class ControlledStream:
    def __init__(self, chunks: list[str] | None = None, *, interval: float = 0.0) -> None:
        self.chunks = list(chunks or [])
        self.interval = interval
        self.closed = False
        self.close_calls = 0

    def __aiter__(self) -> "ControlledStream":
        return self

    async def __anext__(self) -> str:
        if self.interval:
            await asyncio.sleep(self.interval)
        if self.chunks:
            return self.chunks.pop(0)
        await asyncio.Future()
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        self.closed = True
        self.close_calls += 1


def make_budget(**updates: float) -> ExecutionBudget:
    values = {
        "task_seconds": 1.0,
        "stage_seconds": 0.8,
        "file_seconds": 0.5,
        "model_call_seconds": 0.1,
    }
    values.update(updates)
    return ExecutionBudget(**values)


def make_context(seconds: float = 0.05) -> ModelCallContext:
    started_at = utc_now()
    return ModelCallContext(
        task_id="task-1",
        stage_id="generating-1",
        file_path="src/main.py",
        call_id="call-1",
        react_round=2,
        started_at=started_at,
        deadline_at=started_at + timedelta(seconds=seconds),
    )


def test_execution_budget_is_immutable_and_hierarchical() -> None:
    budget = make_budget()

    assert budget.remaining_model_seconds(file_elapsed_seconds=0.45) == pytest.approx(0.05)
    with pytest.raises(ValidationError, match="model_call_seconds"):
        make_budget(model_call_seconds=0.6)
    with pytest.raises(ValidationError, match="frozen"):
        budget.task_seconds = 2.0


def test_exhausted_parent_budget_identifies_scope() -> None:
    with pytest.raises(ExecutionBudgetExhausted) as raised:
        make_budget().remaining_model_seconds(stage_elapsed_seconds=0.8)

    assert raised.value.scope == "stage"


def test_context_uses_smallest_remaining_scope_for_deadline() -> None:
    context = ModelCallContext.from_budget(
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
        file_path="main.py",
        call_id="call-1",
        file_elapsed_seconds=0.46,
    )

    assert (context.deadline_at - context.started_at).total_seconds() == pytest.approx(0.04)


@pytest.mark.asyncio
async def test_non_streaming_call_times_out_with_structured_diagnostic() -> None:
    async def hanging_caller(**_: Any) -> dict[str, Any]:
        await asyncio.Future()
        raise AssertionError("unreachable")

    with pytest.raises(ModelCallTimeout) as raised:
        await ModelGateway(hanging_caller).call(make_context(0.02), model="test", prompt="hi")

    assert raised.value.diagnostic == {
        "code": "model_timeout",
        "message": "model call wall-clock deadline exceeded",
        "task_id": "task-1",
        "stage_id": "generating-1",
        "file_path": "src/main.py",
        "call_id": "call-1",
        "react_round": 2,
    }


@pytest.mark.asyncio
async def test_keepalive_activity_does_not_extend_stream_deadline() -> None:
    stream = ControlledStream([": heartbeat"] * 100, interval=0.004)

    async def caller(**_: Any) -> ControlledStream:
        return stream

    gateway = ModelGateway(caller)
    observed = []
    with pytest.raises(ModelCallTimeout):
        async for chunk in gateway.stream(make_context(0.025), model="test", prompt="hi"):
            observed.append(chunk)

    activity = gateway.activity_for("call-1")
    assert observed
    assert activity.last_keepalive_at is not None
    assert activity.last_model_data_at is None
    assert stream.closed is True


@pytest.mark.asyncio
async def test_model_and_stream_activity_are_tracked_separately() -> None:
    chunks = [
        ': heartbeat',
        '{"usage":{"completion_tokens":1}}',
        '{"choices":[{"delta":{"content":"hello"}}]}',
    ]
    stream = ControlledStream(chunks)
    observations: list[ModelStreamDataKind] = []

    async def caller(**_: Any) -> ControlledStream:
        return stream

    gateway = ModelGateway(
        caller,
        activity_callback=lambda _context, kind, _at: observations.append(kind),
    )
    received = []
    gateway_stream = gateway.stream(make_context(), model="test", prompt="hi")
    try:
        async for chunk in gateway_stream:
            received.append(chunk)
            if len(received) == 3:
                break
    finally:
        await gateway_stream.aclose()

    activity = gateway.activity_for("call-1")
    assert observations == [
        ModelStreamDataKind.KEEPALIVE,
        ModelStreamDataKind.STREAM_DATA,
        ModelStreamDataKind.MODEL_DATA,
    ]
    assert activity.last_stream_data_at is not None
    assert activity.last_keepalive_at is not None
    assert activity.last_model_data_at is not None
    assert stream.closed is True


@pytest.mark.asyncio
async def test_user_cancellation_closes_hanging_stream() -> None:
    stream = ControlledStream()
    cancel_event = asyncio.Event()

    async def caller(**_: Any) -> ControlledStream:
        return stream

    async def consume() -> None:
        async for _ in ModelGateway(caller).stream(
            make_context(1.0), cancel_event=cancel_event, model="test", prompt="hi"
        ):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    cancel_event.set()

    with pytest.raises(ModelCallCancelled) as raised:
        await task
    assert raised.value.diagnostic["code"] == "model_cancelled"
    assert stream.closed is True


@pytest.mark.asyncio
async def test_external_task_cancellation_closes_hanging_stream() -> None:
    stream = ControlledStream()

    async def caller(**_: Any) -> ControlledStream:
        return stream

    async def consume() -> None:
        async for _ in ModelGateway(caller).stream(make_context(1.0), model="test", prompt="hi"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed is True


@pytest.mark.asyncio
async def test_semaphore_stream_close_is_idempotent() -> None:
    stream = ControlledStream()
    global_sem = asyncio.Semaphore(0)
    model_sem = asyncio.Semaphore(0)
    wrapped = _SemaphoreWrappedAsyncIterator(stream, global_sem, model_sem)

    await wrapped.aclose()
    await wrapped.aclose()

    assert global_sem._value == 1
    assert model_sem._value == 1
    assert stream.close_calls == 1


@pytest.mark.asyncio
async def test_semaphore_stream_releases_on_cancelled_iteration() -> None:
    stream = ControlledStream()
    global_sem = asyncio.Semaphore(0)
    model_sem = asyncio.Semaphore(0)
    wrapped = _SemaphoreWrappedAsyncIterator(stream, global_sem, model_sem)
    task = asyncio.create_task(wrapped.__anext__())
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert global_sem._value == 1
    assert model_sem._value == 1
    assert stream.closed is True
