"""Technology-neutral contracts for constrained code synthesis."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .capabilities import Capability, CapabilitySet


class HttpContract(BaseModel):
    """HTTP wire contract; preserve existing route extensions and omitted fields."""

    model_config = ConfigDict(extra="allow", frozen=True)

    method: str = ""
    path: str = ""
    request_body_schema: dict[str, Any] | bool | None = None
    response_body_schema: dict[str, Any] | bool | None = None
    serialization_guidance: str | None = None
    source: str = "model_proposal"
    status: str = "proposed"

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "HttpContract":
        allowed_sources = {"user", "fixture", "existing", "architect", "model_proposal"}
        allowed_statuses = {"proposed", "validated", "frozen", "rejected"}
        if self.source not in allowed_sources:
            raise ValueError("unsupported contract source")
        if self.status not in allowed_statuses:
            raise ValueError("unsupported contract status")
        if self.status == "frozen" and self.source == "model_proposal":
            raise ValueError("model proposals cannot be frozen directly")
        return self

    @property
    def is_authoritative(self) -> bool:
        return self.status == "frozen"


class GenerationStrategy(str, Enum):
    SCAFFOLD = "scaffold"
    SCHEMA_CODEGEN = "schema_codegen"
    TEMPLATE = "template"
    PATCH = "patch"
    LLM = "llm"


class ProjectModel(BaseModel):
    """Facts discovered from a workspace, independent of framework syntax."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str = Field(min_length=1)
    framework: str = ""
    runtime: str = ""
    modules: Tuple[str, ...] = ()
    targets: Tuple[str, ...] = ()
    entrypoints: Tuple[str, ...] = ()
    generated_zones: Tuple[str, ...] = ()
    capabilities: CapabilitySet = Field(default_factory=CapabilitySet)


class ValidationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    required_scopes: Tuple[str, ...] = ()
    commands: Tuple[Tuple[str, ...], ...] = ()


class ModelCapabilityProfile(BaseModel):
    """Declare model transport and structured-output capabilities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    supports_structured_output: bool = False
    supports_json_schema: bool = False
    supports_tool_calls: bool = False
    supports_streaming: bool = False
    max_context_tokens: int = Field(default=8192, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    deterministic: bool = False

    @model_validator(mode="after")
    def validate_structured_output(self) -> "ModelCapabilityProfile":
        if self.supports_json_schema and not self.supports_structured_output:
            raise ValueError("JSON Schema output requires structured output support")
        if self.max_output_tokens > self.max_context_tokens:
            raise ValueError("max_output_tokens must not exceed max_context_tokens")
        return self


class ArtifactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    operation: str = Field(pattern=r"^(create|modify|delete|rename)$")
    strategy: GenerationStrategy
    depends_on: Tuple[str, ...] = ()
    validation_profile: str = Field(min_length=1)
    source: str = Field(min_length=1)
    preconditions: Tuple[str, ...] = ()


class ChangePlanIR(BaseModel):
    """Versioned, dynamic artifact DAG consumed by strategy and stack adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    project: ProjectModel
    artifacts: Tuple[ArtifactSpec, ...] = ()
    contracts: Mapping[str, Any] = Field(default_factory=dict)
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_plan(self) -> "ChangePlanIR":
        paths = [artifact.path for artifact in self.artifacts]
        path_set = set(paths)
        if len(paths) != len(path_set):
            raise ValueError("change plan artifact paths must be unique")
        missing = {
            dependency
            for artifact in self.artifacts
            for dependency in artifact.depends_on
            if dependency not in path_set
        }
        if missing:
            raise ValueError(f"change plan has missing artifact dependencies: {sorted(missing)}")
        _assert_acyclic(self.artifacts)
        expected = _plan_digest(
            self.schema_version, self.project, self.artifacts, self.contracts
        )
        if self.digest != expected:
            raise ValueError("change plan IR digest does not match its contents")
        return self

    @classmethod
    def build(
        cls,
        project: ProjectModel,
        artifacts: Tuple[ArtifactSpec, ...] | list[ArtifactSpec],
        contracts: Mapping[str, Any] | None = None,
        *,
        schema_version: int = 1,
    ) -> "ChangePlanIR":
        normalized = tuple(sorted(artifacts, key=lambda item: item.path))
        payload = dict(contracts or {})
        digest = _plan_digest(schema_version, project, normalized, payload)
        return cls(
            schema_version=schema_version,
            project=project,
            artifacts=normalized,
            contracts=payload,
            digest=digest,
        )

    def artifact(self, path: str) -> ArtifactSpec:
        for artifact in self.artifacts:
            if artifact.path == path:
                return artifact
        raise KeyError(path)


class StrategyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: GenerationStrategy
    reason: str = Field(min_length=1)
    capability_evidence: Tuple[str, ...] = ()
    degraded: bool = False


def _plan_digest(
    schema_version: int,
    project: ProjectModel,
    artifacts: Tuple[ArtifactSpec, ...],
    contracts: Mapping[str, Any],
) -> str:
    project_payload = project.model_dump(mode="json")
    capability_values = project_payload.get("capabilities", {}).get("values", ())
    project_payload["capabilities"]["values"] = sorted(capability_values)
    payload = {
        "schema_version": schema_version,
        "project": project_payload,
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
        "contracts": dict(contracts),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _assert_acyclic(artifacts: Tuple[ArtifactSpec, ...]) -> None:
    dependencies = {item.path: set(item.depends_on) for item in artifacts}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path in visiting:
            raise ValueError(f"change plan contains a dependency cycle at: {path}")
        if path in visited:
            return
        visiting.add(path)
        for dependency in dependencies[path]:
            visit(dependency)
        visiting.remove(path)
        visited.add(path)

    for path in dependencies:
        visit(path)


__all__ = [
    "HttpContract",
    "ArtifactSpec",
    "ChangePlanIR",
    "GenerationStrategy",
    "ModelCapabilityProfile",
    "ProjectModel",
    "StrategyDecision",
    "ValidationProfile",
]
