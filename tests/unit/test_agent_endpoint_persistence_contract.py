import asyncio
from pathlib import Path

from fastapi import HTTPException

from app.api.v1.ai_agent.orchestrate_endpoints import _generation_http_exception
from app.api.v1.ai_agent.orchestrate_endpoints import _generation_result_error
from app.api.v1.ai_agent.orchestrate_endpoints import _active_tasks
from app.api.v1.ai_agent.orchestrate_endpoints import _cancel_active_generation


def test_agent_entrypoints_pass_database_context_to_workflow_runner():
    generate_source = Path("app/api/v1/ai_agent/generate_endpoints.py").read_text(encoding="utf-8")
    orchestrate_source = Path("app/api/v1/ai_agent/orchestrate_endpoints.py").read_text(encoding="utf-8")

    assert generate_source.count("db=db") >= 1
    assert orchestrate_source.count("db=db") >= 3


def test_stream_endpoint_initializes_session_manager_state():
    source = Path("app/api/v1/ai_agent/orchestrate_endpoints.py").read_text(encoding="utf-8")
    stream_source = source.split('@router.post("/orchestrate/stream")', 1)[1]
    stream_source = stream_source.split('@router.post("/stop/{session_id}")', 1)[0]

    assert "session_state = await sm.resume_session(session_id)" in stream_source
    assert "await sm.create_session(" in stream_source


def test_cancel_active_generation_stops_and_removes_task():
    async def scenario():
        started = asyncio.Event()

        async def generation():
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(generation())
        await started.wait()
        _active_tasks["cancel-contract"] = {"gen_task": task}

        assert await _cancel_active_generation("cancel-contract") is True
        assert task.cancelled()
        assert "cancel-contract" not in _active_tasks

    asyncio.run(scenario())


def test_provider_configuration_failure_is_actionable_service_unavailable():
    error = _generation_http_exception(
        RuntimeError("All providers failed. Last error: Provider siliconflow is not configured")
    )

    assert isinstance(error, HTTPException)
    assert error.status_code == 503
    assert "siliconflow" in error.detail


def test_unexpected_generation_failure_remains_internal_error():
    error = _generation_http_exception(RuntimeError("database exploded"))

    assert error.status_code == 500
    assert error.detail == "项目生成失败: database exploded"


def test_unsuccessful_generation_result_has_error_terminal_state():
    assert _generation_result_error({"success": False, "errors": ["crud.py 生成失败"]}) == "crud.py 生成失败"
    assert _generation_result_error({"success": True, "errors": []}) is None
