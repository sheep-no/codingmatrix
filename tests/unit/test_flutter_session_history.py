"""Session history and explicit reconnect contracts; no generation calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.schemas import OrchestratorRequest


@pytest.mark.asyncio
async def test_history_payload_and_bounded_query(monkeypatch):
    session = SimpleNamespace(session_id="session", requirement="app", status="completed", output_dir="42/app", files_generated=2, files_total=2, error_message=None, created_at=None, last_activity_at=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [session]
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    monkeypatch.setattr(endpoints, "_active_tasks", {})
    response = await endpoints.list_user_sessions(token={"sub": "42"}, db=db, limit=100)
    assert response["sessions"][0]["output_dir"] == "42/app"
    assert response["sessions"][0]["reconnectable"] is False
    assert db.execute.call_args.args[0].compile().params["param_1"] == 50


@pytest.mark.asyncio
async def test_explicit_reconnect_consumes_existing_queue(monkeypatch):
    session = SimpleNamespace(session_id="session", status="running")
    monkeypatch.setattr(endpoints, "verify_session_ownership", AsyncMock(return_value=session))
    queue = asyncio.Queue()
    await queue.put('data: {"type":"done","data":{}}\n\n')
    await queue.put("[DONE]")
    active = {"gen_task": SimpleNamespace(done=lambda: False), "queue": queue, "connected": False}
    monkeypatch.setattr(endpoints, "_active_tasks", {"session": active})
    response = await endpoints.orchestrate_project_stream(OrchestratorRequest(requirement="reconnect", session_id="session", is_resume=True), token={"sub": "42"}, db=None)
    assert active["connected"] is True
    events = [item async for item in response.body_iterator]
    assert len(events) == 1
    assert '"done"' in events[0]
    assert active["connected"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [True, False])
async def test_detail_reconnectable_matches_subscription_state(monkeypatch, connected):
    session = SimpleNamespace(session_id="session", requirement="app", status="running", output_dir="42/app", files_generated=0, files_total=2, error_message=None, created_at=None, last_activity_at=None)
    ownership = AsyncMock(return_value=session)
    monkeypatch.setattr(endpoints, "verify_session_ownership", ownership)
    monkeypatch.setattr(endpoints, "_active_tasks", {"session": {"gen_task": SimpleNamespace(done=lambda: False), "connected": connected}})
    response = await endpoints.get_user_session("session", token={"sub": "42"}, db=None)
    ownership.assert_awaited_once_with(None, "session", "42")
    assert response["reconnectable"] is (not connected)


@pytest.mark.asyncio
async def test_finished_reconnect_returns_conflict_without_generation(monkeypatch):
    monkeypatch.setattr(endpoints, "verify_session_ownership", AsyncMock(return_value=SimpleNamespace(session_id="session", status="completed")))
    monkeypatch.setattr(endpoints, "_active_tasks", {})
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(OrchestratorRequest(requirement="reconnect", session_id="session", is_resume=True), token={"sub": "42"}, db=None)
    assert error.value.status_code == 409
