import json

import pytest

from app.agent import scaffolding
from app.agent.adapters import LanguageAdapterRegistry
from app.agent.scaffolding import (
    ScaffoldRequest,
    execute_official_scaffold,
    import_scaffold_plan,
    official_scaffold_request,
)


def test_scaffold_request_rejects_unnormalized_target():
    with pytest.raises(ValueError, match="normalized relative path"):
        ScaffoldRequest(
            framework="express",
            language="javascript",
            target_dir="a/",
            command=("x",),
        )


@pytest.mark.asyncio
async def test_execute_rejects_missing_workspace_target_and_failures(tmp_path):
    request = official_scaffold_request("javascript", "express", "sample")

    class NeverRunner:
        async def run(self, spec, workspace):  # pragma: no cover - must not run
            raise AssertionError("runner should not be invoked")

    with pytest.raises(ValueError, match="existing directory"):
        await execute_official_scaffold(tmp_path / "missing", request, runner=NeverRunner())

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="absent or empty"):
        await execute_official_scaffold(
            tmp_path, official_scaffold_request("javascript", "express", "occupied"),
            runner=NeverRunner(),
        )

    class FailingRunner:
        async def run(self, spec, workspace):
            return 2, "stdout-tail", "stderr-tail"

    with pytest.raises(RuntimeError, match="exit code 2: stderr-tail"):
        await execute_official_scaffold(tmp_path, request, runner=FailingRunner())

    class NoopRunner:
        async def run(self, spec, workspace):
            return 0, "", ""

    with pytest.raises(RuntimeError, match="without creating target"):
        await execute_official_scaffold(tmp_path, request, runner=NoopRunner())

    class StdoutOnlyRunner:
        async def run(self, spec, workspace):
            return 1, "only-stdout", ""

    with pytest.raises(RuntimeError, match="exit code 1: only-stdout"):
        await execute_official_scaffold(tmp_path, request, runner=StdoutOnlyRunner())


def test_import_rejects_bad_directory_limits_and_missing_adapter(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="must exist"):
        import_scaffold_plan(tmp_path / "missing", language="python", framework="fastapi")

    with pytest.raises(ValueError, match="must be positive"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi", max_files=0)
    with pytest.raises(ValueError, match="must be positive"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi", max_file_bytes=0)

    monkeypatch.setattr(LanguageAdapterRegistry, "get_adapter", classmethod(lambda cls, lang: None))
    with pytest.raises(LookupError, match="adapter not found"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi")


def test_import_skips_ignored_and_unsupported_files(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"\x00\x01")
    (tmp_path / "notes").write_text("plain\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("from missing import thing\n", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "main.py")
    except OSError:
        pass

    plan = import_scaffold_plan(tmp_path, language="python", framework="fastapi")

    assert {item.path for item in plan.files} == {"main.py", "notes"}
    main_file = next(item for item in plan.files if item.path == "main.py")
    assert main_file.dependencies == ()


def test_import_rejects_oversized_and_non_utf8_files(tmp_path):
    (tmp_path / "big.py").write_text("x = 1\n" * 10, encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds size limit"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi", max_file_bytes=3)

    (tmp_path / "big.py").unlink()
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="not UTF-8"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi")


def test_import_rejects_too_many_files_and_empty_scaffold(tmp_path):
    for index in range(3):
        (tmp_path / f"mod{index}.py").write_text(f"x = {index}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="too many importable files"):
        import_scaffold_plan(tmp_path, language="python", framework="fastapi", max_files=2)

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no importable files"):
        import_scaffold_plan(empty, language="python", framework="fastapi")


def test_import_deduplicates_non_unique_symbols(tmp_path):
    (tmp_path / "a.py").write_text("def same():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def same():\n    pass\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("def unique():\n    pass\n", encoding="utf-8")

    plan = import_scaffold_plan(tmp_path, language="python", framework="fastapi")

    assert plan.interfaces.symbol_owner("unique") == "c.py"
    assert plan.interfaces.symbol_owner("same") is None


def test_resolve_inside_rejects_escape(tmp_path):
    with pytest.raises(ValueError, match="stay inside workspace"):
        scaffolding._resolve_inside(tmp_path, "../outside")


def test_normalize_and_module_name_helpers():
    assert scaffolding._normalize_relative_path("a/b") == "a/b"
    with pytest.raises(ValueError, match="unsafe path components"):
        scaffolding._normalize_relative_path("a b")
    assert scaffolding._module_name("pkg/index.ts") == "pkg"
    assert scaffolding._module_name("pkg/mod.rs") == "pkg"
    assert scaffolding._module_name("pkg/__init__.py") == "pkg"
    assert scaffolding._module_name("README") == "README"


def test_dependency_manifest_reads_package_json_sections(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "dependencies": {"express": "^5.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }),
        encoding="utf-8",
    )
    (tmp_path / "index.js").write_text("export const x = 1\n", encoding="utf-8")
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("express")
    assert manifest.allows("jest")


def test_dependency_manifest_handles_invalid_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid scaffold package.json"):
        scaffolding._read_dependency_manifest(tmp_path)

    (tmp_path / "package.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an object"):
        scaffolding._read_dependency_manifest(tmp_path)

    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": [], "devDependencies": "not-a-mapping"}),
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("nothing") is False


def test_dependency_manifest_reads_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "\n# comment\n-r other.txt\nhttps://example.com/x.whl\n!!!invalid\nfastapi==0.115.0\npytest\n",
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("fastapi")
    assert manifest.allows("pytest")


def test_dependency_manifest_reads_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi>=0.115", "uvicorn", "!!!invalid"]\n',
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("fastapi")
    assert manifest.allows("uvicorn")

    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid scaffold pyproject.toml"):
        scaffolding._read_dependency_manifest(tmp_path)

    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = 1\n", encoding="utf-8")
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("anything") is False


def test_dependency_manifest_reads_cargo(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[dependencies]\nserde = "1.0"\naxum = { version = "0.7" }\n'
        'weird = 1\n'
        '[dev-dependencies]\ncriterion = { version = "0.5" }\n',
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("serde")
    assert manifest.allows("axum")
    assert manifest.allows("criterion")

    (tmp_path / "Cargo.toml").write_text("[dependencies\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid scaffold Cargo.toml"):
        scaffolding._read_dependency_manifest(tmp_path)

    (tmp_path / "Cargo.toml").write_text(
        "[dependencies]\nserde = \"1.0\"\n[dev-dependencies]\ntest = 1\n", encoding="utf-8"
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("serde")


def test_dependency_manifest_reads_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\nrequire (\n    github.com/gin-gonic/gin v1.10.0\n"
        "    local/not-a-version\n)\n",
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("github.com/gin-gonic/gin")
    assert manifest.allows("local/not-a-version") is False


def test_dependency_manifest_reads_pom(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project><dependencies>"
        "<dependency><groupId>org.springframework</groupId>"
        "<artifactId>spring-core</artifactId><version>6.1.0</version></dependency>"
        "<dependency><groupId>org.junit</groupId>"
        "<artifactId>junit</artifactId><scope>test</scope></dependency>"
        "</dependencies></project>",
        encoding="utf-8",
    )
    manifest = scaffolding._read_dependency_manifest(tmp_path)
    assert manifest.allows("org.springframework:spring-core")
    assert manifest.allows("org.junit:junit")

    (tmp_path / "pom.xml").write_text("<project", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid scaffold pom.xml"):
        scaffolding._read_dependency_manifest(tmp_path)
