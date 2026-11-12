"""Branch coverage for app/agent/adapters/boilerplate.py."""

import pytest

from app.agent.adapters import boilerplate
from app.agent.adapters.boilerplate import (
    scaffold_database,
    scaffold_entry,
    scaffold_for_language,
    scaffold_manifest,
    scaffold_readme,
    scaffold_test,
)


# ---------------------------------------------------------------------------
# scaffold_for_language dispatch
# ---------------------------------------------------------------------------


def test_readme_skips_file_plan_entries_without_path() -> None:
    architecture = {
        "requirement": "Demo",
        "file_plan": [
            {"description": "missing path"},
            {"path": "src/a.py", "description": "a"},
        ],
    }

    readme = scaffold_readme(architecture)

    assert "- `src/a.py`: a" in readme
    assert "missing path" not in readme


def test_readme_uses_file_type_as_description() -> None:
    architecture = {"requirement": "Demo", "file_plan": [{"path": "src/a.py", "file_type": "api"}]}

    readme = scaffold_readme(architecture)

    assert "- `src/a.py`: api" in readme


def test_readme_non_python_test_command() -> None:
    architecture = {"requirement": "Demo", "file_plan": [{"path": "tests/test_a.py"}]}

    readme = scaffold_readme(architecture, "javascript")

    assert "see README" in readme


@pytest.mark.parametrize(
    ("name", "marker"),
    [
        ("pyproject.toml", "[project]"),
        ("go.mod", "module example.com/app"),
        ("cargo.toml", 'edition = "2021"'),
        ("pom.xml", "<artifactId>"),
    ],
)
def test_manifest_variants(name: str, marker: str) -> None:
    architecture = {"requirement": "Demo"}

    assert marker in scaffold_manifest("python", name, architecture)


def test_manifest_unknown_name_returns_empty() -> None:
    assert scaffold_manifest("python", "unknown.txt", {}) == ""


@pytest.mark.parametrize("language", ["go", "rust", "java"])
def test_scaffold_entry_unsupported_languages_return_none(language: str) -> None:
    assert scaffold_entry(language, "main.go", {}) is None


def test_scaffold_entry_javascript_without_express_returns_none() -> None:
    assert scaffold_entry("javascript", "src/index.js", {}) is None


def test_scaffold_entry_javascript_express() -> None:
    content = scaffold_entry(
        "javascript", "src/index.js", {"project_spec": {"default": {"framework": "Express"}}}
    )

    assert "require('express')" in content


# ---------------------------------------------------------------------------
# scaffold_database
# ---------------------------------------------------------------------------


def test_database_non_python_language_returns_none() -> None:
    assert scaffold_database("javascript", "db.js", {}) is None


def test_database_backend_normalization_from_sqlite() -> None:
    architecture = {
        "project_spec": {
            "default": {"storage": {"type": "sqlite", "backend": "sqlite"}}
        }
    }

    content = scaffold_database("python", "app/database.py", architecture)

    assert "sqlite:///./app.db" in content


def test_database_backend_from_storage_type_when_missing() -> None:
    architecture = {"project_spec": {"default": {"storage": {"type": "postgresql"}}}}

    content = scaffold_database("python", "app/database.py", architecture)

    assert "postgresql://localhost/app" in content


def test_database_unsupported_backend_returns_none() -> None:
    architecture = {"project_spec": {"default": {"storage": {"type": "mongodb"}}}}

    assert scaffold_database("python", "app/database.py", architecture) is None


def test_database_postgres_backend_omits_connect_args() -> None:
    architecture = {
        "project_spec": {
            "default": {"storage": {"type": "postgres", "backend": "postgres"}}
        }
    }

    content = scaffold_database("python", "app/database.py", architecture)

    assert "postgresql://localhost/app" in content
    assert "check_same_thread" not in content


def test_database_storage_as_non_dict_returns_none() -> None:
    architecture = {"project_spec": {"default": {"storage": "sqlite"}}}

    assert scaffold_database("python", "app/database.py", architecture) is None


# ---------------------------------------------------------------------------
# title / slug helpers
# ---------------------------------------------------------------------------


def test_project_title_falls_back_to_generated_project() -> None:
    assert boilerplate._project_title({}) == "Generated Project"


def test_project_title_uses_project_name_when_requirement_missing() -> None:
    assert boilerplate._project_title({"project_name": "Named"}) == "Named"


def test_strip_pipeline_banner_without_blank_line_returns_empty() -> None:
    banner = "[Pipeline Mode]\nengine=legacy\nno blank line"

    assert boilerplate._strip_pipeline_banner(banner) == ""


def test_slug_collapses_repeated_dashes() -> None:
    slug = boilerplate._slug({"requirement": "a -- b"})

    assert "--" not in slug
    assert slug.startswith("a-")


def test_slug_empty_title_falls_back_to_app() -> None:
    assert boilerplate._slug({"requirement": "!!!"}) == "app"


# ---------------------------------------------------------------------------
# storage / auth helpers
# ---------------------------------------------------------------------------


def test_storage_type_non_dict_storage_returns_empty() -> None:
    architecture = {"project_spec": {"default": {"storage": "sqlite"}}}

    assert boilerplate._storage_type(architecture) == ""


def test_storage_backend_from_symbol_table() -> None:
    architecture = {"symbol_table": {"storage": {"backend": "SQLAlchemy"}}}

    assert boilerplate._storage_backend(architecture) == "sqlalchemy"


def test_auth_scheme_from_symbol_table() -> None:
    architecture = {"symbol_table": {"auth": {"scheme": "JWT"}}}

    assert boilerplate._auth_scheme(architecture) == "jwt"


def test_auth_scheme_defaults_to_empty() -> None:
    assert boilerplate._auth_scheme({}) == ""


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("javascript", "npm start"),
        ("typescript", "npm start"),
        ("go", "go run ."),
        ("java", "mvn spring-boot:run"),
        ("rust", "cargo run"),
        ("ruby", "see README"),
    ],
)
def test_run_command_variants(language: str, expected: str) -> None:
    assert boilerplate._run_command(language, {}) == expected


def test_run_command_python_without_entry_defaults_to_main() -> None:
    assert boilerplate._run_command("python", {}) == "python main.py"


def test_run_command_python_empty_entry_falls_back_to_main() -> None:
    architecture = {"file_plan": [{"path": "", "file_type": "entry"}]}

    assert boilerplate._run_command("python", architecture) == "python main.py"


# ---------------------------------------------------------------------------
# requirements / pyproject / package.json
# ---------------------------------------------------------------------------


def test_requirements_flask_only() -> None:
    architecture = {"project_spec": {"default": {"framework": "Flask"}}}

    requirements = boilerplate._python_requirements(architecture)

    assert "flask" in requirements
    assert "fastapi" not in requirements


def test_requirements_uvicorn_counts_as_fastapi() -> None:
    architecture = {"project_spec": {"default": {"framework": "uvicorn"}}}

    requirements = boilerplate._python_requirements(architecture)

    assert "fastapi" in requirements


def test_requirements_pytest_without_fastapi_omits_httpx() -> None:
    architecture = {"file_plan": [{"path": "tests/test_a.py", "file_type": "test"}]}

    requirements = boilerplate._python_requirements(architecture)

    assert "pytest" in requirements
    assert "httpx" not in requirements


def test_requirements_empty_returns_empty_string() -> None:
    assert boilerplate._python_requirements({}) == ""


def test_pyproject_includes_dependencies() -> None:
    architecture = {"requirement": "Demo", "project_spec": {"default": {"framework": "FastAPI"}}}

    content = boilerplate._python_pyproject(architecture)

    assert 'dependencies = ["fastapi", "uvicorn"]' in content


def test_package_json_without_express_has_empty_dependencies() -> None:
    content = boilerplate._javascript_package_json({"requirement": "Demo"})

    assert '"dependencies": {\n\n  }' in content
    assert '"main": "src/index.js"' in content


def test_package_json_uses_entry_path() -> None:
    architecture = {
        "requirement": "Demo",
        "file_plan": [{"path": "server.js", "file_type": "entry"}],
    }

    content = boilerplate._javascript_package_json(architecture)

    assert '"main": "server.js"' in content


def test_java_pom_contains_artifact() -> None:
    content = boilerplate._java_pom({"requirement": "Demo Service"})

    assert "<artifactId>demo-service</artifactId>" in content


# ---------------------------------------------------------------------------
# python module / entry
# ---------------------------------------------------------------------------


def test_python_module_strips_init_suffix() -> None:
    assert boilerplate._python_module("app/api/__init__.py") == "app.api"


def test_python_entry_flask_with_api_module() -> None:
    architecture = {
        "project_spec": {"default": {"framework": "Flask"}},
        "file_plan": [
            {"path": "app/routes/__init__.py", "file_type": "router"},
        ],
    }

    entry = boilerplate._python_entry("main.py", architecture)

    assert "register_blueprint" in entry
    assert "from app.routes import router as __init___router" in entry
    assert "jsonify" in entry


def test_python_entry_flask_without_api_modules() -> None:
    architecture = {"project_spec": {"default": {"framework": "Flask"}}}

    entry = boilerplate._python_entry("main.py", architecture)

    assert "register_blueprint" not in entry
    assert "app.run" in entry


def test_python_entry_fastapi_without_api_modules() -> None:
    architecture = {"project_spec": {"default": {"framework": "FastAPI"}}}

    entry = boilerplate._python_entry("main.py", architecture)

    assert "include_router" not in entry
    assert "uvicorn.run" in entry


def test_python_entry_unknown_framework_returns_plain_main() -> None:
    entry = boilerplate._python_entry("main.py", {})

    assert "def main() -> None:" in entry
    assert "FastAPI" not in entry


def test_javascript_entry_content() -> None:
    content = boilerplate._javascript_entry({})

    assert "app.listen(3000)" in content


def test_go_entry_content() -> None:
    content = boilerplate._go_entry()

    assert "package main" in content


def test_java_entry_with_java_package_segment() -> None:
    content = boilerplate._java_entry("src/main/java/com/example/App.java")

    assert content.startswith("package com.example;")
    assert "public class App" in content


def test_java_entry_without_package_segment() -> None:
    content = boilerplate._java_entry("App.java")

    assert content.startswith("public class App")


def test_java_entry_java_segment_at_end_has_no_package() -> None:
    content = boilerplate._java_entry("java/App.java")

    assert content.startswith("public class App")


# ---------------------------------------------------------------------------
# scaffold_test / frozen routes
# ---------------------------------------------------------------------------


def test_scaffold_test_non_python_returns_none() -> None:
    assert scaffold_test("javascript", "tests/test_app.py", {}) is None


def test_frozen_routes_skips_non_matching_file_plan_entries() -> None:
    architecture = {
        "file_plan": [
            {"path": "other.py", "contract": {"routes": ["GET /tickets"]}},
            {
                "path": "tests/test_app.py",
                "contract": {"routes": ["POST /register", "GET /tickets"]},
            },
        ]
    }

    routes = boilerplate._frozen_routes(architecture, "tests/test_app.py")

    assert routes == ["POST /register", "GET /tickets"]


def test_frozen_routes_returns_empty_for_unknown_file() -> None:
    assert boilerplate._frozen_routes({}, "tests/test_unknown.py") == []


def test_frozen_routes_skips_falsy_route_items() -> None:
    architecture = {
        "symbol_table": {
            "files": {"tests/test_app.py": {"routes": ["", "GET /tickets"]}}
        }
    }

    assert boilerplate._frozen_routes(architecture, "tests/test_app.py") == ["GET /tickets"]


def test_frozen_routes_handles_non_dict_entry_and_empty_contracts() -> None:
    architecture = {
        "symbol_table": {"files": {"tests/test_app.py": "invalid"}},
        "file_plan": [
            {"path": "tests/test_app.py", "contract": "invalid"},
        ],
    }

    assert boilerplate._frozen_routes(architecture, "tests/test_app.py") == []


def test_scaffold_for_language_test_kind_without_routes() -> None:
    assert scaffold_for_language("python", "tests/test_x.py", "test", {}) is None


def test_scaffold_for_language_test_path_detection() -> None:
    architecture = {
        "symbol_table": {
            "files": {
                "app/tests/test_x.py": {
                    "routes": ["POST /register", "GET /tickets"]
                }
            }
        }
    }

    content = scaffold_for_language("python", "app/tests/test_x.py", "config", architecture)

    assert content is not None
    assert "def test_auth_failure" in content


def test_looks_like_test_path_variants() -> None:
    assert boilerplate._looks_like_test_path("a\\tests\\b.py")
    assert boilerplate._looks_like_test_path("test_x.py")
    assert boilerplate._looks_like_test_path("x_test.py")
    assert not boilerplate._looks_like_test_path("src/main.py")
    assert not boilerplate._looks_like_test_path("")


def test_looks_like_ticket_routes_requires_both_markers() -> None:
    assert not boilerplate._looks_like_ticket_routes(["GET /tickets"])
    assert not boilerplate._looks_like_ticket_routes(["POST /register"])
    assert boilerplate._looks_like_ticket_routes(["POST /register", "GET /tickets"])


def test_api_modules_filters_by_type_and_extension() -> None:
    architecture = {
        "file_plan": [
            {"path": "app/api.py", "file_type": "api"},
            {"path": "app/core/controllers/x.py", "file_type": "service"},
            {"path": "app/web.js", "file_type": "router"},
            {"path": "app/skip.py", "file_type": "config"},
        ]
    }

    assert list(boilerplate._api_modules(architecture)) == [
        "app/api.py",
        "app/core/controllers/x.py",
    ]
