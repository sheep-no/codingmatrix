"""Tests for cloud and local validation state boundaries."""

import pytest

from app.agent.nodes import cloud_validation_node, local_validation_action
from app.agent.local_validation_adapter import local_result_to_delta
from app.agent.nodes.validation import derive_validation_status
from app.agent.state import State, StateReducer


@pytest.mark.asyncio
async def test_cloud_validation_sets_cloud_scope() -> None:
    delta = await cloud_validation_node(State("s1", "t1"), lambda _state: {"passed": True})

    assert delta.status == "syntax_validated"
    assert delta.validation_results[0]["source"] == "cloud"
    assert delta.validation_results[0]["scope"] == "cloud_syntax"


@pytest.mark.asyncio
async def test_cloud_validation_waits_for_required_local_scopes() -> None:
    state = State("s1", "t1", metadata={"required_validation_scopes": ["local_runtime"]})

    delta = await cloud_validation_node(state, lambda _state: {"passed": True})

    assert delta.status == "waiting_local_validation"
    assert delta.pending_actions[0]["scopes"] == ["local_runtime"]


@pytest.mark.asyncio
async def test_cloud_validation_preserves_unsupported_diagnostic() -> None:
    state = State("s1", "t1", metadata={"required_validation_scopes": ["local_runtime"]})

    delta = await cloud_validation_node(
        state,
        lambda _state: {
            "passed": None,
            "status": "unsupported",
            "reason": "language adapter unavailable",
        },
    )

    assert delta.status == "unsupported"
    assert delta.pending_actions == []
    assert delta.validation_results[0]["scope"] == "cloud_syntax"
    assert delta.validation_results[0]["reason"] == "language adapter unavailable"


@pytest.mark.asyncio
async def test_cloud_to_local_validation_round_trip_completes_task() -> None:
    state = State("s1", "t1", metadata={"required_validation_scopes": ["local_runtime"]})
    cloud_delta = await cloud_validation_node(state, lambda _state: {"passed": True})
    state = StateReducer().apply(state, cloud_delta)

    local_delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": state.revision,
            "scope": "local_runtime",
            "status": "passed",
            "exit_code": 0,
        },
    )
    state = StateReducer().apply(state, local_delta)

    assert state.status == "completed"
    assert [result["scope"] for result in state.validation_results] == [
        "cloud_syntax",
        "local_runtime",
    ]
    assert state.pending_actions == []


def test_local_validation_action_creates_pending_action() -> None:
    delta = local_validation_action(
        State("s1", "t1", revision=4),
        {"type": "run_tests", "scope": "local_runtime"},
    )

    assert delta.status == "waiting_local_validation"
    assert delta.pending_actions[0]["source_revision"] == 4


def test_local_validation_action_rejects_unknown_scope() -> None:
    with pytest.raises(ValueError):
        local_validation_action(State("s1", "t1"), {"type": "run_tests", "scope": "cloud_syntax"})


def test_validation_status_waits_for_every_required_scope() -> None:
    status = derive_validation_status(
        [
            {"scope": "local_runtime", "passed": True},
        ],
        {"local_runtime", "local_e2e"},
    )

    assert status == "waiting_local_validation"


def test_validation_status_completes_when_every_required_scope_passes() -> None:
    status = derive_validation_status(
        [
            {"scope": "local_runtime", "passed": True},
            {"scope": "local_e2e", "passed": True},
        ],
        {"local_runtime", "local_e2e"},
    )

    assert status == "completed"


def test_validation_status_fails_when_a_validation_fails() -> None:
    status = derive_validation_status(
        [
            {"scope": "local_runtime", "passed": True},
            {"scope": "local_e2e", "passed": False},
        ],
        {"local_runtime", "local_e2e"},
    )

    assert status == "failed"


def test_validation_status_reports_unsupported_capability() -> None:
    status = derive_validation_status(
        [{"scope": "cloud_syntax", "status": "unsupported", "passed": None}],
        {"local_runtime"},
    )

    assert status == "unsupported"
