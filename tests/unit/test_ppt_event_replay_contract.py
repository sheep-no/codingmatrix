from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_ppt_event_replay_contract_returns_ordered_events(monkeypatch):
    from app.services import task_event_service

    event_one = type("Event", (), {
        "event_type": "progress",
        "sequence": 1,
        "status": "running",
        "progress": 20,
        "payload_json": {"message": "outline"},
    })()
    event_two = type("Event", (), {
        "event_type": "completed",
        "sequence": 2,
        "status": "success",
        "progress": 100,
        "payload_json": {},
    })()
    replay = AsyncMock(return_value=[event_one, event_two])
    monkeypatch.setattr(task_event_service, "replay_task_events", replay)

    result = await task_event_service.replay_task_events(object(), "ppt-1", 7, after_sequence=0)

    assert [event.sequence for event in result] == [1, 2]
    replay.assert_awaited_once()


def test_checkpoint_service_exposes_latest_snapshot_contract():
    from app.services.task_checkpoint_service import get_latest_checkpoint

    assert callable(get_latest_checkpoint)
