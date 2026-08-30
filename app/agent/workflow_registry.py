"""Named workflow entry registry used during incremental endpoint cutover."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from app.agent.adapters import legacy_result_to_delta
from app.agent.state import State, StateGraph, StateGraphBuilder


_active_workflows: Dict[tuple[str, str], tuple[WorkflowDefinition, State]] = {}


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    entry_node: str
    graph: StateGraph
    legacy_endpoint: str


class WorkflowRegistry:
    def __init__(self, definitions: Iterable[WorkflowDefinition] = ()) -> None:
        self._definitions: Dict[str, WorkflowDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: WorkflowDefinition) -> None:
        if not definition.name or definition.name in self._definitions:
            raise ValueError(f"invalid or duplicate workflow: {definition.name!r}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> Optional[WorkflowDefinition]:
        return self._definitions.get(name)

    def names(self) -> list[str]:
        return sorted(self._definitions)


LegacyHandler = Callable[[State], Any | Awaitable[Any]]


def build_legacy_workflow(
    name: str,
    legacy_endpoint: str,
    handler: LegacyHandler,
    *,
    node_name: str = "legacy_agent",
) -> WorkflowDefinition:
    """Wrap one legacy endpoint in a graph while preserving its result payload."""

    async def run_legacy(state: State):
        result = handler(state)
        if hasattr(result, "__await__"):
            result = await result
        delta = legacy_result_to_delta(
            result,
            session_id=state.session_id,
            task_id=state.task_id,
            revision=state.revision,
            node=node_name,
        )
        delta.metadata["legacy_result"] = result if isinstance(result, dict) else {"result": result}
        return delta

    graph = StateGraphBuilder().add_node(node_name, run_legacy).compile()
    return WorkflowDefinition(name, node_name, graph, legacy_endpoint)


async def run_workflow(
    definition: WorkflowDefinition,
    *,
    session_id: str,
    task_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> State:
    """Execute a registered workflow from a serializable initial State."""

    state = State(
        session_id=session_id,
        task_id=task_id,
        metadata=dict(metadata or {}),
    )
    state = await definition.graph.run(state, start_at=definition.entry_node)
    _active_workflows[(session_id, task_id)] = (definition, state)
    if state.pending_actions:
        try:
            from app.api.v1.agent_host import enqueue_state_actions

            enqueue_state_actions(session_id, state)
        except KeyError:
            # A workflow can run without a connected local Host.
            pass
    return state


async def resume_workflow_from_local_result(
    *,
    session_id: str,
    task_id: str,
    result: Dict[str, Any],
) -> State:
    """Merge a local Host result and continue the active workflow state."""
    execution = _active_workflows.get((session_id, task_id))
    if execution is None:
        raise KeyError(f"active workflow not found: {session_id}/{task_id}")

    definition, state = execution
    from app.agent.local_validation_adapter import local_result_to_delta

    state = definition.graph.reducer.apply(state, local_result_to_delta(state, result))
    _active_workflows[(session_id, task_id)] = (definition, state)
    if state.pending_actions:
        try:
            from app.api.v1.agent_host import enqueue_state_actions

            enqueue_state_actions(session_id, state)
        except KeyError:
            pass
    return state
