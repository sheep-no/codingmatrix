"""cloud/local validation 节点的剩余分支补测。"""

import pytest

from app.agent.nodes.validation import (
    _required_scopes,
    cloud_validation_node,
    local_validation_action,
)
from app.agent.state import State


def test_required_scopes_accepts_single_string_and_filters_unknown():
    state = State("s1", "t1", metadata={"required_validation_scopes": "local_runtime"})
    assert _required_scopes(state) == {"local_runtime"}

    state = State("s1", "t1", metadata={"required_validation_scopes": ["cloud_syntax"]})
    assert _required_scopes(state) == set()


@pytest.mark.asyncio
async def test_cloud_validation_awaits_async_validator():
    async def validate(_state):
        return {"passed": True, "detail": "async"}

    delta = await cloud_validation_node(State("s1", "t1"), validate)

    assert delta.validation_results[0]["detail"] == "async"
    assert delta.status == "syntax_validated"


@pytest.mark.asyncio
async def test_cloud_validation_rejects_non_dictionary_result():
    with pytest.raises(TypeError, match="must return a dictionary"):
        await cloud_validation_node(State("s1", "t1"), lambda _state: ["not", "a", "dict"])


@pytest.mark.parametrize("action", [None, [], {}, {"scope": "local_runtime"}])
def test_local_validation_action_rejects_missing_type(action):
    with pytest.raises(ValueError, match="requires a type"):
        local_validation_action(State("s1", "t1"), action)


def test_local_validation_action_accepts_string_scope():
    delta = local_validation_action(
        State("s1", "t1", revision=3),
        {"type": "run_tests", "scopes": "local_e2e"},
    )

    assert delta.pending_actions[0]["scopes"] == ["local_e2e"]
    assert delta.pending_actions[0]["source_revision"] == 3


def test_local_validation_action_rejects_empty_scopes():
    with pytest.raises(ValueError, match="supported scopes"):
        local_validation_action(State("s1", "t1"), {"type": "run_tests", "scopes": []})
