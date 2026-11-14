"""host_action_dispatch 注册点分支补测。"""

import pytest

import app.agent.host_action_dispatch as dispatch_module
from app.agent.host_action_dispatch import (
    dispatch_state_actions,
    register_state_action_dispatcher,
)


@pytest.fixture(autouse=True)
def reset_dispatcher(monkeypatch):
    monkeypatch.setattr(dispatch_module, "_dispatcher", None)
    return dispatch_module


def test_dispatch_without_dispatcher_is_noop():
    dispatch_state_actions("session-1", object())


def test_dispatch_forwards_session_and_state():
    received = []
    register_state_action_dispatcher(lambda session_id, state: received.append((session_id, state)))
    state = object()

    dispatch_state_actions("session-1", state)

    assert received == [("session-1", state)]


@pytest.mark.parametrize("error", [KeyError("session"), ValueError("mismatch")])
def test_dispatch_swallows_session_errors(error):
    def broken(session_id, state):
        raise error

    register_state_action_dispatcher(broken)
    dispatch_state_actions("session-1", object())


def test_dispatch_propagates_unexpected_errors():
    def broken(session_id, state):
        raise RuntimeError("bug")

    register_state_action_dispatcher(broken)
    with pytest.raises(RuntimeError, match="bug"):
        dispatch_state_actions("session-1", object())
