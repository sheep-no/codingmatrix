"""Tests for the versioned Agent state primitives."""

import pytest

from app.agent.state import MessageEnvelope, State, StateConflictError, StateReducer, StateDelta


def make_message(event_id: str) -> MessageEnvelope:
    return MessageEnvelope(
        schema_version=1,
        event_id=event_id,
        session_id="session-1",
        task_id="task-1",
        revision=0,
        sequence=1,
        type="task.started",
        source="test",
    )


def test_state_round_trip_preserves_message() -> None:
    state = State(session_id="session-1", task_id="task-1", messages=[make_message("event-1")])

    restored = State.from_dict(state.to_dict())

    assert restored.to_dict() == state.to_dict()


def test_reducer_increments_revision_and_deduplicates_event() -> None:
    reducer = StateReducer()
    state = State(session_id="session-1", task_id="task-1")
    delta = StateDelta(expected_revision=0, messages=[make_message("event-1")])

    state = reducer.apply(state, delta)
    state = reducer.apply(state, StateDelta(expected_revision=1, messages=[make_message("event-1")]))

    assert state.revision == 1
    assert [message.event_id for message in state.messages] == ["event-1"]


def test_reducer_rejects_stale_revision() -> None:
    reducer = StateReducer()
    state = State(session_id="session-1", task_id="task-1")

    with pytest.raises(StateConflictError):
        reducer.apply(state, StateDelta(expected_revision=1))
