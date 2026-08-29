"""Tests for Spec-first and topology StateGraph nodes."""

import pytest

from app.agent.nodes import dependency_graph_node, specification_node, topology_schedule_node
from app.agent.state import State


@pytest.mark.asyncio
async def test_specification_node_records_plan_and_hash() -> None:
    state = State("s1", "t1")
    delta = await specification_node(state, lambda _state: {"file_plan": [{"path": "main.py"}]})

    assert delta.planned_changes == [{"path": "main.py"}]
    assert delta.metadata["spec_artifact_summary"]["hash"]


@pytest.mark.asyncio
async def test_dependency_and_topology_nodes_record_diagnostics() -> None:
    state = State("s1", "t1")
    graph_delta = await dependency_graph_node(
        state,
        lambda _state: {
            "nodes": ["a"],
            "adjacency": {"a": []},
            "reverse_adjacency": {"a": []},
            "language_adapter_decisions": {"a": "python"},
            "diagnostics": ["cycle"],
        },
    )
    topology_delta = await topology_schedule_node(
        state,
        lambda _state: {
            "layers": [["a"]],
            "node_statuses": {"a": "skipped"},
            "skipped_reasons": {"a": "checkpoint"},
            "cycle_diagnostics": ["cycle"],
        },
    )

    assert graph_delta.metadata["graph_diagnostics"] == ["cycle"]
    assert graph_delta.metadata["graph_adjacency"] == {"a": []}
    assert graph_delta.metadata["language_adapter_decisions"] == {"a": "python"}
    assert topology_delta.metadata["generation_layers"] == [["a"]]
    assert topology_delta.metadata["skipped_reasons"] == {"a": "checkpoint"}
    assert topology_delta.metadata["cycle_diagnostics"] == ["cycle"]


@pytest.mark.asyncio
async def test_capability_nodes_preserve_input_revision_and_support_async_handlers() -> None:
    state = State("s1", "t1", revision=4)

    async def generate(_state):
        return {"file_plan": []}

    async def build(_state):
        return {"nodes": [], "adjacency": {}}

    async def schedule(_state):
        return {"layers": [], "node_statuses": {}}

    deltas = [
        await specification_node(state, generate),
        await dependency_graph_node(state, build),
        await topology_schedule_node(state, schedule),
    ]

    assert [item.expected_revision for item in deltas] == [4, 4, 4]
