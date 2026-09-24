"""回归：adapters AD11/AD3（Python 相对导入层级）、AD6（类内方法误判顶层）、AD10（TS 泛型箭头）。"""

from app.agent.adapters import JavaScriptLanguageAdapter, PythonLanguageAdapter


class TestPythonRelativeImports:
    """AD11/AD3: 相对导入保留层级，`from .` 符号按子模块解析"""

    def test_level_one_resolves_to_current_package(self):
        adapter = PythonLanguageAdapter()
        imp = adapter.parse_imports("from .models import X", "app/api/users.py")[0]
        assert imp.level == 1
        assert imp.module == "models"
        assert imp.is_relative
        assert adapter.resolve_import_to_file(imp, "app/api/users.py") == [
            "app/api/models.py",
            "app/api/models/__init__.py",
        ]

    def test_level_two_resolves_to_parent_package(self):
        adapter = PythonLanguageAdapter()
        imp = adapter.parse_imports("from ..models import X", "app/api/users.py")[0]
        assert imp.level == 2
        assert adapter.resolve_import_to_file(imp, "app/api/users.py") == [
            "app/models.py",
            "app/models/__init__.py",
        ]

    def test_level_three_resolves_to_project_root(self):
        adapter = PythonLanguageAdapter()
        imp = adapter.parse_imports("from ...pkg import X", "app/api/users.py")[0]
        assert imp.level == 3
        assert adapter.resolve_import_to_file(imp, "app/api/users.py") == [
            "pkg.py",
            "pkg/__init__.py",
        ]

    def test_dotted_only_import_resolves_symbols_as_submodules(self):
        adapter = PythonLanguageAdapter()
        imp = adapter.parse_imports("from . import utils", "app/api/users.py")[0]
        assert imp.level == 1
        assert imp.module == ""
        assert adapter.resolve_import_to_file(imp, "app/api/users.py") == [
            "app/api/utils.py",
            "app/api/utils/__init__.py",
        ]

    def test_absolute_import_unchanged(self):
        adapter = PythonLanguageAdapter()
        imp = adapter.parse_imports("from app.models import X", "app/api/users.py")[0]
        assert imp.level == 0
        assert not imp.is_relative
        assert adapter.resolve_import_to_file(imp, "app/api/users.py") == [
            "app/models.py",
            "app/models/__init__.py",
        ]


class TestPythonExtractDefinitions:
    """AD6: 类内/嵌套定义不再被提为顶层符号"""

    def test_methods_and_nested_functions_excluded(self):
        content = (
            "def top():\n"
            "    pass\n"
            "\n"
            "class C:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n"
            "    async def am(self):\n"
            "        pass\n"
            "\n"
            "    def outer(self):\n"
            "        def inner():\n"
            "            pass\n"
            "        return inner\n"
        )
        definitions = PythonLanguageAdapter().extract_definitions(content)
        assert set(definitions) == {"top", "C"}

    def test_module_level_async_function_kept(self):
        definitions = PythonLanguageAdapter().extract_definitions("async def fetch():\n    pass\n")
        assert "fetch" in definitions


class TestJavaScriptGenericArrow:
    """AD10: 泛型箭头函数被识别"""

    def test_generic_arrow_extracted(self):
        content = (
            "export const foo = <T>(x: T): T => x\n"
            "const bar = async <T,>(x: T) => x\n"
        )
        definitions = JavaScriptLanguageAdapter().extract_definitions(content)
        assert {"foo", "bar"} <= set(definitions)
        assert definitions["foo"].symbol_type == "function"

    def test_plain_arrow_still_extracted(self):
        definitions = JavaScriptLanguageAdapter().extract_definitions("const baz = () => 1\n")
        assert "baz" in definitions
