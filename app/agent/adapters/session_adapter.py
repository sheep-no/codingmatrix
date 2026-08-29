"""Compatibility helpers for session state and event stream consumers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.agent.state import MessageEnvelope, State


def state_to_session_summary(state: State) -> Dict[str, Any]:
    return {
        "session_id": state.session_id,
        "task_id": state.task_id,
        "revision": state.revision,
        "status": state.status,
        "generated_files": list(state.generated_files),
        "validation_results": list(state.validation_results),
        "pending_actions": list(state.pending_actions),
        "errors": list(state.errors),
    }


def replay_messages(state: State, after_sequence: int = 0) -> List[Dict[str, Any]]:
    return [
        message.to_dict()
        for message in state.messages
        if message.sequence > after_sequence
    ]


def replay_session(state: State, after_sequence: int = 0) -> Dict[str, Any]:
    """Return replay data and a recovery action when the requested window has a gap."""
    messages = replay_messages(state, after_sequence)
    expected = after_sequence + 1
    sequences = [message["sequence"] for message in messages]
    has_gap = bool(sequences and sequences[0] > expected) or any(
        current != previous + 1
        for previous, current in zip(sequences, sequences[1:])
    )
    return {
        "messages": messages,
        "recovery_action": (
            {
                "type": "snapshot_recovery",
                "task_id": state.task_id,
                "revision": state.revision,
            }
            if has_gap
            else None
        ),
    }
