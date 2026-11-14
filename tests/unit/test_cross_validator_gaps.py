"""CrossValidator 剩余分支补测：符号解析兜底、掩码边界与批量修复回退。"""

import asyncio
import tokenize
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agent.adapters.language_adapter import ImportInfo
from app.agent.cross_validator import CrossValidator
from app.agent.shared_context import SharedContext


def _plain_validator() -> CrossValidator:
    return CrossValidator(SharedContext("test", Path(".")))


class _StubAdapter:
    """最小语言适配器：可控的 parse_imports / resolve_import_to_file。"""

    extensions = [".py"]
    supports_cross_file_symbol_validation = True

    def __init__(self, imports=None, resolved=None):
        self.imports = imports or []
        self.resolved = resolved or {}

    def parse_imports(self, content, file_path):
        return list(self.imports)

    def resolve_import_to_file(self, imp, usage_file):
        return list(self.resolved.get(imp.module, []))


class TestSymbolValidationGaps:
    def test_imported_symbol_missing_from_source_is_reported(self):
        files = {
            "main.py": "from helpers import missing\nmissing()\n",
            "helpers.py": "present = 1\n",
        }
        issues = _plain_validator()._validate_symbols(files)
        assert [issue["type"] for issue in issues] == ["symbol_not_defined"]
        assert "helpers.py" in issues[0]["message"]

    def test_symbol_defined_in_source_file_is_not_reported(self, monkeypatch):
        validator = _plain_validator()
        monkeypatch.setattr(validator, "_extract_all_definitions", lambda files: {})
        monkeypatch.setattr(validator, "_extract_all_usages", lambda files: [
            _usage("x", "main.py")
        ])
        monkeypatch.setattr(validator, "_extract_file_definitions", lambda content, *a: {
            "x": object()
        })
        monkeypatch.setattr(
            validator, "_find_symbol_source", lambda *a, **k: "helpers.py"
        )
        files = {"main.py": "x()\n", "helpers.py": "def x(): pass\n"}
        assert validator._validate_symbols(files) == []

    def test_symbol_defined_locally_when_source_unresolved(self, monkeypatch):
        validator = _plain_validator()
        monkeypatch.setattr(validator, "_extract_all_definitions", lambda files: {})
        monkeypatch.setattr(validator, "_extract_all_usages", lambda files: [
            _usage("x", "main.py")
        ])
        monkeypatch.setattr(validator, "_find_symbol_source", lambda *a, **k: None)
        monkeypatch.setattr(
            validator, "_symbol_defined_in_file", lambda *a, **k: True
        )
        assert validator._validate_symbols({"main.py": "x()\n"}) == []

    def test_symbol_validation_skipped_for_adapter_without_support(self):
        adapter = _StubAdapter()
        adapter.supports_cross_file_symbol_validation = False
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        with patch.object(validator, "_validate_symbols") as symbol_check:
            with patch.object(validator, "_validate_function_signatures") as sig_check:
                asyncio.run(
                    validator.validate_cross_file_consistency({"a.py": "x = 1\n"}, {})
                )
        symbol_check.assert_not_called()
        sig_check.assert_not_called()


class TestSymbolSourceAdapterGaps:
    def test_real_adapter_resolves_imported_symbol(self):
        from app.agent.adapters.python import PythonLanguageAdapter

        validator = CrossValidator(
            SharedContext("test", Path(".")),
            language_adapter=PythonLanguageAdapter(),
        )
        files = {
            "pkg/helpers.py": "def x(): pass\n",
            "main.py": "from pkg.helpers import x\n",
        }
        assert validator._find_symbol_source("x", "main.py", files) == "pkg/helpers.py"

    def test_adapter_skips_unrelated_import_then_matches(self):
        adapter = _StubAdapter(
            imports=[
                ImportInfo(module="other", symbols=["y"]),
                ImportInfo(module="helpers", symbols=["x"]),
            ],
            resolved={"helpers": ["missing.py", "helpers.py"]},
        )
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": "from helpers import x\n", "helpers.py": "def x(): pass\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "helpers.py"

    def test_adapter_exhausted_candidates_fall_back_to_text(self):
        class _SequenceAdapter(_StubAdapter):
            def __init__(self):
                super().__init__(imports=[ImportInfo(module="helpers", symbols=["x"])])
                self.calls = 0

            def resolve_import_to_file(self, imp, usage_file):
                self.calls += 1
                return ["nowhere.py"] if self.calls == 1 else ["helpers.py"]

        adapter = _SequenceAdapter()
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": "from helpers import x\n", "helpers.py": "def x(): pass\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "helpers.py"

    def test_text_fallback_without_adapter_skips_non_matching_name(self):
        validator = _plain_validator()
        files = {"main.py": "from helpers import other, x\n", "helpers.py": "x = 1\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "helpers.py"

    def test_text_fallback_with_adapter_resolves_module(self):
        adapter = _StubAdapter(imports=[], resolved={"helpers": ["helpers.py"]})
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": "from helpers import x\n", "helpers.py": "x = 1\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "helpers.py"

    def test_text_fallback_adapter_candidates_not_in_files(self):
        adapter = _StubAdapter(imports=[], resolved={"helpers": ["other.py"]})
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": "from helpers import x\n"}
        assert validator._find_symbol_source("x", "main.py", files) is None

    def test_quoted_import_adapter_resolves(self):
        adapter = _StubAdapter(imports=[], resolved={"pkg/mod": ["pkg/mod.py"]})
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": 'import "pkg/mod"\n', "pkg/mod.py": "x = 1\n"}
        assert validator._find_symbol_source("x", "main.py", files) == "pkg/mod.py"

    def test_quoted_import_adapter_exhausted_candidates(self):
        adapter = _StubAdapter(imports=[], resolved={"pkg/mod": ["other.py"]})
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=adapter
        )
        files = {"main.py": 'import "pkg/mod"\n'}
        assert validator._find_symbol_source("x", "main.py", files) is None

    def test_quoted_import_plain_unresolved(self):
        files = {"main.py": 'import "nowhere"\n'}
        assert _plain_validator()._find_symbol_source("x", "main.py", files) is None

    def test_rust_use_unresolved(self):
        files = {"main.rs": "use nowhere::mod\n"}
        assert _plain_validator()._find_symbol_source("x", "main.rs", files) is None

    def test_module_exists_falls_back_when_adapter_cannot_resolve(self):
        from app.agent.adapters.python import PythonLanguageAdapter

        validator = CrossValidator(
            SharedContext("test", Path(".")),
            language_adapter=PythonLanguageAdapter(),
        )
        assert validator._module_exists_in_files("unknown.pkg", {"a.py": ""}) is False


class TestMaskAndParamGaps:
    def test_extract_call_params_skips_blank_argument(self, monkeypatch):
        validator = _plain_validator()
        monkeypatch.setattr(validator, "_split_top_level_args", lambda args: ["  "])
        assert validator._extract_call_params("   ") == set()

    def test_mask_handles_token_beyond_content(self, monkeypatch):
        FakeToken = namedtuple(
            "FakeToken", ["type", "string", "start", "end", "line"]
        )
        token = FakeToken(tokenize.STRING, '"x"', (1, 5), (2, 7), '"x"')
        monkeypatch.setattr(tokenize, "generate_tokens", lambda readline: iter([token]))
        masked = _plain_validator()._mask_python_noncode('x = "x"\n', "a.py")
        assert masked.startswith("x = ")
        assert masked.endswith("\n")

    def test_mask_multi_line_string_skips_newline(self):
        content = 'x = """line1\nline2"""\n'
        masked = _plain_validator()._mask_python_noncode(content, "a.py")
        assert masked.count("\n") == content.count("\n")


class TestMissingModuleGaps:
    def test_import_error_without_module_name_ignored(self):
        issues = [{"type": "import_error", "message": "导入的模块不存在: "}]
        assert _plain_validator()._find_missing_modules(issues) == []

    def test_symbol_issue_without_module_name_ignored(self):
        issues = [{"type": "symbol_not_defined", "message": "引用的符号 'x' 未定义"}]
        assert _plain_validator()._find_missing_modules(issues) == []

    def test_symbol_issue_with_adapter_strips_extension(self):
        validator = CrossValidator(
            SharedContext("test", Path(".")), language_adapter=_StubAdapter()
        )
        issues = [
            {
                "type": "symbol_not_defined",
                "message": "引用的符号 'x' 在源模块 app/models.py 中未定义",
            }
        ]
        assert validator._find_missing_modules(issues) == ["app.models"]


class TestFixFlowGaps:
    def test_successful_llm_fix_returns_fixed_files(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        fixed = {"a.py": "def missing_call():\n    return 1\n"}

        async def fake_fix(current, selected, model):
            return fixed

        with patch.object(validator, "_fix_with_llm", side_effect=fake_fix):
            out, issues = asyncio.run(
                validator.validate_and_fix(files, {}, fix_model="glm")
            )
        assert out == fixed
        assert issues

    def test_single_file_fallback_empty_content_keeps_original(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]
        calls = {"n": 0}

        async def fake_llm(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("batch failed")
            return {"choices": [{"message": {"content": ""}}]}

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files

    def test_single_file_fallback_skips_missing_file(self):
        validator = _plain_validator()
        files = {"a.py": "x = 1\n"}
        issues = [
            {"type": "symbol_not_found", "file": "gone.py", "message": "m"},
            {"type": "symbol_not_found", "file": "a.py", "message": "m"},
        ]

        async def fake_llm(**_kwargs):
            raise RuntimeError("batch failed")

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files

    def test_single_file_fallback_rejects_invalid_fix(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [{"type": "symbol_not_found", "file": "a.py", "message": "m"}]
        calls = {"n": 0}

        async def fake_llm(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("batch failed")
            return {"choices": [{"message": {"content": "def broken(:"}}]}

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            assert asyncio.run(validator._fix_with_llm(files, issues, "glm")) == files

    def test_fix_with_llm_groups_multiple_issues_per_file(self):
        validator = _plain_validator()
        files = {"a.py": "missing_call()\n"}
        issues = [
            {"type": "symbol_not_found", "file": "a.py", "message": "m1"},
            {"type": "symbol_not_found", "file": "a.py", "message": "m2"},
        ]
        prompts = []

        async def fake_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return {"choices": [{"message": {"content": ""}}]}

        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            asyncio.run(validator._fix_with_llm(files, issues, "glm"))
        assert len(prompts) == 1
        assert "m1" in prompts[0] and "m2" in prompts[0]

    def test_accept_rejects_think_tag_after_cleaning(self, monkeypatch):
        validator = _plain_validator()
        monkeypatch.setattr(
            validator, "_clean_code_block", lambda content: "<thinking>x"
        )
        assert validator._accept_llm_fix("a.py", "x", "orig") is None


def _usage(name: str, file_path: str):
    from app.agent.cross_validator import SymbolUsage

    return SymbolUsage(name=name, file_path=file_path, line_number=1, context="")
