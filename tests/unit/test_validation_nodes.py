"""Tests for cloud and local validation state boundaries."""

import pytest

from app.agent.nodes import cloud_validation_node, local_validation_action
from app.agent.nodes.validation import derive_validation_status
from app.agent.state import State


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
