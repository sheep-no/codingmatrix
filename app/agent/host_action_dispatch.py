"""Dispatch point for pending workflow actions towards an agent host.

The workflow registry runs inside the agent layer, while the Host session store
lives in the Web layer. A registration point keeps the dependency direction
pointing inward: the Web layer registers its dispatcher instead of the agent
layer importing the Web layer.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


StateActionDispatcher = Callable[[str, Any], int]

_dispatcher: Optional[StateActionDispatcher] = None


def register_state_action_dispatcher(dispatcher: StateActionDispatcher) -> None:
    """Install the dispatcher that forwards pending actions to a Host session."""
    global _dispatcher
    _dispatcher = dispatcher


def dispatch_state_actions(session_id: str, state: Any) -> None:
    """Forward pending actions to the registered dispatcher, if one is installed.

    A workflow can run without a connected local Host, so a missing dispatcher
    and an unknown session are both treated as no-ops.
    """
    if _dispatcher is None:
        return
    try:
        _dispatcher(session_id, state)
    except KeyError:
        pass
