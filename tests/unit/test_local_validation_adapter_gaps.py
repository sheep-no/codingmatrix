"""local_validation_adapter 输入校验分支补测。"""

import pytest

from app.agent.local_validation_adapter import local_result_to_delta
from app.agent.state import State


@pytest.fixture
def state():
    return State("s1", "t1", revision=2)


def test_non_dict_result_rejected(state):
    with pytest.raises(TypeError, match="dictionary"):
        local_result_to_delta(state, ["nope"])


def test_task_id_mismatch_rejected(state):
    with pytest.raises(ValueError, match="task_id"):
        local_result_to_delta(state, {"task_id": "other", "revision": 2})


def test_revision_mismatch_rejected(state):
    with pytest.raises(ValueError, match="revision"):
        local_result_to_delta(state, {"task_id": "t1", "revision": 3})


def test_schema_version_mismatch_rejected(state):
    with pytest.raises(ValueError, match="schema version"):
        local_result_to_delta(
            state, {"task_id": "t1", "revision": 2, "schema_version": 2}
        )


def test_protocol_source_mismatch_rejected(state):
    with pytest.raises(ValueError, match="source"):
        local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "validation_scope": "local_runtime",
                "source": "cloud",
            },
        )


def test_protocol_session_mismatch_rejected(state):
    with pytest.raises(ValueError, match="session_id"):
        local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "validation_scope": "local_runtime",
                "source": "local",
                "session_id": "other",
            },
        )


def test_unsupported_status_rejected(state):
    with pytest.raises(ValueError, match="status"):
        local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "scope": "local_runtime",
                "status": "weird",
            },
        )


def test_missing_passed_rejected(state):
    with pytest.raises(ValueError, match="boolean passed"):
        local_result_to_delta(
            state, {"task_id": "t1", "revision": 2, "scope": "local_runtime"}
        )


def test_non_string_event_id_rejected(state):
    with pytest.raises(ValueError, match="event_id"):
        local_result_to_delta(
            state,
            {
                "task_id": "t1",
                "revision": 2,
                "scope": "local_runtime",
                "passed": True,
                "event_id": 42,
            },
        )


def test_failed_status_maps_to_false(state):
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "scope": "local_runtime",
            "status": "failed",
        },
    )
    assert delta.validation_results[0]["passed"] is False


def test_skipped_status_maps_to_true(state):
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "scope": "local_runtime",
            "status": "skipped",
        },
    )
    assert delta.validation_results[0]["passed"] is True


def test_waiting_status_keeps_none(state):
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "scope": "local_runtime",
            "status": "waiting_for_confirmation",
        },
    )
    assert delta.validation_results[0]["passed"] is None


def test_pending_action_without_scopes_uses_scope_key(state):
    state.pending_actions = [{"type": "local_validation", "scope": "local_runtime"}]
    delta = local_result_to_delta(
        state,
        {"task_id": "t1", "revision": 2, "scope": "local_runtime", "passed": True},
    )
    assert delta.replace_pending_actions == []


def test_invalid_scope_rejected(state):
    with pytest.raises(ValueError, match="scope"):
        local_result_to_delta(
            state, {"task_id": "t1", "revision": 2, "scope": "cloud", "passed": True}
        )


def test_unsupported_status_marks_validation(state):
    delta = local_result_to_delta(
        state,
        {
            "task_id": "t1",
            "revision": 2,
            "scope": "local_runtime",
            "status": "unsupported",
            "event_id": "evt-1",
        },
    )
    validation = delta.validation_results[0]
    assert validation["unsupported"] is True
    assert validation["event_id"] == "evt-1"


def test_actions_for_other_scopes_are_kept(state):
    state.pending_actions = [{"type": "local_validation", "scopes": ["local_e2e"]}]
    delta = local_result_to_delta(
        state,
        {"task_id": "t1", "revision": 2, "scope": "local_runtime", "passed": True},
    )
    assert delta.replace_pending_actions == [
        {"type": "local_validation", "scopes": ["local_e2e"]}
    ]
