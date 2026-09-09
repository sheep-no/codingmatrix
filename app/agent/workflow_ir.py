"""Serializable workflow intermediate representation for Helix orchestration."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

class WorkflowNodeKind(str, Enum):
    PLAN = "plan"
    GENERATE = "generate"
    VALIDATE = "validate"
    REPAIR = "repair"
    TOOL = "tool"
    REVIEW = "review"


class ScopeRef(BaseModel):
    """A scope that limits context, memory, or tool access."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["user", "workspace", "project", "session", "task", "node", "file"]
    ref: str = Field(min_length=1)


class ContextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: Tuple[str, ...] = ()
    scopes: Tuple[ScopeRef, ...] = ()
    max_chars: int = Field(default=120_000, gt=0)
    inherit_parent: bool = True


class ToolGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    operations: Tuple[Literal["read", "write", "execute"], ...] = ()
    scopes: Tuple[ScopeRef, ...] = ()
    timeout_seconds: float = Field(default=30, gt=0)
    require_approval: bool = False

    @model_validator(mode="after")
    def validate_scope_for_execution(self) -> "ToolGrant":
        if "execute" in self.operations and not self.scopes:
            raise ValueError("execute tool grants require at least one scope")
        return self


class ModelPolicy(BaseModel):
    """Provider-neutral model routing declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capabilities: Tuple[str, ...] = ()
    preferred_models: Tuple[str, ...] = ()
    allow_fallback: bool = True
    max_attempts: int = Field(default=1, ge=1, le=10)


class TechnologyProfile(BaseModel):
    """Artifact-level technology facts used to select adapters and validators."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str = ""
    framework: str = ""
    runtime: str = ""


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    kind: WorkflowNodeKind
    handler_ref: str = Field(min_length=1)
    depends_on: Tuple[str, ...] = ()
    agent_role: Optional[str] = None
    input_refs: Tuple[str, ...] = ()
    output_refs: Tuple[str, ...] = ()
    provided_symbols: Tuple[str, ...] = ()
    required_symbols: Tuple[str, ...] = ()
    required_fixtures: Tuple[str, ...] = ()
    technology: TechnologyProfile = Field(default_factory=TechnologyProfile)
    context_policy: ContextPolicy = Field(default_factory=ContextPolicy)
    tool_grants: Tuple[ToolGrant, ...] = ()
    model_policy: ModelPolicy = Field(default_factory=ModelPolicy)
    budget_scope: Literal["task", "stage", "file", "model_call"] = "stage"
    max_attempts: int = Field(default=1, ge=1, le=10)


class WorkflowIR(BaseModel):
    """Versioned, deterministic and callable-free workflow definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    workflow_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    language: str = ""
    framework: str = ""
    runtime: str = ""
    languages: Tuple[str, ...] = ()
    frameworks: Tuple[str, ...] = ()
    runtimes: Tuple[str, ...] = ()
    entry_node: str = Field(min_length=1)
    nodes: Tuple[WorkflowNode, ...] = ()
    generation_plan: Optional[Any] = None
    contract_index: Optional[Any] = None
    budgets: Any
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_workflow(self) -> "WorkflowIR":
        node_map = {node.node_id: node for node in self.nodes}
        if len(node_map) != len(self.nodes):
            raise ValueError("workflow node IDs must be unique")
        if self.entry_node not in node_map:
            raise ValueError("workflow entry_node must reference an existing node")

        for node in self.nodes:
            missing = set(node.depends_on) - node_map.keys()
            if missing:
                raise ValueError(f"node {node.node_id} has missing dependencies: {sorted(missing)}")
            if node.node_id in node.depends_on:
                raise ValueError(f"node {node.node_id} cannot depend on itself")

        _validate_acyclic(node_map)
        children = {node_id: set() for node_id in node_map}
        for node in self.nodes:
            for dependency in node.depends_on:
                children[dependency].add(node.node_id)
        reachable = {self.entry_node}
        pending = [self.entry_node]
        while pending:
            current = pending.pop()
            for child in children[current]:
                if child not in reachable:
                    reachable.add(child)
                    pending.append(child)
        if reachable != set(node_map):
            raise ValueError("all workflow nodes must be reachable from entry_node")

        for node in self.nodes:
            for field, declared in (
                ("language", self.languages),
                ("framework", self.frameworks),
                ("runtime", self.runtimes),
            ):
                value = getattr(node.technology, field)
                if value and declared and value not in declared:
                    raise ValueError(
                        f"node {node.node_id} {field} is outside the workflow technology set"
                    )

        if self.digest != _workflow_digest(self):
            raise ValueError("workflow digest does not match its contents")
        return self

    @classmethod
    def build(cls, **values: Any) -> "WorkflowIR":
        """Normalize input models and calculate the immutable workflow digest."""
        values.pop("digest", None)
        candidate = cls.model_construct(digest="0" * 64, **values)
        return cls.model_validate({**candidate.model_dump(mode="json"), "digest": _workflow_digest(candidate)})


def _validate_acyclic(nodes: Mapping[str, WorkflowNode]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("workflow dependencies must form a DAG")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in nodes[node_id].depends_on:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in nodes:
        visit(node_id)


def _workflow_digest(workflow: WorkflowIR) -> str:
    payload = workflow.model_dump(mode="json", exclude={"digest"})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ContextPolicy",
    "ModelPolicy",
    "ScopeRef",
    "ToolGrant",
    "TechnologyProfile",
    "WorkflowIR",
    "WorkflowNode",
    "WorkflowNodeKind",
]
