"""Readers for checkpoint schema versions and legacy session payloads."""

from __future__ import annotations

from typing import Any, Dict

from .models import MessageEnvelope


def migrate_state_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical State dictionary without mutating the input."""
    data = dict(payload)
    schema_version = data.pop("schema_version", 0)
    state = dict(data.pop("state", data))

    if schema_version not in (0, 1):
        raise ValueError(f"unsupported checkpoint schema version: {schema_version}")

    # SessionManager payloads predate graph state and retain useful file metadata.
    if "task_id" not in state:
        state["task_id"] = state.get("session_id", "legacy-task")
    state.setdefault("session_id", state["task_id"])
    state.setdefault("status", "planned")
    state.setdefault("revision", 0)
    state.setdefault("messages", [])
    state.setdefault("planned_changes", state.pop("file_plan", []))
    state.setdefault("generated_files", _legacy_generated_files(state.pop("file_statuses", {})))
    state.setdefault("validation_results", [])
    state.setdefault("pending_actions", [])
    state.setdefault("errors", _legacy_errors(state.pop("warnings", [])))
    state.setdefault("metadata", {})
    legacy = {
        key: state[key]
        for key in ("requirement", "output_dir", "architecture", "current_step", "current_file")
        if key in state
    }
    if legacy:
        state["metadata"] = {**state["metadata"], "legacy": legacy}
    allowed = {
        "session_id", "task_id", "revision", "status", "messages",
        "planned_changes", "generated_files", "validation_results",
        "pending_actions", "errors", "metadata",
    }
    return {key: value for key, value in state.items() if key in allowed}


def _legacy_generated_files(file_statuses: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [
        {"path": path, **details} if isinstance(details, dict) else {"path": path, "status": details}
        for path, details in file_statuses.items()
    ]


def _legacy_errors(warnings: list[Any]) -> list[Dict[str, Any]]:
    return [{"code": "legacy.warning", "message": str(item), "retryable": False, "details": {}}
            for item in warnings]
