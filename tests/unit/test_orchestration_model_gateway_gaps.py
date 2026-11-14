"""ModelGateway 边界补测：校验器、流类型错误与遥测清理分支。"""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.agent.orchestration import (
    ModelCallContext,
    ModelCallTimeout,
    ModelGateway,
)
from app.agent.orchestration.models import utc_now
from tests.unit.test_orchestration_model_gateway import ControlledStream, make_context


def test_context_rejects_naive_timestamps() -> None:
    started = utc_now().replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone-aware"):
        ModelCallContext(
            task_id="t",
            stage_id="s",
            call_id="c",
            started_at=started,
            deadline_at=started + timedelta(seconds=1),
        )


def test_context_rejects_non_positive_window() -> None:
    started = utc_now()
    with pytest.raises(ValidationError, match="deadline_at must be after"):
        ModelCallContext(
            task_id="t",
            stage_id="s",
            call_id="c",
            started_at=started,
            deadline_at=started,
        )


def test_model_profile_property_and_default_activity() -> None:
    gateway = ModelGateway(lambda **_: None)

    assert gateway.model_profile is None
    activity = gateway.activity_for("missing")
    assert activity.call_id == "missing"
    assert gateway.telemetry_for("missing") is None


@pytest.mark.asyncio
async def test_non_streaming_call_rejects_stream_result() -> None:
    stream = ControlledStream(["x"])

    async def caller(**_: Any) -> ControlledStream:
        return stream

    with pytest.raises(Exception, match="non-streaming model call returned a stream"):
        await ModelGateway(caller).call(make_context(1.0), prompt="hi")

    assert stream.closed is True


@pytest.mark.asyncio
async def test_streaming_call_rejects_non_stream_result() -> None:
    async def caller(**_: Any) -> dict[str, Any]:
        return {}

    with pytest.raises(Exception, match="streaming model call returned a non-stream result"):
        async for _ in ModelGateway(caller).stream(make_context(1.0), prompt="hi"):
            pass


@pytest.mark.asyncio
async def test_stream_consumed_to_exhaustion_completes_telemetry() -> None:
    class _FiniteStream(ControlledStream):
        async def __anext__(self) -> str:
            if self.chunks:
                return self.chunks.pop(0)
            raise StopAsyncIteration

    stream = _FiniteStream(["a", "b"])

    async def caller(**_: Any) -> ControlledStream:
        return stream

    gateway = ModelGateway(caller)
    received = [chunk async for chunk in gateway.stream(make_context(1.0), prompt="hi")]

    assert received == ["a", "b"]
    assert stream.closed is True
    telemetry = gateway.telemetry_for("call-1")
    assert telemetry is not None and telemetry.completed_at is not None


@pytest.mark.asyncio
async def test_messages_are_measured_for_input_chars() -> None:
    async def caller(**_: Any) -> dict[str, Any]:
        return {}

    gateway = ModelGateway(caller)
    await gateway.call(
        make_context(1.0),
        messages=[{"content": "abc"}, {"content": "de"}],
    )

    telemetry = gateway.telemetry_for("call-1")
    assert telemetry is not None
    assert telemetry.input_chars == 5


def test_telemetry_helpers_tolerate_missing_call_and_non_dict_payloads() -> None:
    gateway = ModelGateway(lambda **_: None)
    context = make_context(1.0)

    gateway._finish_telemetry(context)
    gateway._merge_response_metadata(context.call_id, {"usage": {"total_tokens": 1}})
    gateway._record_telemetry_chunk(context, {"not": "a string"})
    gateway._record_telemetry_chunk(context, "42")

    assert gateway.telemetry_for(context.call_id) is None


@pytest.mark.asyncio
async def test_finish_telemetry_after_external_removal_is_noop() -> None:
    async def caller(**_: Any) -> dict[str, Any]:
        return {}

    gateway = ModelGateway(caller)
    context = make_context(1.0)
    await gateway.call(context, prompt="hi")
    gateway._telemetry.pop(context.call_id)

    gateway._finish_telemetry(context)
    gateway._merge_response_metadata(context.call_id, {"usage": {"total_tokens": 3}})

    assert gateway.telemetry_for(context.call_id) is None


@pytest.mark.asyncio
async def test_expired_deadline_raises_timeout() -> None:
    async def caller(**_: Any) -> dict[str, Any]:
        return {}

    context = make_context(0.01)
    await asyncio.sleep(0.03)

    with pytest.raises(ModelCallTimeout):
        await ModelGateway(caller).call(context, prompt="hi")


@pytest.mark.asyncio
async def test_cancel_before_await_closes_coroutine() -> None:
    gateway = ModelGateway(lambda **_: None)
    cancel_event = asyncio.Event()
    cancel_event.set()

    async def pending() -> None:
        raise AssertionError("should not run")

    with pytest.raises(Exception, match="cancelled"):
        await gateway._await_with_cancel(pending(), make_context(1.0), cancel_event)


class _PlainAwaitable:
    def __await__(self):
        raise AssertionError("should not be awaited")


@pytest.mark.asyncio
async def test_cancel_before_await_skips_non_coroutine_close() -> None:
    gateway = ModelGateway(lambda **_: None)
    cancel_event = asyncio.Event()
    cancel_event.set()

    with pytest.raises(Exception, match="cancelled"):
        await gateway._await_with_cancel(_PlainAwaitable(), make_context(1.0), cancel_event)


@pytest.mark.asyncio
async def test_cancel_event_unset_returns_operation_result() -> None:
    async def immediate() -> str:
        return "done"

    gateway = ModelGateway(lambda **_: None)
    result = await gateway._await_with_cancel(
        immediate(), make_context(1.0), asyncio.Event()
    )

    assert result == "done"


@pytest.mark.asyncio
async def test_close_stream_without_aclose_is_noop() -> None:
    await ModelGateway._close_stream(object())


@pytest.mark.asyncio
async def test_close_stream_swallows_errors() -> None:
    class _Broken:
        async def aclose(self):
            raise RuntimeError("boom")

    await ModelGateway._close_stream(_Broken())


@pytest.mark.asyncio
async def test_finish_telemetry_stops_when_metadata_merge_removes_entry(monkeypatch) -> None:
    async def caller(**_: Any) -> dict[str, Any]:
        return {"usage": {"total_tokens": 1}}

    gateway = ModelGateway(caller)
    context = make_context(1.0)
    await gateway.call(context, prompt="hi")

    original = gateway._merge_response_metadata
    monkeypatch.setattr(
        gateway, "_merge_response_metadata",
        lambda call_id, response: gateway._telemetry.pop(call_id, None),
    )
    gateway._finish_telemetry(context, {"usage": {"total_tokens": 2}})
    monkeypatch.setattr(gateway, "_merge_response_metadata", original)

    assert gateway.telemetry_for(context.call_id) is None


@pytest.mark.asyncio
async def test_cancel_after_operation_completed_closes_stream_result() -> None:
    stream = ControlledStream(["x"])
    cancel_event = asyncio.Event()
    gateway = ModelGateway(lambda **_: None)

    async def completes_with_stream() -> ControlledStream:
        cancel_event.set()
        return stream

    with pytest.raises(Exception, match="cancelled"):
        await gateway._await_with_cancel(
            completes_with_stream(), make_context(1.0), cancel_event
        )

    assert stream.closed is True


@pytest.mark.asyncio
async def test_cancel_while_operation_pending_cancels_operation() -> None:
    cancel_event = asyncio.Event()
    gateway = ModelGateway(lambda **_: None)

    async def hanging() -> None:
        await asyncio.Future()

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        cancel_event.set()

    trigger_task = asyncio.create_task(trigger())
    with pytest.raises(Exception, match="cancelled"):
        await gateway._await_with_cancel(hanging(), make_context(1.0), cancel_event)

    await trigger_task


@pytest.mark.asyncio
async def test_external_cancellation_propagates_from_await_with_cancel() -> None:
    gateway = ModelGateway(lambda **_: None)

    async def hanging() -> None:
        await asyncio.Future()

    task = asyncio.create_task(
        gateway._await_with_cancel(hanging(), make_context(1.0), None)
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_with_completed_non_stream_result_cleans_operation() -> None:
    cancel_event = asyncio.Event()
    gateway = ModelGateway(lambda **_: None)

    async def completes_with_value() -> str:
        cancel_event.set()
        return "value"

    with pytest.raises(Exception, match="cancelled"):
        await gateway._await_with_cancel(
            completes_with_value(), make_context(1.0), cancel_event
        )


@pytest.mark.asyncio
async def test_external_cancellation_with_cancel_event_propagates() -> None:
    gateway = ModelGateway(lambda **_: None)

    async def hanging() -> None:
        await asyncio.Future()

    task = asyncio.create_task(
        gateway._await_with_cancel(hanging(), make_context(1.0), asyncio.Event())
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
