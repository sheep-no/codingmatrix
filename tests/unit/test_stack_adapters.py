"""Tests for technology-specific constrained synthesis adapters."""

from pathlib import Path

import pytest

from app.agent.capabilities import Capability
from app.agent.code_synthesis_contracts import GenerationStrategy, ProjectModel
from app.agent.orchestration.ir_projection import project_change_plan
from app.agent.stack_adapters import (
    DEFAULT_STACK_ADAPTERS,
    ExpressStackAdapter,
    FastAPIStackAdapter,
    GoStackAdapter,
    SpringStackAdapter,
    UnsupportedStackError,
)


def test_stack_registry_resolves_canonical_keys_and_aliases() -> None:
    express = DEFAULT_STACK_ADAPTERS.require("typescript", "express")
    spring = DEFAULT_STACK_ADAPTERS.require("java", "spring-boot")

    assert express is DEFAULT_STACK_ADAPTERS.require("javascript", "express")
    assert express is DEFAULT_STACK_ADAPTERS.require("js", "express")
    assert DEFAULT_STACK_ADAPTERS.require("go", "stdlib") is DEFAULT_STACK_ADAPTERS.require(
        "go", "net/http"
    )
    assert spring is DEFAULT_STACK_ADAPTERS.require("java", "spring-boot-gradle")
    assert len(DEFAULT_STACK_ADAPTERS.all()) == 4


def test_fastapi_adapter_detects_runtime_entrypoint_and_dynamic_zones(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\ndependencies = ["fastapi"]\n',
        encoding="utf-8",
    )
    source = tmp_path / "service"
    source.mkdir()
    (source / "api.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )

    adapter, project = DEFAULT_STACK_ADAPTERS.detect(tmp_path)

    assert isinstance(adapter, FastAPIStackAdapter)
    assert project.runtime == ">=3.11"
    assert project.entrypoints == ("service/api.py",)
    assert project.generated_zones == ("service",)


def test_express_adapter_detects_package_entrypoint_and_node_runtime(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"main":"src/server.ts","engines":{"node":">=20"},'
        '"dependencies":{"express":"5.0.0"}}',
        encoding="utf-8",
    )
    source = tmp_path / "src"
    source.mkdir()
    (source / "server.ts").write_text(
        "import express from 'express';\nconst app = express();\n", encoding="utf-8"
    )

    adapter, project = DEFAULT_STACK_ADAPTERS.detect(tmp_path)

    assert isinstance(adapter, ExpressStackAdapter)
    assert project.runtime == ">=20"
    assert project.entrypoints == ("src/server.ts",)
    assert project.targets == ("package.json",)


def test_go_adapter_detects_module_runtime_and_nested_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n\ngo 1.23\n", encoding="utf-8")
    command = tmp_path / "cmd" / "api"
    command.mkdir(parents=True)
    (command / "main.go").write_text(
        'package main\nimport "net/http"\nfunc main() { http.ListenAndServe(":8080", nil) }\n',
        encoding="utf-8",
    )

    adapter, project = DEFAULT_STACK_ADAPTERS.detect(tmp_path)

    assert isinstance(adapter, GoStackAdapter)
    assert project.runtime == "1.23"
    assert project.modules == ("example.com/demo",)
    assert project.entrypoints == ("cmd/api/main.go",)


@pytest.mark.parametrize(
    ("manifest_name", "manifest", "framework", "runtime"),
    (
        (
            "pom.xml",
            "<project><artifactId>demo</artifactId><properties>"
            "<java.version>21</java.version></properties>"
            "<dependency><artifactId>spring-boot-starter-web</artifactId></dependency></project>",
            "spring-boot",
            "21",
        ),
        (
            "build.gradle",
            "plugins { id 'org.springframework.boot' version '3.4.0' }\n"
            "sourceCompatibility = '17'\n",
            "spring-boot-gradle",
            "17",
        ),
    ),
)
def test_spring_adapter_detects_maven_and_gradle_profiles(
    tmp_path: Path,
    manifest_name: str,
    manifest: str,
    framework: str,
    runtime: str,
) -> None:
    (tmp_path / manifest_name).write_text(manifest, encoding="utf-8")
    source = tmp_path / "src" / "main" / "java" / "com" / "example"
    source.mkdir(parents=True)
    (source / "Application.java").write_text(
        "@SpringBootApplication\npublic class Application {}\n", encoding="utf-8"
    )

    adapter, project = DEFAULT_STACK_ADAPTERS.detect(tmp_path)

    assert isinstance(adapter, SpringStackAdapter)
    assert project.framework == framework
    assert project.runtime == runtime
    assert project.entrypoints == ("src/main/java/com/example/Application.java",)


@pytest.mark.parametrize(
    ("adapter", "project"),
    (
        (FastAPIStackAdapter(), ProjectModel(language="python", framework="fastapi")),
        (ExpressStackAdapter(), ProjectModel(language="typescript", framework="express")),
        (GoStackAdapter(), ProjectModel(language="go", framework="stdlib")),
        (SpringStackAdapter(), ProjectModel(language="java", framework="spring-boot")),
    ),
)
def test_stack_adapters_build_and_project_arbitrary_artifact_dags(adapter, project) -> None:
    change_plan = adapter.build_change_plan(
        project,
        {
            "artifacts": [
                {"path": "src/domain.ext", "role": "domain", "strategy": "template"},
                {
                    "path": "src/api.ext",
                    "role": "api",
                    "depends_on": ["src/domain.ext"],
                    "strategy": "llm",
                },
                {
                    "path": "tests/api_test.ext",
                    "role": "test",
                    "depends_on": ["src/api.ext"],
                },
            ],
            "contracts": {"api": {"path": "/items"}},
        },
    )
    projected = project_change_plan(
        change_plan,
        requested_paths=(artifact.path for artifact in change_plan.artifacts),
    )

    assert len(change_plan.artifacts) == 3
    assert change_plan.artifact("src/api.ext").depends_on == ("src/domain.ext",)
    assert change_plan.artifact("src/domain.ext").strategy is GenerationStrategy.TEMPLATE
    assert projected.policy.value == "strict"
    assert {item.path for item in projected.files} == {
        "src/domain.ext", "src/api.ext", "tests/api_test.ext"
    }


@pytest.mark.parametrize("artifact_count", (1, 2, 6, 9))
def test_fastapi_plan_size_is_driven_by_request(artifact_count: int) -> None:
    artifacts = []
    for index in range(artifact_count):
        artifacts.append({
            "path": f"modules/area_{index}/artifact.py",
            "role": "module",
            "depends_on": [f"modules/area_{index - 1}/artifact.py"] if index else [],
        })

    plan = FastAPIStackAdapter().build_change_plan(
        ProjectModel(language="python", framework="fastapi"),
        {"artifacts": artifacts},
    )

    assert len(plan.artifacts) == artifact_count


@pytest.mark.parametrize(
    ("adapter", "path", "content", "expected"),
    (
        (FastAPIStackAdapter(), "api.py", "class Todo:\n    pass\n", "Todo"),
        (ExpressStackAdapter(), "api.ts", "export interface Todo { id: number }\n", "Todo"),
        (GoStackAdapter(), "api.go", "type Todo struct {}\nfunc ListTodos() []Todo {", "Todo"),
        (
            SpringStackAdapter(),
            "Todo.java",
            "public class Todo { public String getName() { return null; } }",
            "Todo",
        ),
    ),
)
def test_stack_adapters_delegate_symbol_extraction(adapter, path, content, expected) -> None:
    index = adapter.extract_symbols(Path(path), content)

    assert expected in {symbol.name for symbol in index.symbols}
    assert index.path == path


def test_validation_and_scaffold_capabilities_are_explicit() -> None:
    express = ExpressStackAdapter()
    fastapi = FastAPIStackAdapter()
    express_project = ProjectModel(language="typescript", framework="express")
    fastapi_project = ProjectModel(language="python", framework="fastapi")

    assert express.capabilities().supports(Capability.HTTP_API)
    assert fastapi.capabilities().supports(Capability.DEPENDENCY_INJECTION)
    assert express.synthesis_capabilities().scaffolder is True
    assert fastapi.synthesis_capabilities().scaffolder is False
    assert express.validation_profile(express_project).required_scopes == ("build", "test")
    assert fastapi.validation_profile(fastapi_project).commands[0] == (
        "python3", "-m", "compileall", "."
    )


@pytest.mark.asyncio
async def test_adapter_reports_missing_official_scaffold_without_side_effects(tmp_path: Path) -> None:
    project = ProjectModel(language="python", framework="fastapi")

    result = await FastAPIStackAdapter().scaffold(project, tmp_path / "service")

    assert result.supported is False
    assert result.request is None
    assert result.plan is None


def test_adapter_rejects_mismatched_project_and_unsafe_artifact_path() -> None:
    adapter = FastAPIStackAdapter()

    with pytest.raises(UnsupportedStackError, match="does not match"):
        adapter.build_change_plan(
            ProjectModel(language="go", framework="stdlib"),
            {"artifacts": [{"path": "main.go", "role": "entry"}]},
        )
    with pytest.raises(ValueError, match="unsafe components"):
        adapter.build_change_plan(
            ProjectModel(language="python", framework="fastapi"),
            {"artifacts": [{"path": "../main.py", "role": "entry"}]},
        )
