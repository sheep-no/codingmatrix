"""CrossValidator 分支补测：聚焦解析兜底、匹配回退与 LLM 修复链路。"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agent.cross_validator import (
    CrossValidator,
    SymbolInfo,
    _identifier_tokens,
    _load_cross_validation_config,
    _matches_critical_pattern,
    is_review_timeout,
    select_llm_fix_issues,
)
from app.agent.shared_context import SharedContext


def _plain_validator() -> CrossValidator:
    return CrossValidator(SharedContext("test", Path(".")))


def _python_validator() -> CrossValidator:
    from app.agent.adapters.python import PythonLanguageAdapter

    return CrossValidator(
        SharedContext("test", Path(".")), language_adapter=PythonLanguageAdapter()
    )


def _js_validator() -> CrossValidator:
    from app.agent.adapters.javascript import JavaScriptLanguageAdapter

    return CrossValidator(
        SharedContext("test", Path(".")), language_adapter=JavaScriptLanguageAdapter()
    )


class TestModuleHelpers:
    def test_identifier_tokens_skip_empty_segments(self):
        assert _identifier_tokens(" app//auth.py ") == {"app", "auth", "py"}
        assert _identifier_tokens("") == set()

    def test_identifier_tokens_split_camel_and_upper(self):
        assert _identifier_tokens("HTTPServer") == {"http", "server"}
        assert _identifier_tokens("authServiceV2") == {"auth", "service", "v", "2"}

    def test_matches_critical_pattern_plural_forms(self):
        assert _matches_critical_pattern({"orders"}, "order") is True
        assert _matches_critical_pattern({"cryptography"}, "crypto") is True
        assert _matches_critical_pattern({"random"}, "order") is False

    def test_select_llm_fix_issues_limits_per_file_and_total(self):
        issues = [
            {"type": "symbol_not_found", "file": "a.py", "message": f"m{i}"}
            for i in range(30)
        ]
        selected = select_llm_fix_issues(issues, max_issues=5, max_issues_per_file=3)
        assert len(selected) == 3

    def test_select_llm_fix_issues_stops_at_max_issues(self):
        issues = [
            {"type": "import_error", "file": f"f{i}.py", "message": f"m{i}"}
            for i in range(30)
        ]
        assert len(select_llm_fix_issues(issues, max_issues=4, max_files=30)) == 4

    def test_select_llm_fix_issues_skips_new_files_over_limit(self):
        issues = [
            {"type": "import_error", "file": f"f{i}.py", "message": f"m{i}"}
            for i in range(6)
        ]
        selected = select_llm_fix_issues(issues, max_files=2, max_issues=20)
        assert {issue["file"] for issue in selected} == {"f0.py", "f1.py"}

    def test_select_llm_fix_issues_handles_missing_fields(self):
        issues = [{"type": "import_error"}, {"type": "import_error"}]
        assert len(select_llm_fix_issues(issues)) == 1

    def test_is_review_timeout_detects_httpx_timeout(self):
        import httpx

        assert is_review_timeout(httpx.ConnectTimeout("slow")) is True

    def test_is_review_timeout_detects_text(self):
        assert is_review_timeout(RuntimeError("request Timeout")) is True
        assert is_review_timeout(RuntimeError("请求超时")) is True
        assert is_review_timeout(RuntimeError("bad request")) is False

    def test_load_config_returns_empty_on_error(self, monkeypatch):
        import app.agent.cross_validator as module

        monkeypatch.setattr(module.Path, "exists", lambda self: True)
        monkeypatch.setattr(
            "app.utils.model_config_io.load_model_config",
            lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert _load_cross_validation_config() == {}

    def test_load_config_returns_empty_when_file_missing(self, monkeypatch):
        import app.agent.cross_validator as module

        monkeypatch.setattr(module.Path, "exists", lambda self: False)
        assert _load_cross_validation_config() == {}


class TestValidateAndSelectBranches:
    def _run(self, validator, content, payload=None):
        calls = {"n": 0}

        async def fake_llm(**_kwargs):
            calls["n"] += 1
            if callable(content):
                return content(calls["n"])
            return {"choices": [{"message": {"content": content}}]}

        kwargs = dict(
            file_path="test.py",
            file_type="backend",
            description="d",
            version_a="A",
            model_a="model-a",
            version_b="B",
            model_b="model-b",
            judge_model="judge-model",
        )
        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            return asyncio.run(validator.validate_and_select(**kwargs))

    def test_selects_version_b(self):
        validator = _plain_validator()
        assert self._run(validator, '{"winner": "B", "reason": "better"}') == (
            "B",
            "model-b",
        )

    def test_merged_requires_final_code(self):
        validator = _plain_validator()
        with pytest.raises(ValueError, match="merged result had no final_code"):
            self._run(validator, '{"winner": "merged"}')

    def test_merged_returns_combined_model_label(self):
        validator = _plain_validator()
        result = self._run(
            validator, '{"winner": "merged", "final_code": "def f(): pass"}'
        )
        assert result == ("def f(): pass", "model-a+model-b")

    def test_invalid_winner_raises(self):
        validator = _plain_validator()
        with pytest.raises(ValueError, match="winner was invalid"):
            self._run(validator, '{"winner": "C"}')

    def test_retries_once_when_first_response_empty(self):
        validator = _plain_validator()

        def responses(n):
            content = "" if n == 1 else '{"winner": "A"}'
            return {"choices": [{"message": {"content": content}}]}

        assert self._run(validator, responses) == ("A", "model-a")

    def test_non_timeout_failure_is_retried(self):
        validator = _plain_validator()
        state = {"n": 0}

        async def fake_llm(**_kwargs):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("temporary")
            return {"choices": [{"message": {"content": '{"winner": "A"}'}}]}

        kwargs = dict(
            file_path="test.py",
            file_type="backend",
            description="d",
            version_a="A",
            model_a="model-a",
            version_b="B",
            model_b="model-b",
            judge_model="judge-model",
        )
        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator.validate_and_select(**kwargs)) == ("A", "model-a")
        assert state["n"] == 2

    def test_payload_error_is_wrapped(self):
        validator = _plain_validator()
        with patch.object(validator, "_extract_json", side_effect=RuntimeError("bad")):
            with pytest.raises(ValueError, match="judge failed"):
                self._run(validator, '{"winner": "A"}')

    def test_cross_validate_uses_judge_model_for_merged(self):
        validator = _plain_validator()
        captured = {}

        class Loop:
            async def refine(self, **kwargs):
                captured.update(kwargs)
                return "refined"

        async def fake_select(**_kwargs):
            return "code", "model-a+model-b"

        with patch.object(validator, "validate_and_select", side_effect=fake_select):
            result = asyncio.run(
                validator.cross_validate_with_refinement(
                    file_path="a.py",
                    file_type="backend",
                    description="d",
                    content_a="A",
                    model_a="model-a",
                    content_b="B",
                    model_b="model-b",
                    judge_model="judge-model",
                    refinement_loop=Loop(),
                )
            )
        assert result == "refined"
        assert captured["model_name"] == "judge-model"


class TestGenericDefinitions:
    def test_empty_content_returns_empty(self):
        assert _plain_validator()._extract_definitions_generic("") == {}

    def test_comments_and_blank_lines_are_skipped(self):
        defs = _plain_validator()._extract_definitions_generic(
            "\n// c\n# c\n/* c */\n"
        )
        assert defs == {}

    def test_keyword_named_function_is_ignored(self):
        defs = _plain_validator()._extract_definitions_generic("def if(a):\n")
        assert "if" not in defs

    def test_class_definition_is_parsed(self):
        defs = _plain_validator()._extract_definitions_generic("class Foo:\n")
        assert defs["Foo"].symbol_type == "class"

    def test_keyword_named_class_is_ignored(self):
        defs = _plain_validator()._extract_definitions_generic("class return:\n")
        assert "return" not in defs

    def test_indented_variable_is_ignored(self):
        defs = _plain_validator()._extract_definitions_generic("    x = 1\n")
        assert "x" not in defs

    def test_keyword_variable_is_ignored(self):
        defs = _plain_validator()._extract_definitions_generic("import = 1\n")
        assert "import" not in defs

    def test_private_symbols_not_exported(self):
        defs = _plain_validator()._extract_definitions_generic("_x = 1\n")
        assert defs["_x"].is_exported is False

    def test_adapter_failure_falls_back_to_generic(self):
        class Adapter:
            extensions = {".py"}

            def extract_definitions(self, content):
                raise RuntimeError("boom")

        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=Adapter()
        )
        defs = validator._extract_file_definitions("def alpha():\n    pass\n", "a.py")
        assert "alpha" in defs

    def test_empty_content_short_circuits(self):
        assert _plain_validator()._extract_file_definitions("") == {}


class TestSymbolSourceResolution:
    def test_missing_usage_file_returns_none(self):
        assert _plain_validator()._find_symbol_source("x", "missing.py", {}) is None

    def test_generic_from_import_resolves_module(self):
        files = {"pkg/helpers.py": "def x(): pass\n", "main.py": "from pkg.helpers import x\n"}
        assert _plain_validator()._find_symbol_source("x", "main.py", files) == "pkg/helpers.py"

    def test_generic_from_import_star_resolves_module(self):
        files = {"helpers.py": "def x(): pass\n", "main.py": "from helpers import *\n"}
        assert _plain_validator()._find_symbol_source("x", "main.py", files) == "helpers.py"

    def test_generic_import_quoted_resolves_module(self):
        files = {"helper.py": "x = 1\n", "main.py": 'import "helper"\n'}
        assert _plain_validator()._find_symbol_source("x", "main.py", files) == "helper.py"

    def test_rust_use_resolves_module(self):
        files = {"pkg/mod.py": "x = 1\n", "main.rs": "use pkg::mod\n"}
        assert _plain_validator()._find_symbol_source("x", "main.rs", files) == "pkg/mod.py"

    def test_unresolvable_import_returns_none(self):
        files = {"main.py": "from nowhere import x\n"}
        assert _plain_validator()._find_symbol_source("x", "main.py", files) is None

    def test_adapter_parse_imports_empty_falls_back_to_generic(self):
        from app.agent.adapters.python import PythonLanguageAdapter

        class Adapter(PythonLanguageAdapter):
            def parse_imports(self, content, file_path):
                return []

        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=Adapter()
        )
        files = {"pkg/helpers.py": "def x(): pass\n", "main.py": "from pkg.helpers import x\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "pkg/helpers.py"

    def test_adapter_quoted_import_falls_back_to_generic(self):
        from app.agent.adapters.python import PythonLanguageAdapter

        class Adapter(PythonLanguageAdapter):
            def parse_imports(self, content, file_path):
                return []

        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=Adapter()
        )
        files = {"helper.py": "x = 1\n", "main.py": 'import "helper"\n'}
        assert validator._find_symbol_source("x", "main.py", files) == "helper.py"

    def test_find_module_prefers_init_file(self):
        files = {"pkg/index.js": "x", "pkg/mod.js": "y"}
        result = _plain_validator()._find_module_in_files("pkg", files)
        assert result in {"pkg/index.js", "pkg/mod.js"}

    def test_find_module_exact_path_match(self):
        files = {"pkg/mod": "x"}
        assert _plain_validator()._find_module_in_files("pkg/mod", files) == "pkg/mod"

    def test_find_module_falls_back_to_default_extensions(self):
        validator = _plain_validator()
        assert validator._find_module_in_files("pkg.core", {"pkg/core.py": ""}) == "pkg/core.py"

    def test_find_module_default_extensions_when_none_collected(self):
        validator = _plain_validator()
        assert validator._find_module_in_files("pkg.core", {"pkg/mod": ""}) is None

    def test_find_module_without_extension_returns_none(self):
        assert _plain_validator()._find_module_in_files("a.b", {"a/c.py": ""}) is None

    def test_symbol_defined_in_missing_file_is_false(self):
        validator = _plain_validator()
        assert validator._symbol_defined_in_file("x", "missing.py", {"missing.py": ""}) is False

    def test_external_symbols_empty_without_adapter(self):
        assert _plain_validator()._external_imported_symbols("import os", "a.py") == set()

    def test_external_symbols_swallow_parse_errors(self):
        class Adapter:
            def parse_imports(self, content, path):
                raise RuntimeError("boom")

        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=Adapter()
        )
        assert validator._external_imported_symbols("import os", "a.py") == set()

    def test_external_symbols_include_alias(self):
        validator = _python_validator()
        symbols = validator._external_imported_symbols(
            "import numpy as np\nfrom fastapi import FastAPI\n", "a.py"
        )
        assert {"np", "FastAPI"} <= symbols


class TestSignatureFallbacks:
    def test_variadic_parameter_helper(self):
        validator = _plain_validator()
        assert validator._extract_function_params("a, *values, **options") == {"a": None}

    def test_self_and_cls_skipped(self):
        validator = _plain_validator()
        assert validator._extract_function_params("self, cls, a=1") == {"a": "1"}

    def test_call_params_skip_blank_and_positional(self):
        validator = _plain_validator()
        assert validator._extract_call_params("1, , b=2") == {"b"}

    def test_split_args_handles_escaped_quote(self):
        validator = _plain_validator()
        assert validator._split_top_level_args("'a\\'b', 2") == ["'a\\'b'", "2"]

    def test_split_args_handles_brackets(self):
        validator = _plain_validator()
        assert validator._split_top_level_args("[1, 2], {a: 3}") == ["[1, 2]", "{a: 3}"]

    def test_iter_call_sites_skips_unclosed_parenthesis(self):
        validator = _plain_validator()
        assert list(validator._iter_call_sites("call(1", "a.py")) == []

    def test_iter_call_sites_skips_attribute_and_decorator(self):
        validator = _plain_validator()
        assert list(validator._iter_call_sites("obj.call(1)\n@deco(2)\n", "a.py")) == []

    def test_signature_validation_without_adapter_skips_other_extensions(self):
        validator = _plain_validator()
        files = {"a.js": "function run(a, b) {}\nrun(1)\n"}
        assert validator._validate_function_signatures(files) == []

    def test_keyword_arg_name_escaped_quote(self):
        assert CrossValidator._keyword_arg_name('text="a\\"b"') == "text"
        assert CrossValidator._keyword_arg_name("'a\\'b'") is None

    def test_empty_argument_is_ignored(self):
        validator = _plain_validator()
        assert validator._extract_call_params(" , ") == set()
        assert validator._count_positional_args("") == 0

    def test_balanced_paren_returns_none_when_unclosed(self):
        assert CrossValidator._balanced_paren_body("call(1", 4) is None


class TestImportValidation:
    def test_empty_content_produces_no_generic_imports(self):
        assert _plain_validator()._extract_imports_generic("") == []

    def test_comment_lines_are_skipped(self):
        content = "// import a\n# import b\n/* import c */\n"
        assert _plain_validator()._extract_imports_generic(content) == []

    def test_generic_imports_cover_multiple_languages(self):
        content = "\n".join(
            [
                "from pkg.mod import x",
                'import "go/pkg"',
                "import java.util.List",
                "use crate::core",
                "#include <stdio.h>",
                "using System.Text;",
                "const x = require('node:fs')",
            ]
        )
        imports = _plain_validator()._extract_imports_generic(content)
        assert imports == [
            "pkg.mod",
            "go/pkg",
            "java.util.List",
            "crate::core",
            "stdio.h",
            "System.Text",
            "node:fs",
        ]

    def test_python_import_extraction(self):
        content = "# import skipped\nimport os\n\nfrom app import models\n"
        assert _plain_validator()._extract_python_imports(content) == ["os", "app"]

    def test_generic_relative_and_third_party_are_skipped(self):
        validator = _plain_validator()
        files = {"main.py": "from .local import x\nimport fastapi\n"}
        assert validator._validate_imports(files) == []

    def test_module_exists_via_adapter_resolution(self):
        validator = _python_validator()
        assert validator._module_exists_in_files("pkg.mod", {"pkg/mod.py": ""}) is True

    def test_module_exists_via_namespace_package(self):
        validator = _plain_validator()
        assert validator._module_exists_in_files("pkg", {"pkg/mod.py": ""}) is True

    def test_module_exists_false_for_empty_module(self):
        validator = _plain_validator()
        assert validator._package_dir_exists_in_files("", {"a.py": ""}) is False


class TestApiAndModelValidation:
    def _backend(self):
        return (
            "from fastapi import FastAPI\n"
            "from pydantic import BaseModel\n"
            "app = FastAPI()\n"
            "class ItemOut(BaseModel):\n"
            "    id: int\n"
            '@app.get("/api/items/{item_id}", response_model=ItemOut)\n'
            "def one(item_id: int):\n"
            "    return ItemOut(id=item_id)\n"
        )

    def test_frontend_template_endpoint_is_skipped(self):
        files = {
            "main.py": self._backend(),
            "src/api.js": "const res = await fetch(`/api/items/${id}`)\n",
        }
        assert _plain_validator()._extract_frontend_api_calls(files) == []

    def test_axios_response_fields_use_data_prefix(self):
        files = {
            "main.py": self._backend(),
            "src/api.js": (
                "export async function load() {\n"
                "  const res = await axios.get('/api/items/1')\n"
                "  return res.data.missing\n"
                "}\n"
            ),
        }
        issues = _plain_validator()._validate_api_contracts(files, {})
        assert any("missing" in issue["message"] for issue in issues)

    def test_path_parameter_route_matches(self):
        api = {"path": "/api/items/{item_id}", "response_fields": ["id"]}
        assert _plain_validator()._find_matching_api("/api/items/7", [api]) is api

    def test_subpath_route_matches(self):
        api = {"path": "/api/items", "response_fields": ["id"]}
        assert _plain_validator()._find_matching_api("/api/items/7/detail", [api]) is api

    def test_unmatched_endpoint_returns_none(self):
        api = {"path": "/api/items", "response_fields": ["id"]}
        assert _plain_validator()._find_matching_api("/api/other", [api]) is None

    def test_pydantic_and_sqlalchemy_models_are_extracted(self):
        files = {
            "models.py": (
                "from pydantic import BaseModel\n"
                "class Out(BaseModel):\n"
                "    id: int\n"
                "from sqlalchemy import Column\n"
                "class Row(Base):\n"
                "    id = Column(Integer)\n"
            )
        }
        models = _plain_validator()._extract_model_definitions(files)
        assert models["Out"]["type"] == "pydantic"
        assert models["Row"]["fields"] == ["id"]

    def test_base_like_class_without_columns_is_skipped(self):
        files = {
            "models.py": "class Custom(Base):\n    label = 'x'\n",
        }
        models = _plain_validator()._extract_model_definitions(files)
        assert models == {}

    def test_model_name_absent_from_content_is_skipped(self):
        files = {
            "models.py": "from pydantic import BaseModel\nclass Out(BaseModel):\n    id: int\n",
            "usage.py": "value = 1\n",
        }
        assert _plain_validator()._validate_model_consistency(files) == []

    def test_unbalanced_model_call_is_skipped(self):
        files = {
            "models.py": "from pydantic import BaseModel\nclass Out(BaseModel):\n    id: int\n",
            "usage.py": "Out(id=1\n",
        }
        assert _plain_validator()._validate_model_consistency(files) == []

    def test_non_identifier_field_is_skipped(self):
        files = {
            "models.py": "from pydantic import BaseModel\nclass Out(BaseModel):\n    id: int\n",
            "usage.py": "Out(1 + 2, self=1, id=2)\n",
        }
        assert _plain_validator()._validate_model_consistency(files) == []

    def test_nonexistent_file_returns_none(self):
        assert _plain_validator()._mask_python_noncode("x = 1", "a.js") == "x = 1"

    def test_syntax_error_returns_content(self):
        content = "def broken(:\n"
        assert _plain_validator()._mask_python_noncode(content, "a.py") == content


class TestValidateAndFixFlow:
    def test_no_issues_returns_inputs(self):
        validator = _plain_validator()
        files = {"a.py": "x = 1\n"}
        out, issues = asyncio.run(
            validator.validate_and_fix(files, {}, fix_model=None)
        )
        assert out is files and issues == []

    def test_without_fix_model_returns_issues(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        out, issues = asyncio.run(validator.validate_and_fix(files, {}))
        assert out == files
        assert issues

    def test_missing_modules_regenerated_then_revalidated(self):
        validator = _plain_validator()
        files = {"main.py": "from helper import x\n"}
        calls = {"n": 0}

        async def fake_generate(current, modules, architecture, model):
            calls["n"] += 1
            return {"main.py": "from helper import x\n", "helper.py": "x = 1\n"}

        with patch.object(validator, "_generate_missing_modules", side_effect=fake_generate):
            out, issues = asyncio.run(validator.validate_and_fix(files, {}))
        assert calls["n"] == 1
        assert "helper.py" in out
        assert issues == []

    def test_no_selected_issues_returns_unchanged(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        with patch(
            "app.agent.cross_validator.select_llm_fix_issues", return_value=[]
        ):
            out, issues = asyncio.run(
                validator.validate_and_fix(files, {}, fix_model="glm")
            )
        assert out == files and issues

    def test_llm_fix_timeout_is_reraised(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}

        async def boom(*_args, **_kwargs):
            raise TimeoutError("slow")

        with patch.object(validator, "_fix_with_llm", side_effect=boom):
            with pytest.raises(TimeoutError):
                asyncio.run(validator.validate_and_fix(files, {}, fix_model="glm"))

    def test_missing_module_extraction_from_symbol_issues(self):
        validator = _plain_validator()
        issues = [
            {"type": "import_error", "message": "导入的模块不存在: app.models"},
            {"type": "symbol_not_defined", "message": "引用的符号 'x' 在源模块 app/models.py 中未定义"},
            {"type": "other", "message": "noise"},
        ]
        modules = validator._find_missing_modules(issues)
        assert set(modules) == {"app.models"}

    def test_generate_missing_modules_returns_when_all_present(self):
        validator = _python_validator()
        files = {"helper.py": "x = 1\n"}
        assert asyncio.run(
            validator._generate_missing_modules(files, ["helper"], {}, None)
        ) is files


class TestLLMFixHelpers:
    def test_format_referencing_files_truncates_to_twenty_lines(self):
        validator = _plain_validator()
        content = "\n".join(f"line{i}" for i in range(30))
        formatted = validator._format_referencing_files({"a.py": content}, ["a.py", "b.py"])
        assert "line19" in formatted
        assert "line20" not in formatted
        assert "--- b.py ---" in formatted

    def test_parse_batch_result_ignores_unexpected_file(self):
        validator = _plain_validator()
        content = "===other.py===\nprint(1)\n===END==="
        assert validator._parse_batch_fix_result(content, ["a.py"]) == {}

    def test_parse_batch_result_single_file_fallback(self):
        validator = _plain_validator()
        content = "print('fallback')"
        assert validator._parse_batch_fix_result(content, ["a.py"]) == {
            "a.py": "print('fallback')"
        }

    def test_parse_batch_result_multiple_unmatched_returns_empty(self):
        validator = _plain_validator()
        assert validator._parse_batch_fix_result("no markers", ["a.py", "b.py"]) == {}

    def test_accept_rejects_empty_and_thinking(self):
        validator = _plain_validator()
        assert validator._accept_llm_fix("a.py", "", "orig") is None
        assert validator._accept_llm_fix("a.py", "<think>x", "orig") is None

    def test_accept_rejects_invalid_python(self):
        validator = _plain_validator()
        assert validator._accept_llm_fix("a.py", "def broken(:", "orig") is None

    def test_accept_allows_invalid_python_for_non_python_file(self):
        validator = _plain_validator()
        assert validator._accept_llm_fix("a.js", "function (", "orig") == "function ("

    def test_fix_with_llm_skips_missing_file(self):
        validator = _plain_validator()
        files = {"a.py": "x = 1\n"}
        issues = [{"type": "symbol_not_found", "file": "gone.py", "message": "m"}]
        assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files

    def test_fix_with_llm_applies_batch_result(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]

        async def fake_llm(**_kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "===a.py===\ndef present():\n    return 1\n===END==="
                        }
                    }
                ]
            }

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            out = asyncio.run(validator._fix_with_llm(files, issues, "glm"))
        assert "def present" in out["a.py"]

    def test_fix_with_llm_falls_back_to_single_file(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]
        calls = {"n": 0}

        async def fake_llm(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("batch failed")
            return {"choices": [{"message": {"content": "def present():\n    return 1"}}]}

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            out = asyncio.run(validator._fix_with_llm(files, issues, "glm"))
        assert calls["n"] == 2
        assert "def present" in out["a.py"]

    def test_fix_with_llm_single_file_failure_is_logged(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]

        async def fake_llm(**_kwargs):
            raise RuntimeError("always fails")

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files

    def test_fix_with_llm_single_file_timeout_is_reraised(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]
        calls = {"n": 0}

        async def fake_llm(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("batch failed")
            raise TimeoutError("slow")

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            with pytest.raises(TimeoutError):
                asyncio.run(validator._fix_with_llm(files, issues, "glm"))

    def test_batch_timeout_is_reraised(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]

        async def fake_llm(**_kwargs):
            raise TimeoutError("slow")

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            with pytest.raises(TimeoutError):
                asyncio.run(validator._fix_with_llm(files, issues, "glm"))

    def test_batch_response_with_empty_content_keeps_files(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]

        async def fake_llm(**_kwargs):
            return {"choices": [{"message": {"content": ""}}]}

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files
