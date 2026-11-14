"""补齐 js_syntax 的 node/tsc 子进程与降级分支。"""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import js_syntax


def test_heuristic_detects_python_syntax():
    ok, error = js_syntax._heuristic_js("def main():\n    pass\n")

    assert ok is False
    assert "Python" in error


def test_heuristic_detects_unbalanced():
    ok, error = js_syntax._heuristic_js("const x = {")

    assert ok is False
    assert "不匹配" in error


def test_heuristic_accepts_valid():
    assert js_syntax._heuristic_js("const x = {a: 1};") == (True, "")


def test_check_js_source_negative_return_uses_heuristic(monkeypatch):
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=-9, stderr="killed"),
    )

    assert js_syntax.check_js_source("const x = 1;") == (True, "")


def test_check_js_source_positive_return_reports_stderr(monkeypatch):
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="SyntaxError"),
    )

    assert js_syntax.check_js_source("const = 1;") == (False, "SyntaxError")


def test_check_js_source_success(monkeypatch):
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
    )

    assert js_syntax.check_js_source("const x = 1;") == (True, "")


def test_check_js_source_missing_node_uses_heuristic(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(js_syntax.subprocess, "run", boom)

    assert js_syntax.check_js_source("const x = 1;") == (True, "")


def test_check_js_source_timeout_uses_heuristic(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("node", 5)

    monkeypatch.setattr(js_syntax.subprocess, "run", boom)

    assert js_syntax.check_js_source("const x = 1;") == (True, "")


def test_check_ts_source_jsx_python_syntax_rejected():
    assert js_syntax.check_ts_source("def main(): pass", jsx=True) == (
        False,
        "源码中出现 Python 专有语法",
    )


def test_check_ts_source_no_tsc(monkeypatch):
    monkeypatch.setattr(js_syntax.shutil, "which", lambda name: None)

    assert js_syntax.check_ts_source("const x: number = 1;") == (True, "")
    assert js_syntax.check_ts_source("const x = {") == (False, "花括号或圆括号不匹配")


def test_check_ts_source_missing_typescript_module(monkeypatch, tmp_path):
    tsc = tmp_path / "bin" / "tsc"
    tsc.parent.mkdir()
    tsc.write_text("", encoding="utf-8")
    monkeypatch.setattr(js_syntax.shutil, "which", lambda name: str(tsc))

    assert js_syntax.check_ts_source("const x = 1;") == (True, "")


def _install_fake_tsc(monkeypatch, tmp_path):
    tsc = tmp_path / "bin" / "tsc"
    tsc.parent.mkdir()
    tsc.write_text("", encoding="utf-8")
    module = tmp_path / "lib" / "typescript.js"
    module.parent.mkdir()
    module.write_text("", encoding="utf-8")
    monkeypatch.setattr(js_syntax.shutil, "which", lambda name: str(tsc))
    return module


def test_check_ts_source_success(monkeypatch, tmp_path):
    _install_fake_tsc(monkeypatch, tmp_path)
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
    )

    assert js_syntax.check_ts_source("const x: number = 1;") == (True, "")


def test_check_ts_source_diagnostics_error(monkeypatch, tmp_path):
    _install_fake_tsc(monkeypatch, tmp_path)
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="TS1005"),
    )

    assert js_syntax.check_ts_source("const x: = 1;", jsx=True) == (False, "TS1005")


def test_check_ts_source_empty_stderr_fallback(monkeypatch, tmp_path):
    _install_fake_tsc(monkeypatch, tmp_path)
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr=""),
    )

    assert js_syntax.check_ts_source("const x: = 1;") == (False, "TypeScript 语法错误")


def test_check_ts_source_negative_return_balanced(monkeypatch, tmp_path):
    _install_fake_tsc(monkeypatch, tmp_path)
    monkeypatch.setattr(
        js_syntax.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=-9, stderr=""),
    )

    assert js_syntax.check_ts_source("const x = 1;") == (True, "")
    assert js_syntax.check_ts_source("const x = {") == (False, "花括号或圆括号不匹配")


def test_check_ts_source_timeout_falls_back(monkeypatch, tmp_path):
    _install_fake_tsc(monkeypatch, tmp_path)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("node", 5)

    monkeypatch.setattr(js_syntax.subprocess, "run", boom)

    assert js_syntax.check_ts_source("const x = 1;") == (True, "")


def test_vue_script_source_without_script():
    assert js_syntax.vue_script_source("<template><div/></template>") == ("", False, False)


def test_vue_script_source_tsx():
    content = '<script lang="tsx">const A = <div/>;</script>'

    source, is_ts, is_tsx = js_syntax.vue_script_source(content)

    assert "const A" in source
    assert is_ts is True
    assert is_tsx is True
