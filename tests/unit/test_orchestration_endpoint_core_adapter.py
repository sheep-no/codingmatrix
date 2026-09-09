import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.orchestration import IncrementalAdapter, SpecFirstAdapter, TraditionalAdapter
from app.api.v1.ai_agent import orchestrate_endpoints
from app.api.v1.ai_agent.schemas import OrchestratorRequest
from app.api.v1.ai_agent.orchestrate_endpoints import (
    _cancel_stream_generation,
    _select_core_adapter,
    _watch_stream_disconnect,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,incremental,expected", [
    ("core", False, "spec_first"),
    ("core", True, "incremental"),
    (None, False, "legacy"),
    (None, True, "legacy"),
    ("legacy", False, "legacy"),
])
async def test_endpoint_routes_explicit_core_and_preserves_legacy_default(
    monkeypatch, tmp_path, engine, incremental, expected
):
    from app.agent import workflow_registry

    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", "legacy")
    result = dict(success=True, output_dir=str(tmp_path), total_files_created=0,
                  files=[], validation={}, errors=[], warnings=[], elapsed_time=0)
    agent = SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock(return_value=result))
    core = AsyncMock(return_value=result)
    shortcut = AsyncMock(return_value=None)
    monkeypatch.setattr(orchestrate_endpoints, "OrchestratorAgent", lambda **kw: agent)
    monkeypatch.setattr(orchestrate_endpoints, "execute_core_generation", core)
    monkeypatch.setattr(orchestrate_endpoints, "generate_single_file", shortcut)
    monkeypatch.setattr(orchestrate_endpoints, "create_agent_session", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrate_endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(workflow_registry, "_checkpoint_store", SimpleNamespace(save=lambda *a: None))
    monkeypatch.setattr(workflow_registry, "_active_workflows", {})
    request = OrchestratorRequest(requirement="implement inventory", engine=engine,
                                  incremental=incremental, enable_skills=False)

    response = await orchestrate_endpoints.orchestrate_project(request, {"sub": "1"}, None)

    assert response.success
    if expected == "legacy":
        agent.generate.assert_awaited_once()
        core.assert_not_awaited()
        shortcut.assert_awaited_once()
    else:
        agent.generate.assert_not_awaited()
        shortcut.assert_not_awaited()
        core.assert_awaited_once()
        assert core.await_args.kwargs["mode"] == expected


def test_engine_schema_rejects_unknown_engine():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OrchestratorRequest(requirement="implement inventory", engine="cor")


def test_core_orchestrate_selects_traditional_adapter_for_standard_request():
    agent = SimpleNamespace(output_dir="/tmp/core-adapter-test")

    adapter, mode = _select_core_adapter(agent, incremental=False, spec_first=False)

    assert isinstance(adapter, TraditionalAdapter)
    assert mode == "traditional"


@pytest.mark.parametrize("incremental", [False, True])
def test_core_request_preserves_structured_context(incremental):
    payload = {
        "requirement": "implement inventory behavior",
        "incremental": incremental,
        "contracts": {"routes": [{
            "method": "PATCH", "path": "/inventory",
            "request_body_schema": {"type": "object"},
            "response_body_schema": False,
            "serialization_guidance": "Encode domain values before sending a JSON body.",
        }]},
        "framework": "flask",
        "runtime": "python3.12",
        "allowed_files": ["inventory.py"],
        "change_plan": [{"path": "inventory.py", "action": "modify"}],
    }
    request = OrchestratorRequest.model_validate(payload)
    metadata = orchestrate_endpoints._core_request_metadata(request)

    for key in ("contracts", "framework", "runtime", "allowed_files", "change_plan"):
        assert metadata[key] == payload[key]
    assert metadata["requested_paths"] == ["inventory.py"]
    assert metadata["user_requirement"] == payload["requirement"]
    metadata["contracts"]["routes"].clear()
    assert request.contracts["routes"]


def test_core_request_omitted_context_does_not_override_adapter_defaults():
    metadata = orchestrate_endpoints._core_request_metadata(
        OrchestratorRequest(requirement="implement inventory behavior")
    )
    assert not {"contracts", "framework", "runtime"}.intersection(metadata)


@pytest.mark.asyncio
async def test_traditional_finalize_projects_legacy_response_fields():
    agent = SimpleNamespace(
        output_dir="/tmp/core-adapter-test",
        complexity=SimpleNamespace(level="medium"),
        model_assignment=SimpleNamespace(
            architect_model="architect",
            frontend_model="frontend",
            backend_model="backend",
            reviewer_model="reviewer",
        ),
    )
    adapter = TraditionalAdapter(agent)
    adapter._plan = SimpleNamespace(files=())
    adapter._started_at = 0.0
    adapter._shared_context = SimpleNamespace(get_artifact_manifest=lambda: {})
    state = SimpleNamespace(status=SimpleNamespace(value="completed"), diagnostics=())

    result = await adapter.finalize(state)

    assert result.result["complexity"] == "medium"
    assert result.result["models_used"]["backend"] == "backend"


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
