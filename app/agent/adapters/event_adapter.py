"""Translate legacy progress callback payloads into MessageEnvelope."""

from __future__ import annotations

import json
from typing import Any, Dict

from app.agent.state import MessageEnvelope


def progress_event_to_message(
    event: str | Dict[str, Any],
    *,
    session_id: str,
    task_id: str,
    revision: int,
    sequence: int,
) -> MessageEnvelope:
    if isinstance(event, str):
        try:
            payload = json.loads(event)
        except json.JSONDecodeError:
            payload = {"message": event}
    elif isinstance(event, dict):
        payload = dict(event)
    else:
        payload = {"value": str(event)}
    event_type = str(payload.pop("type", "progress"))
    return MessageEnvelope(
        schema_version=1,
        event_id=f"{task_id}:{revision}:{sequence}",
        session_id=session_id,
        task_id=task_id,
        revision=revision,
        sequence=sequence,
        type=event_type,
        source="legacy_progress",
        payload=payload,
    )
