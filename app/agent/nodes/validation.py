"""Cloud validation and local validation action nodes."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, Set

from app.agent.state import State, StateDelta


LOCAL_SCOPES = {"local_runtime", "local_e2e"}


def _required_scopes(state: State) -> Set[str]:
    configured = state.metadata.get("required_validation_scopes", [])
    if isinstance(configured, str):
        configured = [configured]
    return {scope for scope in configured if scope in LOCAL_SCOPES}


def derive_validation_status(
    validation_results: Iterable[Dict[str, Any]],
    required_scopes: Set[str],
) -> str:
    results = list(validation_results)
    if any(result.get("passed") is False for result in results):
        return "failed"
    completed_scopes = {
        result.get("scope")
        for result in results
        if result.get("passed") is True and result.get("scope") in LOCAL_SCOPES
    }
    if required_scopes - completed_scopes:
        return "waiting_local_validation"
    if required_scopes:
        return "completed"
    return "local_validated" if completed_scopes else "syntax_validated"


async def cloud_validation_node(
    state: State,
    validate: Callable[[State], Any],
) -> StateDelta:
    result = validate(state)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise TypeError("cloud validator must return a dictionary")
    validation = {
        **result,
        "source": "cloud",
        "scope": "cloud_syntax",
    }
    validations = [*state.validation_results, validation]
    required_scopes = _required_scopes(state)
    pending = []
    if required_scopes:
        pending = [
            {
                "type": "local_validation",
                "scopes": sorted(required_scopes),
                "status": "waiting_local_validation",
                "source_revision": state.revision,
            }
        ]
    return StateDelta(
        expected_revision=state.revision,
        status=derive_validation_status(validations, required_scopes),
        validation_results=[validation],
        pending_actions=pending,
    )


def local_validation_action(state: State, action: Dict[str, Any]) -> StateDelta:
    if not isinstance(action, dict) or not action.get("type"):
        raise ValueError("local validation action requires a type")
    scopes = action.get("scopes", action.get("scope", []))
    if isinstance(scopes, str):
        scopes = [scopes]
    if not scopes or any(scope not in LOCAL_SCOPES for scope in scopes):
        raise ValueError("local validation action requires supported scopes")
    pending = {
        **action,
        "scopes": list(scopes),
        "status": "waiting_local_validation",
        "source_revision": state.revision,
    }
    return StateDelta(
        expected_revision=state.revision,
        status="waiting_local_validation",
        pending_actions=[pending],
    )
