"""Validate and translate VS Code local validation results."""

from __future__ import annotations

from typing import Any, Dict

from app.agent.state import State, StateDelta
from app.agent.nodes.validation import LOCAL_SCOPES, derive_validation_status


def local_result_to_delta(state: State, result: Dict[str, Any]) -> StateDelta:
    if not isinstance(result, dict):
        raise TypeError("local validation result must be a dictionary")
    if result.get("task_id") != state.task_id:
        raise ValueError("local validation task_id does not match state")
    if result.get("revision") != state.revision:
        raise ValueError("local validation revision does not match state")
    if result.get("schema_version", 1) != 1:
        raise ValueError("unsupported local validation schema version")
    scope = result.get("scope")
    if scope not in LOCAL_SCOPES:
        raise ValueError("local validation scope must be local_runtime or local_e2e")
    validation = {
        **result,
        "source": "vscode",
        "scope": scope,
    }
    validations = [*state.validation_results, validation]
    required_scopes = {
        required
        for required in state.metadata.get("required_validation_scopes", [])
        if required in LOCAL_SCOPES
    }
    remaining_actions = []
    for action in state.pending_actions:
        action_scopes = action.get("scopes", [action.get("scope")])
        remaining_scopes = [pending_scope for pending_scope in action_scopes if pending_scope != scope]
        if remaining_scopes:
            remaining_actions.append({**action, "scopes": remaining_scopes})
    return StateDelta(
        expected_revision=state.revision,
        status=derive_validation_status(validations, required_scopes),
        validation_results=[validation],
        replace_pending_actions=remaining_actions,
    )
