"""StateGraph wrapper for dependency graph construction."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from app.agent.state import State, StateDelta

from ._utils import artifact_summary


async def dependency_graph_node(
    state: State,
    build: Callable[[State], Any],
) -> StateDelta:
    result = build(state)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise TypeError("dependency graph builder must return a dictionary")
    return StateDelta(
        expected_revision=state.revision,
        status="generated",
        metadata={
            "graph_artifact": result,
            "graph_artifact_summary": artifact_summary(result),
            "spec_first_stage": "dependency_graph",
            "graph_diagnostics": result.get("diagnostics", []),
            "graph_nodes": result.get("nodes", []),
            "graph_adjacency": result.get("adjacency", {}),
            "graph_reverse_adjacency": result.get("reverse_adjacency", {}),
            "language_adapter_decisions": result.get("language_adapter_decisions", {}),
        },
    )
