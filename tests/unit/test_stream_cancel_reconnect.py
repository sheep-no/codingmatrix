"""Cancel-before-register and stale SSE reconnect contracts."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.helpers import detect_resume_intent
from app.api.v1.ai_agent.schemas import OrchestratorRequest


class ConnectedRequest:
    async def is_disconnected(self):
        return False


class DisconnectedRequest:
    async def is_disconnected(self):
        return True


@pytest.mark.asyncio
async def test_detect_resume_intent_skips_llm_for_plain_requirement(monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("LLM should not be called for a new generation prompt")

    monkeypatch.setattr("app.utils.call_llm", boom)
    result = await detect_resume_intent("写一个 Python 文件 hello.py，运行后打印 Hello World。")
    assert result["is_resume"] is False
    assert result["has_changes"] is False


@pytest.mark.asyncio
async def test_pending_stream_allows_cancel_before_db(monkeypatch):
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess": "42"})
    monkeypatch.setattr(endpoints, "_cancel_events", {"sess": asyncio.Event()})
    await endpoints._verify_session_ownership_or_queue("sess", "42", db=None)
    with pytest.raises(HTTPException) as error:
        await endpoints._verify_session_ownership_or_queue("sess", "99", db=None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_session_cancel_succeeds_for_pending_stream(monkeypatch):
    event = asyncio.Event()
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess": "42"})
    monkeypatch.setattr(endpoints, "_cancel_events", {"sess": event})
    monkeypatch.setattr(endpoints, "_active_tasks", {})
    sm = SimpleNamespace(cancel_session=AsyncMock(), _lock=asyncio.Lock(), _active_sessions={})
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        commit=AsyncMock(),
    )
    result = await endpoints.session_action_endpoint(
        "sess", "cancel", token={"sub": "42", "role": "user"}, db=db
    )
    assert result["status"] == "cancelled"
    assert event.is_set()


@pytest.mark.asyncio
async def test_mark_disconnected_if_stale_clears_connected_flag():
    active = {
        "gen_task": SimpleNamespace(done=lambda: False),
        "connected": True,
        "http_request": DisconnectedRequest(),
    }
    assert await endpoints._mark_disconnected_if_stale(active) is True
    assert active["connected"] is False


@pytest.mark.asyncio
async def test_explicit_reconnect_when_stale_connection(monkeypatch):
    session = SimpleNamespace(session_id="session", status="running")
    monkeypatch.setattr(endpoints, "verify_session_ownership", AsyncMock(return_value=session))
    queue = asyncio.Queue()
    await queue.put('data: {"type":"done","data":{}}\n\n')
    await queue.put("[DONE]")
    active = {
        "gen_task": SimpleNamespace(done=lambda: False),
        "queue": queue,
        "connected": True,
        "http_request": DisconnectedRequest(),
    }
    monkeypatch.setattr(endpoints, "_active_tasks", {"session": active})
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="reconnect", session_id="session", is_resume=True),
        ConnectedRequest(),
        token={"sub": "42"},
        db=None,
    )
    events = [item async for item in response.body_iterator]
    assert len(events) == 1
    assert '"done"' in events[0]
    assert active["connected"] is False


@pytest.mark.asyncio
async def test_live_connection_still_conflicts_on_explicit_resume(monkeypatch):
    session = SimpleNamespace(session_id="session", status="running")
    monkeypatch.setattr(endpoints, "verify_session_ownership", AsyncMock(return_value=session))
    active = {
        "gen_task": SimpleNamespace(done=lambda: False),
        "queue": asyncio.Queue(),
        "connected": True,
        "http_request": ConnectedRequest(),
    }
    monkeypatch.setattr(endpoints, "_active_tasks", {"session": active})
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="reconnect", session_id="session", is_resume=True),
            ConnectedRequest(),
            token={"sub": "42"},
            db=None,
        )
    assert error.value.status_code == 409
    assert "订阅连接" in error.value.detail


@pytest.mark.asyncio
async def test_disconnect_watcher_keeps_generation_running():
    cancel_event = asyncio.Event()

    async def worker():
        await cancel_event.wait()

    generation_task = asyncio.create_task(worker())
    endpoints._active_tasks["watch"] = {
        "gen_task": generation_task,
        "connected": True,
        "http_request": DisconnectedRequest(),
    }
    try:
        await endpoints._watch_stream_disconnect(
            DisconnectedRequest(),
            "watch",
            cancel_event,
            generation_task,
        )
        assert not cancel_event.is_set()
        assert not generation_task.done()
        assert endpoints._active_tasks["watch"]["connected"] is False
    finally:
        generation_task.cancel()
        await asyncio.gather(generation_task, return_exceptions=True)
        endpoints._active_tasks.pop("watch", None)
