"""Adapters that expose existing generation modes to the orchestration core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import ast
import re
import hashlib
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

from .generation_scheduler import FileGenerationContext, GeneratedContent, TestGenerationContract
from .models import OrchestrationState
from .plan import GenerationPlan, build_file_plan, normalize_plan_path
from app.agent.generation_plan import GenerationPlan as ProjectGenerationPlan, add_profile_components
from app.agent.contract_index import ContractIndex
from app.agent.change_plan import ChangePlan
from app.agent.project_snapshot import ProjectSnapshot
from app.agent.declarative_contracts import ContractDeclaration, validate_candidate
from app.agent.languages import get_language_adapter
from app.agent.stack_adapters.contract_validation import contracts_from_openapi
from app.agent.stack_adapters.repair_strategies import (
    RepairContext,
    StackRepairCandidate,
    StackRepairStrategyRegistry,
    repair_contract_digest,
)
from app.agent.workflow_ir import TechnologyProfile


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


def _context_contract_payload(
    context: FileGenerationContext,
    fallback_index: ContractIndex,
) -> Dict[str, Any]:
    """Project a file's frozen contracts into prompt-ready structured data."""
    contract_index = getattr(context, "contract_index", fallback_index)
    http_contracts = getattr(
        context,
        "http_contracts",
        tuple(entry for entry in contract_index.entries if entry.kind == "api"),
    )
    cross_file_contracts = getattr(
        context,
        "cross_file_contracts",
        tuple(entry for entry in contract_index.entries if entry.kind != "api"),
    )
    test_contract = getattr(
        context,
        "test_generation_contract",
        TestGenerationContract(),
    )
    return {
        "contract_digest": contract_index.digest,
        "contract_index": contract_index.model_dump(mode="json"),
        "http_contracts": [
            entry.model_dump(mode="json") for entry in http_contracts
        ],
        "cross_file_contracts": [
            entry.model_dump(mode="json") for entry in cross_file_contracts
        ],
        "test_generation_contract": test_contract.model_dump(mode="json"),
    }


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
        self._shared_context: Any = None
        self._started_at = 0.0
        self._generated_contents: Dict[str, str] = {}
        self.project_plan: Optional[ProjectGenerationPlan] = None
        self.contract_index = ContractIndex.build(())

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        self._project_context = dict(request.metadata)
        self._project_context.setdefault("context_hash", request.metadata.get("context_hash"))
        await self.agent._initialize_components(request.requirement)
        self._architecture = await self.agent.architect.design_architecture(
            request.requirement,
            self.agent.complexity,
            callback=getattr(self.agent, "callback", None),
        )
        self._architecture = {
            **self._architecture,
            **{key: request.metadata[key] for key in ("contracts", "framework", "runtime")
               if request.metadata.get(key) is not None},
        }
        # Freeze the project-level contract first; the legacy scheduler receives
        # a compatibility projection of the same validated file nodes.
        requested_paths = request.metadata.get("requested_paths") or request.metadata.get("allowed_files")
        if requested_paths:
            requested_paths = tuple(
                dict.fromkeys(normalize_plan_path(path) for path in requested_paths)
            )
            self._architecture = {
                **self._architecture,
                "file_plan": list(
                    SpecFirstAdapter._build_allowed_file_plan(
                        requested_paths,
                        request.requirement,
                    )
                ),
            }
            self.project_plan = ProjectGenerationPlan.from_architecture(
                self._architecture,
                requested_paths=requested_paths,
                policy="strict",
            )
        else:
            self.project_plan = ProjectGenerationPlan.from_architecture(self._architecture)

        profile_context = request.metadata.get("profile_context")
        if isinstance(profile_context, Mapping):
            self.project_plan = add_profile_components(
                self.project_plan.files,
                profile_context,
                policy=self.project_plan.policy,
                requested_paths=self.project_plan.requested_paths,
                language=self.project_plan.language,
                framework=self.project_plan.framework,
                runtime=self.project_plan.runtime,
            )

        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph

        entries = list(self.project_plan.file_entries())
        dependency_architecture = {
            **self._architecture,
            "file_plan": entries,
        }
        language_adapter = LanguageAdapterRegistry.get_adapter(self.project_plan.language)
        dependency_graph = DependencyGraph(language_adapter=language_adapter)
        dependency_graph.build_from_architecture(dependency_architecture)

        planned_paths = {item.path for item in self.project_plan.files}
        projected_entries = []
        for raw_entry in entries:
            entry = dict(raw_entry)
            path = normalize_plan_path(str(entry.get("path", "")))
            entry["dependencies"] = sorted(
                dependency
                for dependency in dependency_graph.adjacency.get(path, ())
                if dependency in planned_paths
            )
            projected_entries.append(entry)

        self.project_plan = ProjectGenerationPlan.build(
            projected_entries,
            language=self.project_plan.language,
            framework=self.project_plan.framework,
            runtime=self.project_plan.runtime,
            policy=self.project_plan.policy,
            requested_paths=self.project_plan.requested_paths,
            interfaces=self.project_plan.interfaces,
            dependencies=self.project_plan.dependencies,
        )
        self._architecture = {
            **dependency_architecture,
            "file_plan": list(self.project_plan.file_entries()),
        }
        dependency_graph.generation_plan = self.project_plan
        self.agent.dependency_graph_obj = dependency_graph

        entries = list(self.project_plan.file_entries())
        frozen_paths = (
            self.project_plan.requested_paths
            if self.project_plan.policy == "strict"
            else None
        )
        self._plan = build_file_plan(entries, requested_paths=frozen_paths)
        self._project_context["architecture"] = self._architecture
        self.contract_index = ContractIndex.from_generation_plan(
            self.project_plan,
            contracts=request.metadata.get("contracts") or self._architecture.get("contracts"),
        )
        self._project_context["contract_index"] = self.contract_index.model_dump(mode="json")
        self._project_context["contract_digest"] = self.contract_index.digest
        return self._plan

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent:
        if self._plan is None:
            raise RuntimeError("create_plan must run before generate_file")
        file_info = next(item for item in self._plan.files if item.path == context.file_path)
        generated_contents = {
            **self._generated_contents,
            **dict(context.upstream_contents),
        }
        self._project_context["generation_contract"] = {
            **_context_contract_payload(context, self.contract_index),
            "target_file": context.file_path,
        }
        result = await self.agent._generate_single_file(
            {
                "path": file_info.path,
                "description": file_info.role,
                "priority": file_info.priority,
            },
            self._project_context,
            len(self._plan.files),
            generated_contents,
        )
        if not result or not result.get("success", True):
            raise RuntimeError(f"traditional generation failed for {context.file_path}")
        content = result.get("content")
        if content is None:
            path = self.agent.output_dir / context.file_path
            content = path.read_text(encoding="utf-8")
        self._generated_contents[context.file_path] = str(content)
        return GeneratedContent(
            content=str(content),
            model_name=str(result.get("model") or self.agent._select_model_for_file(context.file_path)),
            validation_passed=bool(result.get("validation_passed", True)),
            diagnostics=tuple(str(item) for item in result.get("diagnostics", ())),
            contract_refs=tuple(
                str(item)
                for item in result.get("contract_refs", file_info.contract_refs)
            ),
        )

    async def finalize(self, state: OrchestrationState) -> AdapterResult:
        manifest = (
            self._shared_context.get_artifact_manifest()
            if self._shared_context is not None
            else {}
        )
        success = state.status.value == "completed"
        files = [dict(manifest[path]) for path in sorted(manifest)]
        diagnostics = [str(item.get("message") or item) for item in state.diagnostics]
        planned_count = len(self._plan.files) if self._plan is not None else 0
        complexity_level = getattr(getattr(self.agent, "complexity", None), "level", "unknown")
        if hasattr(complexity_level, "value"):
            complexity_level = complexity_level.value
        assignment = getattr(self.agent, "model_assignment", None)
        result = {
            "success": success,
            "output_dir": str(self.agent.output_dir),
            "total_files_created": len(files),
            "total_files_failed": 0 if success else max(planned_count - len(files), 1),
            "total_files": planned_count,
            "complexity": str(complexity_level),
            "models_used": {
                role: str(getattr(assignment, attribute, "N/A"))
                for role, attribute in {
                    "architect": "architect_model",
                    "frontend": "frontend_model",
                    "backend": "backend_model",
                    "reviewer": "reviewer_model",
                }.items()
            },
            "files": files,
            "generated_files": files,
            "validation": {"runnable": success, "status": state.status.value},
            "errors": diagnostics,
            "warnings": [],
            "elapsed_time": max(time.monotonic() - self._started_at, 0.0),
            "fix_attempts": [],
        }
        return AdapterResult(success=success, result=result)


class _PlannedAgentAdapter:
    """Shared production bridge for Core-owned scheduling and persistence."""

    engine_version = "planned-agent-adapter-v1"

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.output_dir = Path(agent.output_dir)
        self.project_plan: Optional[ProjectGenerationPlan] = None
        self.contract_index = ContractIndex.build(())
        self._plan: Optional[GenerationPlan] = None
        self._requirement = ""
        self._project_context: Dict[str, Any] = {}
        self._file_entries: Dict[str, Dict[str, Any]] = {}
        self._generated_contents: Dict[str, str] = {}
        self._repair_evidence: list[dict[str, str]] = []
        self._repair_strategies = StackRepairStrategyRegistry()
        self._dependency_graph: Any = None
        self._spec_generator: Any = None
        self._shared_context: Any = None
        self._started_at = 0.0
        self.preserved_paths: Tuple[str, ...] = ()

    @property
    def shared_context(self) -> Any:
        if self._shared_context is None:
            from app.agent.shared_context import SharedContext

            self._shared_context = SharedContext(self._requirement, self.output_dir)
        return self._shared_context

    def _complexity_payload(self) -> Dict[str, Any]:
        complexity = getattr(self.agent, "complexity", None)
        if complexity is None:
            return {"level": "small", "estimated_files": 1}
        level = getattr(complexity, "level", "small")
        return {
            "level": getattr(level, "value", level),
            "estimated_files": getattr(complexity, "estimated_files", 1),
            "has_frontend": getattr(complexity, "has_frontend", False),
            "has_backend": getattr(complexity, "has_backend", True),
            "has_database": getattr(complexity, "has_database", False),
            "key_technologies": list(getattr(complexity, "key_technologies", ())),
        }

    def _model_assignment_payload(self) -> Dict[str, str]:
        assignment = getattr(self.agent, "model_assignment", None)
        if assignment is None:
            return {}
        names = ("architect_model", "frontend_model", "backend_model", "reviewer_model", "fallback_model")
        return {name: str(getattr(assignment, name)) for name in names if getattr(assignment, name, None)}

    def _freeze_plan(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        language: str = "",
        allow_empty: bool = False,
    ) -> GenerationPlan:
        requested_paths = tuple(str(item.get("path", "")) for item in entries)
        requested_set = set(requested_paths)
        scoped_entries = []
        for entry in entries:
            projected = dict(entry)
            dependencies = projected.get("dependencies", projected.get("depends_on", ()))
            if isinstance(dependencies, str):
                dependencies = (dependencies,)
            projected["dependencies"] = [path for path in dependencies or () if path in requested_set]
            scoped_entries.append(projected)
        self.project_plan = ProjectGenerationPlan.build(
            scoped_entries,
            language=language,
            framework=self._project_context.get("architecture", {}).get("framework", ""),
            runtime=self._project_context.get("architecture", {}).get("runtime", ""),
            requested_paths=requested_paths,
            policy="strict",
        )
        self._file_entries = {str(item["path"]): dict(item) for item in scoped_entries}
        self.contract_index = ContractIndex.from_generation_plan(
            self.project_plan,
            contracts=self._project_context.get("contracts"),
        )
        self._project_context["contract_index"] = self.contract_index.model_dump(mode="json")
        self._project_context["contract_digest"] = self.contract_index.digest
        self._plan = build_file_plan(
            self.project_plan.file_entries(),
            requested_paths=requested_paths,
            allow_empty=allow_empty,
        )
        return self._plan

    def _validate_local_imports(self, file_path: str, content: str) -> Tuple[str, ...]:
        """Reject Python imports that escape the frozen project file set."""
        if not file_path.endswith(".py"):
            return ()
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as exc:
            return (f"syntax error: {exc.msg}",)
        planned = {Path(path).with_suffix("").as_posix().replace("/", ".") for path in self._file_entries}
        planned.update({Path(path).parent.as_posix().replace("/", ".") for path in self._file_entries})
        planned.update({f"app.{module}" for module in planned if module and module != "."})
        diagnostics = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if module.startswith("app.") and module not in planned:
                    diagnostics.append(f"local import outside frozen file set: {module}")
        return tuple(dict.fromkeys(diagnostics))

    def _contract_file_role(self, file_path: str) -> str | None:
        entry = self._file_entries.get(file_path, {})
        role = entry.get("role") or entry.get("type")
        return str(role) if role else None

    def _validate_candidate_contract(
        self,
        file_path: str,
        content: str,
        *,
        language: str = "",
    ) -> tuple[Any, Tuple[str, ...]]:
        file_info = self._file_entries.get(file_path, {})
        selected_language = str(
            language or
            file_info.get("language") or getattr(self.project_plan, "language", "")
        )
        try:
            language_adapter = get_language_adapter(selected_language)
        except LookupError as exc:
            return None, (f"contract parser capability unsupported: {exc}",)
        try:
            declaration = ContractDeclaration.from_mapping(file_info.get("contract"))
        except ValueError as exc:
            return language_adapter, (f"invalid contract declaration: {exc}",)
        planned_contents = {
            path: self._generated_contents.get(path, "") for path in self._file_entries
        }
        for path in self.preserved_paths:
            target = self.output_dir / path
            if target.is_file() and target.resolve().is_relative_to(self.output_dir.resolve()):
                planned_contents[path] = target.read_text(encoding="utf-8", errors="replace")
        planned_contents[file_path] = content
        result = validate_candidate(
            language_adapter,
            file_path,
            content,
            declaration,
            planned_contents,
        )
        return language_adapter, result.diagnostics

    def _contract_retry_candidate(self, file_path: str) -> StackRepairCandidate | None:
        selected = self._repair_strategies.select(
            file_path,
            RepairContext(
                requirement=self._requirement,
                file_entries=tuple(self._file_entries),
                project_context=dict(self._project_context),
            ),
        )
        if selected is not None:
            strategy, content = selected
            return StackRepairCandidate(
                strategy=strategy.name,
                file_path=file_path,
                content=content,
                trigger_reason="stack contract retry requested",
                input_contract_digest=self._repair_contract_digest(),
                candidate_version=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            )
        return None

    def _repair_contract_digest(self) -> str:
        return repair_contract_digest(self._requirement, self._file_entries)

    async def _assemble_retrieved_context(self, contract_context: Mapping[str, Any]) -> None:
        """Run the local retrieval path and expose its provenance to the model."""
        from app.agent.context_assembler import ContextAssembler
        from app.agent.retrieval import CallableRetriever, RetrievalService
        from app.agent.retrieval.models import RetrievalChunk, RetrievalRequest

        user_requirement = getattr(self, "_user_requirement", self._requirement)
        target_file = str(contract_context.get("target_file") or "")
        target_description = str(
            self._file_entries.get(target_file, {}).get("description") or ""
        )
        retrieval_query = " ".join(
            item for item in (user_requirement, target_file, target_description, "generating") if item
        )
        records = (
            ("requirement", user_requirement),
            ("generation_contract", str(contract_context)),
            ("architecture", str(self._project_context.get("architecture", {}))),
            ("target_file", f"{target_file} {target_description}"),
        )

        def search(request: RetrievalRequest) -> list[RetrievalChunk]:
            query_terms = set(re.findall(r"[a-zA-Z0-9_]+", request.query.lower()))
            results = []
            for source_id, content in records:
                terms = set(re.findall(r"[a-zA-Z0-9_]+", content.lower()))
                score = len(query_terms & terms) / max(len(query_terms), 1)
                results.append(RetrievalChunk(
                    content=content,
                    source_type="local_generation_context",
                    source_id=source_id,
                    score=score,
                ))
            return results

        retrieval = await RetrievalService([
            CallableRetriever("local_generation_context", search),
        ]).retrieve(RetrievalRequest(query=retrieval_query, limit=3))
        envelope = ContextAssembler(max_chars=24000).assemble(
            task_id=str(self._project_context.get("task_id", "generation")),
            stage="generating",
            file_path=None,
            retrieval=retrieval,
        )
        self._project_context["context_envelope"] = envelope.model_dump(mode="json")
        self._project_context["retrieval_status"] = {
            "enabled": True,
            "source_count": len(retrieval.chunks),
            "degraded": retrieval.degraded,
            "sources": [chunk.source_id for chunk in retrieval.chunks],
        }

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent:
        if self._plan is None:
            raise RuntimeError("create_plan must run before generate_file")
        file_info = self._file_entries[context.file_path]
        upstream = {**self._generated_contents, **dict(context.upstream_contents)}
        contract = file_info.get("contract") or {}
        technology = getattr(context, "technology", None) or TechnologyProfile(
            language=str(file_info.get("language") or getattr(self.project_plan, "language", "")),
            framework=str(contract.get("framework") or getattr(self.project_plan, "framework", "")),
            runtime=str(contract.get("runtime") or getattr(self.project_plan, "runtime", "")),
        )
        language = technology.language.lower()
        framework = technology.framework.lower()
        typescript_backend = language in {"typescript", "javascript"} and framework in {
            "express", "nestjs"
        }
        model_name = str(
            self.agent.model_assignment.backend_model
            if typescript_backend and getattr(self.agent, "model_assignment", None)
            else self.agent._select_model_for_file(context.file_path)
        )

        # Keep every file generation grounded in the same frozen contract. The
        # legacy generator can otherwise let each specialist invent a separate
        # domain model even when the plan already defines shared interfaces.
        contract_index = getattr(context, "contract_index", self.contract_index)
        contract_context = {
            **_context_contract_payload(context, self.contract_index),
            "frozen_file_set": sorted(set(self._file_entries) | set(self.preserved_paths)),
            "writable_file_set": [item.path for item in self._plan.files],
            "target_file": context.file_path,
            "target_technology": technology.model_dump(mode="json"),
            "target_contract": dict(file_info.get("contract") or {}),
            "file_contracts": {
                path: {
                    "file_type": str(entry.get("file_type", "")),
                    "description": str(entry.get("description", entry.get("role", ""))),
                    "imports": list(entry.get("imports") or entry.get("dependencies") or ()),
                    "contract": dict(entry.get("contract") or {}),
                }
                for path, entry in self._file_entries.items()
            },
            "rules": [
                "Use the domain entities, field names, routes, storage abstraction, and framework from the requirement and frozen contracts.",
                "Keep all local imports inside frozen_file_set; do not invent modules or dependencies.",
                "Keep models, schemas, CRUD/service code, entrypoint, and tests consistent across the whole file set.",
                "Apply each HTTP contract's request_body_schema, response_body_schema, and serialization_guidance to callers, handlers, and tests, including repairs.",
                "Define every test client fixture in the test file or conftest and bind each test parameter to the exact fixture name.",
                "Pass only a JSON-serializable mapping to request json parameters; explicitly serialize Pydantic and dataclass instances first.",
                "Resolve cross-file test entrypoints from the declared exports of the actual entry module.",
                "Frozen HTTP contracts are authoritative: implement their method, path, status, fields, and serialization exactly; report contract_gap for missing details instead of inventing changes.",
            ],
        }
        previous_diagnostics = tuple(getattr(context, "previous_diagnostics", ()))
        if previous_diagnostics:
            contract_context["retry_feedback"] = list(previous_diagnostics)
            contract_context["rules"].append(
                "The previous candidate was rejected. Fix every validation diagnostic before returning the complete file: "
                + "; ".join(previous_diagnostics)
            )
        requirement_text = self._requirement.lower()
        if framework == "fastapi" or (not framework and "fastapi" in requirement_text):
            contract_context["rules"].extend([
                "The FastAPI entrypoint must expose the application named by the frozen contract and import every FastAPI symbol it uses, including HTTPException.",
                "Every referenced Python global must be defined or explicitly imported, including SQLAlchemy Base, Column, and field types.",
                "Pydantic request and response schemas must inherit BaseModel independently; SQLAlchemy ORM models from models.py are never schema base classes.",
                "Response schemas must explicitly declare the fields returned by the ORM/service layer and use model_config or orm_mode as required by the installed Pydantic version.",
                "SQLAlchemy column defaults belong to Column(default=...), while DateTime(...) only receives type options such as timezone=True; every ORM model exported from models.py must be importable at runtime.",
                "A route returning HTTP 204 must not declare response_model or return a response body.",
                "Async lifespan handlers must await async cleanup directly and must not call asyncio.run() from an active event loop.",
                "When repairing an API entrypoint, return the complete file and preserve every existing contracted route.",
            ])
        if (
            language == "java" and framework in {"spring", "spring boot", "spring-boot"}
        ) or (not language and "java" in requirement_text and "spring" in requirement_text):
            contract_context["rules"].extend([
                "Each Java file must declare the top-level type matching its file name and must not declare a differently named public type.",
                "Use supported JdbcTemplate query, queryForObject, update, and execute operations; convert LocalDateTime with Timestamp.valueOf and ResultSet.getTimestamp.",
                "Every Java source file must have unambiguous imports and compile independently within the frozen Maven project.",
                "Do not declare nested types with the same simple name as an imported type, including RowMapper.",
            ])
        self._project_context["generation_contract"] = contract_context
        await self._assemble_retrieved_context(contract_context)

        retry_candidate = self._contract_retry_candidate(context.file_path)
        if retry_candidate is not None:
            self._repair_evidence.append({
                "strategy": retry_candidate.strategy,
                "file_path": retry_candidate.file_path,
                "trigger_reason": retry_candidate.trigger_reason,
                "input_contract_digest": retry_candidate.input_contract_digest,
                "candidate_version": retry_candidate.candidate_version,
            })
            result = {
                "success": True,
                "content": retry_candidate.content,
                "model": "deterministic-contract-retry",
            }
        elif hasattr(self.agent, "_generate_file_with_model") and self._dependency_graph is not None:
            engineer = self.agent.backend_engineer if typescript_backend else self.agent._select_engineer(context.file_path)
            content = await self.agent._generate_file_with_model(
                context.file_path,
                file_info,
                engineer,
                model_name,
                self._project_context,
                upstream,
                self._spec_generator,
                self._dependency_graph,
                getattr(self.agent, "callback", None),
                persist=False,
            )
            result: Mapping[str, Any] = {"success": bool(content), "content": content, "model": model_name}
        else:
            result = await self.agent._generate_single_file(
                file_info,
                self._project_context,
                len(self._plan.files),
                upstream,
            )

        if not result or not result.get("success", True) or not result.get("content"):
            raise RuntimeError(f"{self.__class__.__name__} generation failed for {context.file_path}")
        from app.agent.file_response import parse_file_response

        response = parse_file_response(result["content"], expected_path=context.file_path)
        if response.content is None:
            return GeneratedContent(
                content="",
                model_name=str(result.get("model") or model_name),
                validation_passed=False,
                diagnostics=(response.diagnostic or "invalid model file response",),
            )
        content = response.content
        self._generated_contents[context.file_path] = content
        validation_passed = bool(result.get("validation_passed", True))
        language_adapter, contract_diagnostics = self._validate_candidate_contract(
            context.file_path, content
        )
        source_repair = (
            language_adapter.repair_source(content, context.file_path, contract_diagnostics)
            if language_adapter is not None
            else None
        )
        if source_repair is not None and source_repair != content:
            candidate_version = hashlib.sha256(source_repair.encode("utf-8")).hexdigest()
            self._repair_evidence.append({
                "strategy": "language-source-repair",
                "file_path": context.file_path,
                "trigger_reason": contract_diagnostics[0],
                "input_contract_digest": self.contract_index.digest,
                "candidate_version": candidate_version,
            })
            content = source_repair
            self._generated_contents[context.file_path] = content
            _, contract_diagnostics = self._validate_candidate_contract(
                context.file_path, content
            )
        if contract_diagnostics:
            validation_passed = False
        if validation_passed and hasattr(self.agent, "_validate_content_syntax"):
            validation_passed = bool(await self.agent._validate_content_syntax(context.file_path, content))
        return GeneratedContent(
            content=content,
            model_name=str(result.get("model") or model_name),
            validation_passed=validation_passed,
            diagnostics=tuple(str(item) for item in result.get("diagnostics", ())) + contract_diagnostics,
            contract_refs=tuple(
                str(item)
                for item in result.get("contract_refs", file_info.get("contract_refs", ()))
            ),
        )

    async def finalize(self, state: OrchestrationState) -> AdapterResult:
        manifest = self.shared_context.get_artifact_manifest()
        success = state.status.value == "completed"
        files = [dict(manifest[path]) for path in sorted(manifest)]
        diagnostics = [str(item.get("message") or item) for item in state.diagnostics]
        for diagnostic in state.diagnostics:
            nodes = diagnostic.get("details", {}).get("nodes", {})
            if not isinstance(nodes, Mapping):
                continue
            for path, node in nodes.items():
                if not isinstance(node, Mapping):
                    continue
                for item in node.get("diagnostics", ()):
                    if not isinstance(item, Mapping):
                        continue
                    message = str(item.get("message") or "").strip()
                    if message:
                        diagnostics.append(f"{path}: {message}")
        diagnostics = list(dict.fromkeys(diagnostics))
        result = {
            "success": success,
            "output_dir": str(self.output_dir),
            "total_files_created": len(files),
            "total_files_failed": 0 if success else max(len(self._file_entries) - len(files), 1),
            "total_files": len(self._file_entries),
            "complexity": str(self._complexity_payload().get("level", "small")),
            "models_used": self._model_assignment_payload(),
            "files": files,
            "generated_files": files,
            "validation": {"runnable": success, "status": state.status.value},
            "errors": diagnostics,
            "warnings": [],
            "elapsed_time": max(time.monotonic() - self._started_at, 0.0),
            "fix_attempts": list(self._repair_evidence),
        }
        return AdapterResult(success=success, result=result)


class SpecFirstAdapter(_PlannedAgentAdapter):
    """Generate specifications first and freeze their architecture file plan."""

    engine_version = "spec-first-adapter-v1"

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        self._user_requirement = str(request.metadata.get("user_requirement") or request.requirement)
        supplied = request.metadata.get("specification") or request.metadata.get("architecture")
        architecture = dict(supplied) if isinstance(supplied, Mapping) else None
        allowed_paths = tuple(dict.fromkeys(
            normalize_plan_path(path)
            for path in request.metadata.get("allowed_files", ())
        ))

        await self.agent._initialize_components(request.requirement)
        context = self.shared_context
        context.complexity = self._complexity_payload()
        context.model_assignment = self._model_assignment_payload()

        if architecture is None and allowed_paths:
            from app.agent.language_detector import LanguageDetector

            language = LanguageDetector.detect(request.requirement).language
            architecture = {
                "language": language,
                "project_requirement": self._user_requirement,
                "file_plan": self._build_allowed_file_plan(allowed_paths, self._user_requirement),
            }
        if architecture is None:
            from app.agent.language_detector import LanguageDetector
            from app.agent.spec_first_generator import SpecFirstGenerator

            language = LanguageDetector.detect(request.requirement).language
            self._spec_generator = SpecFirstGenerator(
                context,
                language=language,
                api_key_token=getattr(self.agent, "api_key_token", None),
            )
            if not await self._spec_generator.generate_all_specs(
                request.requirement,
                context.complexity,
                getattr(self.agent, "callback", None),
            ):
                raise RuntimeError("Spec-First specification generation failed")
            architecture = await self.agent.architect.design_architecture(
                request.requirement,
                self.agent.complexity,
                callback=getattr(self.agent, "callback", None),
            )

        architecture = {
            **architecture,
            **{key: request.metadata[key] for key in ("contracts", "framework", "runtime")
               if request.metadata.get(key) is not None},
        }
        entries = architecture.get("file_plan", ())
        allowed_files = set(allowed_paths)
        if allowed_files:
            by_path = {
                normalize_plan_path(str(entry.get("path", ""))): dict(entry)
                for entry in entries
                if normalize_plan_path(str(entry.get("path", ""))) in allowed_files
            }
            inferred = {
                entry["path"]: entry for entry in self._build_allowed_file_plan(allowed_paths)
            }
            entries = tuple(by_path.get(path, inferred[path]) for path in allowed_paths)
        if not entries:
            raise ValueError("Spec-First architecture must contain a non-empty file_plan")
        language = str(architecture.get("language", ""))
        contracts = (
            architecture.get("contracts")
            or request.metadata.get("contracts")
            or contracts_from_openapi(context)
        )
        self._project_context = {
            **dict(request.metadata),
            "requirement": self._user_requirement,
            "architecture": architecture,
            "contracts": contracts,
            "complexity": context.complexity,
            "output_dir": str(self.output_dir),
            "is_spec_first": True,
        }
        self._dependency_graph = self._build_dependency_graph(architecture, language)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._dependency_graph.save(str(self.output_dir / ".dep_graph.json"))
        adjacency = getattr(self._dependency_graph, "adjacency", {})
        planned_entries = []
        for raw_entry in entries:
            entry = dict(raw_entry)
            if "dependencies" not in entry and "depends_on" not in entry:
                entry["dependencies"] = sorted(adjacency.get(str(entry.get("path", "")), ()))
            planned_entries.append(entry)
        return self._freeze_plan(planned_entries, language=language)

    @staticmethod
    def _build_allowed_file_plan(
        paths: Sequence[str], requirement: str = ""
    ) -> Tuple[Dict[str, Any], ...]:
        """Create a stable plan when the caller supplies a frozen file set."""
        manifests = {
            path
            for path in paths
            if Path(path).name
            in {
                "go.mod",
                "Cargo.toml",
                "pom.xml",
                "build.gradle",
                "build.gradle.kts",
                "package.json",
                "pyproject.toml",
                "requirements.txt",
            }
        }

        def role(path: str) -> int:
            name = Path(path).stem.lower()
            normalized = path.lower()
            if path in manifests:
                return 0
            if normalized.startswith(("test/", "tests/")) or name.endswith(("test", "spec")):
                return 5
            if name == "db" or any(part in normalized for part in ("model", "schema", "database", "store", "repository")):
                return 1
            if any(part in normalized for part in ("service", "crud")):
                return 2
            if any(part in normalized for part in ("route", "controller", "handler")):
                return 3
            if name in {"main", "app", "index", "application", "server"}:
                return 4
            return 1

        roles = {path: role(path) for path in paths}

        def is_direct_domain_dependency(path: str, candidate: str) -> bool:
            stem = Path(path).stem.lower()
            candidate_stem = Path(candidate).stem.lower()
            suffixes = ("repository", "store", "schema", "model")
            return any(
                stem.endswith(suffix) and stem.removesuffix(suffix) == candidate_stem
                for suffix in suffixes
            )

        entries = []
        for path in paths:
            dependencies: Tuple[str, ...] = tuple(
                candidate
                for candidate in paths
                if candidate != path
                and (
                    roles[candidate] < roles[path]
                    or is_direct_domain_dependency(path, candidate)
                )
            )
            if path.startswith("tests/"):
                dependencies = tuple(item for item in paths if not item.startswith("tests/"))
            entries.append({
                "path": path,
                "description": (
                    f"Implement {path} for this exact project requirement: {requirement.strip()}"
                    if requirement.strip()
                    else f"Required project file {path}"
                ),
                "dependencies": list(dependencies),
            })
        return tuple(entries)

    def _build_dependency_graph(self, architecture: Mapping[str, Any], language: str) -> Any:
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=LanguageAdapterRegistry.get_adapter(language or "python"))
        graph.build_from_architecture(dict(architecture))
        return graph


class IncrementalAdapter(_PlannedAgentAdapter):
    """Freeze one strict plan containing only files affected by a change."""

    engine_version = "incremental-adapter-v1"

    change_plan: Optional[ChangePlan] = None

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        self._project_context = dict(request.metadata)
        architecture = dict(request.metadata.get("architecture") or {})
        for key in ("contracts", "framework", "runtime"):
            if request.metadata.get(key) is not None:
                architecture[key] = request.metadata[key]
            elif key in architecture:
                self._project_context[key] = architecture[key]
        self._project_context["architecture"] = architecture
        await self.agent._initialize_components_fast(request.requirement)

        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.language_detector import LanguageDetector

        language = architecture.get("language") or LanguageDetector.detect(request.requirement).language
        graph = request.metadata.get("dependency_graph")
        if graph is None:
            graph = DependencyGraph.load(
                str(self.output_dir / ".dep_graph.json"),
                language_adapter=LanguageAdapterRegistry.get_adapter(language),
            )
        if graph is None:
            if not self.output_dir.is_dir() or not any(self.output_dir.iterdir()):
                raise RuntimeError("incremental Core generation requires an existing project")
            graph = DependencyGraph(language_adapter=LanguageAdapterRegistry.get_adapter(language))
            await graph.build_from_existing_project(self.output_dir)
            if not graph.nodes:
                raise RuntimeError("incremental Core generation could not rebuild the dependency graph")
            graph.save(str(self.output_dir / ".dep_graph.json"))
        if isinstance(graph, DependencyGraph):
            graph.enrich_and_save(self.output_dir)
        self._dependency_graph = graph
        adjacency = getattr(graph, "adjacency", {})

        allowed_files = {
            normalize_plan_path(path)
            for path in request.metadata.get("planned_files", request.metadata.get("allowed_files", ()))
        }
        raw_changes = request.metadata.get("change_plan") or None
        if raw_changes is None:
            summary = self.agent._build_project_summary_from_graph(graph)
            raw_changes = await self.agent._analyze_changes_with_architect(
                request.requirement,
                summary,
                graph,
                getattr(self.agent, "callback", None),
            )
        changes = [dict(item) for item in raw_changes or ()]
        if allowed_files:
            changes = [
                change
                for change in changes
                if normalize_plan_path(str(change.get("path", ""))) in allowed_files
            ]
        if not changes:
            raise ValueError("incremental change plan must contain at least one affected file")
        snapshot = ProjectSnapshot.scan(
            self.output_dir,
            revision=str(request.metadata.get("base_revision") or "working-tree"),
        )
        try:
            self.change_plan = ChangePlan.build(snapshot, changes)
        except ValueError as exc:
            if any(item.get("action") == "delete" for item in changes):
                raise ValueError(f"incremental deletion is not transactional: {exc}") from exc
            raise
        entries = []
        for change in changes:
            if change.get("action", "modify") == "delete":
                continue
            path = str(change.get("path", ""))
            if "dependencies" not in change and "depends_on" not in change:
                change["dependencies"] = sorted(adjacency.get(path, ()))
            if change.get("action", "modify") == "modify" and "original_content" not in change:
                target = self.output_dir / path
                change["original_content"] = target.read_text(encoding="utf-8") if target.is_file() else ""
            entries.append(change)

        affected = set(self.change_plan.affected_files if self.change_plan else ())
        affected.update(str(item.get("path", "")) for item in entries)
        external_dependencies = {
            dependency
            for path in affected
            for dependency in adjacency.get(path, ())
            if dependency not in affected
        }
        self.preserved_paths = tuple(sorted(
            item.path for item in snapshot.files
            if item.path not in affected
            and (not allowed_files or item.path in allowed_files)
            and (self.output_dir / item.path).is_file()
            and (self.output_dir / item.path).resolve().is_relative_to(self.output_dir.resolve())
        ))
        for dependency in external_dependencies:
            normalized = normalize_plan_path(dependency)
            target = self.output_dir / normalized
            if normalized in self.preserved_paths and target.is_file():
                self._generated_contents[normalized] = target.read_text(encoding="utf-8")
        self._project_context = {
            **self._project_context,
            "requirement": request.requirement,
            "architecture": {**architecture, "language": language, "file_plan": entries},
            "complexity": self._complexity_payload(),
            "output_dir": str(self.output_dir),
            "is_incremental": True,
            "change_plan": self.change_plan.model_dump(mode="json"),
            "base_snapshot": snapshot.model_dump(mode="json"),
        }
        return self._freeze_plan(entries, language=language, allow_empty=True)
