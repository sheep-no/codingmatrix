"""Compiler-owned diagnostics must stay accurate and degrade without tooling."""

from __future__ import annotations

import shutil

import pytest

from app.agent import compiler_diagnostics


def test_empty_source_produces_no_diagnostics() -> None:
    assert compiler_diagnostics.compiler_source_diagnostics("go", "") == ()


def test_unknown_language_is_not_probed() -> None:
    assert compiler_diagnostics.compiler_source_diagnostics("cobol", "IDENTIFICATION DIVISION.") == ()


def test_go_syntax_error_is_reported_when_gofmt_present() -> None:
    if shutil.which("gofmt") is None:
        pytest.skip("gofmt is not installed")

    diagnostics = compiler_diagnostics.compiler_source_diagnostics(
        "go", "package main\n\nfunc main( {\n"
    )

    assert diagnostics
    assert diagnostics[0].startswith("Go syntax error:")


def test_valid_go_source_has_no_diagnostics() -> None:
    if shutil.which("gofmt") is None:
        pytest.skip("gofmt is not installed")

    content = "package main\n\nfunc main() {\n}\n"

    assert compiler_diagnostics.compiler_source_diagnostics("go", content) == ()


def test_go_probe_degrades_when_gofmt_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compiler_diagnostics.shutil, "which", lambda name: None)

    assert compiler_diagnostics.compiler_source_diagnostics("go", "package") == ()


def test_java_syntax_error_is_reported_when_javac_present() -> None:
    if shutil.which("javac") is None:
        pytest.skip("javac is not installed")

    diagnostics = compiler_diagnostics.compiler_source_diagnostics(
        "java", "public class App {\n    void broken( {\n}\n", "src/App.java"
    )

    assert diagnostics
    assert diagnostics[0].startswith("Java syntax error:")


def test_java_missing_symbol_is_not_a_syntax_error() -> None:
    if shutil.which("javac") is None:
        pytest.skip("javac is not installed")

    content = (
        "public class App {\n"
        "    Store store = new Store();\n"
        "}\n"
    )

    assert compiler_diagnostics.compiler_source_diagnostics("java", content, "App.java") == ()


def test_java_lowercase_file_name_keeps_real_name() -> None:
    if shutil.which("javac") is None:
        pytest.skip("javac is not installed")

    content = "public class main {\n}\n"

    # A non-public class in a lowercase file is legal and must not be rejected.
    assert compiler_diagnostics.compiler_source_diagnostics("java", content, "main.java") == ()


def test_javascript_diagnostic_drops_temp_path_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    noisy = "/tmp/tmpabc.js:1\nSyntaxError: Unexpected token ';'\n    at node:internal"
    monkeypatch.setattr(
        compiler_diagnostics, "check_js_source", lambda _source: (False, noisy)
    )

    diagnostics = compiler_diagnostics.compiler_source_diagnostics(
        "javascript", "const value = ;\n", "src/app.js"
    )

    assert diagnostics == ("JavaScript syntax error: Unexpected token ';'",)


def test_typescript_tsx_jsx_is_accepted() -> None:
    content = "export const App = () => <div>ok</div>;\n"

    assert compiler_diagnostics.compiler_source_diagnostics("typescript", content, "src/App.tsx") == ()
