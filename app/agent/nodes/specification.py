"""StateGraph wrapper for Spec-first specification generation."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Dict

from app.agent.state import State, StateDelta

from ._utils import artifact_summary


async def specification_node(
    state: State,
    generate: Callable[[State], Any],
) -> StateDelta:
    result = generate(state)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise TypeError("specification generator must return a dictionary")
    return StateDelta(
        expected_revision=state.revision,
        status="generated",
        planned_changes=result.get("file_plan", []),
        metadata={
            "spec_artifacts": result,
            "spec_artifact_summary": artifact_summary(result),
            "spec_first_stage": "specification",
        },
    )
