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

_PYTHON_ONLY_PATTERNS = (
    r'^\s*def\s+\w+\s*\(.*\)\s*:',
    r'^\s*elif\s+.*:\s*$',
    r'^\s*class\s+\w+(\([^)]*\))?\s*:\s*$',
    r'\bself\.',
)

# `node -c file.js` parses .js as CommonJS, so an invalid ESM module exits 0.
# Detect module syntax and re-check it in module mode to close that blind spot.
_ESM_PATTERN = re.compile(
    r'(?m)^\s*(?:export\b|import\s+(?!\()|import\.meta\b)'
)

# JSX is legal in .js files for React/Vite setups; when the module check fails
# we give JSX a chance in the JSX-aware parser instead of rejecting valid code.
_JSX_PATTERN = re.compile(r'<[A-Za-z][\w.:-]*(?:\s|/?>)')
_JSX_CLOSING_PATTERN = re.compile(r'</[A-Za-z]')


def _looks_like_esm(source: str) -> bool:
    return bool(_ESM_PATTERN.search(source))


def _looks_like_jsx(source: str) -> bool:
    return bool(_JSX_PATTERN.search(source) or _JSX_CLOSING_PATTERN.search(source))


def _try_jsx_parser(source: str, stderr: str) -> tuple[bool, str] | None:
    """Re-check with the JSX parser only when the failure is about a JSX token."""
    if "<" not in stderr or not _looks_like_jsx(source):
        return None
    return check_ts_source(source, jsx=True)


def has_python_only_syntax(source: str) -> bool:
    """检测 JS/TS 源码中出现的 Python 专有语法。"""
    return any(re.search(p, source, re.MULTILINE) for p in _PYTHON_ONLY_PATTERNS)


def balanced_delimiters(source: str) -> bool:
    return source.count('{') == source.count('}') and source.count('(') == source.count(')')


def _heuristic_js(source: str) -> tuple[bool, str]:
    if has_python_only_syntax(source):
        return False, "源码中出现 Python 专有语法"
    if not balanced_delimiters(source):
        return False, "花括号或圆括号不匹配"
    return True, ""


def _node_typescript_check(source: str) -> tuple[bool, str] | None:
    """Parse TS with node's built-in stripper when no `tsc` is installed.

    `stripTypeScriptTypes` exists in Node 22.6+ and surfaces syntax errors for
    non-JSX TypeScript, giving a real gate instead of a delimiter heuristic.
    Returns None when the runtime lacks the API so callers can degrade.
    """
    script = (
        "const m=require('node:module');"
        "if(typeof m.stripTypeScriptTypes!=='function'){process.exit(2);}"
        "let b='';process.stdin.setEncoding('utf8');"
        "process.stdin.on('data',d=>b+=d);"
        "process.stdin.on('end',()=>{try{m.stripTypeScriptTypes(b,{mode:'transform'});}"
        "catch(e){process.stderr.write(String(e.message||e));process.exit(1);}});"
    )
    try:
        result = subprocess.run(
            ['node', '-e', script],
            input=source,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode == 2 or result.returncode < 0:
        return None
    if result.returncode != 0:
        return False, result.stderr.strip() or "TypeScript 语法错误"
    return True, ""


def check_js_source(source: str) -> tuple[bool, str]:
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
            # JSX in a .js file is valid for React/Vite projects; node's
            # CommonJS parser cannot read it, so give the JSX parser a chance.
            jsx_result = _try_jsx_parser(source, result.stderr)
            if jsx_result is not None:
                return jsx_result
            return False, result.stderr.strip()
        if _looks_like_esm(source):
            try:
                module_result = subprocess.run(
                    ['node', '--input-type=module', '--check'],
                    input=source, capture_output=True, text=True, timeout=5,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return True, ""
            if module_result.returncode < 0:
                return True, ""
            if module_result.returncode != 0:
                jsx_result = _try_jsx_parser(source, module_result.stderr)
                if jsx_result is not None:
                    return jsx_result
                return False, module_result.stderr.strip()
        return True, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _heuristic_js(source)


def check_ts_source(source: str, *, jsx: bool = False) -> tuple[bool, str]:
    """校验 TypeScript/TSX 源码，返回 (是否通过, 错误信息)。"""
    if jsx and has_python_only_syntax(source):
        return False, "源码中出现 Python 专有语法"
    balanced = balanced_delimiters(source)
    unbalanced_error = "花括号或圆括号不匹配"

    def _fallback() -> tuple[bool, str]:
        if not balanced:
            return False, unbalanced_error
        # node's stripper cannot parse JSX, so only route TSX through it when
        # the source has no JSX tokens to trip it up.
        if not jsx or not _looks_like_jsx(source):
            node_result = _node_typescript_check(source)
            if node_result is not None:
                return node_result
        return True, ""

    tsc_path = shutil.which('tsc')
    if not tsc_path:
        return _fallback()
    typescript_module = Path(tsc_path).resolve().parent.parent / 'lib' / 'typescript.js'
    if not typescript_module.is_file():
        return _fallback()
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
            return _fallback()
        if result.returncode != 0:
            return False, result.stderr.strip() or "TypeScript 语法错误"
        return True, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _fallback()


def vue_script_source(content: str) -> tuple[str, bool, bool]:
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
