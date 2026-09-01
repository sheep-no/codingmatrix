"""Tests for project-level generation contracts."""

import pytest
from app.agent.dependency_manifest import DependencyKind, DependencyManifest
from app.agent.generation_plan import GenerationPlan
from app.agent.interface_registry import InterfaceRegistry


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
