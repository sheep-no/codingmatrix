"""Translate legacy endpoint result dictionaries into StateDelta objects."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.agent.state import MessageEnvelope, StateDelta


def legacy_result_to_delta(
    result: Any,
    *,
    session_id: str,
    task_id: str,
    revision: int,
    node: str = "legacy_agent",
) -> StateDelta:
    """Normalize common generate, modify, and orchestrate result shapes."""
    data = result if isinstance(result, dict) else {"result": result}
    status = _status(data)
    message = MessageEnvelope(
        schema_version=1,
        event_id=f"{task_id}:{revision}:{node}",
        session_id=session_id,
        task_id=task_id,
        revision=revision,
        sequence=revision + 1,
        type=f"{node}.completed",
        source="legacy_adapter",
        payload={"status": status},
    )
    validation = data.get("validation")
    validation_results = [validation] if isinstance(validation, dict) else []
    errors = _errors(data)
    return StateDelta(
        expected_revision=revision,
        status=status,
        messages=[message],
        generated_files=_files(data),
        validation_results=validation_results,
        errors=errors,
        metadata={"legacy_node": node},
    )


def _status(data: Dict[str, Any]) -> str:
    if data.get("status") in {"failed", "partial_success", "completed"}:
        return data["status"]
    validation = data.get("validation")
    if isinstance(validation, dict) and validation.get("runnable") is False:
        return "partial_success"
    if data.get("success") is False:
        return "failed"
    return "completed"


def _files(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = data.get("generated_files", data.get("files", []))
    if isinstance(candidates, dict):
        candidates = [{"path": path, **value} if isinstance(value, dict) else {"path": path, "content": value}
                      for path, value in candidates.items()]
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _errors(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_errors = data.get("errors", [])
    if isinstance(raw_errors, str):
        raw_errors = [raw_errors]
    return [
        item if isinstance(item, dict) else {
            "code": "legacy.error",
            "message": str(item),
            "retryable": False,
            "details": {},
        }
        for item in raw_errors
    ] if isinstance(raw_errors, list) else []
