from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent.orchestration import (
    CORE_ENGINE,
    LEGACY_ENGINE,
    GenerationRequest,
    IncrementalAdapter,
    SpecFirstAdapter,
    TraditionalAdapter,
    TestGenerationContract,
    engine_metadata,
    execute_core_generation,
    select_engine,
)
from app.agent.orchestration.models import OrchestrationState, OrchestrationStatus
from app.agent.workflow_registry import build_legacy_workflow, run_workflow
from app.agent.orchestrator_generation.spec_first_generate import SpecFirstGenerateMixin
from app.agent.stack_adapters.contract_validation import contracts_from_openapi
from app.agent.stack_adapters.repair_strategies import StackRepairStrategy, StackRepairStrategyRegistry


class _Architect:
    async def design_architecture(self, requirement, complexity, callback=None):
        return {
            "language": "python",
            "file_plan": [
                {"path": "app.py", "description": "application entry point"},
                {"path": "config.py", "description": "configuration", "depends_on": ["app.py"]},
            ],
        }


class _Agent:
    def __init__(self, tmp_path):
        self.architect = _Architect()
        self.complexity = object()
        self.callback = None
        self.output_dir = Path(tmp_path)

    async def _initialize_components(self, requirement):
        self.initialized_requirement = requirement

    async def _generate_single_file(self, file_info, project_context, total_files, generated_contents):
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "test-model"}

    def _select_model_for_file(self, file_path):
        return "fallback-model"

    async def _initialize_components_fast(self, requirement):
        self.initialized_requirement = requirement


class _CoreFileAgent(_Agent):
    def _select_engineer(self, file_path):
        return object()

    async def _generate_file_with_model(
        self,
        file_path,
        file_info,
        engineer,
        model_name,
        project_context,
        generated_contents,
        spec_generator,
        dependency_graph,
        callback,
        *,
        persist=True,
    ):
        self.persist_requested = persist
        self.generation_contract = project_context.get("generation_contract")
        self.project_context = project_context
        return f"# {file_path}\n"


@pytest.mark.asyncio
async def test_typescript_syntax_validation_accepts_nestjs_decorators():
    content = '''
import { Controller, Get } from "@nestjs/common";

@Controller("health")
export class HealthController {
  @Get()
  check(): { status: string } {
    return { status: "ok" };
  }
}
'''

    assert await SpecFirstGenerateMixin()._validate_content_syntax("src/main.ts", content)


@pytest.mark.asyncio
async def test_typescript_syntax_validation_rejects_invalid_syntax():
    content = "export class Broken { check(: string { return 'bad'; } }\n"

    assert not await SpecFirstGenerateMixin()._validate_content_syntax("src/main.ts", content)


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_diagnostics", [(), ("repair the declared interface",)])
@pytest.mark.parametrize(
    "requirement,language,paths,target,content",
    [
        (
            "Build a pygame snake game", "python",
            ("main.py", "game/rules.py", "game/renderer.py", "game/input_loop.py", "tests/test_game.py"),
            "game/rules.py", "class Arena:\n    pass\n",
        ),
        (
            "Create a Java Spring Boot CRUD API with SQLite at /api/v1/todos", "java",
            ("src/main/java/com/example/Todo.java", "src/main/java/com/example/TodoRepository.java"),
            "src/main/java/com/example/Todo.java", "package com.example;\npublic class Todo { public String label; }\n",
        ),
        (
            "Repair the existing python fastapi CRUD project", "python",
            ("app/models.py", "app/schemas.py", "app/crud.py", "app/main.py", "tests/test_crud.py"),
            "app/models.py", "class Inventory:\n    pass\n",
        ),
        (
            "Repair the existing typescript express CRUD project", "typescript",
            ("src/app.ts", "src/routes/todos.ts", "src/db.ts", "tests/todos.test.ts"),
            "src/db.ts", "export const inventory = [];\n",
        ),
        (
            "Repair the existing typescript nestjs CRUD project", "typescript",
            ("src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts", "test/todos.e2e-spec.ts"),
            "src/todos/todos.service.ts", "export class InventoryService {}\n",
        ),
        (
            "Repair the existing go net/http CRUD project", "go",
            ("go.mod", "go.sum", "cmd/server/main.go", "internal/todos/store.go", "internal/todos/handler.go", "internal/todos/handler_test.go"),
            "internal/todos/store.go", "package todos\n\ntype Inventory struct { Label string }\n",
        ),
        (
            "Repair the existing python flask CRUD project", "python",
            ("models.py", "crud.py", "app.py", "tests/test_crud.py"),
            "models.py", "class Inventory:\n    pass\n",
        ),
        (
            "Build a CLI task tracker", "python", ("main.py",),
            "main.py", "class WorkQueue:\n    pass\n",
        ),
    ],
)
async def test_sample_shaped_requests_use_model_generation(
    tmp_path, requirement, language, paths, target, content, previous_diagnostics
):
    agent = _CoreFileAgent(tmp_path)
    agent.backend_engineer = object()
    agent._generate_file_with_model = AsyncMock(return_value=content)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement=requirement, task_id="model-task", session_id="model-session",
        metadata={"specification": {
            "language": language,
            "file_plan": [{"path": path} for path in paths],
        }},
    ))

    generated = await adapter.generate_file(SimpleNamespace(
        file_path=target, upstream_contents={}, previous_diagnostics=previous_diagnostics,
    ))

    agent._generate_file_with_model.assert_awaited_once()
    assert generated.content == content
    assert generated.model_name == "fallback-model"
    assert generated.validation_passed, generated.diagnostics
    assert adapter._repair_evidence == []
    contract = adapter._project_context["generation_contract"]
    assert set(contract["frozen_file_set"]) == set(paths)
    assert contract.get("retry_feedback", []) == list(previous_diagnostics)
    rules = "\n".join(contract["rules"])
    assert all(marker not in rules for marker in ("Todo", "/api/v1/todos", "Snake.body", "TaskList"))


@pytest.mark.asyncio
@pytest.mark.parametrize("content,passed", [("VALUE = 1\n", True), ("OTHER = 1\n", False)])
async def test_explicit_repair_strategy_keeps_evidence_and_contract_validation(tmp_path, content, passed):
    adapter = SpecFirstAdapter(_CoreFileAgent(tmp_path))
    await adapter.create_plan(GenerationRequest(
        requirement="build declared constants", task_id="repair-task", session_id="repair-session",
        metadata={"specification": {"language": "python", "file_plan": [{
            "path": "constants.py",
            "contract": {"assertions": [{
                "fact": "symbols", "operator": "contains_all", "expected": ["VALUE"],
            }]},
        }]}},
    ))
    adapter._repair_strategies = StackRepairStrategyRegistry((
        StackRepairStrategy("declared-repair", lambda path: content),
    ))

    generated = await adapter.generate_file(SimpleNamespace(file_path="constants.py", upstream_contents={}))

    assert generated.content == content
    assert generated.validation_passed is passed
    evidence, = adapter._repair_evidence
    assert evidence["strategy"] == "declared-repair"
    assert evidence["file_path"] == "constants.py"
    assert len(evidence["input_contract_digest"]) == 64
    assert len(evidence["candidate_version"]) == 16
    if not passed:
        assert any("contract assertion failed for symbols" in item for item in generated.diagnostics)


@pytest.mark.asyncio
async def test_cli_task_tracker_uses_specification_and_architect(tmp_path, monkeypatch):
    generate_specs = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.agent.spec_first_generator.SpecFirstGenerator.generate_all_specs", generate_specs,
    )
    agent = _Agent(tmp_path)
    agent.architect.design_architecture = AsyncMock(return_value={
        "language": "python", "file_plan": [{"path": "queue.py"}, {"path": "cli.py"}],
    })
    adapter = SpecFirstAdapter(agent)

    plan = await adapter.create_plan(GenerationRequest(
        requirement="Build a CLI task tracker", task_id="cli-task", session_id="cli-session", metadata={},
    ))

    generate_specs.assert_awaited_once()
    agent.architect.design_architecture.assert_awaited_once()
    assert set(plan.requested_paths) == {"queue.py", "cli.py"}


@pytest.mark.asyncio
@pytest.mark.parametrize("language,framework,paths", [
    ("python", "fastapi", ("app/models.py", "app/schemas.py", "app/crud.py", "app/main.py", "tests/test_crud.py")),
    ("python", "flask", ("models.py", "crud.py", "app.py", "tests/test_crud.py")),
    ("typescript", "express", ("src/db.ts", "src/app.ts", "src/routes/todos.ts", "tests/todos.test.ts")),
    ("typescript", "nestjs", ("src/todos/todos.service.ts", "src/main.ts", "src/todos/todos.controller.ts", "test/todos.e2e-spec.ts")),
    ("go", "net/http", ("internal/todos/store.go", "go.mod", "go.sum", "cmd/server/main.go", "internal/todos/handler.go", "internal/todos/handler_test.go")),
])
async def test_incremental_sample_file_sets_use_architect_change_plan(tmp_path, language, framework, paths):
    target = paths[0]
    (tmp_path / target).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / target).write_text("", encoding="utf-8")
    agent = _Agent(tmp_path)
    agent._build_project_summary_from_graph = Mock(return_value="existing project")
    agent._analyze_changes_with_architect = AsyncMock(return_value=[{"path": target, "action": "modify"}])
    adapter = IncrementalAdapter(agent)

    plan = await adapter.create_plan(GenerationRequest(
        requirement=f"Repair the existing {language} {framework} CRUD project",
        task_id="change-task", session_id="change-session",
        metadata={"architecture": {"language": language}, "allowed_files": paths, "dependency_graph": object()},
    ))

    agent._analyze_changes_with_architect.assert_awaited_once()
    assert plan.requested_paths == (target,)
    assert adapter.change_plan.affected_files == (target,)


def test_openapi_specs_project_to_stack_neutral_route_contracts():
    context = type("SpecContext", (), {
        "get_spec": lambda self, name: {
            "paths": {
                "/items": {
                    "get": {"operationId": "list_items"},
                    "post": {"operationId": "create_item"},
                }
            }
        } if name == "openapi" else None,
    })()

    contracts = contracts_from_openapi(context)

    assert contracts == {
        "routes": [
            {"method": "GET", "path": "/items", "operation_id": "list_items"},
            {"method": "POST", "path": "/items", "operation_id": "create_item"},
        ]
    }


@pytest.mark.asyncio
async def test_traditional_adapter_creates_plan_and_generates_file(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build a python app",
        task_id="task-1",
        session_id="session-1",
        metadata={},
    )

    plan = await adapter.create_plan(request)
    generated = await adapter.generate_file(
        type("Context", (), {
            "file_path": "app.py",
            "upstream_contents": {},
        })()
    )

    assert [item.path for item in plan.files] == ["app.py", "config.py"]
    assert generated.content == "# app.py\n"
    assert generated.model_name == "test-model"
    assert adapter.project_plan is not None
    assert adapter.project_plan.language == "python"


@pytest.mark.asyncio
async def test_traditional_adapter_exposes_all_completed_files_to_validation(tmp_path):
    agent = _Agent(tmp_path)
    generated_contexts = {}

    async def generate(file_info, project_context, total_files, generated_contents):
        generated_contexts[file_info["path"]] = dict(generated_contents)
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "test-model"}

    agent._generate_single_file = generate
    adapter = TraditionalAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a python app",
        task_id="task-completed-context",
        session_id="session-completed-context",
        metadata={},
    ))

    await adapter.generate_file(type("Context", (), {
        "file_path": "app.py",
        "upstream_contents": {},
    })())
    await adapter.generate_file(type("Context", (), {
        "file_path": "config.py",
        "upstream_contents": {},
    })())

    assert generated_contexts["config.py"] == {"app.py": "# app.py\n"}


@pytest.mark.asyncio
async def test_traditional_adapter_replaces_stale_architecture_context(tmp_path):
    agent = _Agent(tmp_path)
    captured_context = {}

    async def generate(file_info, project_context, total_files, generated_contents):
        captured_context.update(project_context)
        return {"success": True, "content": "# generated\n", "model": "test-model"}

    agent._generate_single_file = generate
    adapter = TraditionalAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a python app",
        task_id="task-projected-architecture",
        session_id="session-projected-architecture",
        metadata={"architecture": {"file_plan": [{"path": "app.py", "file_type": "backend"}]}},
    ))
    await adapter.generate_file(type("Context", (), {
        "file_path": "app.py",
        "upstream_contents": {},
    })())

    file_entries = {
        item["path"]: item for item in captured_context["architecture"]["file_plan"]
    }
    assert captured_context["architecture"] == adapter._architecture
    assert file_entries["app.py"]["file_type"] != "backend"


@pytest.mark.asyncio
async def test_traditional_adapter_preserves_architect_strict_file_set(tmp_path):
    agent = _Agent(tmp_path)

    async def design_strict_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": ["app.py", "config.py"],
            "file_plan": [
                {"path": "app.py", "description": "application entry point"},
                {"path": "config.py", "description": "configuration", "depends_on": ["app.py"]},
            ],
        }

    agent.architect.design_architecture = design_strict_architecture
    adapter = TraditionalAdapter(agent)

    plan = await adapter.create_plan(GenerationRequest(
        requirement="build exactly app.py and config.py",
        task_id="task-strict",
        session_id="session-strict",
        metadata={},
    ))

    assert plan.policy.value == "strict"
    assert plan.requested_paths == ("app.py", "config.py")
    assert set(agent.dependency_graph_obj.nodes) == {"app.py", "config.py"}


@pytest.mark.asyncio
async def test_traditional_adapter_restores_missing_allowed_files(tmp_path):
    agent = _Agent(tmp_path)

    async def design_incomplete_architecture(requirement, complexity, callback=None):
        return {
            "language": "go",
            "file_plan": [{"path": "main.go", "description": "server"}],
        }

    agent.architect.design_architecture = design_incomplete_architecture
    adapter = TraditionalAdapter(agent)

    plan = await adapter.create_plan(GenerationRequest(
        requirement="build exactly main.go and store.go",
        task_id="task-restore-strict-files",
        session_id="session-restore-strict-files",
        metadata={"allowed_files": ["main.go", "store.go"]},
    ))

    assert plan.policy.value == "strict"
    assert set(plan.requested_paths) == {"main.go", "store.go"}
    assert {item.path for item in plan.files} == {"main.go", "store.go"}


@pytest.mark.asyncio
async def test_traditional_adapter_finalize_preserves_planning_failure(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    state = OrchestrationState(
        task_id="task-planning-failed",
        session_id="session-planning-failed",
        engine_version="core-v1",
        mode="traditional",
        status=OrchestrationStatus.FAILED,
        revision=1,
        terminal_event_id="planning-failed",
        applied_event_ids=("planning-failed",),
        diagnostics=({"code": "planning.failed", "message": "original planning failure"},),
    )

    finalized = await adapter.finalize(state)

    assert finalized.result["errors"] == ["original planning failure"]
    assert finalized.result["total_files"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("file_count", [4, 5, 6, 7])
async def test_traditional_adapter_projects_import_dag_for_any_file_count(
    tmp_path, file_count
):
    agent = _Agent(tmp_path)
    paths = [f"layer_{index}.py" for index in range(file_count)]

    async def design_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": paths,
            "file_plan": [
                {
                    "path": path,
                    "description": f"layer {index}",
                    "imports": [] if index == 0 else [f"layer_{index - 1}"],
                }
                for index, path in enumerate(paths)
            ],
        }

    agent.architect.design_architecture = design_architecture
    plan = await TraditionalAdapter(agent).create_plan(GenerationRequest(
        requirement=f"build exactly {file_count} files",
        task_id=f"task-{file_count}",
        session_id=f"session-{file_count}",
        metadata={},
    ))

    dependencies = {item.path: item.dependencies for item in plan.files}
    assert dependencies[paths[0]] == ()
    for index in range(1, file_count):
        assert paths[index - 1] in dependencies[paths[index]]


@pytest.mark.asyncio
async def test_traditional_adapter_resolves_renamed_imports_within_strict_scope(tmp_path):
    agent = _Agent(tmp_path)

    async def design_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": ["domain.py", "storage.py", "web.py", "tests/test_web.py"],
            "file_plan": [
                {"path": "domain.py", "description": "domain models"},
                {"path": "storage.py", "description": "storage", "imports": ["domain"]},
                {"path": "web.py", "description": "web entry", "imports": ["storage", "domain"]},
                {
                    "path": "tests/test_web.py",
                    "description": "web tests",
                    "imports": ["web"],
                },
            ],
        }

    agent.architect.design_architecture = design_architecture
    adapter = TraditionalAdapter(agent)
    plan = await adapter.create_plan(GenerationRequest(
        requirement="build exactly the renamed files",
        task_id="task-renamed",
        session_id="session-renamed",
        metadata={},
    ))

    dependencies = {item.path: set(item.dependencies) for item in plan.files}
    assert dependencies["storage.py"] == {"domain.py"}
    assert dependencies["web.py"].issuperset({"domain.py", "storage.py"})
    assert "web.py" in dependencies["tests/test_web.py"]
    assert {
        dependency
        for item in plan.files
        for dependency in item.dependencies
    }.issubset(set(plan.requested_paths))
    assert {
        item.path: item.dependencies for item in adapter.project_plan.files
    } == {
        item.path: item.dependencies for item in plan.files
    }


@pytest.mark.asyncio
async def test_traditional_adapter_projects_profile_components_into_extensible_plan(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build a game",
        task_id="task-2",
        session_id="session-2",
        metadata={"profile_context": {"capability_policy": {"component_file_plan": [
            {"path": "game/rules.py", "component": "rules"},
            {"path": "game/renderer.py", "component": "renderer"},
        ]}}},
    )

    plan = await adapter.create_plan(request)

    assert "game/rules.py" in {item.path for item in plan.files}
    renderer = next(item for item in adapter.project_plan.files if item.path == "game/renderer.py")
    assert renderer.dependencies == ("game/rules.py",)


def test_engine_selection_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATION_ENGINE", raising=False)
    assert select_engine() == LEGACY_ENGINE
    assert select_engine(CORE_ENGINE) == CORE_ENGINE
    assert engine_metadata(CORE_ENGINE)["engine_version"] == "core-v1"


@pytest.mark.asyncio
async def test_legacy_workflow_checkpoint_contains_selected_engine(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", "core")
    workflow = build_legacy_workflow("test", "/test", lambda state: {"success": True})

    state = await run_workflow(
        workflow,
        session_id="session-adapter-test",
        task_id="task-adapter-test",
    )

    assert state.metadata["engine"] == CORE_ENGINE
    assert state.metadata["engine_version"] == "core-v1"
    assert state.metadata["engine_route"] == "experimental"


@pytest.mark.asyncio
async def test_traditional_adapter_requires_plan(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    context = type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()

    with pytest.raises(RuntimeError, match="create_plan"):
        await adapter.generate_file(context)


@pytest.mark.asyncio
async def test_spec_first_adapter_freezes_supplied_specification_plan(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build from a specification",
        task_id="task-spec",
        session_id="session-spec",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "models"},
                    {"path": "app.py", "description": "entry", "depends_on": ["models.py"]},
                ],
            }
        },
    )

    plan = await adapter.create_plan(request)
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "models.py", "upstream_contents": {}})()
    )

    assert plan.policy.value == "strict"
    assert set(plan.requested_paths) == {"app.py", "models.py"}
    assert adapter.project_plan is not None
    assert adapter.project_plan.policy == "strict"
    assert generated.content == "# models.py\n"


@pytest.mark.asyncio
async def test_spec_first_adapter_projects_dependency_graph_into_plan(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build from a specification",
        task_id="task-spec-dependencies",
        session_id="session-spec-dependencies",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "models", "imports": []},
                    {
                        "path": "app.py",
                        "description": "entry",
                        "imports": ["models"],
                    },
                ],
            }
        },
    )

    plan = await adapter.create_plan(request)

    app_file = next(item for item in plan.files if item.path == "app.py")
    assert app_file.dependencies == ("models.py",)
    assert (tmp_path / ".dep_graph.json").is_file()


@pytest.mark.asyncio
async def test_planned_adapter_leaves_persistence_to_core_committer(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build an app",
        task_id="task-core-write",
        session_id="session-core-write",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    ))

    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()
    )

    assert generated.content == "# app.py\n"
    assert agent.persist_requested is False
    assert agent.generation_contract["frozen_file_set"] == ["app.py"]
    assert agent.generation_contract["target_file"] == "app.py"
    assert agent.project_context["retrieval_status"]["enabled"] is True
    assert agent.project_context["retrieval_status"]["source_count"] == 3
    assert not (tmp_path / "app.py").exists()


@pytest.mark.asyncio
async def test_planned_adapter_rejects_local_import_outside_frozen_set(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build an app",
        task_id="task-core-import-contract",
        session_id="session-core-import-contract",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    ))

    agent._generate_file_with_model = lambda *args, **kwargs: None

    async def generate_invalid(*args, **kwargs):
        return "from app.database import get_session\n"

    agent._generate_file_with_model = generate_invalid
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is False
    assert "outside frozen file set" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_planned_adapter_rejects_orm_schema_inheritance(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a FastAPI CRUD app",
        task_id="task-schema-contract",
        session_id="session-schema-contract",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "SQLAlchemy models"},
                    {
                        "path": "schemas.py",
                        "description": "Pydantic schemas",
                        "depends_on": ["models.py"],
                        "contract": {
                            "schema_version": 1,
                            "assertions": [{
                                "fact": "base_classes",
                                "operator": "excludes_all",
                                "expected": ["Todo"],
                            }],
                        },
                    },
                ],
            }
        },
    ))

    async def generate_model(*args, **kwargs):
        return "class Base: pass\nclass Todo(Base): pass\n"

    async def generate_schema(*args, **kwargs):
        return "from pydantic import BaseModel\nfrom models import Todo\nclass TodoResponse(Todo): pass\n"

    agent._generate_file_with_model = generate_model
    await adapter.generate_file(type("Context", (), {"file_path": "models.py", "upstream_contents": {}})())
    agent._generate_file_with_model = generate_schema
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "schemas.py", "upstream_contents": {"models.py": "class Base: pass\nclass Todo(Base): pass\n"}})()
    )

    assert generated.validation_passed is False
    assert "contract assertion failed for base_classes" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_planned_adapter_enforces_fastapi_entrypoint_contract(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a FastAPI app",
        task_id="task-fastapi-entrypoint",
        session_id="session-fastapi-entrypoint",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{
                    "path": "main.py",
                    "description": "FastAPI entrypoint",
                    "contract": {
                        "schema_version": 1,
                        "assertions": [{
                            "fact": "symbols",
                            "operator": "contains_all",
                            "expected": ["app"],
                        }],
                    },
                }],
            }
        },
    ))

    async def generate_main(*args, **kwargs):
        return "from fastapi import APIRouter\nrouter = APIRouter()\n"

    agent._generate_file_with_model = generate_main
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "main.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is False
    assert "contract assertion failed for symbols" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_planned_adapter_revalidates_language_repair_with_same_gate(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build typed contracts",
        task_id="task-language-repair-gate",
        session_id="session-language-repair-gate",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{
                    "path": "pkg/contracts.py",
                    "description": "typed contracts",
                    "contract": {
                        "schema_version": 1,
                        "assertions": [{
                            "fact": "symbols",
                            "operator": "contains_all",
                            "expected": ["Envelope", "Payload"],
                        }],
                    },
                }],
            }
        },
    ))

    async def generate_contracts(*args, **kwargs):
        return (
            "from pydantic import BaseModel\n"
            "class Envelope(BaseModel):\n"
            "    payload: Payload\n"
            "class Payload(BaseModel):\n"
            "    value: str\n"
        )

    agent._generate_file_with_model = generate_contracts
    gate_inputs = []
    validate = adapter._validate_candidate_contract

    def track_gate(file_path, content):
        gate_inputs.append(content)
        return validate(file_path, content)

    adapter._validate_candidate_contract = track_gate
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "pkg/contracts.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is True
    assert len(gate_inputs) == 2
    assert not gate_inputs[0].startswith("from __future__ import annotations")
    assert gate_inputs[1].startswith("from __future__ import annotations")
    assert generated.content == gate_inputs[1]
    assert adapter._repair_evidence[0]["strategy"] == "language-source-repair"


@pytest.mark.asyncio
async def test_fastapi_entrypoint_contract_uses_artifact_shape_not_filename(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a FastAPI app",
        task_id="task-fastapi-dynamic-entrypoint",
        session_id="session-fastapi-dynamic-entrypoint",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{
                    "path": "src/server.py",
                    "role": "entry",
                    "description": "API entrypoint",
                    "contract": {
                        "schema_version": 1,
                        "assertions": [{
                            "fact": "symbols",
                            "operator": "contains_all",
                            "expected": ["application"],
                        }],
                    },
                }],
            }
        },
    ))

    async def generate_server(*args, **kwargs):
        return "from fastapi import APIRouter\nrouter = APIRouter()\n"

    agent._generate_file_with_model = generate_server
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "src/server.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is False
    assert "contract assertion failed for symbols" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_incremental_adapter_freezes_affected_files_and_preserves_existing_files(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "unchanged.py").write_text("UNCHANGED = True\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing behavior",
        task_id="task-incremental",
        session_id="session-incremental",
        metadata={
            "dependency_graph": object(),
            "change_plan": [
                {
                    "path": "existing.py",
                    "action": "modify",
                    "description": "update value",
                    "depends_on": ["unchanged.py"],
                }
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.policy.value == "strict"
    assert plan.requested_paths == ("existing.py",)
    assert plan.files[0].dependencies == ()
    assert adapter.preserved_paths == ("unchanged.py",)
    assert adapter._file_entries["existing.py"]["original_content"] == "VALUE = 1\n"


@pytest.mark.asyncio
async def test_incremental_adapter_normalizes_model_priority(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing behavior",
        task_id="task-incremental-priority",
        session_id="session-incremental-priority",
        metadata={
            "dependency_graph": object(),
            "change_plan": [{
                "path": "existing.py",
                "action": "modify",
                "description": "update value",
                "priority": 6,
            }],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.files[0].priority == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", [TraditionalAdapter, SpecFirstAdapter, IncrementalAdapter])
@pytest.mark.parametrize("previous_diagnostics", [(), ("JSON body is not serializable",)])
async def test_adapters_preserve_explicit_project_context(tmp_path, adapter_type, previous_diagnostics):
    from app.api.v1.ai_agent.schemas import OrchestratorRequest
    from app.api.v1.ai_agent.orchestrate_endpoints import _core_request_metadata

    (tmp_path / "inventory.py").write_text("VALUE = 1\n", encoding="utf-8")
    request = OrchestratorRequest(
        requirement="update python inventory module",
        contracts={"routes": [{
            "method": "PATCH", "path": "/inventory",
            "request_body_schema": {"type": "object", "properties": {"quantity": {"type": "integer"}}},
            "response_body_schema": {"type": "object"},
            "serialization_guidance": "Use the installed model library's JSON serializer before client json=.",
        }]},
        framework="flask",
        runtime="python3.12",
        allowed_files=["inventory.py"],
        change_plan=[{"path": "inventory.py", "action": "modify"}],
    )
    metadata = _core_request_metadata(request)
    metadata["dependency_graph"] = object()
    agent = _Agent(tmp_path)
    agent._generate_single_file = AsyncMock(return_value={"success": True, "content": "VALUE = 1\n"})
    adapter = adapter_type(agent)
    await adapter.create_plan(GenerationRequest(
        requirement=request.requirement, task_id="context-task",
        session_id="context-session", metadata=metadata,
    ))

    assert adapter.project_plan.framework == "flask"
    assert adapter.project_plan.runtime == "python3.12"
    assert adapter._project_context["contracts"] == request.contracts
    assert adapter._project_context["architecture"]["contracts"] == request.contracts
    http_contracts = tuple(entry for entry in adapter.contract_index.entries if entry.kind == "api")
    cross_file_contracts = tuple(
        entry for entry in adapter.contract_index.entries if entry.kind != "api"
    )
    await adapter.generate_file(SimpleNamespace(
        file_path="inventory.py", upstream_contents={},
        contract_index=adapter.contract_index, previous_diagnostics=previous_diagnostics,
        http_contracts=http_contracts,
        cross_file_contracts=cross_file_contracts,
        test_generation_contract=TestGenerationContract(),
    ))
    passed_context = agent._generate_single_file.call_args.args[1]
    http_entry = next(entry for entry in passed_context["contract_index"]["entries"]
                      if entry["kind"] == "api")
    assert http_entry["schema"] == request.contracts["routes"][0]
    generation_contract = passed_context["generation_contract"]
    assert generation_contract["contract_index"] == passed_context["contract_index"]
    assert generation_contract["http_contracts"][0]["schema"] == request.contracts["routes"][0]
    assert generation_contract["cross_file_contracts"] == [
        entry.model_dump(mode="json") for entry in cross_file_contracts
    ]
    assert generation_contract["test_generation_contract"] == {
        "discovery": "declared_test_files",
        "execution": "profile_command",
        "dependencies": "declared_contracts",
        "serialization": "framework_defined",
        "stack_rules": {},
    }
    if adapter_type is not TraditionalAdapter:
        if previous_diagnostics:
            assert generation_contract["retry_feedback"] == list(previous_diagnostics)


@pytest.mark.asyncio
async def test_incremental_context_merges_architecture_without_mutating_source(tmp_path):
    (tmp_path / "inventory.py").write_text("VALUE = 1\n", encoding="utf-8")
    architecture = {
        "language": "python", "framework": "flask", "runtime": "python3.11",
        "contracts": {"routes": [{"method": "GET", "path": "/inventory"}]},
        "domain": "inventory", "file_plan": [{"path": "old.py"}],
    }
    adapter = IncrementalAdapter(_Agent(tmp_path))
    await adapter.create_plan(GenerationRequest(
        requirement="update inventory", task_id="merge-task", session_id="merge-session",
        metadata={
            "architecture": architecture, "runtime": "python3.12",
            "dependency_graph": object(),
            "change_plan": [{"path": "inventory.py", "action": "modify"}],
        },
    ))

    assert adapter.project_plan.framework == "flask"
    assert adapter.project_plan.runtime == "python3.12"
    assert adapter._project_context["contracts"] == architecture["contracts"]
    assert adapter._project_context["architecture"]["domain"] == "inventory"
    assert adapter._project_context["architecture"]["file_plan"][0]["path"] == "inventory.py"
    assert architecture["file_plan"] == [{"path": "old.py"}]
    assert architecture["runtime"] == "python3.11"


@pytest.mark.asyncio
async def test_incremental_adapter_filters_changes_outside_allowed_files(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="repair existing behavior",
        task_id="task-incremental-allowed-files",
        session_id="session-incremental-allowed-files",
        metadata={
            "dependency_graph": object(),
            "allowed_files": ["existing.py"],
            "change_plan": [
                {"path": "existing.py", "action": "modify", "description": "repair value"},
                {"path": "invented.py", "action": "add", "description": "scope drift"},
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.requested_paths == ("existing.py",)


@pytest.mark.asyncio
async def test_incremental_adapter_prefers_explicit_add_actions_over_stack_repair_plan(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/models.py").write_text("class Todo:\n    pass\n", encoding="utf-8")
    required_files = [
        "app/models.py",
        "app/schemas.py",
        "app/crud.py",
        "app/main.py",
        "tests/test_crud.py",
    ]
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="Repair the existing python fastapi CRUD project.",
        task_id="task-incremental-explicit-actions",
        session_id="session-incremental-explicit-actions",
        metadata={
            "dependency_graph": object(),
            "allowed_files": required_files,
            "change_plan": [
                {
                    "path": path,
                    "action": "modify" if path == "app/models.py" else "add",
                }
                for path in required_files
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert set(plan.requested_paths) == set(required_files)
    assert adapter.change_plan is not None
    actions = {change.path: change.action.value for change in adapter.change_plan.changes}
    assert actions == {
        "app/models.py": "modify",
        "app/schemas.py": "add",
        "app/crud.py": "add",
        "app/main.py": "add",
        "tests/test_crud.py": "add",
    }


@pytest.mark.asyncio
async def test_incremental_adapter_rebuilds_missing_dependency_graph(tmp_path):
    (tmp_path / "existing.py").write_text("from unchanged import VALUE\n", encoding="utf-8")
    (tmp_path / "unchanged.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing Python behavior",
        task_id="task-incremental-rebuild",
        session_id="session-incremental-rebuild",
        metadata={
            "change_plan": [
                {
                    "path": "existing.py",
                    "action": "modify",
                    "description": "update behavior",
                }
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.requested_paths == ("existing.py",)
    assert adapter._dependency_graph is not None
    assert set(adapter._dependency_graph.nodes) == {"existing.py", "unchanged.py"}
    assert (tmp_path / ".dep_graph.json").is_file()
    assert adapter._file_entries["existing.py"]["original_content"] == "from unchanged import VALUE\n"
    assert adapter.preserved_paths == ("unchanged.py",)


@pytest.mark.asyncio
async def test_incremental_adapter_supports_delete_only_plans(tmp_path):
    (tmp_path / "obsolete.py").write_text("legacy\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="remove obsolete file",
        task_id="task-delete",
        session_id="session-delete",
        metadata={
            "change_plan": [{"path": "obsolete.py", "action": "delete"}],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.files == ()
    assert adapter.change_plan is not None


@pytest.mark.asyncio
async def test_incremental_contract_allows_only_existing_authorized_snapshot_dependencies(tmp_path):
    (tmp_path / "app").mkdir()
    for name in ("main", "models", "unauthorized"):
        (tmp_path / f"app/{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    await adapter.create_plan(GenerationRequest(
        requirement="update Python module", task_id="snapshot-task", session_id="snapshot-session",
        metadata={
            "architecture": {"language": "python"},
            "dependency_graph": object(),
            "allowed_files": ["app/main.py", "app/models.py", "app/missing.py", "app/late.py"],
            "change_plan": [{"path": "app/main.py", "action": "modify"}],
        },
    ))
    assert adapter.preserved_paths == ("app/models.py",)
    assert not adapter._validate_candidate_contract("app/main.py", "from app.models import VALUE\n")[1]
    assert "does not export" in ";".join(adapter._validate_candidate_contract(
        "app/main.py", "from app.models import UNKNOWN\n",
    )[1])
    (tmp_path / "app/late.py").write_text("VALUE = 1\n", encoding="utf-8")
    for module in ("unauthorized", "missing", "late"):
        assert "outside frozen file set" in ";".join(adapter._validate_candidate_contract(
            "app/main.py", f"from app.{module} import VALUE\n",
        )[1])
    (tmp_path / "app/models.py").rename(tmp_path / "models.saved")
    assert "outside frozen file set" in ";".join(adapter._validate_candidate_contract(
        "app/main.py", "from app.models import VALUE\n",
    )[1])


@pytest.mark.asyncio
async def test_core_executes_delete_only_change_transaction(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    obsolete = output_dir / "obsolete.py"
    obsolete.write_text("legacy\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(output_dir))

    result = await execute_core_generation(
        adapter,
        requirement="remove obsolete file",
        task_id="task-delete-only",
        session_id="session-delete-only",
        mode="incremental",
        output_dir=output_dir,
        metadata={
            "change_plan": [{"path": "obsolete.py", "action": "delete"}],
        },
    )

    assert result["success"], result
    assert not obsolete.exists()


@pytest.mark.asyncio
async def test_core_runtime_projects_spec_first_result_to_existing_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    adapter = SpecFirstAdapter(_Agent(output_dir))

    result = await execute_core_generation(
        adapter,
        requirement="build from a specification",
        task_id="task-runtime",
        session_id="session-runtime",
        mode="spec_first",
        output_dir=output_dir,
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    )

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert result["validation"] == {"runnable": True, "status": "completed"}
    assert result["generation_metrics"] == {
        "node_attempts": {"app.py": 1},
        "schedule_status": "completed",
    }
    assert (output_dir / "app.py").read_text(encoding="utf-8") == "# app.py\n"


@pytest.mark.asyncio
async def test_core_runtime_preserves_file_validation_root_cause(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    adapter = SpecFirstAdapter(_Agent(output_dir))

    result = await execute_core_generation(
        adapter,
        requirement="build a FastAPI application",
        task_id="task-runtime-diagnostic",
        session_id="session-runtime-diagnostic",
        mode="spec_first",
        output_dir=output_dir,
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{
                    "path": "app.py",
                    "description": "application entry point",
                    "contract": {
                        "schema_version": 1,
                        "assertions": [{
                            "fact": "symbols",
                            "operator": "contains_all",
                            "expected": ["application"],
                            "reference": "runtime-entry-contract",
                        }],
                    },
                }],
            }
        },
    )

    assert result["success"] is False
    assert any("app.py: contract assertion failed for symbols" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_spec_first_adapter_freezes_plan_to_allowed_files(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="generate an application",
        task_id="task-allowed",
        session_id="session-allowed",
        metadata={
            "allowed_files": ["app.py"],
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "app.py", "description": "entry"},
                    {"path": "README.md", "description": "documentation"},
                ],
            },
        },
    )

    plan = await adapter.create_plan(request)

    assert [item.path for item in plan.files] == ["app.py"]


@pytest.mark.asyncio
async def test_spec_first_allowed_file_plan_preserves_business_requirement(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    requirement = "Build a CLI task tracker with TaskList.add and TaskList.complete"
    request = GenerationRequest(
        requirement=requirement,
        task_id="task-business-context",
        session_id="session-business-context",
        metadata={"allowed_files": ["main.py"]},
    )

    plan = await adapter.create_plan(request)

    assert requirement in adapter._file_entries["main.py"]["description"]


def test_allowed_file_plan_infers_cross_stack_generation_layers():
    paths = (
        "pom.xml",
        "src/main/java/com/example/Todo.java",
        "src/main/java/com/example/TodoRepository.java",
        "src/main/java/com/example/TodoService.java",
        "src/main/java/com/example/TodoController.java",
        "src/main/java/com/example/Application.java",
        "src/test/java/com/example/TodoControllerTest.java",
    )

    entries = SpecFirstAdapter._build_allowed_file_plan(paths)
    dependencies = {entry["path"]: entry["dependencies"] for entry in entries}

    assert dependencies["src/main/java/com/example/Todo.java"] == ["pom.xml"]
    assert dependencies["src/main/java/com/example/TodoRepository.java"] == [
        "pom.xml",
        "src/main/java/com/example/Todo.java",
    ]
    assert dependencies["src/main/java/com/example/TodoService.java"] == [
        "pom.xml",
        "src/main/java/com/example/Todo.java",
        "src/main/java/com/example/TodoRepository.java",
    ]
    assert "src/main/java/com/example/TodoService.java" in dependencies[
        "src/main/java/com/example/TodoController.java"
    ]
    assert "src/main/java/com/example/TodoController.java" in dependencies[
        "src/main/java/com/example/Application.java"
    ]
    assert dependencies["src/test/java/com/example/TodoControllerTest.java"] == list(paths[:-1])


@pytest.mark.asyncio
async def test_spec_first_adapter_adds_missing_allowed_files(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="generate an application",
        task_id="task-missing-allowed",
        session_id="session-missing-allowed",
        metadata={
            "allowed_files": ["app.py", "game/rules.py"],
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            },
        },
    )

    plan = await adapter.create_plan(request)

    assert [item.path for item in plan.files] == ["app.py", "game/rules.py"]


def test_change_plan_tracks_dynamic_incremental_files(tmp_path):
    from app.agent.change_plan import ChangeAction, ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    (tmp_path / "main.py").write_text("print('old')\n", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [
        {"path": "main.py", "action": "modify", "reason": "pause support"},
        {"path": "game/leaderboard.py", "action": "add", "reason": "score history"},
        {"path": "ui.py", "action": "rename", "previous_path": "main.py"},
    ])

    assert plan.base_revision == "r1"
    assert plan.affected_files == ("game/leaderboard.py", "main.py", "ui.py")
    assert plan.changes[1].action is ChangeAction.ADD

    (tmp_path / "unrelated.py").write_text("changed\n", encoding="utf-8")
    current = ProjectSnapshot.scan(tmp_path, revision="r2")
    assert plan.verify_untouched(snapshot, current) == ("unrelated.py",)


def test_incremental_file_transaction_rolls_back_rename(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration.file_transaction import IncrementalFileTransaction
    from app.agent.project_snapshot import ProjectSnapshot

    old = tmp_path / "old.py"
    old.write_text("content", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [{
        "path": "new.py", "action": "rename", "previous_path": "old.py",
    }])
    transaction = IncrementalFileTransaction(tmp_path, plan, transaction_id="test")
    transaction.stage()
    assert not old.exists()
    transaction.rollback()
    assert old.read_text(encoding="utf-8") == "content"


def test_incremental_file_transaction_commits_delete(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration.file_transaction import IncrementalFileTransaction
    from app.agent.project_snapshot import ProjectSnapshot

    obsolete = tmp_path / "obsolete.py"
    obsolete.write_text("legacy", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [{"path": "obsolete.py", "action": "delete"}])
    transaction = IncrementalFileTransaction(tmp_path, plan, transaction_id="delete-test")
    transaction.stage()
    transaction.commit()
    assert not obsolete.exists()


def test_incremental_file_transaction_rolls_back_modify_and_add(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration.file_transaction import IncrementalFileTransaction
    from app.agent.project_snapshot import ProjectSnapshot

    existing = tmp_path / "existing.py"
    added = tmp_path / "added.py"
    existing.write_text("VALUE = 1\n", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [
        {"path": "existing.py", "action": "modify"},
        {"path": "added.py", "action": "add"},
    ])
    transaction = IncrementalFileTransaction(tmp_path, plan, transaction_id="mixed-test")

    transaction.stage()
    existing.write_text("VALUE = 2\n", encoding="utf-8")
    added.write_text("ADDED = True\n", encoding="utf-8")
    transaction.rollback()

    assert existing.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not added.exists()


@pytest.mark.asyncio
async def test_core_rolls_back_all_incremental_files_after_partial_schedule_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    (output_dir / "first.py").write_text("FIRST = 'old'\n", encoding="utf-8")
    (output_dir / "last.py").write_text("LAST = 'old'\n", encoding="utf-8")
    agent = _CoreFileAgent(output_dir)

    async def generate_file(file_path, *args, **kwargs):
        if file_path == "last.py":
            return ""
        return f"# generated {file_path}\n"

    agent._generate_file_with_model = generate_file
    result = await execute_core_generation(
        IncrementalAdapter(agent),
        requirement="update the declared files",
        task_id="task-incremental-partial-failure",
        session_id="session-incremental-partial-failure",
        mode="incremental",
        output_dir=output_dir,
        metadata={
            "dependency_graph": {},
            "change_plan": [
                {"path": "first.py", "action": "modify"},
                {"path": "added.py", "action": "add", "dependencies": ["first.py"]},
                {"path": "last.py", "action": "modify", "dependencies": ["added.py"]},
            ],
        },
    )

    assert result["success"] is False
    assert (output_dir / "first.py").read_text(encoding="utf-8") == "FIRST = 'old'\n"
    assert (output_dir / "last.py").read_text(encoding="utf-8") == "LAST = 'old'\n"
    assert not (output_dir / "added.py").exists()


@pytest.mark.asyncio
async def test_core_runtime_preserves_unaffected_incremental_artifacts(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    (output_dir / "changed.py").write_text("VALUE = 1\n", encoding="utf-8")
    (output_dir / "unchanged.py").write_text("UNCHANGED = True\n", encoding="utf-8")
    graph = type("Graph", (), {"adjacency": {"changed.py": {"unchanged.py"}}})()
    monkeypatch.setattr(DependencyGraph, "load", lambda *args, **kwargs: graph)

    result = await execute_core_generation(
        IncrementalAdapter(_CoreFileAgent(output_dir)),
        requirement="change existing behavior",
        task_id="task-incremental-runtime",
        session_id="session-incremental-runtime",
        mode="incremental",
        output_dir=output_dir,
        metadata={
            "change_plan": [
                {"path": "changed.py", "action": "modify", "description": "update value"}
            ]
        },
    )

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert (output_dir / "changed.py").read_text(encoding="utf-8") == "# changed.py\n"
    assert (output_dir / "unchanged.py").read_text(encoding="utf-8") == "UNCHANGED = True\n"


@pytest.mark.asyncio
async def test_runtime_feedback_survives_transaction_rollback_and_checkpoint(tmp_path, monkeypatch):
    import hashlib
    import json
    from app.api.v1.ai_agent.schemas import OrchestratorResponse

    checkpoints = tmp_path / "checkpoints"
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(checkpoints))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    (output_dir / "changed.py").write_text("OLD = True\n", encoding="utf-8")
    (output_dir / "stable.py").write_text("STABLE = True\n", encoding="utf-8")
    result = await execute_core_generation(
        IncrementalAdapter(_CoreFileAgent(output_dir)),
        requirement="repair changed behavior", task_id="runtime-rollback", session_id="session",
        mode="incremental", output_dir=output_dir,
        metadata={"dependency_graph": {}, "allowed_files": ["changed.py", "stable.py"],
                  "change_plan": [{"path": "changed.py", "action": "modify"}]},
    )
    assert result["success"] is True
    assert (output_dir / "changed.py").read_text() == "# changed.py\n"
    feedback = OrchestratorResponse.model_validate(result).repair_feedback
    assert feedback["rolled_back"] is False
    assert feedback["diagnostics"] == []
    checkpoint = json.loads(next(checkpoints.glob("*.json")).read_text())["state"]
    assert checkpoint["metadata"]["candidate_validation"]["status"] == "waiting_local_validation"
    hashes = checkpoint["metadata"]["candidate_hashes"]
    assert set(hashes) == {"changed.py", "stable.py"}
    assert hashes["changed.py"] == hashlib.sha256(b"# changed.py\n").hexdigest()
    assert feedback["candidate_fingerprint"] == hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
