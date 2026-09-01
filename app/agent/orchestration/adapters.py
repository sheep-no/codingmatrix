"""Adapters that expose existing generation modes to the orchestration core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol

from .generation_scheduler import FileGenerationContext, GeneratedContent
from .models import OrchestrationState
from .plan import GenerationPlan, build_file_plan
from app.agent.generation_plan import GenerationPlan as ProjectGenerationPlan


@dataclass(frozen=True)
class GenerationRequest:
    """Minimal request passed from an endpoint into a generation adapter."""

    requirement: str
    task_id: str
    session_id: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class AdapterResult:
    """Adapter output retained by the compatibility layer."""

    success: bool
    result: Mapping[str, Any]


class GenerationModeAdapter(Protocol):
    async def create_plan(self, request: GenerationRequest) -> GenerationPlan: ...

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent: ...

    async def finalize(self, state: OrchestrationState) -> AdapterResult: ...


class TraditionalAdapter:
    """Expose the existing ``OrchestratorAgent`` through the core contract.

    The adapter owns planning and content normalization while the scheduler owns
    dependency ordering. Existing generation helpers still perform their legacy
    validation and persistence work during this migration phase.
    """

    engine_version = "traditional-adapter-v1"

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self._architecture: Dict[str, Any] = {}
        self._requirement = ""
        self._project_context: Dict[str, Any] = {}
        self._plan: Optional[GenerationPlan] = None
        self.project_plan: Optional[ProjectGenerationPlan] = None

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._requirement = request.requirement
        self._project_context = dict(request.metadata)
        await self.agent._initialize_components(request.requirement)
        self._architecture = await self.agent.architect.design_architecture(
            request.requirement,
            self.agent.complexity,
            callback=getattr(self.agent, "callback", None),
        )
        # Freeze the project-level contract first; the legacy scheduler receives
        # a compatibility projection of the same validated file nodes.
        requested_paths = request.metadata.get("requested_paths")
        self.project_plan = ProjectGenerationPlan.from_architecture(
            self._architecture,
            requested_paths=requested_paths,
            policy="strict" if requested_paths is not None else "extensible",
        )
        entries = [item.model_dump(mode="python") for item in self.project_plan.files]
        self._plan = build_file_plan(entries, requested_paths=requested_paths)
        self._project_context.setdefault("architecture", self._architecture)
        return self._plan

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent:
        if self._plan is None:
            raise RuntimeError("create_plan must run before generate_file")
        file_info = next(item for item in self._plan.files if item.path == context.file_path)
        result = await self.agent._generate_single_file(
            {
                "path": file_info.path,
                "description": file_info.role,
                "priority": file_info.priority,
            },
            self._project_context,
            len(self._plan.files),
            dict(context.upstream_contents),
        )
        if not result or not result.get("success", True):
            raise RuntimeError(f"traditional generation failed for {context.file_path}")
        content = result.get("content")
        if content is None:
            path = self.agent.output_dir / context.file_path
            content = path.read_text(encoding="utf-8")
        return GeneratedContent(
            content=str(content),
            model_name=str(result.get("model") or self.agent._select_model_for_file(context.file_path)),
            validation_passed=bool(result.get("validation_passed", True)),
            diagnostics=tuple(str(item) for item in result.get("diagnostics", ())),
        )

    async def finalize(self, state: OrchestrationState) -> AdapterResult:
        result = state.metadata.get("legacy_result", {})
        if not isinstance(result, dict):
            result = {"result": result}
        return AdapterResult(success=state.status.value == "completed", result=result)
