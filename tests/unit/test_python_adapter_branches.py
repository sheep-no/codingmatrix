"""Branch coverage for PythonLanguageAdapter."""

from __future__ import annotations

import ast
import sys
import textwrap

import pytest

from app.agent.adapters.language_adapter import ImportInfo
from app.agent.adapters.python import PythonLanguageAdapter


@pytest.fixture
def adapter():
    return PythonLanguageAdapter()


class TestParseImports:
    def test_empty_content_returns_empty(self, adapter):
        assert adapter.parse_imports("") == []

    def test_skips_comment_only_and_inline_comment_lines(self, adapter):
        content = "# comment\nimport os  # trailing\nfrom typing import List  # t\n#\n"

        imports = adapter.parse_imports(content)

        assert [item.module for item in imports] == ["os", "typing"]
        assert imports[0].raw_line == "import os"

    def test_relative_and_alias_forms(self, adapter):
        content = "from ..models import (User, Post as P)\nimport app.services as svc\n"

        imports = adapter.parse_imports(content)

        assert imports[0].is_relative is True
        assert imports[0].level == 2
        assert imports[0].module == "models"
        assert imports[0].symbols == ["User", "P"]
        assert imports[1].alias == "svc"

    def test_import_symbols_handles_star_and_blank_alias(self, adapter):
        assert adapter._parse_import_symbols("*, a") == ["*", "a"]
        assert adapter._parse_import_symbols("a as b") == ["b"]
        assert adapter._parse_import_symbols(" , b ,") == ["b"]


class TestSourceDiagnostics:
    def test_syntax_error_returns_empty(self, adapter):
        assert adapter.source_diagnostics("def broken(") == ()

    def test_star_import_suppresses_undefined_names(self, adapter):
        assert adapter.source_diagnostics("from os import *\nfoo()\n") == ()

    def test_reports_undefined_global_and_forward_annotation(self, adapter):
        content = "def f() -> Later:\n    return missing_name\nclass Later:\n    pass\n"

        diagnostics = adapter.source_diagnostics(content)

        assert any("undefined global names" in item for item in diagnostics)
        assert any("annotations before definitions" in item for item in diagnostics)

    def test_reports_unavailable_import_symbols(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"exists"})),
        )

        diagnostics = adapter.source_diagnostics("from json import missing\n")

        assert any("does not export" in item for item in diagnostics)

    def test_reports_incompatible_local_constructors(self, adapter):
        content = "class Plain:\n    pass\nPlain(1)\n"

        diagnostics = adapter.source_diagnostics(content)

        assert any("constructor arguments" in item for item in diagnostics)

    def test_unavailable_symbols_skips_project_and_unknown_modules(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "is_project_module", lambda module: module == "app")

        assert adapter.source_diagnostics(
            "from app import missing\nfrom unknown_mod import nope\n"
        ) == ()

    def test_unavailable_symbols_skips_untracked_module_without_exports(
        self, adapter, monkeypatch
    ):
        monkeypatch.setattr(adapter, "is_project_module", lambda module: False)
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: None),
        )

        assert adapter.source_diagnostics("from json import missing\n") == ()

    def test_deferred_annotations_skip_forward_annotation_check(self, adapter):
        content = (
            "from __future__ import annotations\n"
            "def f() -> Later:\n    pass\nclass Later:\n    pass\n"
        )

        assert adapter.source_diagnostics(content) == ()

    def test_contract_facts_syntax_error(self, adapter):
        facts = adapter.extract_contract_facts("class Broken(")

        assert "base_classes" not in facts


class TestContractFacts:
    def test_collects_base_classes(self, adapter):
        content = "class Child(Base, mod.Mixin):\n    pass\n"

        facts = adapter.extract_contract_facts(content)

        assert facts["base_classes"] == ("Base", "Mixin")


class TestRepair:
    def test_syntax_error_returns_none(self, adapter):
        assert adapter.repair_source("def broken(", "a.py", ("does not export",)) is None

    def test_removes_unused_unavailable_imports(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"kept"})),
        )
        content = "from json import kept, missing\nuse(kept)\n"

        repaired = adapter.repair_source(content, "a.py", ("does not export",))

        assert repaired is not None
        assert "missing" not in repaired
        assert "kept" in repaired

    def test_keeps_retained_imports_when_removing(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"kept"})),
        )
        content = "from json import kept, missing as m\n"

        repaired = adapter.repair_source(content, "a.py", ("does not export",))

        assert repaired == "from json import kept\n"

    def test_drops_whole_import_when_all_symbols_removed(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset()),
        )
        content = "from json import missing\n"

        repaired = adapter.repair_source(content, "a.py", ("does not export",))

        assert repaired.strip() == ""

    def test_adds_uniquely_available_imports(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"helper"})),
        )
        content = "from json import dumps\nhelper()\n"

        repaired = adapter.repair_source(
            content, "a.py", ("uses undefined global names",)
        )

        assert "import dumps, helper" in repaired

    def test_defers_annotations_when_flagged(self, adapter):
        content = "def f() -> Later:\n    pass\nclass Later:\n    pass\n"

        repaired = adapter.repair_source(
            content, "a.py", ("evaluates annotations before definitions",)
        )

        assert repaired.startswith("from __future__ import annotations")


class TestRemoveUnavailableImports:
    def test_syntax_error_returns_content(self, adapter):
        content = "def broken("
        assert adapter._remove_unused_unavailable_imports(content, "a.py") == content

    def test_without_unavailable_symbols_returns_content(self, adapter):
        content = "from json import dumps\n"
        assert adapter._remove_unused_unavailable_imports(content, "a.py") == content

    def test_ignores_nodes_without_module(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset()),
        )
        content = "from . import missing\nfrom json import missing2\n"

        result = adapter._remove_unused_unavailable_imports(content, "a.py")

        assert "from . import missing" in result
        assert "missing2" not in result

    def test_keeps_referenced_missing_symbols(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset()),
        )
        content = "from json import used_missing\nused_missing()\n"

        assert adapter._remove_unused_unavailable_imports(content, "a.py") == content

    def test_ignores_import_without_missing_symbols(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"present"})),
        )
        content = "from json import present\n"

        assert adapter._remove_unused_unavailable_imports(content, "a.py") == content

    def test_second_import_without_missing_symbols_is_skipped(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset() if module == "json" else None),
        )
        content = "from json import missing\nfrom os import path\n"

        result = adapter._remove_unused_unavailable_imports(content, "a.py")

        assert "from os import path" in result
        assert "missing" not in result


class TestAddAvailableImports:
    def test_syntax_error_returns_content(self, adapter):
        assert adapter._add_uniquely_available_imports("def broken(", "a.py") == "def broken("

    def test_skips_project_and_star_imports(self, adapter, monkeypatch):
        # Only the json import is a candidate; the star import must be ignored.
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: frozenset({"helper"})),
        )
        content = "from json import *\nhelper()\n"

        assert adapter._add_uniquely_available_imports(content, "a.py") == content

    def test_multiple_modules_do_not_add_symbol(self, adapter, monkeypatch):
        exports = {"json": frozenset({"helper"}), "os": frozenset({"helper"})}
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: exports.get(module)),
        )
        content = "from json import dumps\nfrom os import path\nhelper()\n"

        assert adapter._add_uniquely_available_imports(content, "a.py") == content

    def test_module_without_exports_is_ignored(self, adapter, monkeypatch):
        monkeypatch.setattr(
            adapter,
            "_static_module_exports",
            staticmethod(lambda module: None),
        )
        content = "from json import dumps\nhelper()\n"

        assert adapter._add_uniquely_available_imports(content, "a.py") == content


class TestStaticModuleExports:
    def test_unknown_module_returns_none(self, adapter):
        assert adapter._static_module_exports("definitely_not_a_module_xyz") is None

    def test_read_failure_returns_none(self, adapter, tmp_path, monkeypatch):
        target = tmp_path / "brokenmod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        def paths():
            return {"stdlib": str(tmp_path)}

        monkeypatch.setattr("app.agent.adapters.python.sysconfig.get_paths", paths)

        def boom(self, *args, **kwargs):
            raise OSError("unreadable")

        monkeypatch.setattr("pathlib.Path.read_text", boom)

        assert adapter._static_module_exports("brokenmod") is None

    def test_module_with_getattr_returns_none(self, adapter, tmp_path, monkeypatch):
        (tmp_path / "dynamic_mod.py").write_text(
            "def __getattr__(name):\n    return None\n", encoding="utf-8"
        )
        monkeypatch.setattr(
            "app.agent.adapters.python.sysconfig.get_paths",
            lambda: {"stdlib": str(tmp_path)},
        )

        assert adapter._static_module_exports("dynamic_mod") is None

    def test_module_with_star_import_returns_none(self, adapter, tmp_path, monkeypatch):
        (tmp_path / "star_mod.py").write_text("from os import *\n", encoding="utf-8")
        monkeypatch.setattr(
            "app.agent.adapters.python.sysconfig.get_paths",
            lambda: {"stdlib": str(tmp_path)},
        )

        assert adapter._static_module_exports("star_mod") is None


class TestEagerAnnotations:
    def test_imports_become_available(self, adapter):
        tree = ast.parse(
            textwrap.dedent(
                """
                import json
                from typing import List
                def f(x: json.JSONDecoder, y: List[str]) -> None:
                    pass
                """
            )
        )

        assert adapter._eager_forward_annotation_names(tree) == set()

    def test_function_argument_variants_and_returns(self, adapter):
        tree = ast.parse(
            textwrap.dedent(
                """
                def f(a: Later, /, *args: Later, b: Later = 1, **kwargs: Later) -> Later:
                    pass
                class Later:
                    pass
                """
            )
        )

        assert adapter._eager_forward_annotation_names(tree) == {"Later"}

    def test_class_annotations_and_module_level_annassign(self, adapter):
        tree = ast.parse(
            textwrap.dedent(
                """
                class Holder:
                    item: Later
                value: Later
                class Later:
                    pass
                """
            )
        )

        assert adapter._eager_forward_annotation_names(tree) == {"Later"}

    def test_module_assign_marks_name_available(self, adapter):
        tree = ast.parse("Later = object\nvalue: Later\n")

        assert adapter._eager_forward_annotation_names(tree) == set()

    def test_function_without_return_annotation(self, adapter):
        tree = ast.parse("def f():\n    pass\n")

        assert adapter._eager_forward_annotation_names(tree) == set()


class TestDeferAnnotations:
    def test_syntax_error_returns_none(self, adapter):
        assert adapter.defer_annotations("def broken(") is None

    def test_already_deferred_returns_none(self, adapter):
        content = "from __future__ import annotations\n"
        assert adapter.defer_annotations(content) is None

    def test_inserts_after_module_docstring(self, adapter):
        content = '"""doc"""\nx: Later = 1\n'

        result = adapter.defer_annotations(content)

        assert result.splitlines()[0] == '"""doc"""'
        assert result.splitlines()[1] == "from __future__ import annotations"

    def test_inserts_at_top_without_docstring(self, adapter):
        assert adapter.defer_annotations("x = 1\n").startswith(
            "from __future__ import annotations"
        )

    def test_non_string_first_statement_inserts_at_top(self, adapter):
        result = adapter.defer_annotations("foo()\nx = 1\n")

        assert result.startswith("from __future__ import annotations")


class TestResolveImports:
    def test_relative_module_without_name(self, adapter):
        info = ImportInfo(module="", symbols=["utils"], is_relative=True, level=1)

        assert adapter.resolve_import_to_file(info, "app/api/views.py") == [
            "app/api/utils.py",
            "app/api/utils/__init__.py",
        ]

    def test_absolute_symbol_without_module_has_no_candidates(self, adapter):
        info = ImportInfo(module="", symbols=[], is_relative=False, level=0)

        assert adapter.resolve_import_to_file(info, "a.py") == []

    def test_absolute_and_relative_modules(self, adapter):
        absolute = ImportInfo(module="app.models", symbols=[], is_relative=False, level=0)
        relative = ImportInfo(module="models", symbols=[], is_relative=True, level=2)

        assert adapter.resolve_import_to_file(absolute, "app/main.py") == [
            "app/models.py",
            "app/models/__init__.py",
        ]
        assert adapter.resolve_import_to_file(relative, "app/api/views.py") == [
            "app/models.py",
            "app/models/__init__.py",
        ]


class TestInferFileType:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("app/__init__.py", "config"),
            ("app/test_routes.py", "test"),
            ("app/routes_test.py", "test"),
            ("app/services/user.py", "service"),
            ("app/repositories/user.py", "repository"),
            ("app/models/user.py", "model"),
            ("app/api/routes.py", "api"),
            ("app/utils/helper.py", "utils"),
            ("app/schemas/user.py", "schema"),
            ("app/config/settings.py", "config"),
            ("app/settings.py", "config"),
            ("app/misc/thing.py", "unknown"),
        ],
    )
    def test_infers_expected_type(self, adapter, path, expected):
        assert adapter.infer_file_type(path) == expected

    def test_directory_rule_without_leading_slash(self, adapter):
        assert adapter.infer_file_type("templates/index.html") == "template"


class TestDefinitions:
    def test_skips_import_aliases_as_variables(self, adapter):
        content = "import os\nfrom json import dumps\nVALUE = 1\nlower = 2\n"

        definitions = adapter.extract_definitions(content)

        assert "VALUE" in definitions and definitions["VALUE"].symbol_type == "constant"
        assert "lower" in definitions and definitions["lower"].symbol_type == "variable"
        assert "import" not in definitions

    def test_ignores_indented_and_comment_lines(self, adapter):
        content = "# comment\n    def inner():\n        pass\n"

        assert adapter.extract_definitions(content) == {}

    def test_private_definitions_are_not_exported(self, adapter):
        content = "_private = 1\ndef _hidden():\n    pass\n"

        definitions = adapter.extract_definitions(content)

        assert definitions["_private"].is_exported is False
        assert definitions["_hidden"].is_exported is False

    def test_directory_rules_cover_all_categories(self, adapter):
        expectations = {
            "pkg/models/user.py": "model",
            "pkg/api/routes.py": "api",
            "pkg/services/user.py": "service",
            "pkg/dao/user.py": "repository",
            "pkg/common/thing.py": "utils",
            "pkg/test/thing.py": "test",
            "pkg/conf/thing.py": "config",
            "pkg/dto/thing.py": "schema",
            # Uppercase segments bypass the case-sensitive PATH_TYPE_RULES
            "pkg/ENTITIES/User.py": "model",
            "pkg/ROUTERS/Routes.py": "api",
            "pkg/SERVICE/User.py": "service",
            "pkg/REPOS/User.py": "repository",
            "pkg/COMMON/Thing.py": "utils",
            "pkg/TESTS/Thing.py": "test",
            "pkg/CONF/Thing.py": "config",
            "pkg/DTO/Thing.py": "types",
        }

        for path, expected in expectations.items():
            assert adapter.infer_file_type(path) == expected, path


class TestValidateStructureBranches:
    def test_existing_init_returns_no_missing(self, adapter):
        assert adapter.validate_package_structure("app", {"app/__init__.py": ""}) == []

    def test_source_without_init_reports_missing(self, adapter):
        files = {"pkg/mod.py": "x = 1\n"}

        assert adapter.validate_package_structure("pkg", files) == ["pkg/__init__.py"]


class TestProjectModules:
    def test_empty_module_name(self, adapter):
        assert adapter.is_project_module("") is False

    def test_relative_module_is_project(self, adapter):
        assert adapter.is_project_module(".local") is True

    @pytest.mark.parametrize(
        ("module", "expected"),
        [
            ("os.path", False),
            ("fastapi", False),
            ("app.services", True),
            ("core.utils", True),
        ],
    )
    def test_project_detection(self, adapter, module, expected):
        assert adapter.is_project_module(module) is expected

    def test_extension_package_files(self, adapter):
        assert adapter.get_package_init_file("app") == "app/__init__.py"
        assert adapter.get_required_package_files("app") == ["app/__init__.py"]

    def test_validate_package_structure_requires_source_extension(self, adapter):
        files = {"app/style.css": "body {}"}

        assert adapter.validate_package_structure("app", files) == []
