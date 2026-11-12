"""GenericLanguageAdapter 全分支回归。"""

import pytest

from app.agent.adapters.generic import GenericLanguageAdapter
from app.agent.adapters.language_adapter import ImportInfo


@pytest.fixture
def adapter():
    return GenericLanguageAdapter()


def test_set_file_plan_data_skips_empty_paths(adapter):
    adapter.set_file_plan_data(
        [{"path": "src/main.go"}, {"path": ""}, {"no_path": 1}]
    )
    assert set(adapter._file_plan_data) == {"src/main.go"}


def test_parse_imports_prefers_file_plan(adapter):
    adapter.set_file_plan_data(
        [{"path": "main.go", "imports": ["fmt", {"module": "os", "symbols": ["Open"]}]}]
    )
    imports = adapter.parse_imports("package main", "main.go")
    assert [i.module for i in imports] == ["fmt", "os"]
    assert imports[0].is_relative is False
    assert imports[1].symbols == ["Open"]


def test_parse_imports_relative_plan_entry(adapter):
    adapter.set_file_plan_data(
        [
            {
                "path": "lib.rs",
                "imports": ["./mod", {"module": ".local", "is_relative": True}],
            }
        ]
    )
    imports = adapter.parse_imports("", "lib.rs")
    assert imports[0].is_relative is True
    assert imports[1].is_relative is True


def test_parse_imports_guess_fallback(adapter):
    content = "\n".join(
        [
            '#include <vector>',
            '#include "mylib.h"',
            "import com.example.Foo;",
            "require('lodash')",
            "using System.Text;",
            "use crate::module;",
            "from mypkg.sub import thing",
            'import "github.com/x/y"',
            "// import ignored",
            "# import ignored",
            "/* import ignored */",
        ]
    )
    modules = [i.module for i in adapter.parse_imports(content)]
    assert "vector" in modules
    assert "mylib.h" in modules
    assert "com.example.Foo" in modules
    assert "lodash" in modules
    assert "System.Text" not in modules  # System 前缀被判为标准库
    assert "crate::module" in modules
    assert "mypkg.sub" in modules
    assert "github.com/x/y" in modules
    assert "ignored" not in modules


def test_parse_imports_skips_lines_without_match(adapter):
    imports = adapter.parse_imports("x = 1\ny = 2\ndef f(): pass")
    assert imports == []


def test_parse_imports_empty_content(adapter):
    assert adapter.parse_imports("") == []


@pytest.mark.parametrize(
    "module,expected",
    [
        ("/usr/include/stdio.h", True),
        ("C:\\Windows\\x", True),
        ("std.io", True),
        ("system.core", True),
        ("core::mem", True),
        ("posix.unistd", True),
        ("win32.api", True),
        ("myapp.models", False),
    ],
)
def test_looks_like_stdlib(module, expected):
    assert GenericLanguageAdapter()._looks_like_stdlib(module) is expected


def test_resolve_import_empty_module(adapter):
    assert adapter.resolve_import_to_file(ImportInfo(module=""), "a.c") == []


def test_resolve_relative_import_returns_candidates(adapter):
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="util", is_relative=True), "src/main.c"
    )
    assert "src/util" in candidates
    assert "src/util.c" in candidates
    assert "src/util.hpp" not in candidates

    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="util", is_relative=True), "main.c"
    )
    assert candidates == []


def test_resolve_absolute_import_matches_plan_and_extensions(adapter):
    adapter.set_file_plan_data(
        [{"path": "pkg/models/user.go"}, {"path": "pkg/models"}, {"path": "main"}]
    )
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="models"), "main.go"
    )
    assert "pkg/models" in candidates
    assert "models.go" in candidates
    assert len(candidates) == len(set(candidates))


def test_resolve_absolute_import_without_extensions(adapter):
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="app.core"), "main.c"
    )
    assert "app/core" in candidates
    assert "app/core.cpp" in candidates
    assert "app/core.swift" in candidates


def test_resolve_import_deduplicates_candidates(adapter):
    adapter.set_file_plan_data([{"path": "app/core"}])
    candidates = adapter.resolve_import_to_file(ImportInfo(module="app.core"), "main.c")
    assert candidates.count("app/core") == 1

    adapter.set_file_plan_data([{"path": "main"}])
    candidates = adapter.resolve_import_to_file(ImportInfo(module="main"), "x.c")
    assert candidates.count("main") == 1


def test_parse_plan_imports_ignores_unknown_entry_types(adapter):
    adapter.set_file_plan_data([{"path": "main.go", "imports": [123, {"module": "os"}]}])
    imports = adapter.parse_imports("", "main.go")
    assert [i.module for i in imports] == ["os"]


def test_infer_file_type_prefers_plan(adapter):
    adapter.set_file_plan_data([{"path": "weird.zzz", "file_type": "custom"}])
    assert adapter.infer_file_type("weird.zzz") == "custom"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("Makefile", "config"),
        (".env.example", "env"),
        ("docs/README.md", "readme"),
        ("src/main.c", "source"),
        ("lib/thing.unknown", "library"),
        ("internal/x.unknown", "internal"),
        ("assets/logo.xyz", "assets"),
        ("include/foo.h", "header"),
        ("foo.unknown", "unknown"),
    ],
)
def test_infer_file_type_patterns(adapter, path, expected):
    assert adapter.infer_file_type(path) == expected


def test_infer_file_type_plan_without_type_falls_through(adapter):
    adapter.set_file_plan_data([{"path": "Makefile", "file_type": ""}])
    assert adapter.infer_file_type("Makefile") == "config"


def test_infer_file_type_plain_source_line(adapter):
    assert adapter.infer_file_type("script") == "unknown"


def test_extract_definitions_functions_and_classes(adapter):
    content = "\n".join(
        [
            "// comment",
            "# comment",
            "/* comment */",
            "public static int calculate(int x) {",
            "def handler():",
            "fn rust_fn() {",
            "if (cond) {",
            "class Widget {",
            "public final class Service {",
            "struct Point",
            "_private_func() {",
            "x = 1",
        ]
    )
    defs = adapter.extract_definitions(content)
    assert defs["calculate"].symbol_type == "function"
    assert defs["calculate"].line_number == 4
    assert defs["handler"].symbol_type == "function"
    assert defs["rust_fn"].symbol_type == "function"
    assert "_private_func".startswith("_")
    assert defs["_private_func"].is_exported is False
    assert defs["Widget"].symbol_type == "class"
    assert defs["Service"].symbol_type == "class"
    assert defs["Point"].symbol_type == "class"
    assert "if" not in defs


def test_extract_definitions_empty_content(adapter):
    assert adapter.extract_definitions("") == {}


def test_extract_definitions_exported_public(adapter):
    defs = adapter.extract_definitions("function visible() {")
    assert defs["visible"].is_exported is True


def test_package_helpers(adapter):
    assert adapter.get_package_init_file("pkg") == ""
    assert adapter.validate_package_structure("pkg", {}) == []


def test_is_project_module(adapter):
    adapter.set_file_plan_data([{"path": "app.models"}, {"path": "app/core/x.go"}])
    assert adapter.is_project_module("") is False
    assert adapter.is_project_module("app.models") is True
    assert adapter.is_project_module("app.core") is True
    assert adapter.is_project_module("other") is False


def test_get_imports_from_file_plan(adapter):
    adapter.set_file_plan_data([{"path": "main.go", "imports": ["fmt"]}])
    imports = adapter.get_imports_from_file_plan("main.go")
    assert [i.module for i in imports] == ["fmt"]
    assert adapter.get_imports_from_file_plan("missing.go") == []


def test_registry_registration():
    from app.agent.adapters.language_adapter import LanguageAdapterRegistry

    assert isinstance(LanguageAdapterRegistry._adapters["generic"], GenericLanguageAdapter)
