"""Named workflow entry registry used during incremental endpoint cutover."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from app.agent.adapters import legacy_result_to_delta
from app.agent.state import CheckpointStore, State, StateGraph, StateGraphBuilder, StateReducer
from app.agent.state.graph import END, NEXT_NODE_METADATA_KEY


_active_workflows: Dict[tuple[str, str], tuple[WorkflowDefinition, State]] = {}
_checkpoint_store = CheckpointStore(
    Path(os.getenv("AGENT_STATE_CHECKPOINT_DIR", "data/agent_state_checkpoints"))
)
_recoverable_workflow_factories: Dict[str, Callable[[], WorkflowDefinition]] = {}


def _checkpoint_id(session_id: str, task_id: str) -> str:
    return f"{session_id}--{task_id}"


def register_recoverable_workflow_factory(
    name: str, factory: Callable[[], WorkflowDefinition]
) -> None:
    """Register a factory used to rebuild a workflow after process restart."""
    if not name or not callable(factory):
        raise ValueError("workflow factory requires a name and callable")
    _recoverable_workflow_factories[name] = factory


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


def get_legacy_result(state: State) -> Dict[str, Any]:
    """Return a wrapped endpoint result or raise the graph's original error."""
    result = state.metadata.get("legacy_result")
    if isinstance(result, dict):
        return result

    error_messages = [
        str(error.get("message") or error)
        for error in state.errors
        if error
    ]
    if error_messages:
        raise RuntimeError("; ".join(error_messages))

    workflow_name = state.metadata.get("_workflow_name", "unknown")
    raise RuntimeError(f"workflow {workflow_name} completed without a result")


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
    db: Any = None,
    user_id: Optional[int] = None,
) -> State:
    """Execute a workflow and persist the result when database context is provided."""

    state = State(
        session_id=session_id,
        task_id=task_id,
        metadata={**dict(metadata or {}), "_workflow_name": definition.name},
    )
    state = await definition.graph.run(state, start_at=definition.entry_node)
    _active_workflows[(session_id, task_id)] = (definition, state)
    _checkpoint_store.save(state, _checkpoint_id(session_id, task_id))
    if db is not None and user_id is not None:
        from app.services.agent_state_adapter import persist_agent_state

        await persist_agent_state(db, user_id, state)
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
    definition = None
    if execution is not None:
        definition, state = execution
    else:
        state = _checkpoint_store.load(_checkpoint_id(session_id, task_id))
        if state is None:
            raise KeyError(f"active workflow not found: {session_id}/{task_id}")
        workflow_name = state.metadata.get("_workflow_name")
        factory = _recoverable_workflow_factories.get(workflow_name)
        if factory is not None:
            definition = factory()
    from app.agent.local_validation_adapter import local_result_to_delta

    reducer = definition.graph.reducer if definition is not None else StateReducer()
    state = reducer.apply(state, local_result_to_delta(state, result))
    next_node = state.metadata.pop(NEXT_NODE_METADATA_KEY, None)
    if definition is not None and not state.pending_actions and next_node and next_node != END:
        state = await definition.graph.run(state, start_at=next_node)
    if definition is not None:
        _active_workflows[(session_id, task_id)] = (definition, state)
    _checkpoint_store.save(state, _checkpoint_id(session_id, task_id))
    if state.pending_actions:
        try:
            from app.api.v1.agent_host import enqueue_state_actions

            enqueue_state_actions(session_id, state)
        except KeyError:
            pass
    return state
