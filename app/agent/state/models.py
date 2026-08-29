"""Serializable state and event models shared by graph nodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEnvelope":
        return cls(**data)


@dataclass
class State:
    session_id: str
    task_id: str
    revision: int = 0
    status: str = "planned"
    messages: List[MessageEnvelope] = field(default_factory=list)
    planned_changes: List[Dict[str, Any]] = field(default_factory=list)
    generated_files: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["messages"] = [message.to_dict() for message in self.messages]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "State":
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
    status: Optional[str] = None
    messages: List[MessageEnvelope] = field(default_factory=list)
    planned_changes: List[Dict[str, Any]] = field(default_factory=list)
    generated_files: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)
    replace_pending_actions: Optional[List[Dict[str, Any]]] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
