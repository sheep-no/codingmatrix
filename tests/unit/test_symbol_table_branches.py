"""Branch coverage for the frozen cross-file symbol table."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import symbol_table
from app.agent.symbol_table import (
    _as_str_list,
    _canonical_path,
    _defined_names,
    _extract_routes,
    _extract_test_paths,
    _file_type,
    _is_local_python_module,
    _looks_like_test,
    _normalize_route,
    _order_packages,
    _router_prefixes,
    _should_use_ticket_table,
    _sync_file_plan_contracts,
    _sync_project_spec,
    _table_has_provides,
    attach_to_project_context,
    build_ticket_eight_file_symbol_table,
    derive_symbol_table,
    finalize_generated_project,
    freeze_symbol_table,
    is_ticket_requirement,
    record_generated_signature,
    remember_generated_file,
    rewrite_manifests,
    scan_python_packages,
    validate_file_against_symbol_table,
    validate_project_against_symbol_table,
)


class TestTicketDetection:
    @pytest.mark.parametrize(
        ("requirement", "expected"),
        [("build a ticket system", True), ("实现工单系统", True), ("blog", False), ("", False)],
    )
    def test_is_ticket_requirement(self, requirement, expected):
        assert is_ticket_requirement(requirement) is expected

    def test_table_has_provides_variants(self):
        assert _table_has_provides(None) is False
        assert _table_has_provides({}) is False
        assert _table_has_provides({"files": []}) is False
        assert _table_has_provides({"files": {"a.py": "x"}}) is False
        assert _table_has_provides({"files": {"a.py": {"provides": []}}}) is False
        assert _table_has_provides({"files": {"a.py": {"provides": ["X"]}}}) is True

    def test_ticket_table_structure(self):
        table = build_ticket_eight_file_symbol_table()

        assert table["storage"]["backend"] == "sqlalchemy"
        assert table["files"]["app/services.py"]["provides"]
        assert "app/routers.py" in table["files"]

    def test_should_use_ticket_flags(self):
        assert _should_use_ticket_table({"requirement": "ticket", "used_compact_eight_file_plan": True})
        paths = [{"path": path} for path in symbol_table._COMPACT_TICKET_PATHS]
        assert _should_use_ticket_table({"requirement": "工单", "file_plan": paths})
        assert not _should_use_ticket_table({"requirement": "ticket", "file_plan": []})


class TestFreeze:
    def test_uses_existing_table_with_provides(self):
        existing = {"files": {"a.py": {"provides": ["A"]}}}
        architecture = {"symbol_table": existing}

        assert freeze_symbol_table(architecture) is existing

    def test_derives_table_for_non_ticket(self):
        architecture = {
            "language": "python",
            "file_plan": [{"path": "app/main.py", "contract": {"exports": ["app"]}}],
        }

        table = freeze_symbol_table(architecture)

        assert table["files"]["app/main.py"]["provides"] == ["app"]

    def test_attach_to_project_context_defaults(self):
        project_context = {}
        architecture = {"language": "python", "file_plan": []}

        table = attach_to_project_context(project_context, architecture)

        assert project_context["symbol_table"] is table
        assert project_context["generated_signatures"] == {}


class TestDerive:
    def test_non_dict_spec_values_are_ignored(self):
        architecture = {
            "project_spec": {"default": {"storage": "bad", "auth": []}},
            "file_plan": [None, "x", {"path": ""}, {"path": "a.py", "contract": "bad"}],
        }

        table = derive_symbol_table(architecture)

        assert table["storage"] == {"backend": "", "dialect": ""}
        assert table["files"]["a.py"]["provides"] == []

    @pytest.mark.parametrize(
        ("dialect", "expected"),
        [("sqlite", "sqlalchemy"), ("postgres", "sqlalchemy"), ("json_file", "json"), ("", "")],
    )
    def test_dialect_backend_inference(self, dialect, expected):
        architecture = {"project_spec": {"default": {"storage": {"type": dialect}}}}

        assert derive_symbol_table(architecture)["storage"]["backend"] == expected

    def test_explicit_backend_wins(self):
        architecture = {"project_spec": {"default": {"storage": {"backend": "SQLAlchemy", "dialect": "sqlite"}}}}

        assert derive_symbol_table(architecture)["storage"]["backend"] == "sqlalchemy"

    def test_spec_non_dict(self):
        assert derive_symbol_table({"project_spec": "bad"})["files"] == {}


class TestValidateFile:
    def test_no_table_returns_empty(self):
        assert validate_file_against_symbol_table("a.py", "x = 1", {}) == []

    def test_empty_content_reports_contract(self):
        architecture = {
            "symbol_table": {"files": {"a.py": {"provides": ["A"], "routes": []}}},
        }

        assert validate_file_against_symbol_table("a.py", "  ", architecture) == [
            "a.py: empty file missing frozen contract"
        ]

    def test_empty_content_without_contract_is_clean(self):
        architecture = {"symbol_table": {"files": {"a.py": {}}}}

        assert validate_file_against_symbol_table("a.py", "", architecture) == []

    def test_missing_route(self):
        architecture = {
            "symbol_table": {
                "route_prefix": "/api",
                "files": {"app/routers.py": {"routes": ["GET /users"]}},
            },
        }

        issues = validate_file_against_symbol_table(
            "app/routers.py", "x = 1\n", architecture
        )

        assert any("missing frozen routes" in item for item in issues)

    def test_test_file_skips_route_check(self):
        architecture = {
            "symbol_table": {
                "route_prefix": "/api",
                "files": {"tests/test_app.py": {"routes": ["GET /users"]}},
            },
        }

        assert validate_file_against_symbol_table("tests/test_app.py", "x = 1\n", architecture) == []

    def test_sqlite_import_conflict(self):
        architecture = {
            "file_plan": [{"path": "app/database.py", "file_type": "database"}],
            "symbol_table": {
                "storage": {"backend": "sqlalchemy"},
                "route_prefix": "",
                "files": {"app/database.py": {}},
            },
        }

        issues = validate_file_against_symbol_table(
            "app/database.py", "import sqlite3\n", architecture
        )

        assert any("sqlite3 import conflicts" in item for item in issues)

    def test_json_store_conflict(self):
        architecture = {
            "file_plan": [{"path": "app/models.py", "file_type": "model"}],
            "symbol_table": {
                "storage": {"backend": "sqlalchemy"},
                "route_prefix": "",
                "files": {"app/models.py": {}},
            },
        }

        issues = validate_file_against_symbol_table(
            "app/models.py", "json.load(open('db.json'))\n", architecture
        )

        assert any("JSON file storage conflicts" in item for item in issues)

    def test_non_sqlalchemy_backend_skips_storage_checks(self):
        architecture = {
            "file_plan": [{"path": "app/models.py", "file_type": "model"}],
            "symbol_table": {
                "storage": {"backend": "json"},
                "route_prefix": "",
                "files": {"app/models.py": {}},
            },
        }

        assert validate_file_against_symbol_table(
            "app/models.py", "import sqlite3\n", architecture
        ) == []

    def test_route_prefix_non_empty_skips_api_v1_check(self):
        architecture = {
            "symbol_table": {
                "storage": {"backend": ""},
                "route_prefix": "/api/v1",
                "files": {"app/routers.py": {}},
            },
        }

        assert validate_file_against_symbol_table(
            "app/routers.py",
            '@router.get("/api/v1/x")\n',
            architecture,
        ) == []

    def test_test_path_uses_api_v1_reports_issue(self):
        architecture = {
            "symbol_table": {
                "storage": {"backend": ""},
                "route_prefix": "",
                "files": {"tests/test_app.py": {}},
            },
        }

        issues = validate_file_against_symbol_table(
            "tests/test_app.py",
            "client.get('/api/v1/users')\n",
            architecture,
        )

        assert any("/api/v1" in item for item in issues)

    def test_project_validation_aggregates(self):
        architecture = {
            "symbol_table": {
                "files": {
                    "a.py": {"provides": ["A"]},
                    "b.py": {"provides": ["B"]},
                }
            }
        }

        issues = validate_project_against_symbol_table(
            {"a.py": "", "b.py": ""}, architecture
        )

        assert len(issues) == 2


class TestDefinedNames:
    def test_json_keys_count_as_definitions(self):
        names = _defined_names("package.json", '{"name": "x", "version": "1"}', {})

        assert {"name", "version"} <= names

    def test_invalid_json_does_not_raise(self):
        assert _defined_names("package.json", "not json", {}) == set()

    def test_adapter_failure_is_swallowed(self, monkeypatch):
        class BrokenAdapter:
            def extract_definitions(self, content):
                raise RuntimeError("parse failure")

        monkeypatch.setattr(symbol_table, "_adapter", lambda architecture: BrokenAdapter())

        names = _defined_names("app/main.py", "def run():\n    pass\n", {})

        assert "run" in names

    def test_no_adapter_uses_regex_only(self, monkeypatch):
        monkeypatch.setattr(symbol_table, "_adapter", lambda architecture: None)

        names = _defined_names("app/main.py", "class A:\n    pass\n", {})

        assert "A" in names


class TestRouteHelpers:
    def test_router_prefixes_handles_strings_with_parens(self):
        text = 'router = APIRouter(prefix="/a(b)", tags=["x"])\n'

        assert _router_prefixes(text) == {"router": "/a(b)"}

    def test_router_prefixes_ignores_non_prefix_router(self):
        assert _router_prefixes("router = APIRouter(tags=['x'])\n") == {}

    def test_extract_routes_without_prefix_and_with_slash(self):
        content = '@router.get("/users")\ndef list_users():\n    pass\n'

        assert _extract_routes(content) == ["GET /users"]

    def test_extract_routes_prefix_normalization(self):
        content = 'router = APIRouter(prefix="/users/")\n@router.get("x")\ndef f(): pass\n'

        assert _extract_routes(content) == ["GET /users/x"]

    def test_extract_test_paths(self):
        content = "client.get('/users')\nTestClient(app).post('/login')\n"

        assert _extract_test_paths(content) == ["/users", "/login"]

    def test_normalize_route_forms(self):
        assert _normalize_route("get users") == "GET /users"
        assert _normalize_route("users") == "/users"
        assert _normalize_route("") == "/"

    def test_canonical_path(self):
        assert _canonical_path("users/{id}/") == "/users/{}"
        assert _canonical_path("/") == "/"
        assert _canonical_path("//") == "/"


class TestPathHelpers:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("tests/test_app.py", True),
            ("app/tests/helper.py", True),
            ("app/test_x.py", True),
            ("app/x_test.py", True),
            ("app/main.py", False),
            ("", False),
        ],
    )
    def test_looks_like_test(self, path, expected):
        assert _looks_like_test(path) is expected

    def test_file_type_from_plan(self):
        architecture = {"file_plan": [{"path": "app/x.py", "file_type": "SERVICE"}]}

        assert _file_type("app\\x.py", architecture) == "service"

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("pkg/database/db.py", "database"),
            ("pkg/model/user.py", "model"),
            ("pkg/service/user.py", "service"),
            ("pkg/router/user.py", "api"),
            ("pkg/controller/user.py", "api"),
            ("tests/test_x.py", "test"),
            ("pkg/main.py", "entry"),
            ("pkg/other.py", ""),
        ],
    )
    def test_file_type_fallbacks(self, path, expected):
        assert _file_type(path, {}) == expected

    def test_adapter_falls_back_to_python(self, monkeypatch):
        from app.agent.adapters import LanguageAdapterRegistry

        calls = []

        def fake_get(language):
            calls.append(language)
            return object() if language == "python" else None

        monkeypatch.setattr(LanguageAdapterRegistry, "get_adapter", staticmethod(fake_get))

        assert symbol_table._adapter({"language": "unknown"}) is not None
        assert calls == ["unknown", "python"]


class TestPackageHelpers:
    def test_as_str_list_variants(self):
        assert _as_str_list(None) == []
        assert _as_str_list("x") == ["x"]
        assert _as_str_list("") == []
        assert _as_str_list(["a", "", None]) == ["a"]
        assert _as_str_list(5) == []

    def test_order_packages_preserves_order(self):
        result = _order_packages(["custom", "pytest", "fastapi", "custom"])

        assert result == ["fastapi", "pytest", "custom"]

    @pytest.mark.parametrize(
        ("top", "files", "expected"),
        [
            ("", {}, False),
            ("app", {"app/__init__.py": ""}, True),
            ("pkg", {"src/pkg/x.py": ""}, True),
            ("pkg", {"other.txt": ""}, False),
        ],
    )
    def test_is_local_python_module(self, top, files, expected):
        assert _is_local_python_module(top, files) is expected


class TestScanPackages:
    def test_skips_relative_and_local_modules(self):
        files = {
            "app/main.py": "from . import local\nfrom app.services import X\nfrom os import path\n",
        }

        assert scan_python_packages(files) == []

    def test_skips_non_python_and_empty(self):
        assert scan_python_packages({"README.md": "x", "a.py": ""}) == []

    def test_maps_and_orders_packages(self):
        files = {
            "main.py": "import requests\nimport jose\nfrom fastapi import FastAPI\n",
        }

        assert scan_python_packages(files) == ["fastapi", "python-jose[cryptography]", "requests"]

    def test_adds_test_dependencies(self):
        files = {"tests/test_app.py": "import pytest\n"}

        assert scan_python_packages(files) == ["httpx", "pytest"]

    def test_does_not_duplicate_test_dependencies(self):
        files = {"tests/test_app.py": "import pytest\nimport httpx\n"}

        assert scan_python_packages(files) == ["httpx", "pytest"]


class TestRewriteManifests:
    def test_python_project_writes_requirements(self, tmp_path, monkeypatch):
        written = []
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic",
            lambda root, name, content, **kwargs: written.append((name, content)),
        )
        architecture = {"language": "python", "file_plan": [{"path": "requirements.txt"}]}

        rewritten = rewrite_manifests(tmp_path, architecture, {})

        assert "requirements.txt" in rewritten
        assert written

    def test_empty_packages_without_planned_requirements_skips_write(
        self, tmp_path, monkeypatch
    ):
        written = []
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic",
            lambda *args, **kwargs: written.append(args),
        )
        architecture = {"language": "python", "file_plan": []}

        rewrite_manifests(tmp_path, architecture, {})

        assert written == []

    def test_sqlalchemy_and_jwt_packages_added(self, tmp_path, monkeypatch):
        contents = {}
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic",
            lambda root, name, content, **kwargs: contents.__setitem__(name, content),
        )
        architecture = {
            "language": "python",
            "file_plan": [{"path": "requirements.txt"}],
            "symbol_table": {
                "storage": {"backend": "sqlalchemy"},
                "auth": {"scheme": "jwt_hs256"},
            },
        }

        rewrite_manifests(tmp_path, architecture, {})

        assert "sqlalchemy" in contents["requirements.txt"]
        assert "python-jose[cryptography]" in contents["requirements.txt"]

    def test_readme_written_with_ctx(self, tmp_path, monkeypatch):
        saved = []
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
        )
        ctx = SimpleNamespace(save_file_content=lambda *args: saved.append(args))
        architecture = {
            "language": "python",
            "file_plan": [{"path": "README.md"}],
        }

        rewritten = rewrite_manifests(tmp_path, architecture, {}, ctx)

        assert "README.md" in rewritten
        assert any(item[0] == "README.md" for item in saved)

    def test_readme_lowercase_plan_matches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
        )
        architecture = {"language": "python", "file_plan": [{"path": "readme.md"}]}

        assert "README.md" in rewrite_manifests(tmp_path, architecture, {})

    def test_test_files_are_scaffolded(self, tmp_path, monkeypatch):
        written = []
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic",
            lambda root, name, content, **kwargs: written.append(name),
        )
        monkeypatch.setattr(
            "app.agent.adapters.boilerplate.scaffold_for_language",
            lambda language, path, kind, arch: "def test_x():\n    pass\n",
        )
        architecture = {
            "language": "python",
            "file_plan": [{"path": "tests/test_app.py", "file_type": "test"}],
        }

        rewritten = rewrite_manifests(tmp_path, architecture, {})

        assert "tests/test_app.py" in rewritten
        assert written == ["tests/test_app.py"]

    def test_empty_scaffold_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            "app.agent.adapters.boilerplate.scaffold_for_language",
            lambda *args: "",
        )
        architecture = {
            "language": "python",
            "file_plan": [{"path": "tests/test_app.py", "file_type": "test"}],
        }

        assert rewrite_manifests(tmp_path, architecture, {}) == {}

    def test_skips_invalid_and_empty_plan_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
        )
        architecture = {
            "language": "python",
            "file_plan": ["bad", {}, {"path": ""}, {"path": "app/main.py"}],
        }

        assert rewrite_manifests(tmp_path, architecture, {}) == {}


class TestSyncHelpers:
    def test_sync_project_spec_skips_non_dict(self):
        architecture = {"project_spec": "bad"}
        _sync_project_spec(architecture, {"storage": {"backend": "x"}})

        assert architecture["project_spec"] == "bad"

    def test_sync_project_spec_skips_non_dict_default(self):
        architecture = {"project_spec": {"default": "bad"}}
        _sync_project_spec(architecture, {"storage": {"backend": "x"}})

        assert architecture["project_spec"]["default"] == "bad"

    def test_sync_project_spec_merges_storage_and_auth(self):
        architecture = {"project_spec": {"default": {"storage": {"type": "sqlite"}}}}

        _sync_project_spec(
            architecture,
            {
                "storage": {"backend": "sqlalchemy", "dialect": "sqlite"},
                "auth": {"scheme": "jwt"},
            },
        )

        default = architecture["project_spec"]["default"]
        assert default["storage"] == {"type": "sqlite", "backend": "sqlalchemy"}
        assert default["auth"] == {"scheme": "jwt"}

    def test_sync_project_spec_empty_tables(self):
        architecture = {}

        _sync_project_spec(architecture, {})

        assert architecture["project_spec"]["default"] == {}

    def test_sync_file_plan_contracts_builds_notes(self):
        architecture = {
            "file_plan": [
                "bad",
                {"path": ""},
                {"path": "app/main.py", "contract": "bad"},
                {"path": "missing.py"},
            ]
        }
        table = {
            "files": {
                "app/main.py": {
                    "provides": ["app"],
                    "requires": ["router"],
                    "routes": ["GET /"],
                    "signatures": {"app": "x"},
                }
            },
            "storage": {"backend": "sqlalchemy"},
            "auth": {"scheme": "jwt"},
        }

        _sync_file_plan_contracts(architecture, table)

        contract = architecture["file_plan"][2]["contract"]
        assert contract["exports"] == ["app"]
        assert contract["required_imports"] == ["router"]
        assert contract["routes"] == ["GET /"]
        assert "implement frozen signatures exactly" in contract["notes"]
        assert "storage.backend=sqlalchemy" in contract["notes"]
        assert "auth.scheme=jwt" in contract["notes"]

    def test_sync_file_plan_contracts_appends_notes(self):
        architecture = {
            "file_plan": [
                {"path": "app/main.py", "contract": {"notes": "existing"}},
            ]
        }
        table = {"files": {"app/main.py": {"provides": ["app"]}}}
        table["files"]["app/main.py"]["signatures"] = {"app": "x"}

        _sync_file_plan_contracts(architecture, table)

        assert architecture["file_plan"][0]["contract"]["notes"].startswith("existing;")

    def test_sync_file_plan_contracts_empty_files(self):
        architecture = {"file_plan": [{"path": "a.py"}]}

        _sync_file_plan_contracts(architecture, {"files": "bad"})

        assert "contract" not in architecture["file_plan"][0]


class TestFinalize:
    def test_logs_issues(self, monkeypatch, tmp_path):
        warnings = []
        monkeypatch.setattr(
            symbol_table.logger, "warning", lambda *args, **kwargs: warnings.append(args)
        )
        monkeypatch.setattr(symbol_table, "rewrite_manifests", lambda *args: {})
        architecture = {
            "symbol_table": {"files": {"a.py": {"provides": ["A"], "routes": []}}},
        }

        issues = finalize_generated_project(tmp_path, architecture, {"a.py": ""})

        assert issues
        assert warnings


class TestRecordGenerated:
    def test_normalizes_backslashes_and_truncates(self):
        context = {}

        record_generated_signature(context, "app\\main.py", "def run():\n    pass\n")

        assert "app/main.py" in context["generated_signatures"]

    def test_empty_content_is_stored(self):
        context = {}

        record_generated_signature(context, "a.py", "")

        assert context["generated_signatures"]["a.py"] == ""

    def test_remember_uses_project_architecture(self):
        context = {
            "architecture": {
                "symbol_table": {"files": {"a.py": {"provides": ["A"], "routes": []}}}
            }
        }

        issues = remember_generated_file(context, "a.py", "x = 1\n")

        assert any("missing frozen symbol A" in item for item in issues)

    def test_remember_without_architecture(self):
        assert remember_generated_file({}, "a.py", "x = 1\n") == []
