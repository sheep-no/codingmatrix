"""
Specialist 内置工具实现

提供文件读写、代码分析、沙箱执行、命令运行等工具函数。
从 specialist_base.py 拆分而来，职责单一：只包含工具实现和注册表。
"""

import re
import json
import glob
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 依赖图白名单：只有在此集合中的文件才允许 write_file/create_file 写入
# 由 TopologyScheduler.build_from_dependency_graph() 设置
_allowed_file_paths: Optional[set] = None


def set_allowed_file_paths(paths: set):
    """设置允许写入的文件路径集合（由依赖图提供）"""
    global _allowed_file_paths
    _allowed_file_paths = set(paths) if paths else None
    import logging
    logger = logging.getLogger(__name__)
    if paths:
        logger.info(f"[白名单] 设置允许写入路径: {sorted(_allowed_file_paths)}")
    else:
        logger.info("[白名单] 清除允许写入路径")


def _safe_join(project_root: str, target: str) -> Path:
    """安全拼接路径：target 必须在 project_root 下（解析符号链接后）

    Raises:
        PermissionError: 当 target 解析后在 project_root 之外时
    """
    root = Path(project_root).resolve()
    if Path(target).is_absolute():
        candidate = Path(target).resolve()
    else:
        candidate = (root / target).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError(f"路径越界：'{target}' 不在项目根目录 '{project_root}' 下")
    return candidate


# ==================== 代码分析辅助 ====================

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
        fallback = {".jsx": ".js", ".tsx": ".ts"}.get(ext, ext)
        patterns = _SYMBOL_PATTERNS.get(fallback, _SYMBOL_PATTERNS.get(".py"))
    return patterns


def _extract_module_name(statement: str, ext: str) -> str:
    """从 import 语句中提取模块名"""
    s = statement.strip()
    if ext == '.py':
        m = re.match(r"from\s+(\S+)", s)
        if m:
            return m.group(1)
        m = re.match(r"import\s+(\S+)", s)
        if m:
            return m.group(1).split('.')[0]
    elif ext in ('.js', '.ts', '.jsx', '.tsx', '.vue'):
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


# ==================== 文件读取工具 ====================


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


# ==================== 代码分析工具（精读级） ====================


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
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue

            fn_match = patterns["function"].search(line)
            if fn_match:
                name = next(g for g in fn_match.groups() if g is not None)
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

        symbols = _tool_read_symbols(project_path, file_path)
        imports = _tool_read_imports(project_path, file_path)

        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "react-jsx", ".tsx": "react-tsx", ".vue": "vue",
            ".go": "go", ".java": "java", ".rs": "rust", ".rb": "ruby",
            ".css": "css", ".html": "html", ".json": "json",
            ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
            ".sql": "sql", ".sh": "shell", ".toml": "toml",
        }
        language = lang_map.get(ext, "unknown")

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


# ==================== 写入/验证工具 ====================


def _tool_partial_update(project_path: str, path: str, target: str = None,
                         replacement: str = None, function_name: str = None) -> Dict:
    """精准替换文件中的函数或代码块"""
    try:
        full_path = _safe_join(project_path, path)
        if not full_path.exists():
            return {"success": False, "error": f"文件不存在: {path}"}

        content = full_path.read_text(encoding='utf-8')

        if function_name:
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
        full_path = _safe_join(project_path, path)
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
        root = Path(project_path).resolve()
        full_path = root / path if not Path(path).is_absolute() else Path(path).resolve()
        # 安全检查：明确路径或 glob 根必须在 project_root 内
        try:
            full_path.relative_to(root)
        except ValueError:
            return {"success": False, "error": f"路径越界：'{path}' 不在项目根目录下"}

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


# ==================== 沙箱执行工具 ====================


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
    """Python 沙箱执行（通过子进程隔离）"""
    import subprocess
    import tempfile

    dangerous_patterns = [
        r'\bimport\s+os\b', r'\bimport\s+sys\b', r'\bimport\s+subprocess\b',
        r'\bfrom\s+os\b', r'\bfrom\s+sys\b', r'\bfrom\s+subprocess\b',
        r'\b__import__\b', r'\bexec\s*\(', r'\beval\s*\(',
        r'\bopen\s*\(', r'\bglobals\s*\(', r'\blocals\s*\(',
        r'\bgetattr\s*\(', r'\bsetattr\s*\(', r'\bdelattr\s*\(',
        r'\bos\.', r'\bsys\.', r'\bshutil\b', r'\bpathlib\b',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            return {"success": False, "error": f"安全限制: 检测到危险操作 {pattern}"}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            ['python3', tmp_path],
            capture_output=True, text=True, timeout=timeout,
            cwd='/tmp',
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp'}
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout or None,
            "error": result.stderr or None if result.returncode != 0 else result.stderr or None
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"执行超时（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _execute_js_sandbox(code: str, timeout: int) -> Dict:
    """JavaScript 沙箱执行（通过 Node.js 子进程）"""
    import subprocess
    import tempfile

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

        try:
            result = subprocess.run(
                ['node', tmp_path],
                capture_output=True, text=True, timeout=timeout,
                cwd='/tmp'
            )
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

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


# ==================== 命令执行工具 ====================

# 危险命令黑名单
_DANGEROUS_COMMANDS = [
    r'\brm\s+(-[a-zA-Z]*[rf]|--recursive)\s+/',
    r'\bshutdown\b', r'\breboot\b', r'\bpoweroff\b',
    r'\bmkfs\b', r'\bfdisk\b', r'\bparted\b',
    r'\bchmod\s+777\b', r'\bchown\s+root\b',
    r'\biptables\b', r'\bufw\b',
    r'\buseradd\b', r'\buserdel\b', r'\bpasswd\b',
    r'\bsudo\b', r'\bsu\b',
    r'\bkill\s+-9\s+1\b',
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
    'git add', 'git commit', 'git show', 'git stash',
    'docker ps', 'docker images', 'docker logs',
    'pytest', 'jest', 'vitest', 'mocha', 'rspec',
    'gcc', 'g++', 'clang', 'rustc',
]


def _tool_run_command(project_path: str, command: str, cwd: str = None, timeout: int = 60) -> Dict:
    """执行终端命令（构建、安装依赖、运行脚本等）"""
    import subprocess
    import os

    try:
        for pattern in _DANGEROUS_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return {"success": False, "error": "安全限制: 检测到危险命令操作"}

        cmd_lower = command.strip().lower()
        allowed = any(cmd_lower.startswith(prefix.lower()) for prefix in _ALLOWED_COMMAND_PREFIXES)
        if not allowed:
            return {"success": False, "error": f"安全限制: 命令不在允许列表中。允许的命令前缀: {', '.join(_ALLOWED_COMMAND_PREFIXES[:10])}..."}

        work_dir = Path(project_path)
        if cwd:
            work_dir = (work_dir / cwd).resolve()
            if not str(work_dir).startswith(str(Path(project_path).resolve())):
                return {"success": False, "error": "安全限制: 工作目录必须在项目路径内"}

        if not work_dir.exists():
            return {"success": False, "error": f"工作目录不存在: {work_dir}"}

        # 使用进程组管理，确保超时时杀死所有子进程
        # 限制输出缓冲区大小，防止 OOM
        MAX_OUTPUT_BYTES = 1024 * 1024  # 1MB
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(work_dir),
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONUNBUFFERED': '1',
            },
            start_new_session=True,  # 独立进程组，超时时可整体杀死
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # 杀死整个进程组
            os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGKILL)
            stdout, stderr = proc.communicate()
            return {"success": False, "error": f"命令执行超时（{timeout}秒）", "command": command}
        except Exception:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise

        return {
            "success": proc.returncode == 0,
            "output": stdout[-5000:] if stdout else "",
            "error": stderr[-2000:] if stderr else None,
            "return_code": proc.returncode,
            "command": command,
            "cwd": str(work_dir),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "command": command}


# ==================== 搜索工具 ====================


def _tool_search_files(
    project_path: str,
    pattern: str,
    file_pattern: str = "*",
    directory: str = ".",
    context_lines: int = 1,
    max_results: int = 50,
) -> Dict:
    """在项目文件中搜索文本或正则模式（grep 封装）

    用于跨文件验证：检查某个符号是否在目标文件中定义、某个导入是否正确等。
    支持正则表达式，对任何编程语言通用。

    Args:
        project_path: 项目根目录
        pattern: 搜索模式（支持正则）
        file_pattern: 文件过滤（如 *.py, *.go, *.rs），默认 * 匹配所有文件
        directory: 搜索目录（相对于项目根目录），默认 .
        context_lines: 匹配行的上下文行数，默认 1
        max_results: 最大返回结果数，默认 50

    Returns:
        {matches: [{file, line_number, content}], total, pattern}
    """
    import subprocess
    import os

    if not pattern or not pattern.strip():
        return {"success": False, "error": "搜索模式不能为空"}

    try:
        work_dir = _safe_join(project_path, directory)

        if not work_dir.exists():
            return {"success": False, "error": f"目录不存在: {directory}"}

        # 优先用 ripgrep (rg)，更快且默认支持正则
        # fallback 到 grep
        rg_available = False
        try:
            subprocess.run(["rg", "--version"], capture_output=True, timeout=5)
            rg_available = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if rg_available:
            cmd = [
                "rg", "-n", "--no-heading",
                "-C", str(context_lines),
                "--max-count", str(max_results),
                "--glob", file_pattern,
                pattern,
                str(work_dir),
            ]
        else:
            cmd = [
                "grep", "-rn",
                f"-C{context_lines}",
                f"--max-count={max_results}",
                f"--include={file_pattern}",
                pattern,
                str(work_dir),
            ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(work_dir),
        )

        matches = []
        if proc.stdout:
            for line in proc.stdout.strip().split('\n'):
                if not line or line.startswith('--'):
                    continue
                # 解析 grep 输出格式: file:line_number:content 或 file-line_number-content
                # 也处理 rg 格式: file:line_number:content
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    # 移除 work_dir 前缀，得到相对路径
                    if file_path.startswith(str(work_dir)):
                        file_path = file_path[len(str(work_dir)):].lstrip('/')
                    try:
                        line_no = int(parts[1])
                    except ValueError:
                        # 上下文行用 - 分隔
                        try:
                            line_no = int(parts[1].replace('-', ''))
                        except (ValueError, AttributeError):
                            line_no = 0
                    matches.append({
                        "file": file_path,
                        "line_number": line_no,
                        "content": parts[2].strip() if len(parts) > 2 else "",
                    })

        return {
            "success": True,
            "matches": matches[:max_results],
            "total": len(matches),
            "pattern": pattern,
            "directory": directory,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"搜索超时（15s）: {pattern}"}
    except Exception as e:
        return {"success": False, "error": f"搜索失败: {e}"}


# ==================== 写入工具 ====================


def _tool_write_file(project_path: str, path: str, content: str) -> Dict:
    """写入文件内容（创建或覆盖）"""
    try:
        # 空内容校验：拒绝空文件写入
        if not content or not content.strip():
            return {"success": False, "error": "内容为空，拒绝写入。请提供实际的文件内容"}

        # 统一占位符检测
        from app.agent.utils import is_placeholder_content
        is_ph, ph_reason = is_placeholder_content(content, path)
        if is_ph:
            return {"success": False, "error": f"检测到占位符代码，拒绝写入。{ph_reason}。请提供完整的实现代码"}

        # 依赖图白名单校验：只允许写入依赖图中的文件
        global _allowed_file_paths
        if _allowed_file_paths is not None:
            # 规范化路径：去除开头的 ./ 和 /
            normalized = path.replace('\\', '/').lstrip('./').lstrip('/')
            if normalized not in _allowed_file_paths:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"[白名单] 拒绝写入: path={path}, normalized={normalized}, allowed={sorted(_allowed_file_paths)[:5]}...")
                return {"success": False, "error": f"文件 '{path}' 不在依赖图中，拒绝写入。只允许生成依赖图中定义的文件"}

        # 文件名验证：拒绝无效文件名
        filename = Path(path).name
        if not filename or filename.startswith('=') or filename.startswith('.') or re.search(r'[<>:"|?*]', filename):
            return {"success": False, "error": f"无效的文件名: '{filename}'。文件名不能以 '=' 或 '.' 开头，不能包含特殊字符"}
        if re.match(r'^=\d', filename):
            return {"success": False, "error": f"无效的文件名: '{filename}'。这看起来像版本号，不是有效的文件名"}

        full_path = _safe_join(project_path, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入前语法验证
        validation_warning = _validate_file_syntax(path, content)

        full_path.write_text(content, encoding='utf-8')
        result = {"success": True, "path": str(full_path), "size": len(content)}
        if validation_warning:
            result["warning"] = validation_warning
        return result
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _validate_file_syntax(file_path: str, content: str) -> str:
    """验证文件语法，返回警告信息（空字符串表示通过）"""
    import ast
    import re
    import subprocess
    import tempfile

    ext = Path(file_path).suffix.lower()

    if ext == '.py':
        try:
            ast.parse(content)
            return ""
        except SyntaxError as e:
            return f"Python 语法错误: {e}"

    elif ext in ('.js', '.ts', '.vue'):
        # 检测 Python 代码混入 JS 文件
        python_indicators = ['def ', 'import ', 'from ', 'class ', 'self.', 'print(']
        python_count = sum(1 for ind in python_indicators if ind in content)
        if python_count >= 3:
            return f"JavaScript 文件疑似包含 Python 代码（匹配 {python_count} 个指标）"
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(content)
                tmp_path = f.name
            result = subprocess.run(
                ['node', '-c', tmp_path],
                capture_output=True, text=True, timeout=5
            )
            Path(tmp_path).unlink(missing_ok=True)
            if result.returncode != 0:
                return f"JavaScript 语法错误: {result.stderr.strip()[:200]}"
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            if content.count('{') != content.count('}'):
                return "花括号不匹配"
            if content.count('(') != content.count(')'):
                return "圆括号不匹配"
            return ""

    elif ext == '.html':
        for tag in ['html', 'head', 'body']:
            open_count = len(re.findall(rf'<{tag}[\s>]', content, re.IGNORECASE))
            close_count = len(re.findall(rf'</{tag}>', content, re.IGNORECASE))
            if open_count > close_count:
                return f"<{tag}> 标签未闭合"
        script_opens = len(re.findall(r'<script[\s>]', content, re.IGNORECASE))
        script_closes = len(re.findall(r'</script>', content, re.IGNORECASE))
        if script_opens > script_closes:
            return "<script> 标签未闭合"
        return ""

    elif ext == '.css':
        if content.count('{') != content.count('}'):
            return "CSS 大括号不匹配"
        # 检测非 CSS 内容（大段中文描述文本）
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('/*')]
        chinese_lines = sum(1 for l in lines if len(re.findall(r'[\u4e00-\u9fff]', l)) > 10)
        if chinese_lines > len(lines) * 0.3 and chinese_lines > 3:
            return f"CSS 文件包含大量非代码文本（{chinese_lines} 行中文描述）"
        return ""

    return ""


# ==================== Git 工具 ====================


def _run_git(project_path: str, args: list, timeout: int = 30) -> Dict:
    """执行 git 命令的内部辅助"""
    import subprocess
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True,
            timeout=timeout, cwd=project_path
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"git 命令超时（{timeout}秒）"}
    except FileNotFoundError:
        return {"success": False, "error": "Git 未安装"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_git_status(project_path: str) -> Dict:
    """查看 Git 工作区状态"""
    result = _run_git(project_path, ["status", "--porcelain"])
    if not result["success"]:
        return result

    files = []
    for line in result["stdout"].split('\n'):
        line = line.strip()
        if not line:
            continue
        status = line[:2].strip()
        path = line[3:]
        status_map = {"M": "modified", "A": "added", "D": "deleted",
                      "R": "renamed", "??": "untracked", "C": "copied"}
        files.append({"path": path, "status": status_map.get(status, status)})

    branch_result = _run_git(project_path, ["branch", "--show-current"])
    branch = branch_result.get("stdout", "unknown") if branch_result["success"] else "unknown"

    return {"success": True, "branch": branch, "files": files, "total": len(files)}


def _tool_git_diff(project_path: str, file_path: str = None, staged: bool = False) -> Dict:
    """查看 Git 文件差异"""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if file_path:
        args.extend(["--", file_path])

    result = _run_git(project_path, args + ["--stat"])
    if not result["success"]:
        return result

    stat = result["stdout"]

    detail_result = _run_git(project_path, args)
    detail = detail_result.get("stdout", "") if detail_result["success"] else ""

    return {"success": True, "stat": stat, "diff": detail[:10000]}


def _tool_git_commit(project_path: str, message: str, files: list = None) -> Dict:
    """提交 Git 修改"""
    if not message:
        return {"success": False, "error": "提交信息不能为空"}

    if files:
        add_result = _run_git(project_path, ["add"] + files)
    else:
        add_result = _run_git(project_path, ["add", "-A"])

    if not add_result["success"]:
        return {"success": False, "error": f"git add 失败: {add_result.get('stderr', '')}"}

    commit_result = _run_git(project_path, ["commit", "-m", message])
    if not commit_result["success"]:
        stderr = commit_result.get("stderr", "")
        if "nothing to commit" in stderr or "nothing to commit" in commit_result.get("stdout", ""):
            return {"success": True, "message": "没有需要提交的修改", "nothing_to_commit": True}
        return {"success": False, "error": f"git commit 失败: {stderr}"}

    log_result = _run_git(project_path, ["log", "-1", "--format=%H %s"])
    return {"success": True, "message": message, "commit_info": log_result.get("stdout", "")}


def _tool_git_log(project_path: str, count: int = 10, file_path: str = None) -> Dict:
    """查看 Git 提交历史"""
    args = ["log", f"-{count}", "--format=%H|%h|%an|%ai|%s"]
    if file_path:
        args.extend(["--", file_path])

    result = _run_git(project_path, args)
    if not result["success"]:
        return result

    commits = []
    for line in result["stdout"].split('\n'):
        if not line.strip():
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
                "message": parts[4],
            })

    return {"success": True, "commits": commits, "total": len(commits)}


# ==================== 网络/搜索工具 ====================


async def _tool_web_search(project_path: str, query: str, limit: int = 5) -> Dict:
    """搜索网络信息（DuckDuckGo）"""
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1}
            )
        data = response.json()
        results = []
        if "RelatedTopics" in data:
            for item in data["RelatedTopics"][:limit]:
                if "Text" in item:
                    results.append(item["Text"])
        return {"success": True, "results": results, "query": query}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _tool_http_request(project_path: str, method: str, url: str,
                              headers: dict = None, body: dict = None) -> Dict:
    """发送 HTTP 请求（带 SSRF 防护）"""
    from urllib.parse import urlparse
    import ipaddress
    import httpx as _httpx

    try:
        if not url:
            return {"success": False, "error": "缺少 url 参数"}

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"success": False, "error": "仅支持 http/https 协议"}

        host = parsed.hostname
        if not host:
            return {"success": False, "error": "URL 缺少主机名"}

        # SSRF 防护：解析 DNS 得到真实 IP，对每个 IP 做内网检查
        # 避免 DNS rebinding：直接拿 IP 走连接，禁用重定向
        try:
            import socket as _socket
            addr_infos = _socket.getaddrinfo(host, None)
        except _socket.gaierror as e:
            return {"success": False, "error": f"DNS 解析失败: {e}"}

        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            # IPv4-mapped IPv6 (::ffff:127.0.0.1) 需要剥离
            if ip_str.startswith("::ffff:"):
                ip_str = ip_str[7:]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if (ip.is_private or ip.is_loopback or ip.is_reserved
                    or ip.is_link_local or ip.is_multicast or ip.is_unspecified):
                return {"success": False, "error": f"不允许访问内网/保留地址: {ip}"}

        async with _httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(
                method=method.upper(), url=url,
                headers=headers or {}, json=body
            )

        return {
            "success": True,
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": response.text[:5000]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 文件删除工具 ====================


def _tool_delete_files_by_pattern(project_path: str, path: str, pattern: str,
                                   recursive: bool = False) -> Dict:
    """按 glob 模式批量删除文件"""
    import os
    try:
        target_dir = Path(project_path) / path if not Path(path).is_absolute() else Path(path)
        if not target_dir.exists():
            return {"success": False, "error": f"目录不存在: {path}"}

        search_pattern = str(target_dir / pattern)
        files = glob.glob(search_pattern, recursive=recursive)
        files = [f for f in files if Path(f).is_file()]

        if not files:
            return {"success": True, "deleted": 0, "files": []}

        deleted = []
        errors = []
        for fp in files:
            try:
                os.remove(fp)
                deleted.append(fp)
            except Exception as e:
                errors.append(f"{fp}: {str(e)}")

        return {"success": True, "deleted": len(deleted), "files": deleted, "errors": errors}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 工具注册表 ====================

SPECIALIST_TOOLS = {
    "read_file": {
        "fn": _tool_read_file,
        "description": "读取文件内容，支持分页。参数: file_path, offset(起始行), limit(行数)",
        "params": {"file_path": "string", "offset": "int(可选)", "limit": "int(可选)"}
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
    "read_imports": {
        "fn": _tool_read_imports,
        "description": "提取文件的 import 语句，分析依赖关系。参数: file_path",
        "params": {"file_path": "string"}
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
        "description": "执行终端命令（构建、安装依赖、运行脚本、搜索代码等）。参数: command(命令), cwd(工作目录,可选), timeout(超时秒数,可选,默认60)。"
                       "支持 pip/npm/python/node/go/cargo/make/grep/find 等。"
                       "grep 示例: grep -rn --include='*.py' 'pattern' . | head -20  "
                       "find 示例: find . -name '*.py' | xargs wc -l",
        "params": {"command": "string", "cwd": "string(可选)", "timeout": "int(可选,默认60)"}
    },
    "search_files": {
        "fn": _tool_search_files,
        "description": "在项目文件中搜索文本或正则模式（grep封装，任何语言通用）。"
                       "参数: pattern(搜索模式,支持正则), file_pattern(文件过滤,如*.py,默认*), "
                       "directory(搜索目录,默认.), context_lines(上下文行数,默认1), max_results(最大结果数,默认50)。"
                       "用途：验证符号是否在目标文件中定义、检查导入是否正确、查找函数/类的使用位置。",
        "params": {"pattern": "string", "file_pattern": "string(可选)", "directory": "string(可选)",
                   "context_lines": "int(可选)", "max_results": "int(可选)"}
    },
    "write_file": {
        "fn": _tool_write_file,
        "description": "写入文件内容（创建或覆盖）。参数: path(文件路径), content(文件内容)",
        "params": {"path": "string", "content": "string"}
    },
    "create_file": {
        "fn": _tool_write_file,
        "description": "创建新文件（等同于 write_file）。参数: path(文件路径), content(文件内容)",
        "params": {"path": "string", "content": "string"}
    },
    "git_status": {
        "fn": _tool_git_status,
        "description": "查看 Git 工作区状态（修改/新增/删除的文件列表）。无参数",
        "params": {}
    },
    "git_diff": {
        "fn": _tool_git_diff,
        "description": "查看 Git 文件差异。参数: file_path(可选,指定文件), staged(是否查看暂存区,默认false)",
        "params": {"file_path": "string(可选)", "staged": "bool(可选)"}
    },
    "git_commit": {
        "fn": _tool_git_commit,
        "description": "提交 Git 修改。参数: message(提交信息), files(要暂存的文件列表,可选,默认全部)",
        "params": {"message": "string", "files": "list(可选)"}
    },
    "git_log": {
        "fn": _tool_git_log,
        "description": "查看 Git 提交历史。参数: count(显示条数,默认10), file_path(可选,过滤特定文件)",
        "params": {"count": "int(可选)", "file_path": "string(可选)"}
    },
    "web_search": {
        "fn": _tool_web_search,
        "description": "搜索网络信息。参数: query(搜索关键词), limit(返回数量,默认5)",
        "params": {"query": "string", "limit": "int(可选)"}
    },
    "http_request": {
        "fn": _tool_http_request,
        "description": "发送 HTTP 请求（带 SSRF 防护）。参数: method(GET/POST/PUT/DELETE), url, headers(可选), body(可选)",
        "params": {"method": "string", "url": "string", "headers": "object(可选)", "body": "object(可选)"}
    },
    "delete_files_by_pattern": {
        "fn": _tool_delete_files_by_pattern,
        "description": "按 glob 模式批量删除文件。参数: path(目录), pattern(如 *.log), recursive(可选)",
        "params": {"path": "string", "pattern": "string", "recursive": "bool(可选)"}
    },
}
