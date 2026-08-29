"""Named workflow entry registry used during incremental endpoint cutover."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from app.agent.adapters import legacy_result_to_delta
from app.agent.state import State, StateGraph, StateGraphBuilder


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
    if state.pending_actions:
        try:
            from app.api.v1.agent_host import enqueue_state_actions

            enqueue_state_actions(session_id, state)
        except KeyError:
            # A workflow can run without a connected local Host.
            pass
    return state
