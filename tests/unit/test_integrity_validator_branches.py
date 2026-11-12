"""IntegrityValidator 全分支回归：计数、包入口、导入校验、契约与补缺生成。"""

from pathlib import Path

import pytest

from app.agent import integrity_validator as iv
from app.agent.adapters import PythonLanguageAdapter
from app.agent.adapters.language_adapter import ImportInfo
from app.agent.integrity_validator import (
    IntegrityIssue,
    IntegrityResult,
    IntegrityValidator,
)


class _Adapter:
    """最小适配器 stub，用于精确控制每条分支。"""

    extensions = {".py"}
    package_init_filename = "__init__.py"

    def __init__(self):
        self.package_missing = {}
        self.project_modules = set()
        self.imports = []
        self.resolve_hits = {}
        self.init_file = None

    def parse_imports(self, content, file_path):
        return self.imports

    def is_project_module(self, module):
        return module in self.project_modules

    def resolve_import_to_file(self, imp, file_path):
        return [self.resolve_hits.get(imp.module)] if imp.module in self.resolve_hits else []

    def validate_package_structure(self, pkg, files):
        return self.package_missing.get(pkg, [])

    def get_package_init_file(self, pkg_path):
        return self.init_file or f"{pkg_path}/__init__.py"


class TestResultHelpers:
    def test_error_and_warning_counts(self):
        result = IntegrityResult()
        result.add_issue(IntegrityIssue("a.py", "missing_module", "m"))
        result.add_issue(
            IntegrityIssue("b.py", "api_mismatch", "m", severity="warning")
        )

        assert result.passed is False
        assert result.error_count == 1
        assert result.warning_count == 1

    def test_warning_only_keeps_passed(self):
        result = IntegrityResult()
        result.add_issue(
            IntegrityIssue("a.py", "api_mismatch", "m", severity="warning")
        )

        assert result.passed is True
        assert result.error_count == 0
        assert result.warning_count == 1


class TestAdapterDetection:
    def test_explicit_adapter_short_circuits(self):
        adapter = PythonLanguageAdapter()
        validator = IntegrityValidator(language_adapter=adapter)

        validator._ensure_language_adapter({"x.rb": "puts 1"})

        assert validator.language_adapter is adapter

    def test_java_project_selects_java(self, monkeypatch):
        shared = PythonLanguageAdapter()
        monkeypatch.setattr(
            iv,
            "Path",
            Path,
        )
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry

        monkeypatch.setattr(
            LanguageAdapterRegistry,
            "get_adapter",
            staticmethod(lambda lang: shared if lang in ("python", "java", "go") else None),
        )
        validator = IntegrityValidator()

        validator._ensure_language_adapter({"src/Main.java": "class Main {}"})

        assert validator.language_adapter is shared

    def test_no_matching_language_leaves_adapter_none(self):
        validator = IntegrityValidator()
        validator._ensure_language_adapter({"lib/main.rb": "puts 1"})
        assert validator.language_adapter is None

    def test_js_only_project_falls_back_to_javascript(self, monkeypatch):
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry

        js_adapter = PythonLanguageAdapter()
        monkeypatch.setattr(
            LanguageAdapterRegistry,
            "get_adapter",
            staticmethod(lambda lang: js_adapter if lang == "javascript" else None),
        )
        validator = IntegrityValidator()
        validator._ensure_language_adapter({"web/app.js": "console.log(1)"})

        assert validator.language_adapter is js_adapter

    def test_registry_returning_none_is_skipped(self, monkeypatch):
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry

        monkeypatch.setattr(
            LanguageAdapterRegistry, "get_adapter", staticmethod(lambda lang: None)
        )
        validator = IntegrityValidator()
        validator._ensure_language_adapter({"main.py": "print(1)"})

        assert validator.language_adapter is None


class TestPackageInitWithAdapter:
    def _run(self, adapter, files):
        validator = IntegrityValidator(language_adapter=adapter)
        result = IntegrityResult()
        validator._check_package_init(files, result)
        return result

    def test_missing_init_reported(self):
        adapter = _Adapter()
        adapter.package_missing["pkg"] = ["pkg/__init__.py"]
        result = self._run(adapter, {"pkg/mod.py": ""})

        assert result.missing_files == ["pkg/__init__.py"]
        assert result.issues[0].issue_type == "missing_init"
        assert result.issues[0].suggestion == "创建 pkg/__init__.py"

    def test_existing_init_not_reported(self):
        adapter = _Adapter()
        adapter.package_missing["pkg"] = ["pkg/__init__.py"]
        result = self._run(adapter, {"pkg/mod.py": "", "pkg/__init__.py": ""})

        assert result.missing_files == []

    def test_nested_packages_all_checked(self):
        adapter = _Adapter()
        adapter.package_missing["a/b"] = ["a/b/__init__.py"]
        result = self._run(adapter, {"a/b/c/mod.py": ""})

        assert "a/b/__init__.py" in result.missing_files


class TestPackageInitFallback:
    def _run(self, files):
        validator = IntegrityValidator()
        # 强制走 fallback 分支
        validator.language_adapter = None
        result = IntegrityResult()
        validator._check_package_init(files, result)
        return result

    def test_python_entry(self):
        result = self._run({"pkg/mod.py": ""})
        assert result.missing_files == ["pkg/__init__.py"]

    def test_typescript_entry(self):
        result = self._run({"web/app.ts": ""})
        assert result.missing_files == ["web/index.ts"]

    def test_javascript_entry(self):
        result = self._run({"web/app.jsx": ""})
        assert result.missing_files == ["web/index.js"]

    def test_unknown_language_skipped(self):
        result = self._run({"cmd/main.rb": ""})
        assert result.missing_files == []

    def test_root_level_file_adds_no_package(self):
        result = self._run({"main.py": ""})
        assert result.missing_files == []

    def test_existing_entry_no_issue(self):
        result = self._run({"web/index.ts": "", "web/app.ts": ""})
        assert result.missing_files == []


class TestValidateImportsAdapter:
    def test_missing_project_module_reported(self):
        adapter = _Adapter()
        adapter.imports = [
            ImportInfo(module="pkg.missing", is_relative=False),
            ImportInfo(module="pkg.relative", is_relative=True),
            ImportInfo(module="thirdparty", is_relative=False),
        ]
        adapter.project_modules = {"pkg.missing"}
        validator = IntegrityValidator(language_adapter=adapter)
        result = IntegrityResult()

        validator._validate_imports({"pkg/main.py": ""}, result)

        assert len(result.issues) == 1
        assert result.issues[0].issue_type == "missing_module"

    def test_existing_module_passes(self):
        adapter = _Adapter()
        adapter.imports = [ImportInfo(module="pkg.dep", is_relative=False)]
        adapter.project_modules = {"pkg.dep"}
        adapter.resolve_hits["pkg.dep"] = "pkg/dep.py"
        validator = IntegrityValidator(language_adapter=adapter)
        result = IntegrityResult()

        validator._validate_imports({"pkg/main.py": "", "pkg/dep.py": ""}, result)

        assert result.issues == []


class TestValidateImportsFallback:
    def _validator(self):
        validator = IntegrityValidator()
        validator.language_adapter = None
        return validator

    def test_skips_non_python_file(self):
        validator = self._validator()
        result = IntegrityResult()

        validator._validate_imports({"notes.txt": "import app.foo"}, result)

        assert result.issues == []

    def test_builtin_and_third_party_skipped(self):
        validator = self._validator()
        result = IntegrityResult()
        content = "import os\nfrom fastapi import FastAPI\nfrom .local import x\n"

        validator._validate_imports({"app/main.py": content}, result)

        assert result.issues == []

    def test_missing_project_module_reported(self):
        validator = self._validator()
        result = IntegrityResult()

        validator._validate_imports({"app/main.py": "import app.missing\n"}, result)

        assert result.issues[0].issue_type == "missing_module"
        assert result.issues[0].message == "导入的模块不存在: app.missing"

    def test_existing_package_module_passes(self):
        validator = self._validator()
        result = IntegrityResult()

        validator._validate_imports(
            {"app/main.py": "import app.helpers\n", "app/helpers/x.py": ""},
            result,
        )

        assert result.issues == []

    def test_builtin_filter_continues_before_module_lookup(self, monkeypatch):
        validator = self._validator()
        result = IntegrityResult()
        monkeypatch.setattr(validator, "_extract_imports", lambda content: ["os"])

        validator._validate_imports({"app/main.py": "import os"}, result)

        assert result.issues == []


class TestExtractImports:
    def test_only_app_and_src_prefixes(self):
        content = (
            "# import app.comment\n"
            "import app.ok\n"
            "from src.pkg import thing\n"
            "import third.party\n"
            "  import app.indented\n"
        )

        assert IntegrityValidator()._extract_imports(content) == [
            "app.ok",
            "src.pkg",
            "app.indented",
        ]

    def test_is_builtin_or_third_party(self):
        validator = IntegrityValidator()
        assert validator._is_builtin_or_third_party("os.path") is True
        assert validator._is_builtin_or_third_party("fastapi.routing") is True
        assert validator._is_builtin_or_third_party(".relative") is True
        assert validator._is_builtin_or_third_party("app.custom") is False


class TestModuleExists:
    def test_adapter_path(self):
        adapter = _Adapter()
        adapter.resolve_hits["pkg.mod"] = "pkg/mod.py"
        validator = IntegrityValidator(language_adapter=adapter)

        assert validator._module_exists("pkg.mod", {"pkg/mod.py": ""}) is True
        assert validator._module_exists("pkg.other", {"pkg/mod.py": ""}) is False

    def test_fallback_file_match(self):
        validator = IntegrityValidator()
        validator.language_adapter = None

        assert validator._module_exists("app.main", {"app/main.py": ""}) is True

    def test_fallback_package_prefix_match(self):
        validator = IntegrityValidator()
        validator.language_adapter = None

        assert validator._module_exists("app", {"app/main.py": ""}) is True
        assert validator._module_exists("app.ghost", {"app/main.py": ""}) is False

    def test_adapter_path_has_no_init_fallback(self):
        adapter = _Adapter()
        validator = IntegrityValidator(language_adapter=adapter)

        # 适配器路径完全交给 resolve_import_to_file，不再做入口文件兜底
        assert validator._module_exists("pkg", {"pkg/__init__.py": ""}) is False


class TestApiContracts:
    def _validate(self, files):
        validator = IntegrityValidator(
            project_type="python", language_adapter=PythonLanguageAdapter()
        )
        result = IntegrityResult()
        validator._validate_api_contracts(files, result)
        return result

    def test_router_prefix_is_applied(self):
        files = {
            "app/api.py": (
                'router = APIRouter(prefix="/api/v1")\n'
                '@router.get("/items")\n'
                "def items():\n"
                "    return []\n"
            ),
            "web/api.js": "fetch('/api/v1/items');\n",
        }

        assert self._validate(files).issues == []

    def test_full_api_router_reference_is_supported(self):
        files = {
            "app/api.py": (
                'router = fastapi.APIRouter(prefix="/x")\n'
                '@router.post("/y")\n'
                "def y():\n"
                "    return {}\n"
            ),
            "web/api.js": "axios.post('/x/y');\n",
        }

        assert self._validate(files).issues == []

    def test_router_prefix_without_slash_is_normalized(self):
        files = {
            "app/api.py": (
                'router = APIRouter(prefix="/api")\n'
                '@router.get("/users")\n'
                "def users():\n"
                "    return []\n"
            ),
            "web/api.js": "fetch('/api/users');\n",
        }

        assert self._validate(files).issues == []

    def test_multiple_routers_use_own_prefix(self):
        files = {
            "app/api.py": (
                'a = APIRouter(prefix="/a")\n'
                'b = APIRouter(prefix="/b")\n'
                '@a.get("/one")\n'
                '@b.get("/two")\n'
                "def handler():\n"
                "    return {}\n"
            ),
            "web/api.js": "fetch('/b/two');\n",
        }

        assert self._validate(files).issues == []

    def test_missing_endpoint_reported_as_warning(self):
        files = {
            "app/api.py": '@app.get("/known")\ndef h():\n    return {}\n',
            "web/api.js": "fetch('/unknown');\n",
        }

        result = self._validate(files)

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is True

    def test_template_literal_variables_skipped(self):
        files = {
            "app/api.py": '@app.get("/known")\ndef h():\n    return {}\n',
            "web/api.js": "fetch(`/api/${id}`);\n",
        }

        assert self._validate(files).issues == []

    def test_axios_method_variants(self):
        files = {
            "app/api.py": (
                '@app.put("/p")\n'
                '@app.delete("/d")\n'
                "def h():\n"
                "    return {}\n"
            ),
            "web/api.js": "axios.put('/p');\nclient.delete('/d');\n",
        }

        assert self._validate(files).issues == []

    def test_query_and_fragment_stripped(self):
        files = {
            "app/api.py": '@app.get("/item")\ndef h():\n    return {}\n',
            "web/api.js": "fetch('/item?x=1#frag');\n",
        }

        assert self._validate(files).issues == []


class TestGenerateFixes:
    def test_python_init_with_symbols(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(
            result,
            {"pkg/mod.py": "class A:\n    pass\n\ndef helper():\n    pass\n"},
        )

        content = fixes["pkg/__init__.py"]
        assert "from .mod import A, helper" in content
        assert result.fixed_files == ["pkg/__init__.py"]

    def test_python_init_without_symbols(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(result, {"pkg/mod.py": "X = 1\n"})

        assert "no public exports" in fixes["pkg/__init__.py"]

    def test_python_init_skips_nested_sibling(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(
            result,
            {"pkg/sub/mod.py": "def f():\n    pass\n"},
        )

        assert "no public exports" in fixes["pkg/__init__.py"]

    def test_index_generation_skips_reserved_and_other_dirs(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["web/index.ts"])
        fixes = validator.generate_fixes(
            result,
            {
                "web/a.ts": "",
                "web/b.jsx": "",
                "web/index2.ts": "",
                "web/package.ts": "",
                "web/config.ts": "",
                "other/c.ts": "",
            },
        )

        content = fixes["web/index.ts"]
        assert 'export * from "./a";' in content
        assert 'export * from "./b";' in content
        assert '"./package"' not in content
        assert '"./config"' not in content
        assert '"./c"' not in content

    def test_index_generation_empty(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["web/index.js"])
        fixes = validator.generate_fixes(result, {"web/index.js": "old"})

        assert fixes == {}

    def test_missing_parent_is_skipped(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["ghost/__init__.py"])
        fixes = validator.generate_fixes(result, {"other/mod.py": ""})

        assert fixes == {}

    def test_unknown_entry_name_is_skipped(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/entry.py"])
        fixes = validator.generate_fixes(result, {"pkg/mod.py": ""})

        assert fixes == {}

    def test_uses_adapter_package_init_filename(self):
        adapter = _Adapter()
        adapter.package_init_filename = "__init__.py"
        validator = IntegrityValidator(language_adapter=adapter)
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(result, {"pkg/mod.py": ""})

        assert "pkg/__init__.py" in fixes

    def test_already_generated_entry_is_skipped(self):
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(
            result, {"pkg/__init__.py": "", "pkg/mod.py": ""}
        )

        assert fixes == {}
        assert result.fixed_files == []

    def test_init_content_skips_entry_and_non_python(self):
        validator = IntegrityValidator()

        content = validator._generate_init_content(
            "pkg/__init__.py",
            {
                "pkg/__init__.py": "",
                "pkg/notes.txt": "",
                "pkg/sub/__init__.py": "",
            },
        )

        assert "no public exports" in content

    def test_index_content_skips_entry_and_non_script(self):
        validator = IntegrityValidator()

        content = validator._generate_index_content(
            "web/index.ts",
            {"web/index.ts": "", "web/readme.md": "", "web/nested/a.ts": ""},
        )

        assert "no public exports" in content


class TestValidateEndToEnd:
    def test_frontend_backend_triggers_contract_check(self):
        validator = IntegrityValidator(
            project_type="python", language_adapter=PythonLanguageAdapter()
        )
        files = {
            "app/main.py": "@app.get('/api/known')\ndef h():\n    return {}\n",
            "app/__init__.py": "",
            "web/api.js": "fetch('/api/known');\nfetch('/api/missing');\n",
        }

        result = validator.validate(files)

        mismatches = [i for i in result.issues if i.issue_type == "api_mismatch"]
        assert len(mismatches) == 1
        assert "missing" in mismatches[0].message

    def test_no_backend_skips_contract_check(self):
        validator = IntegrityValidator(language_adapter=PythonLanguageAdapter())
        result = validator.validate({"web/api.js": "fetch('/api/x');"})

        assert [i for i in result.issues if i.issue_type == "api_mismatch"] == []
