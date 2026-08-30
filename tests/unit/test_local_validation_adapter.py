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


def test_protocol_result_maps_fields_and_status_to_internal_contract() -> None:
    state = State("s1", "t1", revision=2)
    delta = local_result_to_delta(
        state,
        {
            "event_id": "event-1",
            "session_id": "s1",
            "task_id": "t1",
            "revision": 2,
            "schema_version": 1,
            "source": "local",
            "validation_scope": "local_runtime",
            "status": "passed",
        },
    )

    assert delta.validation_results == [{
        "event_id": "event-1",
        "session_id": "s1",
        "task_id": "t1",
        "revision": 2,
        "schema_version": 1,
        "source": "vscode",
        "validation_scope": "local_runtime",
        "status": "passed",
        "scope": "local_runtime",
        "passed": True,
    }]


def test_protocol_result_rejects_wrong_source_or_session() -> None:
    state = State("s1", "t1", revision=2)
    base = {
        "task_id": "t1",
        "revision": 2,
        "source": "local",
        "session_id": "s1",
        "validation_scope": "local_runtime",
        "status": "passed",
    }

    with pytest.raises(ValueError, match="source"):
        local_result_to_delta(state, {**base, "source": "cloud"})
    with pytest.raises(ValueError, match="session_id"):
        local_result_to_delta(state, {**base, "session_id": "other"})


def test_protocol_result_accepts_terminal_failure_statuses() -> None:
    state = State("s1", "t1", revision=2)

    for status in ("timeout", "rejected", "cancelled"):
        delta = local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "source": "local",
                "session_id": "s1",
                "validation_scope": "local_runtime",
                "status": status,
            },
        )
        assert delta.validation_results[0]["passed"] is False


def test_protocol_result_treats_skipped_stage_as_completed() -> None:
    state = State(
        "s1",
        "t1",
        revision=2,
        metadata={"required_validation_scopes": ["local_runtime"]},
    )
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "source": "local",
            "session_id": "s1",
            "validation_scope": "local_runtime",
            "status": "skipped",
        },
    )

    assert delta.validation_results[0]["passed"] is True
    assert delta.status == "completed"


def test_protocol_result_waiting_for_confirmation_keeps_validation_pending() -> None:
    state = State(
        "s1",
        "t1",
        revision=2,
        metadata={"required_validation_scopes": ["local_runtime"]},
    )
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "source": "local",
            "session_id": "s1",
            "validation_scope": "local_runtime",
            "status": "waiting_for_confirmation",
        },
    )

    assert delta.validation_results[0]["passed"] is None
    assert delta.status == "waiting_local_validation"


def test_protocol_result_rejects_unknown_status() -> None:
    state = State("s1", "t1", revision=2)

    with pytest.raises(ValueError, match="status"):
        local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "source": "local",
                "session_id": "s1",
                "validation_scope": "local_runtime",
                "status": "unknown",
            },
        )
