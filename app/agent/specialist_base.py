import re
import json
import glob
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import asyncio

import httpx
from app.utils.aicloud import call_llm
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter
from app.agent.tracing import traced

logger = logging.getLogger(__name__)

MAX_CONCURRENT_LLM_CALLS = 6

# 不可恢复的错误 — 重试和 fallback 都无意义
NON_RECOVERABLE_ERRORS = (
    httpx.HTTPStatusError,  # 401/403 等认证/授权错误
)

# 全局共享 LLM 并发 semaphore（所有 orchestrator 共用）
_global_llm_semaphore: Optional[asyncio.Semaphore] = None


def get_global_llm_semaphore() -> asyncio.Semaphore:
    """获取全局共享的 LLM 并发 semaphore"""
    global _global_llm_semaphore
    if _global_llm_semaphore is None:
        _global_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    return _global_llm_semaphore


# ==================== Specialist 内置工具实现 ====================

def _tool_search_files(project_path: str, pattern: str, file_pattern: str = ".*",
                       max_results: int = 50) -> Dict:
    """正则搜索项目文件内容"""
    try:
        proj = Path(project_path)
        regex = re.compile(pattern)
        file_re = re.compile(file_pattern)
        results = []
        for f in proj.rglob("*"):
            if not f.is_file() or '__pycache__' in str(f) or 'node_modules' in str(f):
                continue
            if not file_re.search(f.name):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                for i, line in enumerate(content.split('\n'), 1):
                    if regex.search(line):
                        results.append({
                            "file": str(f.relative_to(proj)),
                            "line": i,
                            "content": line.strip()[:200]
                        })
                        if len(results) >= max_results:
                            return {"results": results}
            except Exception:
                continue
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


def _tool_read_file(project_path: str, file_path: str, offset: int = 0,
                    limit: int = 100) -> Dict:
    """读取文件内容（支持分页）"""
    try:
        full_path = Path(project_path) / file_path
        if not full_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        if not full_path.is_file():
            return {"error": f"不是文件: {file_path}"}
        lines = full_path.read_text(encoding='utf-8', errors='ignore').split('\n')
        total = len(lines)
        start = min(offset, total)
        end = min(start + limit, total)
        return {
            "file": file_path,
            "total_lines": total,
            "offset": start,
            "content": '\n'.join(lines[start:end])
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_grep_files(project_path: str, keyword: str, file_types: str = None,
                     max_results: int = 50) -> Dict:
    """快速全文关键词搜索"""
    try:
        proj = Path(project_path)
        extensions = None
        if file_types:
            extensions = [f".{ext.strip().lstrip('.')}" for ext in file_types.split(',')]
        results = []
        for f in proj.rglob("*"):
            if not f.is_file() or '__pycache__' in str(f) or 'node_modules' in str(f):
                continue
            if extensions and f.suffix not in extensions:
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                if keyword in content:
                    for i, line in enumerate(content.split('\n'), 1):
                        if keyword in line:
                            results.append({
                                "file": str(f.relative_to(proj)),
                                "line": i,
                                "content": line.strip()[:200]
                            })
                            if len(results) >= max_results:
                                return {"results": results}
            except Exception:
                continue
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


def _tool_list_files(project_path: str, directory: str = ".",
                     max_depth: int = 2) -> Dict:
    """列出目录结构"""
    try:
        target = Path(project_path) / directory
        if not target.exists():
            return {"error": f"目录不存在: {directory}"}
        entries = []
        _scan_dir(target, entries, depth=0, max_depth=max_depth, base=Path(project_path))
        return {"directory": directory, "entries": entries[:200]}
    except Exception as e:
        return {"error": str(e)}


def _scan_dir(path: Path, entries: list, depth: int, max_depth: int, base: Path):
    """递归扫描目录"""
    if depth > max_depth:
        return
    try:
        for item in sorted(path.iterdir()):
            if item.name.startswith('.') or item.name in ('__pycache__', 'node_modules', '.git'):
                continue
            rel = str(item.relative_to(base))
            if item.is_dir():
                entries.append({"type": "dir", "path": rel + "/"})
                _scan_dir(item, entries, depth + 1, max_depth, base)
            else:
                entries.append({"type": "file", "path": rel})
    except PermissionError:
        pass


# ============ 代码分析工具（精读级） ============

# 语言对应的符号定义正则
_SYMBOL_PATTERNS = {
    ".py": {
        "function": re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\("),
        "class": re.compile(r"^class\s+(\w+)(?:\s*\([^)]*\))?\s*:"),
        "import": re.compile(r"^(?:from\s+\S+\s+)?import\s+.+"),
    },
    ".js": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?class\s+(\w+)"),
        "import": re.compile(r"^import\s+.+|^const\s+.+\s*=\s*require\("),
    },
    ".ts": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[<(]|(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
        "import": re.compile(r"^import\s+.+"),
    },
    ".jsx": None,  # fallback to .js
    ".tsx": None,  # fallback to .ts
    ".vue": {
        "function": re.compile(r"(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"class\s+(\w+)"),
        "import": re.compile(r"^import\s+.+"),
    },
    ".go": {
        "function": re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\("),
        "class": re.compile(r"^type\s+(\w+)\s+struct\s*\{"),
        "import": re.compile(r"^import\s+[\(\"']|^import\s+\("),
    },
    ".java": {
        "function": re.compile(r"(?:public|private|protected|static|\s)+\s+\w+\s+(\w+)\s*\("),
        "class": re.compile(r"(?:public|private|protected|\s)*\s*(?:class|interface|enum)\s+(\w+)"),
        "import": re.compile(r"^import\s+.+"),
    },
    ".rs": {
        "function": re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
        "class": re.compile(r"(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?enum\s+(\w+)|(?:pub\s+)?trait\s+(\w+)"),
        "import": re.compile(r"^use\s+.+"),
    },
    ".rb": {
        "function": re.compile(r"^\s*def\s+(\w+)"),
        "class": re.compile(r"^\s*class\s+(\w+)|^\s*module\s+(\w+)"),
        "import": re.compile(r"^require|^require_relative|^include"),
    },
}

# 语言特征到扩展名的映射
_EXT_BY_LANG = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "vue": ".vue",
    "go": ".go", "golang": ".go",
    "java": ".java",
    "rust": ".rs", "rs": ".rs",
    "ruby": ".rb", "rb": ".rb",
}


def _get_patterns_for_file(file_path: str) -> Dict:
    """根据文件扩展名获取对应的正则模式"""
    ext = Path(file_path).suffix.lower()
    patterns = _SYMBOL_PATTERNS.get(ext)
    if patterns is None:
        # .jsx -> .js, .tsx -> .ts
        fallback = {".jsx": ".js", ".tsx": ".ts"}.get(ext, ext)
        patterns = _SYMBOL_PATTERNS.get(fallback, _SYMBOL_PATTERNS.get(".py"))
    return patterns


def _tool_read_symbols(project_path: str, file_path: str) -> Dict:
    """提取文件中的函数和类签名（不读取函数体）"""
    try:
        full_path = Path(project_path) / file_path
        if not full_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        if not full_path.is_file():
            return {"error": f"不是文件: {file_path}"}

        content = full_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        patterns = _get_patterns_for_file(file_path)

        symbols = {"functions": [], "classes": [], "total_lines": len(lines)}

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释和空行
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue

            # 匹配函数
            fn_match = patterns["function"].search(line)
            if fn_match:
                name = next(g for g in fn_match.groups() if g is not None)
                # 提取参数列表（简单提取到右括号）
                param_start = line.index('(')
                depth = 0
                param_end = param_start
                for j in range(param_start, min(param_start + 500, len(line))):
                    if line[j] == '(':
                        depth += 1
                    elif line[j] == ')':
                        depth -= 1
                        if depth == 0:
                            param_end = j + 1
                            break
                signature = stripped[:param_end - len(line) + len(stripped) + 1] if param_end > param_start else stripped
                symbols["functions"].append({
                    "name": name,
                    "line": i,
                    "signature": signature[:300]
                })

            # 匹配类
            cls_match = patterns["class"].search(line)
            if cls_match:
                name = next(g for g in cls_match.groups() if g is not None)
                symbols["classes"].append({
                    "name": name,
                    "line": i,
                    "signature": stripped[:300]
                })

        return symbols
    except Exception as e:
        return {"error": str(e)}


def _tool_find_definition(project_path: str, symbol: str, file_types: str = None) -> Dict:
    """查找符号（函数/类/变量）在项目中的定义位置"""
    try:
        proj = Path(project_path)
        extensions = None
        if file_types:
            extensions = [f".{ext.strip().lstrip('.')}" for ext in file_types.split(',')]
        else:
            # 根据项目中的文件自动推断
            extensions = list(_SYMBOL_PATTERNS.keys())

        results = []
        # 定义模式：函数定义、类定义、变量赋值
        def_patterns = [
            re.compile(rf"(?:async\s+)?def\s+{re.escape(symbol)}\s*\("),
            re.compile(rf"class\s+{re.escape(symbol)}\b"),
            re.compile(rf"^(?:const|let|var|export)\s+{re.escape(symbol)}\s*="),
            re.compile(rf"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?{re.escape(symbol)}\s*\("),
            re.compile(rf"(?:pub\s+)?(?:fn|struct|enum|trait)\s+{re.escape(symbol)}\b"),
            re.compile(rf"^(?:public|private|protected|static|\s)*\s*(?:class|interface|enum)\s+{re.escape(symbol)}\b"),
            re.compile(rf"type\s+{re.escape(symbol)}\s+struct\b"),
            re.compile(rf"^\s*def\s+{re.escape(symbol)}\s*\("),  # Ruby
            re.compile(rf"^\s*(?:class|module)\s+{re.escape(symbol)}\b"),
        ]

        for f in proj.rglob("*"):
            if not f.is_file() or '__pycache__' in str(f) or 'node_modules' in str(f):
                continue
            if extensions and f.suffix not in extensions:
                continue
            try:
                file_content = f.read_text(encoding='utf-8', errors='ignore')
                for i, line in enumerate(file_content.split('\n'), 1):
                    for pat in def_patterns:
                        if pat.search(line):
                            results.append({
                                "file": str(f.relative_to(proj)),
                                "line": i,
                                "content": line.strip()[:200]
                            })
                            if len(results) >= 20:
                                return {"symbol": symbol, "definitions": results}
            except Exception:
                continue

        return {"symbol": symbol, "definitions": results}
    except Exception as e:
        return {"error": str(e)}


def _tool_read_imports(project_path: str, file_path: str) -> Dict:
    """提取文件中的 import 语句，分析依赖关系"""
    try:
        full_path = Path(project_path) / file_path
        if not full_path.exists():
            return {"error": f"文件不存在: {file_path}"}

        content = full_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        patterns = _get_patterns_for_file(file_path)
        import_pat = patterns.get("import")

        imports = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            if import_pat and import_pat.search(stripped):
                # 解析导入的模块名
                module = _extract_module_name(stripped, Path(file_path).suffix)
                imports.append({
                    "line": i,
                    "statement": stripped[:300],
                    "module": module
                })

        return {
            "file": file_path,
            "imports": imports,
            "import_count": len(imports)
        }
    except Exception as e:
        return {"error": str(e)}


def _extract_module_name(statement: str, ext: str) -> str:
    """从 import 语句中提取模块名"""
    s = statement.strip()
    if ext == '.py':
        # from xxx.yyy import zzz -> xxx.yyy
        # import xxx.yyy -> xxx.yyy
        m = re.match(r"from\s+(\S+)", s)
        if m:
            return m.group(1)
        m = re.match(r"import\s+(\S+)", s)
        if m:
            return m.group(1).split('.')[0]
    elif ext in ('.js', '.ts', '.jsx', '.tsx', '.vue'):
        # import xxx from 'yyy' -> yyy
        # import { x } from 'yyy' -> yyy
        m = re.search(r"from\s+['\"]([^'\"]+)['\"]", s)
        if m:
            return m.group(1)
        m = re.search(r"import\s+['\"]([^'\"]+)['\"]", s)
        if m:
            return m.group(1)
        m = re.match(r"const\s+\w+\s*=\s*require\(['\"]([^'\"]+)['\"]\)", s)
        if m:
            return m.group(1)
    elif ext == '.go':
        m = re.search(r'"([^"]+)"', s)
        if m:
            return m.group(1)
    elif ext == '.rs':
        m = re.match(r"use\s+(.+?);", s)
        if m:
            return m.group(1)
    elif ext == '.java':
        m = re.match(r"import\s+([\w.]+)", s)
        if m:
            return m.group(1)
    return s[:50]


def _tool_find_references(project_path: str, symbol: str, file_types: str = None,
                          max_results: int = 50) -> Dict:
    """查找符号在项目中的引用位置（排除定义自身）"""
    try:
        proj = Path(project_path)
        extensions = None
        if file_types:
            extensions = [f".{ext.strip().lstrip('.')}" for ext in file_types.split(',')]

        # 先找到定义位置
        def_results = _tool_find_definition(project_path, symbol, file_types)
        def_locations = set()
        for d in def_results.get("definitions", []):
            def_locations.add((d["file"], d["line"]))

        # 搜索所有引用
        ref_pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        results = []

        for f in proj.rglob("*"):
            if not f.is_file() or '__pycache__' in str(f) or 'node_modules' in str(f):
                continue
            if extensions and f.suffix not in extensions:
                continue
            try:
                file_content = f.read_text(encoding='utf-8', errors='ignore')
                rel_path = str(f.relative_to(proj))
                for i, line in enumerate(file_content.split('\n'), 1):
                    if ref_pattern.search(line):
                        # 排除定义行自身
                        if (rel_path, i) not in def_locations:
                            results.append({
                                "file": rel_path,
                                "line": i,
                                "content": line.strip()[:200]
                            })
                            if len(results) >= max_results:
                                return {"symbol": symbol, "references": results, "definitions_excluded": len(def_locations)}
            except Exception:
                continue

        return {"symbol": symbol, "references": results, "definitions_excluded": len(def_locations)}
    except Exception as e:
        return {"error": str(e)}


def _tool_summarize_file(project_path: str, file_path: str) -> Dict:
    """返回文件摘要：导出的符号、行数、语言、依赖数"""
    try:
        full_path = Path(project_path) / file_path
        if not full_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        if not full_path.is_file():
            return {"error": f"不是文件: {file_path}"}

        content = full_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        ext = Path(file_path).suffix.lower()

        # 获取符号
        symbols = _tool_read_symbols(project_path, file_path)

        # 获取导入
        imports = _tool_read_imports(project_path, file_path)

        # 语言检测
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "react-jsx", ".tsx": "react-tsx", ".vue": "vue",
            ".go": "go", ".java": "java", ".rs": "rust", ".rb": "ruby",
            ".css": "css", ".html": "html", ".json": "json",
            ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
            ".sql": "sql", ".sh": "shell", ".toml": "toml",
        }
        language = lang_map.get(ext, "unknown")

        # 空行和注释统计
        blank = sum(1 for l in lines if not l.strip())
        comment_prefixes = {".py": "#", ".js": "//", ".ts": "//", ".vue": "//",
                            ".go": "//", ".java": "//", ".rs": "//", ".rb": "#"}
        cmt_prefix = comment_prefixes.get(ext, "")
        comments = sum(1 for l in lines if l.strip().startswith(cmt_prefix)) if cmt_prefix else 0

        return {
            "file": file_path,
            "language": language,
            "total_lines": len(lines),
            "blank_lines": blank,
            "comment_lines": comments,
            "code_lines": len(lines) - blank - comments,
            "functions": len(symbols.get("functions", [])),
            "classes": len(symbols.get("classes", [])),
            "imports": imports.get("import_count", 0),
            "top_symbols": {
                "functions": [f["name"] for f in symbols.get("functions", [])[:20]],
                "classes": [c["name"] for c in symbols.get("classes", [])[:20]],
            },
            "dependencies": [imp["module"] for imp in imports.get("imports", [])[:20]]
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== 写入/验证工具（从 ToolRegistry 适配） ====================

def _tool_partial_update(project_path: str, path: str, target: str = None,
                         replacement: str = None, function_name: str = None) -> Dict:
    """精准替换文件中的函数或代码块"""
    try:
        full_path = Path(project_path) / path if not Path(path).is_absolute() else Path(path)
        if not full_path.exists():
            return {"success": False, "error": f"文件不存在: {path}"}

        content = full_path.read_text(encoding='utf-8')

        if function_name:
            # 按函数名替换
            lang_patterns = [
                (r'(\s*function\s+' + re.escape(function_name) + r'\s*\([^)]*\)\s*\{)', '}'),
                (r'(\s*def\s+' + re.escape(function_name) + r'\s*\([^)]*\)\s*:)', None),
                (r'(\s*(?:const|let|var)\s+' + re.escape(function_name) + r'\s*=\s*(?:\([^)]*\)|[^=]*)\s*(?:=>)?\s*\{?)', None),
                (r'(\s*async\s+function\s+' + re.escape(function_name) + r'\s*\([^)]*\)\s*\{)', '}'),
            ]
            found = False
            for header_pat, end_marker in lang_patterns:
                m = re.search(header_pat, content)
                if m:
                    start_pos = m.start()
                    if end_marker:
                        depth = 0
                        i = m.end() - 1
                        while i < len(content):
                            if content[i] == '{':
                                depth += 1
                            elif content[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    content = content[:start_pos] + replacement + content[i+1:]
                                    found = True
                                    break
                            i += 1
                    else:
                        lines_after = content[start_pos:].split('\n')
                        indent_level = len(lines_after[0]) - len(lines_after[0].lstrip())
                        func_lines = []
                        for j, l in enumerate(lines_after):
                            stripped = l.strip()
                            if j > 0 and stripped and (len(l) - len(l.lstrip()) <= indent_level) and not stripped.startswith('#') and not stripped.startswith('//'):
                                break
                            func_lines.append(l)
                        after_content = '\n'.join(lines_after[len(func_lines):])
                        content = content[:start_pos] + replacement + '\n' + after_content
                        found = True
                    break
            if not found:
                return {"success": False, "error": f"未找到函数: {function_name}"}
        elif target and replacement is not None:
            if target not in content:
                return {"success": False, "error": "未找到目标代码块"}
            content = content.replace(target, replacement, 1)
        else:
            return {"success": False, "error": "需要提供 target+replacement 或 function_name"}

        full_path.write_text(content, encoding='utf-8')
        return {"success": True, "path": str(full_path), "size": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_insert_content(project_path: str, path: str, content: str,
                         line: int = None, anchor: str = None) -> Dict:
    """在文件指定位置插入内容（按行号或锚点文本）"""
    try:
        full_path = Path(project_path) / path if not Path(path).is_absolute() else Path(path)
        if not full_path.exists():
            return {"success": False, "error": f"文件不存在: {path}"}

        original = full_path.read_text(encoding='utf-8')
        lines = original.split('\n')

        if line is not None:
            insert_at = max(0, min(line - 1, len(lines)))
        elif anchor:
            insert_at = -1
            for i, l in enumerate(lines):
                if anchor in l:
                    insert_at = i + 1
                    break
            if insert_at == -1:
                return {"success": False, "error": f"未找到锚点文本: {anchor}"}
        else:
            insert_at = len(lines)

        content_lines = content.split('\n')
        new_lines = lines[:insert_at] + content_lines + lines[insert_at:]
        full_path.write_text('\n'.join(new_lines), encoding='utf-8')
        return {"success": True, "path": str(full_path), "inserted_at_line": insert_at + 1, "lines_inserted": len(content_lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_regex_replace(project_path: str, path: str, pattern: str,
                        replacement: str, recursive: bool = False) -> Dict:
    """基于正则表达式的批量替换"""
    try:
        full_path = Path(project_path) / path if not Path(path).is_absolute() else Path(path)
        if '*' in str(full_path) or '?' in str(full_path):
            files = [Path(f) for f in glob.glob(str(full_path), recursive=recursive) if Path(f).is_file()]
        else:
            files = [full_path] if full_path.is_file() else []

        if not files:
            return {"success": False, "error": f"未匹配到文件: {path}"}

        compiled = re.compile(pattern)
        modified = []
        total_replacements = 0
        for fp in files:
            content = fp.read_text(encoding='utf-8')
            new_content, count = compiled.subn(replacement, content)
            if count > 0:
                fp.write_text(new_content, encoding='utf-8')
                modified.append(str(fp))
                total_replacements += count

        return {"success": True, "files_modified": len(modified), "total_replacements": total_replacements, "modified_files": modified}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_execute_code(project_path: str, code: str, language: str = "python",
                       timeout: int = 30) -> Dict:
    """沙箱执行代码验证（支持 Python 和 JavaScript）"""
    from app.core.config import settings

    if not settings.ENABLE_CODE_SANDBOX:
        return {"success": False, "error": "代码沙箱已禁用，请联系管理员开启"}

    allowed_langs = [l.strip() for l in settings.SANDBOX_LANGUAGES.split(",")]
    if language not in allowed_langs:
        return {"success": False, "error": f"语言 {language} 不在沙箱允许列表中，当前支持: {', '.join(allowed_langs)}"}

    try:
        if language == "python":
            return _execute_python_sandbox(code, timeout)
        elif language in ("javascript", "js", "typescript", "ts"):
            return _execute_js_sandbox(code, timeout)
        else:
            return {"success": False, "error": f"不支持的语言: {language}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_python_sandbox(code: str, timeout: int) -> Dict:
    """Python 沙箱执行"""
    import io
    import sys
    import ast

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "error": f"语法错误 第{e.lineno}行: {e.msg}"}

        # 禁止危险语句
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                if func_name in ("exec", "eval", "compile", "__import__", "open",
                                 "getattr", "setattr", "delattr", "globals", "locals"):
                    return {"success": False, "error": f"安全限制: 不允许调用 {func_name}() 函数"}

        safe_globals = {
            "__builtins__": {
                "print": print, "len": len, "range": range, "list": list,
                "dict": dict, "set": set, "tuple": tuple, "str": str,
                "int": int, "float": float, "bool": bool, "abs": abs,
                "min": min, "max": max, "sum": sum, "sorted": sorted,
                "reversed": reversed, "enumerate": enumerate, "zip": zip,
                "map": map, "filter": filter, "isinstance": isinstance,
                "issubclass": issubclass, "type": type, "id": id,
                "hash": hash, "repr": repr, "format": format,
                "input": None, "open": None, "exec": None, "eval": None,
                "compile": None, "__import__": None,
            }
        }

        exec(code, safe_globals)
        return {"success": True, "output": stdout_capture.getvalue(), "error": stderr_capture.getvalue() or None}
    except Exception as e:
        return {"success": False, "output": stdout_capture.getvalue(), "error": str(e)}
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _execute_js_sandbox(code: str, timeout: int) -> Dict:
    """JavaScript 沙箱执行（通过 Node.js 子进程）"""
    import subprocess
    import tempfile

    # 安全检查：禁止危险操作
    dangerous_patterns = [
        r'\brequire\s*\(\s*["\']child_process["\']',
        r'\brequire\s*\(\s*["\']fs["\']',
        r'\bprocess\.\s*exit',
        r'\bprocess\.\s*env',
        r'\beval\s*\(',
        r'\bFunction\s*\(',
    ]
    for pat in dangerous_patterns:
        if re.search(pat, code):
            return {"success": False, "error": "安全限制: 检测到不允许的操作"}

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            ['node', tmp_path],
            capture_output=True, text=True, timeout=timeout,
            cwd='/tmp'
        )

        import os
        os.unlink(tmp_path)

        if result.returncode == 0:
            return {"success": True, "output": result.stdout, "error": result.stderr or None}
        else:
            return {"success": False, "output": result.stdout, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"执行超时（{timeout}秒）"}
    except FileNotFoundError:
        return {"success": False, "error": "Node.js 未安装，无法执行 JavaScript 代码"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# 危险命令黑名单
_DANGEROUS_COMMANDS = [
    r'\brm\s+(-[a-zA-Z]*[rf]|--recursive)\s+/',  # rm -rf /
    r'\bshutdown\b', r'\breboot\b', r'\bpoweroff\b',
    r'\bmkfs\b', r'\bfdisk\b', r'\bparted\b',
    r'\bchmod\s+777\b', r'\bchown\s+root\b',
    r'\biptables\b', r'\bufw\b',
    r'\buseradd\b', r'\buserdel\b', r'\bpasswd\b',
    r'\bsudo\b', r'\bsu\b',
    r'\bkill\s+-9\s+1\b',  # kill init
    r'\bdd\s+if=', r'\bformat\b',
]

# 允许的命令前缀白名单
_ALLOWED_COMMAND_PREFIXES = [
    'pip install', 'pip3 install', 'pip list', 'pip show', 'pip freeze',
    'npm install', 'npm ci', 'npm run', 'npm test', 'npm build', 'npm start',
    'yarn install', 'yarn add', 'yarn run', 'yarn test',
    'pnpm install', 'pnpm run', 'pnpm test',
    'python', 'python3', 'py',
    'node', 'npx',
    'go build', 'go test', 'go run', 'go mod', 'go get',
    'cargo build', 'cargo test', 'cargo run', 'cargo install',
    'make', 'cmake',
    'mvn', 'gradle',
    'dotnet build', 'dotnet test', 'dotnet run',
    'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find', 'tree',
    'echo', 'printf', 'env', 'pwd', 'whoami', 'date',
    'git status', 'git log', 'git diff', 'git branch', 'git tag',
    'docker ps', 'docker images', 'docker logs',
    'curl', 'wget',
    'pytest', 'jest', 'vitest', 'mocha', 'rspec',
    'gcc', 'g++', 'clang', 'rustc',
]


def _tool_run_command(project_path: str, command: str, cwd: str = None, timeout: int = 60) -> Dict:
    """执行终端命令（构建、安装依赖、运行脚本等）"""
    import subprocess

    try:
        # 安全检查：危险命令
        for pattern in _DANGEROUS_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return {"success": False, "error": "安全限制: 检测到危险命令操作"}

        # 安全检查：命令白名单（至少匹配一个前缀）
        cmd_lower = command.strip().lower()
        allowed = any(cmd_lower.startswith(prefix.lower()) for prefix in _ALLOWED_COMMAND_PREFIXES)
        if not allowed:
            return {"success": False, "error": f"安全限制: 命令不在允许列表中。允许的命令前缀: {', '.join(_ALLOWED_COMMAND_PREFIXES[:10])}..."}

        # 确定工作目录
        work_dir = Path(project_path)
        if cwd:
            work_dir = (work_dir / cwd).resolve()
            # 安全检查：工作目录必须在 project_path 内
            if not str(work_dir).startswith(str(Path(project_path).resolve())):
                return {"success": False, "error": "安全限制: 工作目录必须在项目路径内"}

        if not work_dir.exists():
            return {"success": False, "error": f"工作目录不存在: {work_dir}"}

        # 执行命令
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(work_dir),
            env={
                **subprocess.os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONUNBUFFERED': '1',
            }
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout[-5000:] if result.stdout else "",  # 限制输出长度
            "error": result.stderr[-2000:] if result.stderr else None,
            "return_code": result.returncode,
            "command": command,
            "cwd": str(work_dir),
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"命令执行超时（{timeout}秒）", "command": command}
    except Exception as e:
        return {"success": False, "error": str(e), "command": command}


# 工具注册表（名称 -> 实现函数 + 描述）
SPECIALIST_TOOLS = {
    "search_files": {
        "fn": _tool_search_files,
        "description": "正则搜索项目文件内容。参数: pattern(正则), file_pattern(文件名过滤), max_results",
        "params": {"pattern": "string", "file_pattern": "string(可选)", "max_results": "int(可选)"}
    },
    "read_file": {
        "fn": _tool_read_file,
        "description": "读取文件内容，支持分页。参数: file_path, offset(起始行), limit(行数)",
        "params": {"file_path": "string", "offset": "int(可选)", "limit": "int(可选)"}
    },
    "grep_files": {
        "fn": _tool_grep_files,
        "description": "快速全文关键词搜索。参数: keyword, file_types(逗号分隔扩展名), max_results",
        "params": {"keyword": "string", "file_types": "string(可选)", "max_results": "int(可选)"}
    },
    "list_files": {
        "fn": _tool_list_files,
        "description": "列出目录结构。参数: directory(目录路径), max_depth(深度)",
        "params": {"directory": "string(可选)", "max_depth": "int(可选)"}
    },
    "read_symbols": {
        "fn": _tool_read_symbols,
        "description": "提取文件的函数和类签名（不读函数体）。参数: file_path",
        "params": {"file_path": "string"}
    },
    "find_definition": {
        "fn": _tool_find_definition,
        "description": "查找符号（函数/类/变量）在项目中的定义位置。参数: symbol, file_types(可选)",
        "params": {"symbol": "string", "file_types": "string(可选)"}
    },
    "read_imports": {
        "fn": _tool_read_imports,
        "description": "提取文件的 import 语句，分析依赖关系。参数: file_path",
        "params": {"file_path": "string"}
    },
    "find_references": {
        "fn": _tool_find_references,
        "description": "查找符号在项目中的引用位置（排除定义自身）。参数: symbol, file_types(可选), max_results(可选)",
        "params": {"symbol": "string", "file_types": "string(可选)", "max_results": "int(可选)"}
    },
    "summarize_file": {
        "fn": _tool_summarize_file,
        "description": "返回文件摘要：导出的符号、行数、语言、依赖数。参数: file_path",
        "params": {"file_path": "string"}
    },
    "partial_update": {
        "fn": _tool_partial_update,
        "description": "精准替换文件中的函数或代码块。参数: path, target(目标代码文本), replacement(新代码文本), function_name(函数名，精确替换整个函数)。target+replacement 或 function_name+replacement 二选一",
        "params": {"path": "string", "target": "string(可选)", "replacement": "string", "function_name": "string(可选)"}
    },
    "insert_content": {
        "fn": _tool_insert_content,
        "description": "在文件指定位置插入内容。参数: path, content(要插入的内容), line(行号,1-based), anchor(锚点文本)。line 或 anchor 二选一，都不传则追加到文件末尾",
        "params": {"path": "string", "content": "string", "line": "int(可选)", "anchor": "string(可选)"}
    },
    "regex_replace": {
        "fn": _tool_regex_replace,
        "description": "基于正则表达式的批量替换。参数: path(文件路径或glob模式), pattern(正则), replacement(替换文本), recursive(是否递归)",
        "params": {"path": "string", "pattern": "string", "replacement": "string", "recursive": "bool(可选)"}
    },
    "execute_code": {
        "fn": _tool_execute_code,
        "description": "沙箱执行代码验证。参数: code(代码), language(语言: python/javascript), timeout(超时秒数)。仅支持 Python 和 JavaScript",
        "params": {"code": "string", "language": "string(可选,默认python)", "timeout": "int(可选,默认30)"}
    },
    "run_command": {
        "fn": _tool_run_command,
        "description": "执行终端命令（构建、安装依赖、运行脚本等）。参数: command(命令), cwd(工作目录,可选), timeout(超时秒数,可选,默认60)。支持 pip/npm/python/node/go/cargo/make 等常用命令",
        "params": {"command": "string", "cwd": "string(可选)", "timeout": "int(可选,默认60)"}
    },
}


class SpecialistCallError(Exception):
    """Specialist LLM 调用不可恢复错误"""
    pass


class Specialist:
    """专业角色基类"""

    def __init__(self, role_name: str, model_name: str, task_type: str = "generate",
                 api_key_token: Optional[str] = None, provider_id: Optional[str] = None,
                 semaphore: Optional[asyncio.Semaphore] = None, cost_tracker=None):
        self.role_name = role_name
        self.model_name = model_name
        self.task_type = task_type
        self.api_key_token = api_key_token
        self.model_config = LayeredModelRouter.get_model_config(model_name, task_type=task_type, api_key_token=api_key_token)
        self.provider_id = provider_id
        self._semaphore = semaphore if semaphore is not None else get_global_llm_semaphore()
        self._cost_tracker = cost_tracker
        self._edited_files: List[str] = []
        self._write_tools = {"partial_update", "insert_content", "regex_replace"}

    def get_edited_files(self) -> List[str]:
        """获取本轮通过工具直接编辑过的文件列表"""
        return self._edited_files.copy()

    def clear_edits(self):
        """清空编辑记录（每轮生成前调用）"""
        self._edited_files.clear()

    @traced("specialist.call_llm", attributes={"component": "specialist"})
    async def call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用 LLM（带并发限制、超时保护和动态指标记录）"""
        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        try:
            async def _do_call():
                return await call_llm(
                    model=self.model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=False,
                    max_tokens=self.model_config["max_tokens"],
                    thinking_budget=self.model_config["thinking_budget"],
                    temperature=self.model_config["temperature"],
                    api_key_token=self.api_key_token,
                    provider_id=self.provider_id,
                )

            # 超时保护：防止 LLM 端点挂起导致 semaphore slot 永久占用
            call_timeout = self.model_config.get("timeout", 300)

            if self._semaphore:
                async with self._semaphore:
                    response = await asyncio.wait_for(_do_call(), timeout=call_timeout)
            else:
                response = await asyncio.wait_for(_do_call(), timeout=call_timeout)

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=True, latency_ms=latency_ms)

            # 追踪 token 使用量
            usage = response.get("usage", {})
            if usage and self._cost_tracker:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                # 估算成本（美元）
                cost_per_1m_input = self.model_config.get("cost_per_1m_input", 0.0)
                cost_per_1m_output = self.model_config.get("cost_per_1m_output", 0.0)
                cost_usd = (prompt_tokens * cost_per_1m_input + completion_tokens * cost_per_1m_output) / 1000000
                self._cost_tracker.add_usage(self.model_name, prompt_tokens, completion_tokens, cost_usd)

            return content
        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=False, latency_ms=latency_ms, error="timeout")
            logger.error(f"{self.role_name} 调用 LLM 超时 ({call_timeout}s)")
            return ""
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=False, latency_ms=latency_ms, error=str(e))
            logger.error(f"{self.role_name} 调用 LLM 失败: {e}")

            # 不可恢复错误：认证失败(401/403)、配置错误等，直接抛出终止任务
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                raise SpecialistCallError(
                    f"{self.role_name} 认证失败 (HTTP {e.response.status_code})，请检查 API Key 配置"
                ) from e

            # 可恢复错误：网络超时、限流(429)、服务端错误(5xx)等，返回空字符串触发 fallback
            return ""

    @staticmethod
    def _build_tools_description(tools: Dict[str, Dict]) -> str:
        """构建工具描述文本，注入 system prompt"""
        lines = []
        for name, info in tools.items():
            params_desc = ", ".join(f"{k}: {v}" for k, v in info["params"].items())
            lines.append(f"- {name}({params_desc}): {info['description']}")
        return "\n".join(lines)

    @staticmethod
    def _parse_tool_call(content: str) -> Optional[Dict]:
        """从 LLM 回复中解析单个工具调用（简洁格式）

        格式: {"tool": "tool_name", "params": {...}}
        """
        # 清理 <think> 标签
        cleaned = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()

        # 尝试1: JSON 代码块
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # 尝试2: 直接匹配 JSON 对象
        brace_match = re.search(r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:\s*\{[^}]*\}\s*\}', cleaned)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # 尝试3: 更宽松的匹配（params 可能包含嵌套）
        tool_match = re.search(r'\{\s*"tool"\s*:\s*"([^"]+)"', cleaned)
        if tool_match:
            # 提取整个 JSON 对象
            start = tool_match.start()
            brace_count = 0
            in_string = False
            escape_next = False
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            return json.loads(cleaned[start:i + 1])
                        except json.JSONDecodeError:
                            break
        return None

    @traced("specialist.call_llm_with_tools", attributes={"component": "specialist"})
    async def call_llm_with_tools(
        self,
        prompt: str,
        system_prompt: str = "",
        tools: Optional[Dict[str, Dict]] = None,
        project_path: str = "",
        max_rounds: int = 6,
        callback: Optional[Any] = None,
    ) -> str:
        """调用 LLM，支持 ReAct 工具调用循环

        LLM 可以在生成最终代码前，调用工具搜索/读取项目文件以获取上下文。
        采用自然终止：LLM 不再调用工具时自动结束，max_rounds 仅作安全阀。

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt
            tools: 可用工具注册表（默认使用 SPECIALIST_TOOLS）
            project_path: 项目路径（工具搜索用）
            max_rounds: 安全阀上限（防止无限循环，默认 6）
            callback: 进度回调函数

        Returns:
            LLM 最终输出的文本（代码）
        """
        if tools is None:
            tools = SPECIALIST_TOOLS

        # 无项目路径或无工具时，退化为普通 call_llm
        if not project_path or not tools:
            logger.info(f"{self.role_name} call_llm_with_tools: 无项目路径或无工具，退化为普通 call_llm (project_path={project_path}, tools={bool(tools)})")
            return await self.call_llm(prompt, system_prompt)

        logger.info(f"{self.role_name} call_llm_with_tools: 使用 ReAct 工具调用 (project_path={project_path}, tools={list(tools.keys())})")

        tools_desc = self._build_tools_description(tools)
        tool_names = list(tools.keys())

        # 注入工具描述到 system prompt
        enhanced_system = (
            f"{system_prompt}\n\n"
            f"### 可用工具\n"
            f"你可以调用以下工具来搜索、读取、编辑项目文件：\n\n"
            f"{tools_desc}\n\n"
            f"### 工具调用格式\n"
            f"如果需要使用工具，请且仅返回一个 JSON 对象：\n"
            f'{{"tool": "工具名", "params": {{"参数名": "值"}}}}\n\n'
            f"### 重要规则\n"
            f"1. 每次只调用一个工具\n"
            f"2. 收到工具结果后，继续思考或生成最终代码\n"
            f"3. 对于新文件：准备生成代码时，直接返回完整代码，不要包裹 JSON\n"
            f"4. 对于已有文件：使用 partial_update/insert_content/regex_replace 进行精准编辑，编辑完成后返回 JSON: {{\"action\": \"edited\", \"files\": [\"路径\"], \"summary\": \"摘要\"}}\n"
            f"5. 可用工具: {', '.join(tool_names)}\n"
            f"6. 当你已收集足够上下文时，直接生成代码，无需再调用工具\n"
        )

        # 工具调用历史（注入后续轮次的 prompt）
        tool_history: List[str] = []

        for round_num in range(1, max_rounds + 1):
            # 构建 prompt：原始 prompt + 工具历史
            current_prompt = prompt
            if tool_history:
                history_text = "\n\n".join(tool_history)
                current_prompt = (
                    f"{prompt}\n\n"
                    f"### 工具调用记录\n"
                    f"{history_text}\n\n"
                    f"请根据以上工具返回的信息，继续调用工具或直接生成最终代码。"
                )

            # 调用 LLM（思考 + 可能的工具调用）
            response = await self.call_llm(current_prompt, enhanced_system)
            if not response:
                return ""

            # 尝试解析工具调用
            tool_call = self._parse_tool_call(response)
            if not tool_call:
                # LLM 没有调用工具 → 自然终止，直接返回代码
                logger.info(f"{self.role_name} ReAct 自然终止: 第 {round_num} 轮, 工具调用 {len(tool_history)} 次")
                return response

            # 安全阀：达到上限强制生成
            if round_num >= max_rounds:
                logger.warning(f"{self.role_name} ReAct 达到安全阀上限 ({max_rounds} 轮), 强制生成")
                if callback:
                    self._emit_event(callback, "react_generating", {
                        "message": "基于搜索结果生成代码",
                        "round": round_num,
                        "tool_history_count": len(tool_history)
                    })
                final_response = await self.call_llm(
                    f"{current_prompt}\n\n### 注意：已达到工具调用上限，请直接生成最终代码。",
                    enhanced_system
                )
                return final_response

            # 执行工具
            tool_name = tool_call.get("tool", "")
            tool_params = tool_call.get("params", {})

            # 推送工具调用事件
            if callback:
                self._emit_event(callback, "react_tool_call", {
                    "message": f"正在搜索: {tool_name}",
                    "tool": tool_name,
                    "params": {k: str(v)[:100] for k, v in tool_params.items()},
                    "round": round_num,
                    "max_rounds": max_rounds
                })

            if tool_name not in tools:
                logger.warning(f"LLM 调用了不存在的工具: {tool_name}，跳过")
                tool_history.append(
                    f"第 {round_num} 轮工具调用: {tool_name}({json.dumps(tool_params, ensure_ascii=False)})\n"
                    f"错误: 工具不存在，可用工具: {', '.join(tool_names)}"
                )
                continue

            try:
                tool_result = tools[tool_name]["fn"](project_path=project_path, **tool_params)
            except Exception as e:
                tool_result = {"error": str(e)}

            # 追踪写入类工具的编辑
            if tool_name in self._write_tools and isinstance(tool_result, dict) and tool_result.get("success"):
                edited_path = tool_params.get("path", "")
                if edited_path:
                    # 标准化路径
                    full = str(Path(project_path) / edited_path) if not Path(edited_path).is_absolute() else edited_path
                    if full not in self._edited_files:
                        self._edited_files.append(full)
                    logger.info(f"{self.role_name} 工具编辑: {tool_name} -> {edited_path}")

            # 记录工具调用历史
            result_str = json.dumps(tool_result, ensure_ascii=False)[:2000]
            tool_history.append(
                f"第 {round_num} 轮工具调用: {tool_name}({json.dumps(tool_params, ensure_ascii=False)})\n"
                f"返回结果: {result_str}"
            )

            # 推送工具结果事件
            if callback:
                result_count = len(tool_result.get("results", [])) if isinstance(tool_result, dict) else 0
                self._emit_event(callback, "react_tool_result", {
                    "message": f"找到 {result_count} 条结果" if result_count else f"工具返回 {len(result_str)} 字符",
                    "tool": tool_name,
                    "result_count": result_count,
                    "result_size": len(result_str),
                    "round": round_num
                })

            logger.info(
                f"{self.role_name} ReAct 第 {round_num} 轮: 调用 {tool_name}, "
                f"结果 {len(result_str)} 字符"
            )

        # 不应走到这里
        return ""

    @staticmethod
    def _emit_event(callback: Any, event_type: str, data: Dict):
        """推送事件到前端"""
        try:
            import json as _json
            event = {"type": event_type, **data}
            result = callback(_json.dumps(event, ensure_ascii=False))
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception:
            pass
