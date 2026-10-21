"""Serializable state and event models shared by graph nodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MessageEnvelope:
    schema_version: int
    event_id: str
    session_id: str
    task_id: str
    revision: int
    sequence: int
    type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEnvelope:
        return cls(**data)


@dataclass
class State:
    session_id: str
    task_id: str
    revision: int = 0
    status: str = "planned"
    messages: list[MessageEnvelope] = field(default_factory=list)
    planned_changes: list[dict[str, Any]] = field(default_factory=list)
    generated_files: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["messages"] = [message.to_dict() for message in self.messages]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> State:
        values = dict(data)
        values["messages"] = [
            message if isinstance(message, MessageEnvelope)
            else MessageEnvelope.from_dict(message)
            for message in values.get("messages", [])
        ]
        return cls(**values)


@dataclass
class StateDelta:
    expected_revision: int
    status: str | None = None
    messages: list[MessageEnvelope] = field(default_factory=list)
    planned_changes: list[dict[str, Any]] = field(default_factory=list)
    generated_files: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    replace_pending_actions: list[dict[str, Any]] | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
