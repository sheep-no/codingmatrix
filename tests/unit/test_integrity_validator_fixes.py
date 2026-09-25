"""IntegrityValidator 补缺/符号提取/API 提取修复回归（IV6/IV7/IV8/IV9）。"""

from app.agent.adapters import PythonLanguageAdapter
from app.agent.integrity_validator import IntegrityResult, IntegrityValidator


def _api_mismatches(files):
    validator = IntegrityValidator(
        project_type="python", language_adapter=PythonLanguageAdapter()
    )
    result = validator.validate(files)
    return [i for i in result.issues if i.issue_type == "api_mismatch"]


class TestFallbackInitFile:
    """IV6：无适配器时按扩展名推断入口，不再对 Python 硬编码 index.js。"""

    def test_python_project_with_existing_init_has_no_issue(self) -> None:
        validator = IntegrityValidator()  # 不传 adapter，走 fallback
        result = validator.validate(
            {"app/main.py": "print('hi')\n", "app/__init__.py": ""}
        )
        assert [i.issue_type for i in result.issues] == []
        assert result.missing_files == []

    def test_python_project_missing_init_suggests_py_init(self) -> None:
        validator = IntegrityValidator()
        result = validator.validate({"app/main.py": "print('hi')\n"})
        assert "app/__init__.py" in result.missing_files
        assert "app/index.js" not in result.missing_files
        init_issues = [i for i in result.issues if i.issue_type == "missing_init"]
        assert len(init_issues) == 1
        assert "app/__init__.py" in init_issues[0].suggestion

    def test_unknown_extension_project_skips_entry_check(self) -> None:
        validator = IntegrityValidator()
        # .rb 无对应适配器且非 py/js/ts，fallback 不假设入口文件
        result = validator.validate({"cmd/main.rb": "puts 'hi'\n"})
        assert result.missing_files == []


class TestTopLevelSymbols:
    """IV8：AST 提取顶层符号，忽略 docstring/三引号字符串内的伪定义。"""

    def test_symbols_inside_module_docstring_are_ignored(self) -> None:
        content = '"""\nclass Fake:\n    pass\n\ndef fake():\n    pass\n"""\n\nclass Real:\n    pass\n'
        assert IntegrityValidator._extract_top_level_symbols(content) == ["Real"]

    def test_symbols_inside_triple_quoted_string_are_ignored(self) -> None:
        content = "TEXT = '''\ndef fake():\n    pass\n'''\n\nclass Real:\n    pass\n"
        assert IntegrityValidator._extract_top_level_symbols(content) == ["Real"]

    def test_multiline_signature_is_extracted(self) -> None:
        content = "def long_name(\n    a,\n    b,\n):\n    return a + b\n"
        assert IntegrityValidator._extract_top_level_symbols(content) == ["long_name"]

    def test_private_and_nested_names_are_excluded(self) -> None:
        content = (
            "def _hidden():\n"
            "    pass\n"
            "\n"
            "class Outer:\n"
            "    def inner(self):\n"
            "        pass\n"
        )
        assert IntegrityValidator._extract_top_level_symbols(content) == ["Outer"]

    def test_syntax_error_returns_empty(self) -> None:
        assert IntegrityValidator._extract_top_level_symbols("def broken(\n") == []


class TestGenerateFixesParentSkip:
    """IV9：父目录缺失时跳过孤立入口补缺。"""

    def test_entry_generated_when_parent_has_files(self) -> None:
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(result, {"pkg/mod.py": "def f():\n    pass\n"})
        assert "pkg/__init__.py" in fixes
        assert "from .mod import f" in fixes["pkg/__init__.py"]
        assert result.fixed_files == ["pkg/__init__.py"]

    def test_entry_skipped_when_parent_has_no_files(self) -> None:
        validator = IntegrityValidator()
        result = IntegrityResult(missing_files=["pkg/__init__.py"])
        fixes = validator.generate_fixes(result, {"other/mod.py": "def f():\n    pass\n"})
        assert fixes == {}
        assert result.fixed_files == []


class TestBackendApiExtraction:
    """IV7：路由装饰器变量名不限 app/router，并拼接 APIRouter(prefix=...)。"""

    def _apis(self, content):
        validator = IntegrityValidator(language_adapter=PythonLanguageAdapter())
        return validator._extract_backend_apis({"app/routes.py": content})

    def test_arbitrary_router_variable_is_extracted(self) -> None:
        apis = self._apis('@bp.get("/api/x")\ndef h():\n    pass\n')
        assert apis == [{"method": "GET", "path": "/api/x", "file": "app/routes.py"}]

    def test_api_router_post_is_extracted_with_method(self) -> None:
        apis = self._apis('@api_router.post("/api/y")\ndef h():\n    pass\n')
        assert len(apis) == 1
        assert apis[0]["method"] == "POST"
        assert apis[0]["path"] == "/api/y"

    def test_apirouter_prefix_is_prepended(self) -> None:
        content = (
            'router = APIRouter(prefix="/api")\n\n'
            '@router.get("/items")\n'
            "def h():\n"
            "    pass\n"
        )
        assert self._apis(content)[0]["path"] == "/api/items"

    def test_prefix_and_path_slashes_are_normalized(self) -> None:
        content = (
            'r = APIRouter(prefix="/api/")\n\n'
            '@r.get("items")\n'
            "def h():\n"
            "    pass\n"
        )
        assert self._apis(content)[0]["path"] == "/api/items"

    def test_prefixed_route_matches_frontend_call(self) -> None:
        issues = _api_mismatches(
            {
                "app/routes.py": (
                    'router = APIRouter(prefix="/api")\n\n'
                    '@router.get("/items")\n'
                    "def h():\n"
                    "    pass\n"
                ),
                "static/api.js": 'fetch("/api/items")',
            }
        )
        assert issues == []

    def test_missing_prefix_is_reported(self) -> None:
        issues = _api_mismatches(
            {
                "app/routes.py": (
                    'router = APIRouter(prefix="/api")\n\n'
                    '@router.get("/items")\n'
                    "def h():\n"
                    "    pass\n"
                ),
                "static/api.js": 'fetch("/items")',
            }
        )
        assert len(issues) == 1
        assert "GET /items" in issues[0].message
