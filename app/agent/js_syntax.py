"""Shared JavaScript/TypeScript syntax checks for generation-time gates.

`node -c` parses plain JS/ESM only: it rejects decorators, type annotations and
JSX, so TS/TSX must go through the TypeScript parser, and a signal-killed node
(negative return code, e.g. OOM) is an environment fault rather than a source
syntax error. Both the spec-first gate and the refinement loop share these rules.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

_PYTHON_ONLY_PATTERNS = (
    r'^\s*def\s+\w+\s*\(.*\)\s*:',
    r'^\s*elif\s+.*:\s*$',
    r'^\s*class\s+\w+(\([^)]*\))?\s*:\s*$',
    r'\bself\.',
)


def has_python_only_syntax(source: str) -> bool:
    """检测 JS/TS 源码中出现的 Python 专有语法。"""
    return any(re.search(p, source, re.MULTILINE) for p in _PYTHON_ONLY_PATTERNS)


def balanced_delimiters(source: str) -> bool:
    return source.count('{') == source.count('}') and source.count('(') == source.count(')')


def _heuristic_js(source: str) -> Tuple[bool, str]:
    if has_python_only_syntax(source):
        return False, "源码中出现 Python 专有语法"
    if not balanced_delimiters(source):
        return False, "花括号或圆括号不匹配"
    return True, ""


def check_js_source(source: str) -> Tuple[bool, str]:
    """校验 JS/ESM 源码，返回 (是否通过, 错误信息)。

    node 缺失、超时或被信号终止时退回语法启发式，避免把合法代码判为失败。
    """
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(source)
            tmp_path = f.name
        try:
            result = subprocess.run(
                ['node', '-c', tmp_path], capture_output=True, text=True, timeout=5
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        if result.returncode < 0:
            return _heuristic_js(source)
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _heuristic_js(source)


def check_ts_source(source: str, *, jsx: bool = False) -> Tuple[bool, str]:
    """校验 TypeScript/TSX 源码，返回 (是否通过, 错误信息)。"""
    if jsx and has_python_only_syntax(source):
        return False, "源码中出现 Python 专有语法"
    balanced = balanced_delimiters(source)
    unbalanced_error = "花括号或圆括号不匹配"
    tsc_path = shutil.which('tsc')
    if not tsc_path:
        return balanced, "" if balanced else unbalanced_error
    typescript_module = Path(tsc_path).resolve().parent.parent / 'lib' / 'typescript.js'
    if not typescript_module.is_file():
        return balanced, "" if balanced else unbalanced_error
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx' if jsx else '.ts', delete=False) as f:
            f.write(source)
            tmp_path = f.name
        try:
            jsx_option = ",jsx:ts.JsxEmit.React" if jsx else ""
            script = (
                "const ts=require(process.argv[1]);const fs=require('fs');"
                "const source=fs.readFileSync(process.argv[2],'utf8');"
                "const result=ts.transpileModule(source,{reportDiagnostics:true,compilerOptions:{"
                "target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,"
                "experimentalDecorators:true,emitDecoratorMetadata:true" + jsx_option + "}});"
                "process.exit(result.diagnostics?.some(d=>d.category===ts.DiagnosticCategory.Error)?1:0);"
            )
            result = subprocess.run(
                ['node', '-e', script, str(typescript_module), tmp_path],
                capture_output=True, text=True, timeout=5,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        if result.returncode < 0:
            return balanced, "" if balanced else unbalanced_error
        if result.returncode != 0:
            return False, result.stderr.strip() or "TypeScript 语法错误"
        return True, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return balanced, "" if balanced else unbalanced_error


def vue_script_source(content: str) -> Tuple[str, bool, bool]:
    """提取 .vue 单文件组件的 <script> 块。

    返回 (script 源码, 是否 TS, 是否 TSX)。无 <script> 时源码为空串。
    """
    blocks = re.findall(r'<script([^>]*)>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
    if not blocks:
        return "", False, False
    langs = {
        match.group(1).lower()
        for attrs, _ in blocks
        if (match := re.search(r'lang\s*=\s*["\']?(\w+)["\']?', attrs, re.IGNORECASE))
    }
    return "\n;\n".join(body for _, body in blocks), bool(langs & {'ts', 'tsx'}), 'tsx' in langs


__all__ = [
    "balanced_delimiters",
    "check_js_source",
    "check_ts_source",
    "has_python_only_syntax",
    "vue_script_source",
]
