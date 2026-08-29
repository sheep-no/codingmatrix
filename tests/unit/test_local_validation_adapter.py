"""Tests for local validation result boundaries."""

import pytest

from app.agent.local_validation_adapter import local_result_to_delta
from app.agent.state import State


def test_local_result_requires_supported_scope_and_identity() -> None:
    state = State("s1", "t1", revision=2)
    delta = local_result_to_delta(state, {"task_id": "t1", "revision": 2, "scope": "local_e2e", "passed": True})

    assert delta.status == "local_validated"
    assert delta.validation_results[0]["source"] == "vscode"

    with pytest.raises(ValueError):
        local_result_to_delta(state, {"scope": "cloud_syntax", "passed": True})


def test_local_result_keeps_state_waiting_until_all_required_scopes_pass() -> None:
    state = State(
        "s1",
        "t1",
        revision=2,
        status="waiting_local_validation",
        validation_results=[{"scope": "cloud_syntax", "passed": True}],
        pending_actions=[{"type": "local_validation", "scopes": ["local_runtime", "local_e2e"]}],
        metadata={"required_validation_scopes": ["local_runtime", "local_e2e"]},
    )

    delta = local_result_to_delta(
        state,
        {"task_id": "t1", "revision": 2, "scope": "local_runtime", "passed": True},
    )

    assert delta.status == "waiting_local_validation"
    assert delta.replace_pending_actions == [{"type": "local_validation", "scopes": ["local_e2e"]}]


def test_local_result_completes_when_all_required_scopes_are_present() -> None:
    state = State(
        "s1",
        "t1",
        revision=2,
        validation_results=[
            {"scope": "cloud_syntax", "passed": True},
            {"scope": "local_runtime", "passed": True},
        ],
        metadata={"required_validation_scopes": ["local_runtime", "local_e2e"]},
    )

    delta = local_result_to_delta(
        state,
        {"task_id": "t1", "revision": 2, "scope": "local_e2e", "passed": True},
    )

    assert delta.status == "completed"
