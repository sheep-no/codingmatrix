"""Tests for the minimal StateGraph runtime."""

import pytest

from app.agent.state import GraphExecutionError, State, StateConflictError, StateDelta, StateGraphBuilder


def delta(state, status):
    return StateDelta(expected_revision=state.revision, status=status)


@pytest.mark.asyncio
async def test_graph_runs_nodes_in_order_and_merges_state() -> None:
    visited = []

    async def first(state):
        visited.append("first")
        return delta(state, "generated")

    def second(state):
        visited.append("second")
        return delta(state, "completed")

    graph = StateGraphBuilder().add_node("first", first).add_node("second", second).add_edge("first", "second").compile()
    result = await graph.run(State("s1", "t1"), "first")

    assert visited == ["first", "second"]
    assert result.status == "completed"
    assert result.revision == 2


@pytest.mark.asyncio
async def test_graph_uses_conditional_route() -> None:
    async def start(state):
        return delta(state, "generated")

    def choose(state):
        return "done" if state.status == "generated" else "retry"

    graph = (StateGraphBuilder()
             .add_node("start", start)
             .add_node("done", lambda state: delta(state, "completed"))
             .add_node("retry", lambda state: delta(state, "failed"))
             .add_conditional_edges("start", choose, {"done": "done", "retry": "retry"})
             .compile())

    result = await graph.run(State("s1", "t1"), "start")

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_graph_routes_node_failure_to_error_edge() -> None:
    def broken(_state):
        raise RuntimeError("boom")

    def recover(state):
        return delta(state, "completed")

    graph = (StateGraphBuilder()
             .add_node("broken", broken)
             .add_node("recover", recover)
             .add_error_edge("broken", "recover")
             .compile())
    result = await graph.run(State("s1", "t1"), "broken")

    assert result.status == "completed"
    assert result.errors[0]["code"] == "graph.node_failed"


@pytest.mark.asyncio
async def test_graph_gives_nodes_snapshots_and_merges_only_deltas() -> None:
    observed = []

    def node(state):
        state.metadata["mutated_snapshot"] = True
        observed.append(state.metadata.copy())
        return StateDelta(expected_revision=state.revision, metadata={"node": "ran"})

    result = await StateGraphBuilder().add_node("node", node).compile().run(
        State("s1", "t1"), "node"
    )

    assert observed == [{"mutated_snapshot": True}]
    assert result.metadata == {"node": "ran"}
    assert result.revision == 1


def test_graph_reducer_rejects_stale_updates() -> None:
    reducer = StateGraphBuilder().compile().reducer
    state = State("s1", "t1")

    state = reducer.apply(state, StateDelta(expected_revision=0, status="generated"))

    with pytest.raises(StateConflictError):
        reducer.apply(state, StateDelta(expected_revision=0, status="failed"))


@pytest.mark.asyncio
async def test_graph_stops_when_max_steps_is_exceeded() -> None:
    graph = (
        StateGraphBuilder(max_steps=1)
        .add_node("loop", lambda state: delta(state, "generated"))
        .add_edge("loop", "loop")
        .compile()
    )

    with pytest.raises(GraphExecutionError, match="graph exceeded max_steps"):
        await graph.run(State("s1", "t1"), "loop")
