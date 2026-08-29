"""StateGraph wrapper for dynamic topology scheduling."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from app.agent.state import State, StateDelta

from ._utils import artifact_summary


async def topology_schedule_node(
    state: State,
    schedule: Callable[[State], Any],
) -> StateDelta:
    result = schedule(state)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise TypeError("topology scheduler must return a dictionary")
    return StateDelta(
        expected_revision=state.revision,
        status="generated",
        metadata={
            "topology_artifact": result,
            "topology_artifact_summary": artifact_summary(result),
            "generation_layers": result.get("layers", []),
            "node_statuses": result.get("node_statuses", {}),
            "skipped_reasons": result.get("skipped_reasons", {}),
            "cycle_diagnostics": result.get("cycle_diagnostics", []),
            "spec_first_stage": "topology_schedule",
        },
    )
