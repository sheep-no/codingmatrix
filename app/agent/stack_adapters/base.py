"""Shared contracts and behavior for technology-specific stack adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.adapters import SymbolDefinition
from app.agent.capabilities import CapabilitySet
from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ProjectModel,
    ValidationProfile,
)
from app.agent.framework_profiles import FrameworkProfile
from app.agent.languages import get_language_adapter
from app.agent.orchestration.profile_bridge import validation_profile_from_framework
from app.agent.scaffolding import (
    ScaffoldRequest,
    execute_official_scaffold,
    supports_official_scaffold,
)
from app.agent.synthesis_capabilities import (
    SynthesisCapabilityRegistry,
    SynthesisCapabilitySnapshot,
)

if TYPE_CHECKING:
    from app.agent.generation_plan import GenerationPlan as ScaffoldGenerationPlan


class UnsupportedStackError(LookupError):
    """Raised when an adapter cannot represent the discovered stack."""


class StackArtifactRequest(BaseModel):
    """Strict artifact input accepted by every stack adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    operation: str = Field(default="create", pattern=r"^(create|modify|delete|rename)$")
    strategy: GenerationStrategy = GenerationStrategy.LLM
    depends_on: tuple[str, ...] = ()
    owner: str = ""
    source: str = "request"
    preconditions: tuple[str, ...] = ()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _normalize_artifact_path(value)

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize_artifact_path(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("artifact dependencies must be unique")
        return normalized


class StackChangeRequest(BaseModel):
    """Technology-neutral request projected into a stack-owned change plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifacts: tuple[StackArtifactRequest, ...] = Field(min_length=1)
    contracts: Mapping[str, Any] = Field(default_factory=dict)


class SymbolRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    line_number: int = Field(default=0, ge=0)
    signature: str | None = None
    exported: bool = True


class SymbolIndex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    language: str = Field(min_length=1)
    symbols: tuple[SymbolRecord, ...] = ()


@dataclass(frozen=True)
class ScaffoldResult:
    supported: bool
    reason: str
    request: ScaffoldRequest | None = None
    plan: ScaffoldGenerationPlan | None = None


class StackAdapter(Protocol):
    stack_id: str
    aliases: tuple[tuple[str, str], ...]

    def detect(self, workspace: Path) -> ProjectModel: ...

    def capabilities(self) -> CapabilitySet: ...

    def synthesis_capabilities(self) -> SynthesisCapabilitySnapshot: ...

    async def scaffold(self, project: ProjectModel, staging_dir: Path) -> ScaffoldResult: ...

    def build_change_plan(
        self, project: ProjectModel, request: Mapping[str, Any]
    ) -> ChangePlanIR: ...

    def extract_symbols(self, path: Path, content: str) -> SymbolIndex: ...

    def validation_profile(self, project: ProjectModel) -> ValidationProfile: ...


class BaseStackAdapter:
    """Delegate common syntax and lifecycle contracts to existing registries."""

    stack_id = "generic"
    language = "generic"
    framework = "generic"
    aliases: tuple[tuple[str, str], ...] = ()

    def detect(self, workspace: Path) -> ProjectModel:
        raise NotImplementedError

    def framework_profile(self, project: ProjectModel | None = None) -> FrameworkProfile:
        raise NotImplementedError

    def capabilities(self) -> CapabilitySet:
        return self.framework_profile().capabilities

    def synthesis_capabilities(self) -> SynthesisCapabilitySnapshot:
        profile = self.framework_profile()
        project = ProjectModel(
            language=profile.language,
            framework=profile.name,
            runtime=profile.version,
            capabilities=profile.capabilities,
        )
        return SynthesisCapabilityRegistry().inspect(project)

    async def scaffold(self, project: ProjectModel, staging_dir: Path) -> ScaffoldResult:
        profile = self.framework_profile(project)
        if not supports_official_scaffold(profile.language, profile.name):
            return ScaffoldResult(
                supported=False,
                reason=f"official scaffold is unavailable for {profile.language}/{profile.name}",
            )
        workspace = staging_dir.parent.resolve()
        if not workspace.is_dir():
            raise ValueError("scaffold staging parent must be an existing directory")
        request = SynthesisCapabilityRegistry().scaffold_request(
            project, staging_dir.name
        )
        plan = await execute_official_scaffold(workspace, request)
        return ScaffoldResult(
            supported=True,
            reason="fixed-version official scaffold completed",
            request=request,
            plan=plan,
        )

    def build_change_plan(
        self, project: ProjectModel, request: Mapping[str, Any]
    ) -> ChangePlanIR:
        self.framework_profile(project)
        parsed = StackChangeRequest.model_validate(request)
        validation_name = self.validation_profile(project).name
        artifacts = tuple(
            ArtifactSpec(
                path=item.path,
                role=item.role,
                owner=item.owner or f"stack-adapter:{self.stack_id}",
                operation=item.operation,
                strategy=item.strategy,
                depends_on=item.depends_on,
                validation_profile=validation_name,
                source=item.source,
                preconditions=item.preconditions,
            )
            for item in parsed.artifacts
        )
        return ChangePlanIR.build(project, artifacts, parsed.contracts)

    def extract_symbols(self, path: Path, content: str) -> SymbolIndex:
        adapter = get_language_adapter(self.language)
        definitions: Mapping[str, SymbolDefinition] = adapter.extract_definitions(content)
        symbols = tuple(
            SymbolRecord(
                name=symbol.name,
                kind=symbol.symbol_type,
                line_number=symbol.line_number,
                signature=symbol.signature,
                exported=symbol.is_exported,
            )
            for symbol in sorted(definitions.values(), key=lambda item: (item.line_number, item.name))
        )
        return SymbolIndex(
            path=path.as_posix(),
            language=self.language,
            symbols=symbols,
        )

    def validation_profile(self, project: ProjectModel) -> ValidationProfile:
        return validation_profile_from_framework(self.framework_profile(project))


def _normalize_artifact_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if not candidate or path.is_absolute() or candidate != path.as_posix():
        raise ValueError("artifact path must be a normalized relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path contains unsafe components")
    return candidate


__all__ = [
    "BaseStackAdapter",
    "ScaffoldResult",
    "StackAdapter",
    "StackArtifactRequest",
    "StackChangeRequest",
    "SymbolIndex",
    "SymbolRecord",
    "UnsupportedStackError",
]
