"""Versioned, scope-limited operations returned by synthesis models."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .code_synthesis_contracts import ChangePlanIR, ModelCapabilityProfile
from .contract_index import ContractIndex


class ModelOperationKind(str, Enum):
    PLAN = "plan"
    FILE_SLOT = "file_slot"
    PATCH = "patch"
    REPAIR_EXPLANATION = "repair_explanation"


class ModelResponseProtocol(str, Enum):
    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"
    RESTRICTED_JSON = "restricted_json"


class ComparableSynthesisInput(BaseModel):
    """Frozen input identity used to compare different model Profiles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    request: str = Field(min_length=1)
    plan_digest: str = Field(min_length=64, max_length=64)
    contract_digest: str = Field(min_length=64, max_length=64)
    context_hash: str = Field(min_length=64, max_length=64)
    required_paths: Tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        request: str,
        plan: ChangePlanIR,
        contracts: ContractIndex,
        context_hash: str,
    ) -> "ComparableSynthesisInput":
        return cls(
            request=request,
            plan_digest=plan.digest,
            contract_digest=contracts.digest,
            context_hash=context_hash,
            required_paths=tuple(artifact.path for artifact in plan.artifacts),
        )

    def assert_compatible(self, other: "ComparableSynthesisInput") -> None:
        if self != other:
            raise ValueError("synthesis inputs are not comparable")


def select_response_protocol(profile: ModelCapabilityProfile) -> ModelResponseProtocol:
    """Choose the strongest protocol supported by a model profile."""
    if profile.supports_json_schema:
        return ModelResponseProtocol.JSON_SCHEMA
    if profile.supports_tool_calls:
        return ModelResponseProtocol.TOOL_CALL
    return ModelResponseProtocol.RESTRICTED_JSON


class ModelOperation(BaseModel):
    """A model result that can be checked before entering a staging area."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    operation: ModelOperationKind
    target_path: Optional[str] = None
    allowed_paths: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()
    contract_refs: Tuple[str, ...] = ()
    content: Optional[str] = Field(default=None, min_length=1)
    patch: Optional[str] = Field(default=None, min_length=1)
    explanation: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "ModelOperation":
        paths = self.allowed_paths
        if any(not _safe_relative_path(path) for path in paths):
            raise ValueError("allowed_paths must contain safe relative paths")
        if self.target_path is not None and not _safe_relative_path(self.target_path):
            raise ValueError("target_path must be a safe relative path")
        if self.target_path is not None and paths and self.target_path not in paths:
            raise ValueError("target_path is outside the allowed path scope")
        if any(dependency not in paths for dependency in self.depends_on) and paths:
            raise ValueError("depends_on contains a path outside the allowed path scope")

        values = (self.content, self.patch, self.explanation)
        if self.operation is ModelOperationKind.PLAN:
            if self.target_path or any(value is not None for value in values):
                raise ValueError("plan operation cannot contain file content or a target path")
        elif self.operation is ModelOperationKind.FILE_SLOT:
            if not self.target_path or self.content is None or self.patch is not None:
                raise ValueError("file_slot requires target_path and content")
        elif self.operation is ModelOperationKind.PATCH:
            if not self.target_path or self.patch is None or self.content is not None:
                raise ValueError("patch requires target_path and patch")
        elif self.operation is ModelOperationKind.REPAIR_EXPLANATION:
            if self.content is not None or self.patch is not None or not self.explanation:
                raise ValueError("repair_explanation requires explanation only")
        return self


def _safe_relative_path(path: str) -> bool:
    return bool(path) and not path.startswith(("/", "\\")) and ".." not in path.replace("\\", "/").split("/")


__all__ = [
    "ModelOperation",
    "ModelOperationKind",
    "ModelResponseProtocol",
    "ComparableSynthesisInput",
    "select_response_protocol",
]
