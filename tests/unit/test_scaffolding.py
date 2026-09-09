import pytest

from app.agent.scaffolding import (
    execute_official_scaffold,
    import_scaffold_plan,
    official_scaffold_request,
    supports_official_scaffold,
)


def test_official_scaffold_is_parameterized_and_shell_free():
    request = official_scaffold_request("typescript", "express", "sample")

    assert request.as_command_spec().shell is False
    assert request.command == (
        "npx", "--yes", "express-generator@4.16.1", "sample", "--no-view"
    )


def test_nestjs_scaffold_separates_generation_from_dependency_install():
    request = official_scaffold_request("typescript", "nestjs", "sample")

    assert request.command == (
        "npx", "--yes", "@nestjs/cli@11.0.10", "new", "sample",
        "--package-manager", "npm", "--skip-git", "--skip-install",
    )


def test_unknown_framework_has_explicit_pending_state():
    with pytest.raises(LookupError):
        official_scaffold_request("go", "gin", "sample")


def test_official_scaffold_support_can_be_queried_without_execution():
    assert supports_official_scaffold("typescript", "express") is True
    assert supports_official_scaffold("go", "gin") is False


@pytest.mark.parametrize("target", ("../sample", "/tmp/sample", "nested/../sample", "has space"))
def test_scaffold_rejects_unsafe_target_paths(target):
    with pytest.raises(ValueError, match="target_dir"):
        official_scaffold_request("typescript", "express", target)


def test_scaffold_import_builds_frozen_plan_from_real_files(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "models.py").write_text("class Todo:\n    pass\n", encoding="utf-8")
    (app_dir / "service.py").write_text(
        "from .models import Todo\n\ndef list_todos():\n    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi==0.115.0\npytest>=8\n", encoding="utf-8")

    plan = import_scaffold_plan(tmp_path, language="python", framework="fastapi")

    service = next(item for item in plan.files if item.path == "app/service.py")
    assert service.dependencies == ("app/models.py",)
    assert service.imports == ("models",)
    assert plan.requested_paths == tuple(sorted(item.path for item in plan.files))
    assert plan.dependencies.allows("fastapi")
    assert plan.interfaces.symbol_owner("Todo") == "app/models.py"


def test_scaffold_import_includes_runtime_entrypoints_and_text_assets(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "public").mkdir()
    (tmp_path / "bin" / "www").write_text("#!/usr/bin/env node\n", encoding="utf-8")
    (tmp_path / "public" / "index.html").write_text("<h1>Express</h1>\n", encoding="utf-8")
    (tmp_path / "public" / "style.css").write_text("body {}\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("module.exports = {}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")

    plan = import_scaffold_plan(tmp_path, language="javascript", framework="express")

    assert {item.path for item in plan.files} == {
        "app.js",
        "bin/www",
        "package.json",
        "public/index.html",
        "public/style.css",
    }


@pytest.mark.asyncio
async def test_scaffold_execution_imports_generated_directory(tmp_path):
    class FakeRunner:
        async def run(self, spec, workspace):
            target = workspace / "sample"
            target.mkdir()
            (target / "package.json").write_text(
                '{"dependencies":{"express":"^5.0.0"}}', encoding="utf-8"
            )
            (target / "index.js").write_text(
                "export function app() {}\n", encoding="utf-8"
            )
            return 0, "created", ""

    request = official_scaffold_request("javascript", "express", "sample")
    plan = await execute_official_scaffold(tmp_path, request, runner=FakeRunner())

    assert plan.framework == "express"
    assert {item.path for item in plan.files} == {"index.js", "package.json"}
    assert plan.dependencies.allows("express")
