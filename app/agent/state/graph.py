"""Small async StateGraph runtime for incremental Agent migration."""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Union

from .models import State, StateDelta
from .reducer import StateReducer

END = "__end__"
NodeHandler = Callable[[State], Union[StateDelta, Awaitable[StateDelta]]]
RouteHandler = Callable[[State], Union[str, Awaitable[str]]]


class GraphDefinitionError(ValueError):
    """Raised when a graph references an unknown or invalid node."""


class GraphExecutionError(RuntimeError):
    """Raised when graph execution cannot continue safely."""


@dataclass(frozen=True)
class _ConditionalRoute:
    selector: RouteHandler
    mapping: Mapping[str, str]


class StateGraph:
    def __init__(
        self,
        nodes: Mapping[str, NodeHandler],
        edges: Mapping[str, str],
        conditional_edges: Mapping[str, _ConditionalRoute],
        error_edges: Mapping[str, str],
        reducer: Optional[StateReducer] = None,
        max_steps: int = 100,
    ) -> None:
        self.nodes = dict(nodes)
        self.edges = dict(edges)
        self.conditional_edges = dict(conditional_edges)
        self.error_edges = dict(error_edges)
        self.reducer = reducer or StateReducer()
        self.max_steps = max_steps

    async def run(self, state: State, start_at: str) -> State:
        if start_at not in self.nodes:
            raise GraphDefinitionError(f"unknown start node: {start_at}")
        current = start_at
        steps = 0
        while current != END:
            if steps >= self.max_steps:
                raise GraphExecutionError("graph exceeded max_steps")
            handler = self.nodes[current]
            snapshot = copy.deepcopy(state)
            try:
                delta = handler(snapshot)
                if inspect.isawaitable(delta):
                    delta = await delta
                if not isinstance(delta, StateDelta):
                    raise TypeError(f"node {current} must return StateDelta")
                state = self.reducer.apply(state, delta)
            except Exception as exc:
                error_delta = StateDelta(
                    expected_revision=state.revision,
                    status="failed",
                    errors=[{
                        "code": "graph.node_failed",
                        "message": str(exc),
                        "retryable": True,
                        "details": {"node": current},
                    }],
                    metadata={"failed_node": current},
                )
                state = self.reducer.apply(state, error_delta)
                if current in self.error_edges:
                    current = self.error_edges[current]
                    steps += 1
                    continue
                return state

            current = await self._next_node(current, state)
            steps += 1
        return state

    async def _next_node(self, current: str, state: State) -> str:
        if current in self.conditional_edges:
            route = self.conditional_edges[current]
            selected = route.selector(state)
            if inspect.isawaitable(selected):
                selected = await selected
            try:
                return route.mapping[selected]
            except KeyError as exc:
                raise GraphExecutionError(
                    f"route {selected!r} is not configured for node {current}"
                ) from exc
        return self.edges.get(current, END)


class StateGraphBuilder:
    def __init__(self, max_steps: int = 100) -> None:
        self._nodes: Dict[str, NodeHandler] = {}
        self._edges: Dict[str, str] = {}
        self._conditional_edges: Dict[str, _ConditionalRoute] = {}
        self._error_edges: Dict[str, str] = {}
        self._max_steps = max_steps

    def add_node(self, name: str, handler: NodeHandler) -> "StateGraphBuilder":
        if not name or name == END or name in self._nodes:
            raise GraphDefinitionError(f"invalid or duplicate node: {name!r}")
        self._nodes[name] = handler
        return self

    def add_edge(self, source: str, target: str) -> "StateGraphBuilder":
        self._edges[source] = target
        return self

    def add_conditional_edges(
        self, source: str, selector: RouteHandler, mapping: Mapping[str, str]
    ) -> "StateGraphBuilder":
        self._conditional_edges[source] = _ConditionalRoute(selector, dict(mapping))
        return self

    def add_error_edge(self, source: str, target: str) -> "StateGraphBuilder":
        self._error_edges[source] = target
        return self

    def compile(self, reducer: Optional[StateReducer] = None) -> StateGraph:
        references = [*self._edges.values(), *self._error_edges.values()]
        references.extend(target for route in self._conditional_edges.values() for target in route.mapping.values())
        unknown = {name for name in references if name != END and name not in self._nodes}
        if unknown:
            raise GraphDefinitionError(f"unknown target nodes: {sorted(unknown)}")
        return StateGraph(
            self._nodes,
            self._edges,
            self._conditional_edges,
            self._error_edges,
            reducer,
            self._max_steps,
        )
