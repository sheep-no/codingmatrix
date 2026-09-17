import shutil

from app.agent import utils


def test_runtime_validation_is_delegated_to_local_agent_host(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda command: None)

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "print('hello')"},
        level="run",
    )

    assert passed is True
    assert errors == []


def test_cloud_validation_skips_when_bwrap_is_unavailable(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda command: None)

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "print('hello')"},
        level="syntax",
    )

    assert passed is True
    assert errors == []


def test_python_syntax_is_checked_without_bwrap(monkeypatch):
    """Python 语法用 ast.parse 本地判定，bwrap 缺失也真正校验。"""
    monkeypatch.setattr(shutil, "which", lambda command: None)

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "def broken(:\n"},
        level="syntax",
    )

    assert passed is False
    assert any("Python 语法错误" in error for error in errors)


def test_runtime_levels_stay_delegated_to_agent_host():
    """run/import/contract 属本地运行时职责，云端不接管。"""
    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.py": "def broken(:\n"},
        level="import",
    )

    assert passed is True
    assert errors == []


def test_shared_gate_accepts_typescript_annotations():
    """TS 类型注解/JSX 走共享门禁，不再被 node --check 误判为语法错误。"""
    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={
            "main.ts": "interface Props { title: string }\nconst x: number = 1;\nexport default x;\n",
            "App.tsx": "type P = { n: number };\nexport default function App(p: P) { return null; }\n",
        },
        level="syntax",
    )

    assert passed is True
    assert errors == []


def test_shared_gate_accepts_vue_single_file_component():
    """Vue 的 <script> 块按 JS 校验，export default 对象字面量合法。"""
    content = (
        "<template><div>{{ count }}</div></template>\n"
        "<script>\nexport default { name: 'App', data() { return { count: 1 } } }\n</script>\n"
    )

    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"App.vue": content},
        level="syntax",
    )

    assert passed is True
    assert errors == []


def test_shared_gate_reports_unbalanced_typescript():
    """真正的 TS 结构缺陷仍然被拦下，门禁没有整体放行。"""
    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"main.ts": "export default function App() {\n"},
        level="syntax",
    )

    assert passed is False
    assert errors


def test_documentation_files_skip_code_syntax_gate():
    """散文里的括号不构成代码语法错误。"""
    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={"README.md": "see [1 and (foo\n"},
        level="syntax",
    )

    assert passed is True
    assert errors == []


def test_markup_uses_structure_gate_not_raw_counting():
    """注释与字符串里的定界符不算结构错误。"""
    passed, errors = utils.validate_in_sandbox(
        project_dir="/tmp/project",
        files={
            "index.html": "<!DOCTYPE html>\n<html><body><!-- [ --><p>hi</p></body></html>\n",
            "style.css": '/* (todo */\n.a { content: "("; }\n',
        },
        level="syntax",
    )

    assert passed is True
    assert errors == []
