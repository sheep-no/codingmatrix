"""Authoritative syntax/build diagnostics from the installed language toolchains.

Hand-written parsers only cover Python semantics; TypeScript, Go and Java were
accepted unconditionally during generation. The installed compilers already own
the real grammar rules, so the adapter layer borrows them instead of
reimplementing each language. Every probe is best-effort: a missing toolchain
degrades to "no diagnostics" rather than rejecting valid source.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.agent.js_syntax import balanced_delimiters, check_js_source, check_ts_source

_GOFMT_TIMEOUT_SECONDS = 10
_JAVAC_TIMEOUT_SECONDS = 30
_MAX_DIAGNOSTIC_LINES = 6

# javac runs attribution even with -XDshould-stop.at=PARSE, so a file that
# references a sibling project class is reported as "cannot find symbol". Those
# are cross-file/resolution concerns owned by the contract gate, not syntax.
_JAVA_ATTRIBUTION_MARKERS = (
    "cannot find symbol",
    "package ",
    "does not exist",
    "incompatible types",
    "cannot be applied",
    "unreported exception",
)


def _go_diagnostics(content: str) -> tuple[str, ...]:
    gofmt = shutil.which("gofmt")
    if gofmt is None:
        return ()
    try:
        completed = subprocess.run(
            [gofmt, "-e"],
            input=content,
            capture_output=True,
            text=True,
            timeout=_GOFMT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if completed.returncode == 0:
        return ()
    messages = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
    if not messages:
        return ()
    return (f"Go syntax error: {'; '.join(messages[:_MAX_DIAGNOSTIC_LINES])}",)


def _java_diagnostics(content: str, file_path: str) -> tuple[str, ...]:
    javac = shutil.which("javac")
    if javac is None:
        return ()
    # Keep the real file name so a genuine public-type/file-name mismatch is
    # still reported. Without a path, use the declared public type name so that
    # valid source is not rejected against an arbitrary synthetic name.
    class_name = Path(file_path).stem
    if not class_name:
        match = re.search(
            r"public\s+(?:final\s+|abstract\s+|sealed\s+)*"
            r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)",
            content,
        )
        class_name = match.group(1) if match else "Generated"
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        source = root / "src"
        output = root / "out"
        source.mkdir()
        output.mkdir()
        target = source / f"{class_name}.java"
        try:
            target.write_text(content, encoding="utf-8")
        except OSError:
            return ()
        try:
            completed = subprocess.run(
                [javac, "-proc:none", "-XDshould-stop.at=PARSE", "-d", str(output), str(target)],
                capture_output=True,
                text=True,
                timeout=_JAVAC_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
    if completed.returncode == 0:
        return ()
    errors = [
        line.strip().replace(f"{target}:", "")
        for line in completed.stderr.splitlines()
        if "error:" in line
        and not any(marker in line for marker in _JAVA_ATTRIBUTION_MARKERS)
    ]
    if not errors:
        return ()
    return (f"Java syntax error: {'; '.join(errors[:_MAX_DIAGNOSTIC_LINES])}",)


def _javascript_diagnostics(content: str, file_path: str) -> tuple[str, ...]:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".ts", ".tsx"}:
        ok, error = check_ts_source(content, jsx=suffix == ".tsx")
    elif suffix == ".jsx":
        # .jsx exists to carry JSX; node -c rejects it, so use the JSX parser.
        ok, error = check_ts_source(content, jsx=True)
    elif suffix in {".mjs", ".cjs", ".js"}:
        ok, error = check_js_source(content)
    else:
        return ()
    if ok:
        return ()
    lines = [line.strip() for line in (error or "").splitlines() if line.strip()]
    # Prefer the parser's own message line; the first line is a temp path that
    # would make retry feedback differ between attempts.
    syntax_line = next((line for line in lines if "Error:" in line), None)
    detail = (syntax_line or (lines[0] if lines else "")).replace("SyntaxError: ", "")
    detail = detail or "invalid source"
    return (f"JavaScript syntax error: {detail}",)


def compiler_source_diagnostics(language: str, content: str, file_path: str = "") -> tuple[str, ...]:
    """Return compiler-owned diagnostics, degrading silently when unavailable."""
    if not content:
        return ()
    normalized = (language or "").lower()
    if normalized in {"js", "ts", "typescript", "javascript"}:
        return _javascript_diagnostics(content, file_path)
    if normalized == "go":
        return _go_diagnostics(content)
    if normalized == "java":
        return _java_diagnostics(content, file_path)
    return ()


__all__ = ["balanced_delimiters", "compiler_source_diagnostics"]
