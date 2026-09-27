"""回归：AD3 剩余项——多行 import 合并与 Python 行尾注释剥离。"""

from app.agent.adapters import JavaScriptLanguageAdapter, PythonLanguageAdapter


class TestPythonMultilineImports:
    def test_parenthesized_import_collects_all_symbols(self):
        content = "from app.models import (\n    User,\n    Post,\n)\n"
        imports = PythonLanguageAdapter().parse_imports(content)

        assert len(imports) == 1
        assert imports[0].module == "app.models"
        assert imports[0].symbols == ["User", "Post"]

    def test_parenthesized_import_keeps_alias(self):
        content = "from app.models import (\n    User as U,\n    Post,\n)\n"
        imports = PythonLanguageAdapter().parse_imports(content)

        assert imports[0].symbols == ["U", "Post"]

    def test_relative_multiline_import_keeps_level(self):
        content = "from ..models import (\n    User,\n    Post,\n)\n"
        imp = PythonLanguageAdapter().parse_imports(content, "app/api/users.py")[0]

        assert imp.level == 2
        assert imp.module == "models"
        assert imp.symbols == ["User", "Post"]

    def test_trailing_comment_is_stripped(self):
        imports = PythonLanguageAdapter().parse_imports(
            "from app.utils import helper  # noqa: F401\n"
        )

        assert imports[0].symbols == ["helper"]

    def test_plain_import_trailing_comment_is_stripped(self):
        imports = PythonLanguageAdapter().parse_imports("import os.path  # pragma\n")

        assert imports[0].module == "os.path"


class TestJavaScriptMultilineImports:
    def test_multiline_named_import_is_parsed(self):
        content = "import {\n  a,\n  b\n} from 'models/user';\n"
        imports = JavaScriptLanguageAdapter().parse_imports(content)

        assert len(imports) == 1
        assert imports[0].module == "models/user"
        assert imports[0].symbols == ["a", "b"]

    def test_plain_code_lines_are_not_merged(self):
        content = "const value = compute(\n  1,\n  2,\n)\nimport x from 'm';\n"
        imports = JavaScriptLanguageAdapter().parse_imports(content)

        assert [imp.module for imp in imports] == ["m"]
