"""Tests for project-level generation contracts."""

import pytest
from app.agent.dependency_manifest import DependencyKind, DependencyManifest
from app.agent.generation_plan import GenerationPlan, add_profile_components
from app.agent.interface_registry import InterfaceRegistry
from app.agent.toolchain import detect_toolchain
from app.agent.validation_coordinator import ValidationCoordinator, ValidationResult
from app.agent.toolchain import CommandSpec, ToolchainAction
from app.agent.validation_coordinator import ValidationPlan
from app.agent.signature_extractor import extract_signatures
from app.agent.backend_engineer import BackendEngineer


def test_generation_plan_freezes_strict_scope_and_dependency_closure() -> None:
    plan = GenerationPlan.build(
        [{"path": r"src\service.py", "depends_on": ["src/model.py"]}, {"path": "src/model.py"}],
        requested_paths=["./src/service.py", "src/model.py"],
        policy="strict",
        language="python",
    )

    assert plan.requested_paths == ("src/model.py", "src/service.py")
    assert plan.files[1].dependencies == ("src/model.py",)
    assert GenerationPlan.model_validate_json(plan.model_dump_json()) == plan
    payload = plan.model_dump(mode="json")
    payload["digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        GenerationPlan.model_validate(payload)


def test_generation_plan_rejects_missing_dependency_and_unsafe_path() -> None:
    with pytest.raises(ValueError, match="missing file dependencies"):
        GenerationPlan.build([{"path": "main.go", "dependencies": ["missing.go"]}])
    with pytest.raises(ValueError, match="traversal"):
        GenerationPlan.build([{"path": "../main.go"}])
    with pytest.raises(ValueError, match="cycle"):
        GenerationPlan.build([
            {"path": "a.py", "dependencies": ["b.py"]},
            {"path": "b.py", "dependencies": ["a.py"]},
        ])


def test_profile_components_extend_only_extensible_plans() -> None:
    context = {"capability_policy": {"component_file_plan": [
        {"path": "game/rules.py", "component": "rules"},
        {"path": "game/renderer.py", "component": "renderer"},
    ]}}
    plan = add_profile_components([{"path": "main.py"}], context, language="python")

    assert [item.path for item in plan.files] == ["game/renderer.py", "game/rules.py", "main.py"]
    assert plan.files[0].dependencies == ("game/rules.py",)


def test_profile_components_preserve_strict_file_scope() -> None:
    context = {"capability_policy": {"component_file_plan": [{"path": "game/rules.py", "component": "rules"}]}}
    plan = add_profile_components(
        [{"path": "main.py"}], context, policy="strict", requested_paths=["main.py"], language="python"
    )

    assert tuple(item.path for item in plan.files) == ("main.py",)


def test_incremental_component_change_can_carry_projected_dependencies() -> None:
    context = {"capability_policy": {"component_file_plan": [
        {"path": "game/rules.py", "component": "rules"},
        {"path": "game/renderer.py", "component": "renderer"},
    ]}}
    plan = add_profile_components([{"path": "main.py"}], context, language="python")
    renderer = next(item for item in plan.files if item.path == "game/renderer.py")

    assert list(renderer.dependencies) == ["game/rules.py"]


def test_interface_registry_rejects_duplicate_public_owner() -> None:
    with pytest.raises(ValueError, match="multiple owners"):
        InterfaceRegistry.build([
            {"module": "a.py", "owner": "a.py", "exports": ["Todo"]},
            {"module": "b.py", "owner": "b.py", "exports": ["Todo"]},
        ])


def test_dependency_manifest_rejects_forbidden_and_duplicate_dependencies() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        DependencyManifest.build([{"name": "unsafe-package", "kind": DependencyKind.FORBIDDEN}])
    with pytest.raises(ValueError, match="more than once"):
        DependencyManifest.build([{"name": "pytest", "kind": "test"}, {"name": "pytest", "kind": "test"}])


def test_architecture_conversion_preserves_language_profile_and_runtime() -> None:
    plan = GenerationPlan.from_architecture({
        "project_spec": {"language": "go", "framework": "chi", "runtime": "go1.23"},
        "file_plan": [{"path": "cmd/api/main.go"}],
    })
    assert (plan.language, plan.framework, plan.runtime) == ("go", "chi", "go1.23")


def test_architecture_conversion_preserves_strict_file_scope() -> None:
    paths = ["pom.xml", "src/main/java/com/example/Application.java"]
    plan = GenerationPlan.from_architecture({
        "language": "java",
        "file_plan": [{"path": path} for path in paths],
        "strict_file_paths": paths,
    })

    projected = add_profile_components(
        plan.files,
        {"capability_policy": {"component_file_plan": [{"path": "app/command.py"}]}},
        policy=plan.policy,
        requested_paths=plan.requested_paths,
        language=plan.language,
    )

    assert plan.policy == "strict"
    assert set(plan.requested_paths) == set(paths)
    assert {item.path for item in projected.files} == set(paths)


def test_architecture_conversion_normalizes_legacy_dependency_groups() -> None:
    plan = GenerationPlan.from_architecture({
        "file_plan": [{"path": "pom.xml"}],
        "dependencies": {
            "runtime": ["org.springframework.boot:spring-boot-starter-web"],
            "backend": ["org.xerial:sqlite-jdbc"],
        },
    })

    assert plan.dependencies.names() == (
        "org.springframework.boot:spring-boot-starter-web",
        "org.xerial:sqlite-jdbc",
    )


def test_architecture_conversion_normalizes_package_version_map() -> None:
    plan = GenerationPlan.from_architecture({
        "file_plan": [{"path": "pom.xml"}],
        "dependencies": {
            "spring-boot-starter-web": "^3.3.5",
            "spring-boot-starter-data-jpa": "^3.3.5",
        },
    })

    assert plan.dependencies.names() == (
        "spring-boot-starter-data-jpa",
        "spring-boot-starter-web",
    )
    assert {item.version for item in plan.dependencies.dependencies} == {"^3.3.5"}


def test_validation_coordinator_projects_profile_steps_to_safe_commands(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    profile = {"capability_policy": {"validation_steps": ["syntax", "tests", "headless_startup"]}}

    validation = ValidationCoordinator().build_plan(profile, detect_toolchain(tmp_path))

    assert [command.command for command in validation.commands] == [
        ("python3", "-m", "compileall", "-q", "."),
        ("python3", "-m", "pytest"),
    ]
    assert validation.unsupported_steps == ("headless_startup",)


@pytest.mark.asyncio
async def test_validation_coordinator_executes_without_shell(tmp_path) -> None:
    plan = ValidationPlan((CommandSpec(
        action=ToolchainAction.TEST,
        command=("python3", "-c", "print('ok')"),
        timeout_seconds=5,
    ),), ())

    results = await ValidationCoordinator().execute(plan, tmp_path)

    assert results[0].passed
    assert results[0].stdout.strip() == "ok"


def test_validation_coordinator_maps_failures_to_report() -> None:
    plan = ValidationPlan((), ("headless_startup",))
    report = ValidationCoordinator().to_report(
        plan, (), context_hash="a" * 64
    )

    assert not report.passed
    assert report.source == "toolchain"
    assert report.findings[0].scope == "local_runtime"


@pytest.mark.parametrize(
    ("action", "category"),
    [
        (ToolchainAction.INSTALL, "dependency"),
        (ToolchainAction.LINT, "type"),
        (ToolchainAction.TYPECHECK, "type"),
        (ToolchainAction.BUILD, "framework"),
        (ToolchainAction.TEST, "test"),
        (ToolchainAction.SMOKE, "framework"),
    ],
)
def test_validation_coordinator_preserves_stage_failure_category(action, category) -> None:
    command = CommandSpec(action=action, command=("python3", "-c", "pass"))
    plan = ValidationPlan((command,), ())
    result = ValidationResult(command, 1, "", "failed")

    report = ValidationCoordinator().to_report(plan, (result,), context_hash="a" * 64)

    assert report.findings[0].category.value == category


def test_plan_projection_preserves_scheduler_metadata_and_imports() -> None:
    plan = GenerationPlan.build([{
        "path": "src/main.ts",
        "file_type": "entry",
        "priority": 1,
        "imports": ["src/config.ts"],
        "contract": {"exports": ["main"]},
    }, {"path": "src/config.ts"}])
    item = next(item for item in plan.files if item.path == "src/main.ts")
    assert (item.file_type, item.priority, item.imports) == ("entry", 1, ("src/config.ts",))
    assert item.contract == {"exports": ["main"]}
    assert plan.file_entries()[1]["dependencies"] == []


def test_generation_plan_normalizes_model_priority() -> None:
    plan = GenerationPlan.build([
        {"path": "low.py", "priority": 0},
        {"path": "high.py", "priority": 6},
        {"path": "default.py", "priority": "unexpected"},
    ])

    priorities = {item.path: item.priority for item in plan.files}
    assert priorities == {"default.py": 3, "high.py": 5, "low.py": 1}


def test_python_signature_extraction_preserves_return_types_and_fields() -> None:
    signatures = extract_signatures("todo.py", """
from dataclasses import dataclass

@dataclass
class Todo:
    id: int
    title: str

def list_todos() -> list[Todo]:
    return []
""")

    assert signatures is not None
    assert "class Todo:" in signatures
    assert "id: int" in signatures
    assert "def list_todos() -> list[Todo]:" in signatures


def test_backend_dependency_context_declares_object_access_semantics() -> None:
    constraints = BackendEngineer._build_interface_constraints("""
## 依赖文件: todo.py
```
class Todo:
  id: int
def list_todos() -> list[Todo]:
```
""")

    assert "list_todos() -> list[Todo]" in constraints
    assert "属性访问" in constraints
    assert "下标访问" in constraints
