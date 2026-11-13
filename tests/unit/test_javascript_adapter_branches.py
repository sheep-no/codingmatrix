"""JavaScriptLanguageAdapter 导入解析与符号提取的分支补测。"""

from app.agent.adapters import ImportInfo, JavaScriptLanguageAdapter


def test_parse_imports_returns_empty_for_blank_content():
    adapter = JavaScriptLanguageAdapter()
    assert adapter.parse_imports("", "src/a.js") == []


def test_parse_imports_skips_blank_and_comment_lines():
    adapter = JavaScriptLanguageAdapter()
    imports = adapter.parse_imports(
        "\n// import a from 'a'\n/* import b from 'b' */\n",
        "src/a.js",
    )
    assert imports == []


def test_parse_imports_handles_default_named_and_namespace_forms():
    adapter = JavaScriptLanguageAdapter()
    imports = adapter.parse_imports(
        "import React from 'react'\n"
        "import { a, b as c } from './local'\n"
        "import * as ns from '../shared/ns'\n",
        "src/App.jsx",
    )

    assert imports[0].module == "react"
    assert imports[0].symbols == ["React"]
    assert imports[0].is_relative is False

    assert imports[1].module == "./local"
    assert imports[1].symbols == ["a", "c"]
    assert imports[1].is_relative is True

    assert imports[2].module == "../shared/ns"
    assert imports[2].symbols == ["ns"]


def test_parse_imports_handles_side_effect_and_dynamic_imports():
    adapter = JavaScriptLanguageAdapter()
    imports = adapter.parse_imports(
        "import './styles.css'\n"
        "const mod = await import('./lazy')\n",
        "src/App.js",
    )

    assert imports[0].module == "./styles.css"
    assert imports[0].symbols == []
    assert imports[1].module == "./lazy"
    assert imports[1].is_relative is True


def test_parse_imports_handles_require_variants():
    adapter = JavaScriptLanguageAdapter()
    imports = adapter.parse_imports(
        "const fs = require('fs')\n"
        "const { join, resolve: r } = require('path')\n",
        "src/index.js",
    )

    assert imports[0].module == "fs"
    assert imports[0].symbols == ["fs"]
    assert imports[0].is_relative is False

    assert imports[1].module == "path"
    assert imports[1].symbols == ["join", "resolve: r"]


def test_resolve_import_to_file_returns_empty_without_module():
    adapter = JavaScriptLanguageAdapter()
    assert adapter.resolve_import_to_file(
        ImportInfo(module="", symbols=[], is_relative=False), "src/a.js"
    ) == []


def test_resolve_import_to_file_handles_relative_without_parent_dir():
    adapter = JavaScriptLanguageAdapter()
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="./sibling", symbols=[], is_relative=True), "index.js"
    )
    assert "sibling.js" in candidates
    assert "sibling/index.js" in candidates


def test_resolve_import_to_file_appends_extensions_for_alias():
    adapter = JavaScriptLanguageAdapter()
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="@/components/Card", symbols=[], is_relative=False),
        "src/App.jsx",
    )
    assert "src/components/Card.js" in candidates
    assert "src/components/Card/index.tsx" in candidates


def test_resolve_import_to_file_strips_js_extension_and_keeps_non_js_suffix():
    adapter = JavaScriptLanguageAdapter()
    js_candidates = adapter.resolve_import_to_file(
        ImportInfo(module="@/utils/format.ts", symbols=[], is_relative=False),
        "src/App.jsx",
    )
    assert "src/utils/format.js" in js_candidates
    assert "src/utils/format.ts.ts" not in js_candidates

    vue_candidates = adapter.resolve_import_to_file(
        ImportInfo(module="@/components/Card.vue", symbols=[], is_relative=False),
        "src/App.jsx",
    )
    assert "src/components/Card.vue" in vue_candidates


def test_resolve_import_to_file_handles_src_prefixed_modules():
    adapter = JavaScriptLanguageAdapter()
    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="src/utils/format.ts", symbols=[], is_relative=False),
        "src/App.jsx",
    )
    assert "src/utils/format.js" in candidates


def test_infer_file_type_supports_directory_rule_pattern(monkeypatch):
    adapter = JavaScriptLanguageAdapter()
    monkeypatch.setattr(
        adapter,
        "PATH_TYPE_RULES",
        [("screens/", "page"), (".spec.", "test")],
    )

    assert adapter.infer_file_type("app/screens/Home.tsx") == "page"
    assert adapter.infer_file_type("screens/Home.tsx") == "page"
    assert adapter.infer_file_type("app/unit.spec.ts") == "test"


def test_infer_file_type_directory_inference_covers_all_branches(monkeypatch):
    adapter = JavaScriptLanguageAdapter()
    monkeypatch.setattr(adapter, "PATH_TYPE_RULES", [])

    expected = {
        "x/models/a.ts": "model",
        "x/api/a.ts": "api",
        "x/services/a.ts": "service",
        "x/components/a.ts": "component",
        "x/pages/a.ts": "page",
        "x/utils/a.ts": "utils",
        "x/tests/a.ts": "test",
        "x/hooks/a.ts": "hook",
        "x/other/a.ts": "unknown",
    }
    for path, file_type in expected.items():
        assert adapter.infer_file_type(path) == file_type


def test_resolve_import_to_file_returns_empty_for_bare_package():
    adapter = JavaScriptLanguageAdapter()
    assert adapter.resolve_import_to_file(
        ImportInfo(module="lodash", symbols=[], is_relative=False), "src/a.js"
    ) == []


def test_infer_file_type_matches_path_rules_and_directory_names():
    adapter = JavaScriptLanguageAdapter()

    assert adapter.infer_file_type("package.json") == "config"
    assert adapter.infer_file_type("src/main.ts") == "entry"
    assert adapter.infer_file_type("src/__tests__/a.js") == "test"
    assert adapter.infer_file_type("src/components/Button.tsx") == "component"
    assert adapter.infer_file_type("src/models/user.ts") == "model"
    assert adapter.infer_file_type("src/services/user.ts") == "service"
    assert adapter.infer_file_type("src/hooks/useAuth.ts") == "hook"
    assert adapter.infer_file_type("src/utils/format.ts") == "utils"
    assert adapter.infer_file_type("src/pages/Home.tsx") == "page"
    assert adapter.infer_file_type("src/api/client.ts") == "api"
    assert adapter.infer_file_type("src/unknown/thing.ts") == "unknown"


def test_extract_definitions_handles_all_symbol_kinds():
    adapter = JavaScriptLanguageAdapter()

    definitions = adapter.extract_definitions(
        "// export const ignored = 1\n"
        "export async function fetchData(id) {}\n"
        "export const arrow = async (x) => x\n"
        "export class Widget {}\n"
        "export interface Props { a: string }\n"
        "export type Id = string\n"
        "export { localA, localB as b }\n"
        "const plain = 1\n"
    )

    assert definitions["fetchData"].symbol_type == "function"
    assert definitions["fetchData"].signature == "id"
    assert definitions["arrow"].symbol_type == "function"
    assert definitions["Widget"].symbol_type == "class"
    assert definitions["Props"].symbol_type == "interface"
    assert definitions["Id"].symbol_type == "type"
    assert definitions["localA"].symbol_type == "export"
    assert definitions["b"].symbol_type == "export"
    assert definitions["plain"].symbol_type == "variable"
    assert definitions["plain"].is_exported is False


def test_extract_definitions_ignores_arrow_variables_duplicates():
    adapter = JavaScriptLanguageAdapter()
    definitions = adapter.extract_definitions("export const compute = () => 42\n")
    assert definitions["compute"].symbol_type == "function"


def test_extract_definitions_skips_trailing_empty_export_and_arrow_like_variable():
    adapter = JavaScriptLanguageAdapter()
    definitions = adapter.extract_definitions(
        "export { alpha, }\nconst config = { handler: () => 1 }\n"
    )
    assert definitions["alpha"].symbol_type == "export"
    assert "config" not in definitions


def test_get_package_init_file_uses_index_js():
    adapter = JavaScriptLanguageAdapter()
    assert adapter.get_package_init_file("src/components") == "src/components/index.js"


def test_is_project_module_distinguishes_relative_alias_and_packages():
    adapter = JavaScriptLanguageAdapter()

    assert adapter.is_project_module("") is False
    assert adapter.is_project_module("./local") is True
    assert adapter.is_project_module("@/components/Card") is True
    assert adapter.is_project_module("src/utils/format") is True
    assert adapter.is_project_module("node:fs") is False
    assert adapter.is_project_module("path") is False
    assert adapter.is_project_module("@scope/pkg") is False
    assert adapter.is_project_module("some-lib") is False
