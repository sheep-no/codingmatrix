"""
内置工具函数单元测试

覆盖：
- _tool_read_file: 正常读取、分页、不存在文件
- _tool_list_files: 正常列出、深度控制、不存在目录
- _tool_read_symbols: Python/JS 符号提取
- _tool_read_imports: import 提取
- _tool_summarize_file: 文件摘要
- _tool_partial_update: 精准替换
- _tool_insert_content: 按行/锚点插入
- _tool_regex_replace: 正则替换
- 辅助函数: _get_patterns_for_file, _extract_module_name
- SPECIALIST_TOOLS 注册表
"""

import os
import tempfile
import pytest
from pathlib import Path

from app.agent.tools import (
    _tool_read_file,
    _tool_list_files,
    _tool_read_symbols,
    _tool_read_imports,
    _tool_summarize_file,
    _tool_partial_update,
    _tool_insert_content,
    _tool_regex_replace,
    _get_patterns_for_file,
    _extract_module_name,
    SPECIALIST_TOOLS,
    _SYMBOL_PATTERNS,
    _EXT_BY_LANG,
    _execute_python_sandbox,
    _tool_run_command,
    _tool_delete_files_by_pattern,
)


@pytest.fixture
def project_dir():
    """Create a temp project with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Python file
        with open(os.path.join(tmpdir, "main.py"), "w") as f:
            f.write("""import os
import json
from pathlib import Path

class MyService:
    def __init__(self):
        pass

    def process(self, data):
        return data

def helper():
    pass
""")

        # JS file
        with open(os.path.join(tmpdir, "app.js"), "w") as f:
            f.write("""const express = require('express');
import { Router } from 'express';

class App {
    constructor() {
        this.router = Router();
    }
}

function init() {
    return new App();
}
""")

        # Subdirectory
        os.makedirs(os.path.join(tmpdir, "utils"))
        with open(os.path.join(tmpdir, "utils", "helpers.py"), "w") as f:
            f.write("def format_date(d):\n    return str(d)\n")

        yield tmpdir


class TestReadFile:
    def test_read_existing_file(self, project_dir):
        result = _tool_read_file(project_dir, "main.py")
        assert "content" in result
        assert "import os" in result["content"]
        assert result["file"] == "main.py"
        assert result["total_lines"] > 0

    def test_read_with_offset(self, project_dir):
        result = _tool_read_file(project_dir, "main.py", offset=1, limit=2)
        assert result["offset"] == 1
        # Line 2 is "import json" (0-indexed offset=1 means line 2)
        content_lines = result["content"].split("\n")
        assert len(content_lines) <= 2

    def test_read_nonexistent_file(self, project_dir):
        result = _tool_read_file(project_dir, "nonexistent.py")
        assert "error" in result
        assert "不存在" in result["error"]

    def test_read_directory_as_file(self, project_dir):
        result = _tool_read_file(project_dir, "utils")
        assert "error" in result

    @pytest.mark.parametrize("file_path", ["../outside.py", "/etc/hosts"])
    def test_read_rejects_path_outside_project(self, project_dir, file_path):
        result = _tool_read_file(project_dir, file_path)
        assert "error" in result
        assert "越界" in result["error"]


class TestSandboxAndCommand:
    def test_python_sandbox_executes_and_cleans_up(self):
        result = _execute_python_sandbox("print('ok')", timeout=5)
        assert result["success"] is True
        assert result["output"].strip() == "ok"

    def test_command_cwd_rejects_prefix_collision(self, project_dir):
        sibling = f"{project_dir}_evil"
        result = _tool_run_command(project_dir, "pwd", cwd=f"../{Path(sibling).name}")
        assert result["success"] is False
        assert "项目路径内" in result["error"]

    def test_command_uses_argument_array_without_shell_operators(self, project_dir):
        result = _tool_run_command(
            project_dir,
            "python3 -c \"print('ok')\"",
        )
        assert result["success"] is True
        assert result["output"].strip() == "ok"

    def test_command_requires_exact_allowed_subcommand(self, project_dir):
        result = _tool_run_command(project_dir, "npm installevil")
        assert result["success"] is False
        assert "不在允许列表" in result["error"]

    @pytest.mark.parametrize("command", [
        "python3 -c \"print('ok')\"; pwd",
        "python3 -c \"print('ok')\" | cat",
        "bash -c 'pwd'",
    ])
    def test_command_rejects_shell_composition(self, project_dir, command):
        result = _tool_run_command(project_dir, command)
        assert result["success"] is False
        assert "安全限制" in result["error"]


class TestListFiles:
    def test_list_root(self, project_dir):
        result = _tool_list_files(project_dir, ".")
        assert "entries" in result
        assert result["directory"] == "."
        paths = [e["path"] for e in result["entries"]]
        assert "main.py" in paths

    def test_list_with_depth(self, project_dir):
        result = _tool_list_files(project_dir, ".", max_depth=0)
        paths = [e["path"] for e in result["entries"]]
        assert "utils/" in paths
        # deep files should not appear at depth 0
        assert "utils/helpers.py" not in paths

    def test_list_nonexistent_dir(self, project_dir):
        result = _tool_list_files(project_dir, "nonexistent")
        assert "error" in result

    def test_list_max_entries(self, project_dir):
        result = _tool_list_files(project_dir, ".", max_depth=10)
        assert len(result["entries"]) <= 200

    @pytest.mark.parametrize("directory", ["..", "/tmp"])
    def test_list_rejects_path_outside_project(self, project_dir, directory):
        result = _tool_list_files(project_dir, directory)
        assert "error" in result
        assert "越界" in result["error"]


class TestDeleteFiles:
    def test_delete_rejects_path_outside_project(self, project_dir):
        result = _tool_delete_files_by_pattern(project_dir, "..", "*.py")
        assert result["success"] is False
        assert "越界" in result["error"]


class TestReadSymbols:
    def test_python_symbols(self, project_dir):
        result = _tool_read_symbols(project_dir, "main.py")
        assert "functions" in result
        assert "classes" in result
        func_names = [f["name"] for f in result["functions"]]
        assert "helper" in func_names
        cls_names = [c["name"] for c in result["classes"]]
        assert "MyService" in cls_names

    def test_js_symbols(self, project_dir):
        result = _tool_read_symbols(project_dir, "app.js")
        assert "functions" in result
        assert "classes" in result

    def test_nonexistent_file(self, project_dir):
        result = _tool_read_symbols(project_dir, "missing.py")
        assert "error" in result


class TestReadImports:
    def test_python_imports(self, project_dir):
        result = _tool_read_imports(project_dir, "main.py")
        assert "imports" in result
        assert result["import_count"] >= 3
        modules = [i["module"] for i in result["imports"]]
        assert "os" in modules
        assert "json" in modules

    def test_nonexistent_file(self, project_dir):
        result = _tool_read_imports(project_dir, "missing.py")
        assert "error" in result


class TestSummarizeFile:
    def test_summary_python(self, project_dir):
        result = _tool_summarize_file(project_dir, "main.py")
        assert result["language"] == "python"
        assert result["total_lines"] > 0
        assert result["functions"] >= 1
        assert result["classes"] >= 1
        assert "dependencies" in result

    def test_summary_nonexistent(self, project_dir):
        result = _tool_summarize_file(project_dir, "missing.py")
        assert "error" in result


class TestPartialUpdate:
    def test_replace_by_target(self, project_dir):
        target_path = os.path.join(project_dir, "main.py")
        result = _tool_partial_update(project_dir, "main.py", target="def helper():", replacement="def helper_v2():")
        assert result["success"] is True
        content = Path(target_path).read_text()
        assert "helper_v2" in content
        assert "def helper():" not in content

    def test_replace_nonexistent_target(self, project_dir):
        result = _tool_partial_update(project_dir, "main.py", target="NOT_FOUND", replacement="x")
        assert result["success"] is False
        assert "未找到" in result["error"]

    def test_replace_nonexistent_file(self, project_dir):
        result = _tool_partial_update(project_dir, "missing.py", target="x", replacement="y")
        assert result["success"] is False

    def test_no_target_no_function(self, project_dir):
        result = _tool_partial_update(project_dir, "main.py")
        assert result["success"] is False


class TestInsertContent:
    def test_insert_by_line(self, project_dir):
        target_path = os.path.join(project_dir, "main.py")
        result = _tool_insert_content(project_dir, "main.py", "# inserted comment", line=1)
        assert result["success"] is True
        content = Path(target_path).read_text()
        assert "# inserted comment" in content

    def test_insert_by_anchor(self, project_dir):
        target_path = os.path.join(project_dir, "main.py")
        result = _tool_insert_content(project_dir, "main.py", "# after import", anchor="import json")
        assert result["success"] is True
        content = Path(target_path).read_text()
        lines = content.split("\n")
        # find the inserted line
        found = False
        for i, line in enumerate(lines):
            if "import json" in line:
                if i + 1 < len(lines) and "# after import" in lines[i + 1]:
                    found = True
                break
        assert found

    def test_insert_anchor_not_found(self, project_dir):
        result = _tool_insert_content(project_dir, "main.py", "x", anchor="NOT_FOUND")
        assert result["success"] is False

    def test_insert_nonexistent_file(self, project_dir):
        result = _tool_insert_content(project_dir, "missing.py", "x", line=1)
        assert result["success"] is False


class TestRegexReplace:
    def test_simple_replace(self, project_dir):
        target_path = os.path.join(project_dir, "main.py")
        result = _tool_regex_replace(project_dir, "main.py", r"helper", "new_helper")
        assert result["success"] is True
        assert result["total_replacements"] >= 1
        content = Path(target_path).read_text()
        assert "new_helper" in content

    def test_no_match(self, project_dir):
        result = _tool_regex_replace(project_dir, "main.py", r"NOT_FOUND_PATTERN_xyz", "replacement")
        assert result["success"] is True
        assert result["total_replacements"] == 0

    def test_nonexistent_file(self, project_dir):
        result = _tool_regex_replace(project_dir, "missing.py", r"x", "y")
        assert result["success"] is False


class TestHelperFunctions:
    def test_get_patterns_for_py(self):
        patterns = _get_patterns_for_file("test.py")
        assert "function" in patterns
        assert "class" in patterns

    def test_get_patterns_for_js(self):
        patterns = _get_patterns_for_file("test.js")
        assert "function" in patterns

    def test_get_patterns_for_tsx_fallback(self):
        patterns = _get_patterns_for_file("test.tsx")
        assert patterns is not None

    def test_get_patterns_for_unknown(self):
        patterns = _get_patterns_for_file("test.xyz")
        assert patterns is not None  # falls back to .py

    def test_extract_module_name_python_from(self):
        result = _extract_module_name("from app.utils import helper", ".py")
        assert result == "app.utils"

    def test_extract_module_name_python_import(self):
        result = _extract_module_name("import os", ".py")
        assert result == "os"

    def test_extract_module_name_js_require(self):
        result = _extract_module_name("const express = require('express')", ".js")
        assert result == "express"

    def test_extract_module_name_js_import(self):
        result = _extract_module_name("import { Router } from 'express'", ".js")
        assert result == "express"

    def test_extract_module_name_go(self):
        result = _extract_module_name('import "fmt"', ".go")
        assert result == "fmt"

    def test_extract_module_name_rust(self):
        result = _extract_module_name("use std::io;", ".rs")
        assert result == "std::io"

    def test_extract_module_name_java(self):
        result = _extract_module_name("import java.util.List", ".java")
        assert result == "java.util.List"


class TestSpecialistToolsRegistry:
    def test_registry_has_tools(self):
        assert len(SPECIALIST_TOOLS) > 0

    def test_read_file_registered(self):
        assert "read_file" in SPECIALIST_TOOLS

    def test_list_files_registered(self):
        assert "list_files" in SPECIALIST_TOOLS

    def test_partial_update_registered(self):
        assert "partial_update" in SPECIALIST_TOOLS

    def test_insert_content_registered(self):
        assert "insert_content" in SPECIALIST_TOOLS

    def test_regex_replace_registered(self):
        assert "regex_replace" in SPECIALIST_TOOLS

    def test_run_command_registered(self):
        assert "run_command" in SPECIALIST_TOOLS

    def test_all_registered_tools_have_fn(self):
        for name, tool in SPECIALIST_TOOLS.items():
            assert callable(tool["fn"]), f"{name} fn not callable"

    def test_all_registered_tools_have_description(self):
        for name, tool in SPECIALIST_TOOLS.items():
            assert tool.get("description"), f"{name} missing description"


class TestSymbolPatterns:
    def test_python_patterns_exist(self):
        assert ".py" in _SYMBOL_PATTERNS
        patterns = _SYMBOL_PATTERNS[".py"]
        assert "function" in patterns
        assert "class" in patterns
        assert "import" in patterns

    def test_js_patterns_exist(self):
        assert ".js" in _SYMBOL_PATTERNS

    def test_go_patterns_exist(self):
        assert ".go" in _SYMBOL_PATTERNS

    def test_jsx_fallback(self):
        assert _SYMBOL_PATTERNS[".jsx"] is None  # falls back to .js

    def test_tsx_fallback(self):
        assert _SYMBOL_PATTERNS[".tsx"] is None  # falls back to .ts


class TestExtByLang:
    def test_python_mappings(self):
        assert _EXT_BY_LANG["python"] == ".py"
        assert _EXT_BY_LANG["py"] == ".py"

    def test_js_mappings(self):
        assert _EXT_BY_LANG["javascript"] == ".js"
        assert _EXT_BY_LANG["js"] == ".js"

    def test_go_mappings(self):
        assert _EXT_BY_LANG["go"] == ".go"
        assert _EXT_BY_LANG["golang"] == ".go"


class TestWriteSyntaxWarning:
    """写前语法警告复用共享校验器，不能把合法 TS/Vue/HTML 片段判为错误。"""

    def test_typescript_type_annotations_are_accepted(self):
        from app.agent.tools import _validate_file_syntax

        assert _validate_file_syntax("src/api.ts", "export const n: number = 1;\n") == ""

    def test_vue_single_file_component_is_accepted(self):
        from app.agent.tools import _validate_file_syntax

        content = (
            "<template><div>hi</div></template>\n"
            "<script>export default { name: 'A' }</script>\n"
        )

        assert _validate_file_syntax("src/App.vue", content) == ""

    def test_html_fragment_with_markup_inside_script_string_is_accepted(self):
        from app.agent.tools import _validate_file_syntax

        content = '<script>\nconst t = "<body>";\n</script>\n'

        assert _validate_file_syntax("partial.html", content) == ""

    def test_css_delimiters_inside_strings_and_comments_are_accepted(self):
        from app.agent.tools import _validate_file_syntax

        content = '/* } */\nbody::after {\n  content: "}";\n  background: url("a(b");\n}\n'

        assert _validate_file_syntax("styles.css", content) == ""

    def test_real_defects_are_still_reported(self):
        from app.agent.tools import _validate_file_syntax

        assert _validate_file_syntax("app.py", "def f(:\n").startswith("Python 语法错误")
        assert "JavaScript 语法错误" in _validate_file_syntax("a.js", "const x = ;\n")
        assert "</script>" in _validate_file_syntax(
            "broken.html", "<html><body><script>var a=1;</body></html>"
        )
        assert "大括号不匹配" in _validate_file_syntax("broken.css", "body {\n  margin: 0;\n")


class TestWriteFileEmptyContentGate:
    """空内容门禁：拒绝普通空文件，放行空 __init__.py 包标记。"""

    def test_empty_package_entry_is_written(self, tmp_path):
        from app.agent.tools import _tool_write_file

        result = _tool_write_file(str(tmp_path), "pkg/__init__.py", "")

        assert result["success"] is True
        assert (tmp_path / "pkg" / "__init__.py").read_text(encoding="utf-8") == ""

    def test_empty_regular_file_is_rejected(self, tmp_path):
        from app.agent.tools import _tool_write_file

        result = _tool_write_file(str(tmp_path), "pkg/main.py", "")

        assert result["success"] is False
        assert "内容为空" in result["error"]
        assert not (tmp_path / "pkg" / "main.py").exists()


class TestWriteFileDotfileGate:
    """点号文件名（.gitignore 等）不应被误判为无效名或被白名单吞掉。"""

    def test_dotfile_is_written(self, tmp_path):
        from app.agent.tools import _tool_write_file

        result = _tool_write_file(str(tmp_path), ".gitignore", "node_modules/\n")

        assert result["success"] is True
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"

    def test_dotfile_matches_dependency_graph_whitelist(self, tmp_path):
        from app.agent.tools import _tool_write_file, set_allowed_file_paths

        set_allowed_file_paths({".gitignore", "app/main.py"})
        try:
            result = _tool_write_file(str(tmp_path), ".gitignore", "node_modules/\n")
            assert result["success"] is True
            assert (tmp_path / ".gitignore").exists()
        finally:
            set_allowed_file_paths(None)

    def test_path_outside_whitelist_is_still_rejected(self, tmp_path):
        from app.agent.tools import _tool_write_file, set_allowed_file_paths

        set_allowed_file_paths({"app/main.py"})
        try:
            result = _tool_write_file(str(tmp_path), ".gitignore", "node_modules/\n")
            assert result["success"] is False
            assert "不在依赖图中" in result["error"]
        finally:
            set_allowed_file_paths(None)

    def test_dot_dot_filename_is_rejected(self, tmp_path):
        from app.agent.tools import _tool_write_file

        result = _tool_write_file(str(tmp_path), "..", "x")

        assert result["success"] is False
        assert "无效的文件名" in result["error"]
