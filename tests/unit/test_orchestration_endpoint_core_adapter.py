import asyncio
from types import SimpleNamespace

import pytest

from app.agent.orchestration import IncrementalAdapter, SpecFirstAdapter, TraditionalAdapter
from app.api.v1.ai_agent import orchestrate_endpoints
from app.api.v1.ai_agent.orchestrate_endpoints import (
    _cancel_stream_generation,
    _select_core_adapter,
    _watch_stream_disconnect,
)


def test_core_orchestrate_selects_traditional_adapter_for_standard_request():
    agent = SimpleNamespace(output_dir="/tmp/core-adapter-test")

    adapter, mode = _select_core_adapter(agent, incremental=False, spec_first=False)

    assert isinstance(adapter, TraditionalAdapter)
    assert mode == "traditional"


def test_core_orchestrate_keeps_specialized_mode_adapters():
    agent = SimpleNamespace(output_dir="/tmp/core-adapter-test")

    incremental, incremental_mode = _select_core_adapter(
        agent, incremental=True, spec_first=False
    )
    spec_first, spec_first_mode = _select_core_adapter(
        agent, incremental=False, spec_first=True
    )

    assert isinstance(incremental, IncrementalAdapter)
    assert incremental_mode == "incremental"
    assert isinstance(spec_first, SpecFirstAdapter)
    assert spec_first_mode == "spec_first"


@pytest.mark.asyncio
async def test_stream_disconnect_signal_converges_generation_task():
    cancel_event = asyncio.Event()
    worker_stopped = asyncio.Event()

    async def worker():
        await cancel_event.wait()
        worker_stopped.set()

    generation_task = asyncio.create_task(worker())
    orchestrate_endpoints._active_tasks["disconnect-session"] = {
        "gen_task": generation_task,
        "cancel_event": cancel_event,
    }

    await _cancel_stream_generation(
        "disconnect-session",
        cancel_event,
        generation_task,
    )

    assert cancel_event.is_set()
    assert worker_stopped.is_set()
    assert generation_task.done()
    assert "disconnect-session" not in orchestrate_endpoints._active_tasks


@pytest.mark.asyncio
async def test_stream_disconnect_force_cancels_unresponsive_generation_task():
    cancel_event = asyncio.Event()

    async def worker():
        await asyncio.Event().wait()

    generation_task = asyncio.create_task(worker())
    await _cancel_stream_generation(
        "stubborn-session",
        cancel_event,
        generation_task,
        grace_seconds=0.01,
    )

    assert cancel_event.is_set()
    assert generation_task.cancelled()


@pytest.mark.asyncio
async def test_disconnect_watcher_propagates_asgi_disconnect():
    cancel_event = asyncio.Event()

    class DisconnectedRequest:
        async def is_disconnected(self):
            return True

    async def worker():
        await cancel_event.wait()

    generation_task = asyncio.create_task(worker())
    await _watch_stream_disconnect(
        DisconnectedRequest(),
        "watch-session",
        cancel_event,
        generation_task,
    )

    assert cancel_event.is_set()
    assert generation_task.done()
