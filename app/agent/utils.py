"""
Agent 公共工具函数
"""

import asyncio
import logging
import re
from pathlib import Path
import json
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LANGUAGE_VALIDATION_TIMEOUT_SECONDS = 30

# 文档/文本类文件：其正确内容本来就是 Markdown/散文或数据，针对「代码形态」
# 的启发式（Markdown 说明、截断散文、思考泄漏散文）不适用于它们。
_DOCUMENTATION_EXTENSIONS = ('.md', '.markdown', '.rst', '.txt', '.adoc')
_DOCUMENTATION_FILE_NAMES = frozenset({
    'readme', 'license', 'licence', 'changelog', 'notice',
    'authors', 'contributing', 'copying',
})

# 标记/模板语言：合法内容天然包含列表符号（`- `、`1. `）和标签闭合后的 `> `，
# 用「Markdown 文档」启发式判别必然误报。
_MARKUP_EXTENSIONS = frozenset({
    '.html', '.htm', '.xhtml', '.xml', '.svg', '.vue', '.svelte', '.astro',
})


def _is_documentation_file(file_path: str) -> bool:
    """判断文件是否为文档/文本类文件（扩展名或无扩展名的常见文档名）。"""
    path = Path(file_path)
    if path.suffix.lower() in _DOCUMENTATION_EXTENSIONS:
        return True
    return path.name.lower() in _DOCUMENTATION_FILE_NAMES


def is_package_entry_file(file_path: str) -> bool:
    """判断文件是否为包入口文件（Python 的 __init__.py）。

    包入口文件允许为空或只含极短内容，空文件是合法的包标记。
    """
    return Path(file_path).name == "__init__.py"


def clean_code_block(content: str) -> str:
    """从 LLM 输出中提取代码块

    支持 ```python ... ```、``` ... ``` 等格式。
    先剥离 <think>...</think>` 标签，再提取代码块。
    如果没有代码块标记，返回原始内容（strip 后）。
    """
    import asyncio
    if asyncio.iscoroutine(content):
        logger.warning("clean_code_block 收到协程对象，降级为 str")
        content = str(content)
    elif not isinstance(content, str):
        content = str(content)

    # 只在内容以思考块开头时剥离（DeepSeek-R1 等模型的思考过程）。
    # 全局删除会把代码里作为字面量的 "<think>...</think>" 一并抹掉，
    # 例如 PROMPT = "<think>请思考</think>" 会被清空。
    for tag in ("think", "thinking"):
        if not re.match(rf'\s*<{tag}>', content):
            continue
        closed = re.sub(rf'\s*<{tag}>.*?</{tag}>', '', content, count=1, flags=re.DOTALL)
        if closed == content:
            # 未闭合的思考块：整段输出都是思考过程
            closed = re.sub(rf'\s*<{tag}>.*', '', content, flags=re.DOTALL)
        content = closed
    content = content.strip()

    pattern = r'```(?:\w+)?\s*(.*?)\s*```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


def strip_leading_file_label(content: str, file_path: str) -> str:
    """Remove a model-emitted file label preceding the actual file content."""
    lines = content.splitlines(keepends=True)
    if not lines:
        return content
    label = lines[0].strip()
    if label in {file_path, f"File: {file_path}", f"file: {file_path}"}:
        return "".join(lines[1:]).lstrip("\r\n")
    return content


async def extract_engineer_content(
    content: Optional[str],
    engineer,
    output_dir: Path,
    file_path: str,
    fix_imports_fn=None,
    all_files=None,
    expected_language: Optional[str] = None,
    llm_caller=None,
) -> Optional[str]:
    """从工程师输出中提取最终文件内容

    统一处理三种情况：
    1. 工程师通过工具直接编辑了文件（get_edited_files）
    2. 工程师返回了编辑标记（JSON）
    3. 工程师返回了完整文件内容

    Args:
        content: 工程师返回的原始内容
        engineer: 工程师实例（需提供 get_edited_files 方法）
        output_dir: 项目输出目录
        file_path: 文件相对路径
        fix_imports_fn: 可选的 import 修复函数 (content, file_path, all_files) -> fixed_content
        all_files: 所有文件列表（用于 import 修复）
        expected_language: 期望的语言（如 "Python", "JavaScript"），用于 LLM 语言检测
        llm_caller: async 函数，接受 prompt 返回 response，用于 LLM 语言检测

    Returns:
        提取后的文件内容，失败返回 None
    """
    import asyncio
    if asyncio.iscoroutine(content):
        logger.warning(f"extract_engineer_content 收到协程对象，降级为 str: {file_path}")
        content = str(content)
    elif content is not None and not isinstance(content, str):
        content = str(content)

    edited_files = engineer.get_edited_files()

    logger.info(f"extract_engineer_content: file_path={file_path}, expected_language={expected_language}, llm_caller={llm_caller is not None}, edited_files={len(edited_files) if edited_files else 0}, output_dir={output_dir}, edited_files_content={edited_files[:3] if edited_files else []}")

    if edited_files:
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师通过工具直接编辑了文件: {file_path}，跳过写入步骤")
            # 沙箱验证
            sandbox_ok, sandbox_reason = validate_file_in_sandbox(file_path, content)
            if not sandbox_ok:
                logger.warning(f"沙箱验证失败: {file_path} - {sandbox_reason}")
                return None
            # LLM 语言检测
            if expected_language and llm_caller:
                lang_ok, lang_reason = await validate_language_with_llm(
                    file_path, content, expected_language, llm_caller
                )
                if not lang_ok:
                    logger.warning(f"语言检测失败: {file_path} - {lang_reason}")
                    return None
            return content
        else:
            # 工程师报告编辑了文件但目标文件不存在
            full_path_str = str(full_path)
            if full_path_str in edited_files:
                logger.error(f"工程师报告编辑了文件但文件不存在: {file_path}")
            else:
                logger.info(f"工程师编辑了其他文件，当前文件 {file_path} 未被编辑")
            return None

    if content and _is_edit_marker(content, file_path):
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师返回编辑标记: {file_path}，读取已修改文件")
            # 沙箱验证
            sandbox_ok, sandbox_reason = validate_file_in_sandbox(file_path, content)
            if not sandbox_ok:
                logger.warning(f"沙箱验证失败: {file_path} - {sandbox_reason}")
                return None
            # LLM 语言检测
            if expected_language and llm_caller:
                lang_ok, lang_reason = await validate_language_with_llm(
                    file_path, content, expected_language, llm_caller
                )
                if not lang_ok:
                    logger.warning(f"语言检测失败: {file_path} - {lang_reason}")
                    return None
            return content
        else:
            logger.error(f"工程师返回编辑标记但文件不存在: {file_path}")
            return None

    if content:
        # 尝试从 JSON 元数据中提取实际代码
        extracted = try_extract_from_metadata(file_path, content)
        if extracted:
            content = extracted

        content = clean_code_block(content)
        content = strip_leading_file_label(content, file_path)

        # 内容有效性验证：检测 JSON 元数据、Markdown 等无效内容
        is_valid, reason = is_valid_code_content(file_path, content)
        if not is_valid:
            logger.warning(f"内容验证失败: {file_path} - {reason}")
            return None  # 返回 None 触发调用方的恢复流程

        is_placeholder, placeholder_reason = is_placeholder_content(content, file_path)
        if is_placeholder:
            logger.warning(f"内容验证失败: {file_path} - {placeholder_reason}")
            return None  # 返回 None 触发调用方的恢复流程

        # 沙箱验证：在 bubblewrap 中检查语法和基本正确性
        sandbox_ok, sandbox_reason = validate_file_in_sandbox(file_path, content)
        if not sandbox_ok:
            logger.warning(f"沙箱验证失败: {file_path} - {sandbox_reason}")
            return None  # 返回 None 触发调用方的恢复流程

        # LLM 语言检测：检查内容语言是否匹配文件扩展名
        if expected_language and llm_caller:
            lang_ok, lang_reason = await validate_language_with_llm(
                file_path, content, expected_language, llm_caller
            )
            if not lang_ok:
                logger.warning(f"语言检测失败: {file_path} - {lang_reason}")
                return None  # 返回 None 触发调用方的恢复流程

        if fix_imports_fn and all_files:
            content = fix_imports_fn(content, file_path, all_files)
        return content

    return None


def _is_edit_marker(content: str, file_path: str = "") -> bool:
    """检查内容是否是编辑标记或元数据（JSON 格式）"""
    stripped = content.strip()
    if not stripped.startswith('{'):
        return False
    try:
        import json
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            return False
        # 编辑标记
        if "action" in obj or "operation" in obj:
            return True
        # .json 文件的整体内容本身就是合法 JSON，status/output/result 等键
        # 可能只是数据字段。此时只有显式 action/operation 才算编辑标记。
        if file_path.lower().endswith('.json'):
            return False
        # LLM 返回的元数据（非代码内容）
        metadata_keys = {
            "status", "message", "file_path", "file_size",
            "key_features", "notes", "summary", "result",
            "output", "response"
        }
        if metadata_keys & set(obj.keys()):
            return True
        return False
    except (json.JSONDecodeError, ValueError):
        return False


def try_extract_from_metadata(file_path: str, content: str) -> Optional[str]:
    """尝试从 JSON 元数据中提取实际代码内容

    LLM 有时返回 JSON 格式的"生成摘要"而非实际代码，如：
    {"status": "completed", "content": "actual code here", ...}

    本函数尝试从常见字段中提取代码。

    Args:
        file_path: 文件路径（用于日志）
        content: 原始内容

    Returns:
        提取的代码内容，失败返回 None
    """
    if not content:
        return None

    stripped = content.strip()
    if not stripped.startswith('{'):
        return None

    try:
        import json
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            return None

        # .json 文件的整体内容本身就是合法 JSON，字段可能就叫 content/code/source。
        # 只有在出现明确的"生成摘要"标记键时才提取，避免把数据文件改写成字段值。
        if file_path.lower().endswith('.json'):
            wrapper_markers = ('status', 'file_path', 'filepath', 'language', 'action')
            if not any(marker in obj for marker in wrapper_markers):
                return None

        # 尝试从常见字段提取代码
        code_keys = ['content', 'code', 'file_content', 'source', 'body', 'implementation']
        for key in code_keys:
            if key in obj and isinstance(obj[key], str) and len(obj[key].strip()) > 50:
                logger.info(f"从 JSON 元数据的 '{key}' 字段提取代码: {file_path}")
                return obj[key]

        return None
    except (json.JSONDecodeError, ValueError):
        return None


def is_valid_code_content(file_path: str, content: str) -> tuple:
    """语言无关的内容有效性检查

    检查内容是否是有效的代码，而非 JSON 元数据、Markdown 文档或其他非代码内容。
    对所有编程语言通用。

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        (is_valid, reason): 有效返回 (True, "")，无效返回 (False, "原因")
    """
    if not content:
        # 空 __init__.py 是合法的包标记，不算无效内容
        if is_package_entry_file(file_path):
            return True, ""
        return False, "内容为空"

    stripped = content.strip()

    # 包入口文件可以只含 __all__ 或一句 docstring；文档/文本文件的正确内容
    # 也可以很短（如单行 requirements.txt、短 README），都不受最小长度限制。
    if (
        len(stripped) < 10
        and not is_package_entry_file(file_path)
        and not _is_documentation_file(file_path)
    ):
        return False, "内容过短（<10 字符）"

    ext = Path(file_path).suffix.lower()
    name = Path(file_path).name.lower()

    # 整体 JSON 形态且含元数据键，通常意味着 LLM 返回了包装结果而非代码。
    # 对 .json 文件本身跳过：合法配置文件可以包含这些键。
    if ext != '.json':
        # 检查是否是 JSON 元数据
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                import json
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    metadata_keys = {
                        "status", "message", "file_path", "file_size",
                        "key_features", "notes", "summary", "result",
                        "output", "response", "action", "operation"
                    }
                    if metadata_keys & set(obj.keys()):
                        return False, "内容是 JSON 元数据而非代码"
            except (json.JSONDecodeError, ValueError):
                pass

        # 检查是否是 JSON 数组
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                import json
                json.loads(stripped)
                return False, "内容是 JSON 数组而非代码"
            except (json.JSONDecodeError, ValueError):
                pass

    # 符号启发式只用于没有确定性语法校验的类型；docstring 中的项目符号
    # （- / 1. / >）会让合法代码命中，因此 .py 等类型交给解析器判定。
    # 文档类文件的正确内容本来就是 Markdown/富文本，不能据此判为无效。
    if (
        ext not in ('.py', '.pyw', '.pyi', '.json')
        and ext not in _MARKUP_EXTENSIONS
        and name != 'pom.xml'
        and not _is_documentation_file(file_path)
    ):
        # 检查是否是 Markdown 文档（用特征模式而非单个 #）
        md_patterns = ['## ', '### ', '- ', '* ', '1. ', '```', '> ']
        md_count = sum(1 for p in md_patterns if p in stripped[:500])
        # 代码里以字符串/模板字面量承载 Markdown（如生成文档的 JS/TS）会命中
        # 上面的项目符号，因此只要出现明确代码构造就不判为 Markdown。
        code_constructs = (
            "function ", "const ", "let ", "var ", "=>", "import ", "export ",
            "return ", "class ", "def ", "package ", "func ", "public ",
            "private ", "protected ", "void ", "console.", "#include", "<?php",
            "SELECT ", "print(", "echo ",
        )
        if md_count >= 3 and not any(token in stripped[:500] for token in code_constructs):
            return False, "内容是 Markdown 文档而非代码"

    # 快速语法验证（JSON、Python 语法等）
    syntax_ok, syntax_reason = validate_syntax_for_extension(file_path, stripped)
    if not syntax_ok:
        return False, syntax_reason

    return True, ""


def validate_syntax_for_extension(file_path: str, content: str) -> tuple:
    """根据文件扩展名验证内容语法（快速，不需要 LLM）

    用于快速过滤明显的格式错误（JSON、Python 语法等），不做语言检测。
    语言检测由 validate_language_with_llm 负责。

    Args:
        file_path: 文件路径
        content: 文件内容（已 strip）

    Returns:
        (is_valid, reason): 有效返回 (True, "")，无效返回 (False, "原因")
    """
    import re
    ext = Path(file_path).suffix.lower()

    # JSON 文件：验证 JSON 格式
    if ext == '.json':
        import json
        try:
            json.loads(content)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"JSON 格式错误: {e}"

    # Maven accepts XML syntax but requires selected project-level elements to be unique.
    if Path(file_path).name.lower() == 'pom.xml':
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            return False, f"POM XML 格式错误: {e}"
        child_names = [child.tag.rsplit('}', 1)[-1] for child in root]
        for unique_name in ('properties', 'dependencies', 'build'):
            if child_names.count(unique_name) > 1:
                return False, f"POM 包含重复的 <{unique_name}> 元素"
        return True, ""

    # Python 文件：用 ast.parse 验证语法
    if ext in ('.py', '.pyw', '.pyi'):
        import ast
        try:
            ast.parse(content)
            return True, ""
        except SyntaxError as e:
            return False, f"Python 语法错误: {e}"

    # 其他文件类型：跳过快速检查，由 LLM 语言检测负责
    return True, ""


# ============ 统一沙箱验证系统 ============

# 验证级别定义
SANDBOX_LEVELS = {
    "syntax": "语法正确性检查",
    "import": "跨文件导入验证",
    "contract": "接口契约验证",
    "run": "启动运行验证",
}

# 硬编码规则：触发事件 → 验证级别
HARDCODED_RULES = {
    "file_created": "syntax",
    "file_modified": "syntax",
    "project_complete": "run",
    "single_file_fix": "syntax",
    "cross_file_fix": "import",
    "final_validation": "run",
}

class SandboxValidator:
    """沙箱验证器基类

    子类只需声明 extensions 属性，系统会自动按扩展名注册。
    """

    # 子类覆盖：支持的文件扩展名
    extensions: list = []

    def filter_files(self, files: dict) -> dict:
        """过滤出本验证器支持的文件"""
        return {f: c for f, c in files.items()
                if any(f.endswith(ext) for ext in self.extensions)}

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        """构建验证脚本（子类实现）

        脚本规范：
        - 使用 os.environ["SANDBOX_TMP_DIR"] 获取临时目录
        - 将文件写入临时目录后验证
        - 错误输出到 stderr，成功输出 "OK"
        - 验证失败退出码 1

        Args:
            files: 文件字典 {file_path: content}
            level: 验证级别 "syntax"|"import"|"run"
        """
        raise NotImplementedError


class GoSandboxValidator(SandboxValidator):
    """Go 沙箱验证器"""
    extensions = ['.go']

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        go_files = self.filter_files(files)
        if not go_files:
            return ""

        files_repr = repr(go_files)

        return f'''
import sys, os, subprocess, tempfile
from pathlib import Path

files = {files_repr}
errors = []

tmp_dir = os.environ.get("SANDBOX_TMP_DIR", tempfile.mkdtemp())
project_dir = os.path.join(tmp_dir, "project")
os.makedirs(project_dir, exist_ok=True)

# 写入文件
for file_path, content in files.items():
    full_path = Path(project_dir) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)

# 初始化 go module (如果没有 go.mod)
go_mod = Path(project_dir) / "go.mod"
if not go_mod.exists():
    subprocess.run(['go', 'mod', 'init', 'temp'], cwd=project_dir, capture_output=True)

# 验证语法 (go vet)
result = subprocess.run(
    ['go', 'vet', './...'],
    cwd=project_dir, capture_output=True, text=True, timeout=30
)
if result.returncode != 0:
    errors.append(f"go vet failed: {{result.stderr.strip()}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
'''


class RustSandboxValidator(SandboxValidator):
    """Rust 沙箱验证器"""
    extensions = ['.rs']

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        rs_files = self.filter_files(files)
        if not rs_files:
            return ""

        files_repr = repr(rs_files)

        return f'''
import sys, os, subprocess, tempfile
from pathlib import Path

files = {files_repr}
errors = []

tmp_dir = os.environ.get("SANDBOX_TMP_DIR", tempfile.mkdtemp())
project_dir = os.path.join(tmp_dir, "project")
os.makedirs(project_dir, exist_ok=True)

# 写入文件
for file_path, content in files.items():
    full_path = Path(project_dir) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)

# 检查 rustc 是否可用
try:
    subprocess.run(['rustc', '--version'], capture_output=True, check=True)
except FileNotFoundError:
    print("OK")
    sys.exit(0)

# 逐文件语法检查
for file_path in files:
    full_path = Path(project_dir) / file_path
    result = subprocess.run(
        ['rustc', '--edition', '2021', '--crate-type', 'lib', str(full_path)],
        cwd=project_dir, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        errors.append(f"{{file_path}}: {{result.stderr.strip()[:200]}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
'''


# ============ 验证器自动注册表（按扩展名） ============

# 仅保留用真实编译器校验的语言。Python 与 JS/TS 家族已由本地解析器覆盖
# （见 _SHARED_SYNTAX_EXTENSIONS），无需在此注册。
_VALIDATOR_INSTANCES = [
    GoSandboxValidator(),
    RustSandboxValidator(),
]

# 按扩展名自动建立映射
_EXTENSION_VALIDATORS = {}
for _v in _VALIDATOR_INSTANCES:
    for _ext in _v.extensions:
        _EXTENSION_VALIDATORS[_ext] = _v


def register_sandbox_validator(validator: SandboxValidator):
    """注册新的沙箱验证器（按扩展名自动注册）"""
    for ext in validator.extensions:
        _EXTENSION_VALIDATORS[ext] = validator
    _VALIDATOR_INSTANCES.append(validator)


def _decide_level(context: dict = None) -> str:
    """决策引擎：确定验证级别

    优先级：硬编码规则 > 用户配置 > 默认值
    """
    if not context:
        return "syntax"

    trigger = context.get("trigger")

    # L1: 硬编码规则
    if trigger in HARDCODED_RULES:
        return HARDCODED_RULES[trigger]

    # L2: 用户配置
    config = context.get("config", {})
    if config:
        config_level = config.get(f"on_{trigger}")
        if config_level and config_level in SANDBOX_LEVELS:
            return config_level

    # 默认：语法验证
    return "syntax"


# 统一语法门禁覆盖的扩展名。这些文件不再送 bwrap 生成脚本：
# `ast.parse` / 共享解析器就能给出确定性判断，语法检查不执行代码，无需隔离。
# `node --check` 无法解析 TS 类型注解、JSX 与 Vue 单文件组件，纯定界符计数
# 又会把注释和字符串里的括号当成结构错误。
_SHARED_SYNTAX_EXTENSIONS = frozenset({
    '.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue',
    '.html', '.htm', '.xhtml', '.css',
})


def _shared_syntax_errors(file_path: str, content: str) -> list:
    """用本地解析器校验 Python、JS/TS 家族与标记语言文件。

    检查只做语法解析、不执行代码，因此无需 bwrap。Python 用 `ast.parse`，
    JS/TS 家族与标记语言走 app/agent/js_syntax.py 与 app/agent/markup_syntax.py，
    与写入门禁保持同源。
    """
    import ast

    from app.agent.js_syntax import check_js_source, check_ts_source, vue_script_source
    from app.agent.markup_syntax import css_structure_errors, html_structure_errors

    ext = Path(file_path).suffix.lower()

    if ext == '.py':
        try:
            ast.parse(content)
            return []
        except SyntaxError as e:
            return [f"{file_path}: Python 语法错误: {e}"]

    if ext in ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue'):
        source = content
        use_ts = ext in ('.ts', '.tsx')
        use_jsx = ext in ('.jsx', '.tsx')
        if ext == '.vue':
            source, use_ts, use_jsx = vue_script_source(content)
        if not source.strip():
            return []
        if use_ts:
            ok, error = check_ts_source(source, jsx=use_jsx)
            label = "TypeScript"
        else:
            ok, error = check_js_source(source)
            label = "JavaScript"
        if ok:
            return []
        return [f"{file_path}: {label} 语法错误: {(error or '语法检查未通过')[:200]}"]

    if ext in ('.html', '.htm', '.xhtml'):
        return [f"{file_path}: {error}" for error in html_structure_errors(content)]

    if ext == '.css':
        return [f"{file_path}: {error}" for error in css_structure_errors(content)]

    return []


def validate_in_sandbox(
    project_dir: str,
    files: dict,
    level: str = "auto",
    context: dict = None,
) -> tuple:
    """执行云端基础语法验证。

    运行时、依赖、构建和 E2E 验证属于 VS Code Agent Host 的本地职责。
    `syntax` 级用本地解析器完成，不执行代码、不依赖 bwrap。只有注册了真实
    编译器验证器的语言（Go/Rust）才构造 bwrap 脚本，bwrap 缺失时跳过；其余
    扩展名交由 VS Code Agent Host 本地验证。

    Args:
        project_dir: 项目目录路径
        files: 文件字典 {file_path: content}
        level: "syntax"|"import"|"contract"|"run"|"auto"
        context: 上下文信息 {trigger, modified_files, config, ...}

    Returns:
        (is_valid, errors): 有效返回 (True, [])，无效返回 (False, [错误列表])
    """
    import shutil
    import subprocess
    import tempfile

    if not files:
        return True, []

    # 1. 决策：确定验证级别
    if level == "auto":
        level = _decide_level(context)

    if level in {"run", "import", "contract"}:
        logger.info(
            "云端跳过运行时沙箱验证: level=%s, scope=local_runtime, "
            "由 VS Code Agent Host 执行",
            level,
        )
        return True, []

    logger.info(f"云端语法验证: level={level}, files={len(files)}")

    # 2. 统一门禁：Python 与 JS/TS 家族、标记语言按扩展名走本地解析器；
    #    文档/文本类文件的正确内容本就是散文或数据，不做代码语法门禁；
    #    其余扩展名（本地解析器不覆盖）继续走 bwrap 脚本。
    shared_errors = []
    remaining_files = {}
    for file_path, content in files.items():
        ext = Path(file_path).suffix.lower()
        if ext in _SHARED_SYNTAX_EXTENSIONS:
            shared_errors.extend(_shared_syntax_errors(file_path, content))
        elif _is_documentation_file(file_path):
            continue
        else:
            remaining_files[file_path] = content

    if shared_errors:
        return False, shared_errors
    if not remaining_files:
        return True, []

    # 3. 只有注册了真实编译器验证器的语言才构造 bwrap 脚本；其余扩展名
    #    （如 .rb/.php/.java）不在此处做启发式检查，交由 VS Code Agent Host
    #    本地验证，避免朴素括号计数把字符串/注释判成结构错误。
    groups = {}
    for file_path, content in remaining_files.items():
        groups.setdefault(Path(file_path).suffix.lower(), {})[file_path] = content

    scripts = []
    for ext, group_files in groups.items():
        validator = _EXTENSION_VALIDATORS.get(ext)
        if validator is None:
            continue
        script = validator.build_validation_script(group_files, level)
        if script:
            scripts.append(script)

    if not scripts:
        return True, []

    # 4. 合并脚本
    combined_script = "\n# === 分组分隔 ===\n".join(scripts)

    # 5. 编译器级验证需要 bwrap；本地运行验证由 Agent Host 执行。
    if shutil.which("bwrap") is None:
        logger.info("云端语法验证跳过：bwrap 不可用，等待 VS Code Agent Host 本地验证")
        return True, []

    with tempfile.TemporaryDirectory(prefix='sandbox_validate_') as tmp_dir:
        bwrap_cmd = [
            'bwrap',
            '--ro-bind', '/', '/',
            '--tmpfs', '/tmp',
            '--bind', tmp_dir, tmp_dir,
            '--proc', '/proc',
            '--dev', '/dev',
            '--unshare-pid',
            '--die-with-parent',
        ]

        # 注入临时目录
        script_with_env = f'''
import os
os.environ["SANDBOX_TMP_DIR"] = {repr(tmp_dir)}
''' + combined_script

        try:
            proc = subprocess.run(
                bwrap_cmd + ['python3', '-c', script_with_env],
                capture_output=True,
                text=True,
                timeout=60
            )

            if proc.returncode != 0:
                error = proc.stderr.strip() or proc.stdout.strip()
                errors = [line.strip() for line in error.split('\n') if line.strip()]
                return False, errors

            return True, []

        except subprocess.TimeoutExpired:
            logger.warning(f"沙箱验证超时: {project_dir}")
            return True, []
        except Exception as e:
            logger.warning(f"沙箱验证异常: {project_dir} - {e}")
            return True, []


# ============ 向后兼容接口 ============

def validate_file_in_sandbox(file_path: str, content: str) -> tuple:
    """单文件沙箱验证（向后兼容接口）

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        (is_valid, reason): 有效返回 (True, "")，无效返回 (False, "原因")
    """
    if not content or not content.strip():
        return False, "内容为空"

    ok, errors = validate_in_sandbox(
        project_dir="",
        files={file_path: content},
        level="syntax",
        context={"trigger": "file_modified"}
    )

    if ok:
        return True, ""
    else:
        return False, errors[0] if errors else "验证失败"


def validate_project_in_sandbox(project_dir: str, files: dict, language: str = None) -> tuple:
    """项目级沙箱验证（向后兼容接口）

    Args:
        project_dir: 项目目录路径
        files: 文件字典 {file_path: content}
        language: 项目语言（已废弃，自动检测）

    Returns:
        (is_valid, errors): 有效返回 (True, [])，无效返回 (False, [错误列表])
    """
    return validate_in_sandbox(
        project_dir=project_dir,
        files=files,
        level="import",
        context={"trigger": "project_complete"}
    )


async def validate_language_with_llm(
    file_path: str,
    content: str,
    expected_language: str,
    llm_caller,
) -> tuple:
    """用 LLM 检测内容语言是否匹配文件扩展名

    Args:
        file_path: 文件路径（用于日志）
        content: 文件内容
        expected_language: 期望的语言（如 "Python", "JavaScript", "CSS"）
        llm_caller: async 函数，接受 prompt 返回 response

    Returns:
        (is_valid, reason): 匹配返回 (True, "")，不匹配返回 (False, "原因")
    """
    logger.info(f"validate_language_with_llm 调用: file_path={file_path}, expected_language={expected_language}, llm_caller={llm_caller is not None}")
    if not expected_language or not llm_caller:
        logger.debug(f"LLM 语言检测跳过: expected_language={expected_language}, llm_caller={llm_caller is not None}")
        return True, ""

    if not content or len(content.strip()) < 20:
        logger.debug(f"LLM 语言检测跳过: 内容太短 ({len(content.strip()) if content else 0} 字符)")
        return True, ""  # 内容太短，跳过检测
    if _heuristic_language_match(file_path, content, expected_language):
        logger.info("LLM 语言检测跳过: 启发式匹配 %s", file_path)
        return True, ""
    logger.info("LLM 语言检测跳过: 不阻塞生成 %s", file_path)
    return True, ""


def _heuristic_language_match(file_path: str, content: str, expected_language: str) -> bool:
    expected = (expected_language or "").strip().lower()
    suffix = Path(file_path).suffix.lower()
    text = content or ""
    if suffix in {".md", ".txt", ".json", ".toml", ".yml", ".yaml", ".xml"}:
        return True
    if expected in {"python", "py"} and suffix == ".py":
        return any(marker in text for marker in ("def ", "class ", "import ", "from ", "async def "))
    if expected in {"javascript", "js", "typescript", "ts"} and suffix in {".js", ".ts", ".mjs", ".cjs"}:
        return any(marker in text for marker in ("function ", "const ", "let ", "export ", "import "))
    return False


def _has_effective_code_after(content: str, end_index: int) -> bool:
    """判断给定位置之后是否还有实质代码行。

    空行、整行注释、以及只含标点的片段（如截断句尾的「）」）都不算代码。
    """
    for line in content[end_index:].split('\n'):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line.startswith(('#', '//', '/*', '*')):
            continue
        if not re.search(r'[A-Za-z0-9_\u4e00-\u9fff]', stripped_line):
            continue
        return True
    return False


def is_placeholder_content(content: str, file_path: str = "") -> tuple:
    """检测内容是否为占位符代码

    统一的占位符检测逻辑，所有写入路径都应调用此函数。

    Args:
        content: 文件内容
        file_path: 文件路径（用于日志）

    Returns:
        (is_placeholder, reason): 是占位符返回 (True, "原因"), 否则返回 (False, "")
    """
    if not content or not content.strip():
        # 空的 __init__.py 是合法的包标记，不是占位符
        if is_package_entry_file(file_path):
            return False, ""
        return True, "内容为空"

    stripped = content.strip()

    truncation_patterns = [
        (r"未展示完整", "LLM truncated output"),
        (r"后续代码与", "LLM truncated output"),
        (r"其他代码保持不变", "LLM truncated output"),
        (r"代码保持不变", "LLM truncated output"),
        (r"需替换为真实实现", "stub implementation"),
        (r"omitted for brevity", "LLM truncated output"),
        (r"rest of (the )?code (is |remains )?(the same|unchanged)", "LLM truncated output"),
        (r"not shown (here|in (this )?snippet)", "LLM truncated output"),
        (r"\.\.\.\s*（后续", "LLM truncated output"),
    ]
    # 文档/文本文件里这些短语是正常行文（如更新日志「其他代码保持不变」），
    # 不能据此判为截断，否则合法的 README/说明文件会被反复重生成。
    if not _is_documentation_file(file_path):
        for pattern, desc in truncation_patterns:
            for match in re.finditer(pattern, stripped, re.IGNORECASE):
                # 短语之后若还有实质代码，说明输出没有在短语处被砍断，
                # 它是代码里的注释/说明（如 patch 注释「其余代码保持不变」）。
                if _has_effective_code_after(stripped, match.end()):
                    continue
                return True, desc

    # 占位符模式匹配
    placeholder_patterns = [
        # Python 占位符
        (r'^""".*placeholder.*"""', "Python docstring placeholder"),
        (r"^'''.*placeholder.*'''", "Python docstring placeholder"),
        (r'^""".*TODO.*"""', "Python docstring TODO"),
        (r"^'''.*TODO.*'''", "Python docstring TODO"),
        (r'^#\s*TODO\b', "Python TODO comment"),
        (r'^#\s*FIXME\b', "Python FIXME comment"),
        (r'^#\s*placeholder\b', "Python placeholder comment"),
        (r'^pass\s*$', "Python pass statement"),
        (r'^raise NotImplementedError', "NotImplementedError"),
        # JS/TS 占位符
        (r'^//\s*TODO\b', "JS TODO comment"),
        (r'^//\s*FIXME\b', "JS FIXME comment"),
        (r'^//\s*[Pp]laceholder', "JS placeholder comment"),
        (r'^/\*.*[Pp]laceholder.*\*/', "CSS/JS placeholder comment"),
        (r'^/\*.*TODO.*\*/', "CSS/JS TODO comment"),
        (r'^console\.log\(["\']placeholder', "console.log placeholder"),
        (r'^console\.log\(["\']TODO', "console.log TODO"),
        (r'^console\.log\(["\']FIXME', "console.log FIXME"),
        (r'^throw new Error\(["\']Not implemented', "Not implemented error"),
        (r'^throw new Error\(["\']TODO', "TODO error"),
        # 通用占位符
        (r'^//\s*Package initialization\s*$', "Package initialization stub"),
        (r'^"""Package initialization"""', "Python package init stub"),
        # 注意：`"""Module: ...` / `// Module: ...` 是合法的模块头文档，不能作为
        # 占位符特征，否则正常 __init__.py 会被误判并反复重生成。
        # LLM 工具调用 JSON（LLM 误返回工具调用而非代码）
        (r'^\{"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:', "LLM tool call JSON"),
        (r'^\{"tool"\s*:\s*"[^"]+"\s*\}', "LLM tool call JSON"),
        # 纯 URL 内容（LLM 误返回链接而非代码）
        (r'^https?://\S+$', "Pure URL content"),
    ]

    # 检查代码中嵌入的工具调用 JSON（不在开头，但在代码中间）
    embedded_tool_call_patterns = [
        r'\{"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:\s*\{[^}]*\}\s*\}',
        r'\{"tool"\s*:\s*"[^"]+"\s*\}',
    ]

    # 注释类特征不能单独证明"未实现"：合法的小模块也会带 TODO 注释。
    # 这类特征只在文件没有任何有效代码行时才判为占位符，因此收集时让位给
    # 非注释类特征（如 pass、NotImplementedError）。
    comment_only_reasons = {
        "Python TODO comment", "Python FIXME comment", "Python placeholder comment",
        "JS TODO comment", "JS FIXME comment", "JS placeholder comment",
        "CSS/JS placeholder comment", "CSS/JS TODO comment",
    }

    matched_pattern = None
    comment_only_match = None
    # 仅含 pass 的 __init__.py 是合法的空包声明，不是占位实现；其它模块的
    # 顶格 pass 仍然按 stub 处理。
    is_package_entry = Path(file_path).name == '__init__.py'
    for pattern, desc in placeholder_patterns:
        if not re.search(pattern, stripped, re.IGNORECASE | re.MULTILINE):
            continue
        if desc == "Python pass statement" and is_package_entry:
            continue
        if desc in comment_only_reasons:
            comment_only_match = comment_only_match or desc
            continue
        matched_pattern = desc
        break
    if matched_pattern is None:
        matched_pattern = comment_only_match

    if matched_pattern:
        min_effective_lines = 0 if matched_pattern in comment_only_reasons else 2

        # 过滤掉空行、注释行、docstring、pass 行后，检查剩余行数
        lines = []
        for l in stripped.split('\n'):
            l_stripped = l.strip()
            if not l_stripped:
                continue
            if l_stripped.startswith('#') or l_stripped.startswith('//'):
                continue
            if l_stripped.startswith('"""') or l_stripped.startswith("'''"):
                continue
            if l_stripped.startswith('/*') or l_stripped.endswith('*/'):
                continue
            if l_stripped == 'pass':
                continue
            lines.append(l_stripped)
        if len(lines) <= min_effective_lines:
            return True, f"占位符代码（{matched_pattern}），有效行数: {len(lines)}"

    # 检查代码中嵌入的工具调用 JSON（不在开头，但在代码中间）
    for pattern in embedded_tool_call_patterns:
        # 只有内容整体就是一个工具调用 JSON 时才判为泄漏（LLM 误返回工具调用
        # 而非代码）。工具注册表、LLM function schema、API 响应夹具等合法代码
        # 同样包含 `{"tool": ..., "params": {...}}`，按子串匹配会大面积误报。
        if re.fullmatch(rf"\s*{pattern}\s*", stripped, re.DOTALL):
            return True, "内容整体为工具调用 JSON"

    return False, ""


def reusable_existing_file_content(file_path: str, content: str) -> tuple:
    """Whether on-disk content is complete enough to skip regeneration."""
    is_valid, reason = is_valid_code_content(file_path, content)
    if not is_valid:
        return False, reason
    is_placeholder, placeholder_reason = is_placeholder_content(content, file_path)
    if is_placeholder:
        return False, placeholder_reason
    return True, ""


def compact_project_context_for_file(file_path: str, project_context: Dict[str, Any]) -> str:
    """Build a per-file generation context without dumping the full architecture."""
    architecture = project_context.get("architecture") or {}
    if not isinstance(architecture, dict):
        architecture = {}
    file_plan = architecture.get("file_plan") or []
    normalized = (file_path or "").replace("\\", "/")
    this_file: Dict[str, Any] = {}
    for item in file_plan:
        if isinstance(item, dict) and item.get("path", "").replace("\\", "/") == normalized:
            this_file = item
            break
    contract = this_file.get("contract") or {}
    if not isinstance(contract, dict):
        contract = {}
    compact: Dict[str, Any] = {
        "requirement": (project_context.get("requirement") or "")[:2000],
        "language": architecture.get("language"),
        "tech_stack": (architecture.get("tech_stack") or [])[:10],
        "this_file": {
            "path": this_file.get("path") or file_path,
            "file_type": this_file.get("file_type"),
            "description": this_file.get("description"),
            "imports": this_file.get("imports") or [],
            "exports": this_file.get("exports") or contract.get("exports"),
            "contract": contract,
        },
    }
    generation_contract = project_context.get("generation_contract")
    if isinstance(generation_contract, dict):
        compact["generation_contract"] = generation_contract
    symbol_table = architecture.get("symbol_table")
    if not isinstance(symbol_table, dict):
        symbol_table = project_context.get("symbol_table")
    if isinstance(symbol_table, dict) and symbol_table:
        compact["symbol_table"] = symbol_table
        frozen_facts = {}
        if isinstance(symbol_table.get("storage"), dict):
            frozen_facts["storage"] = symbol_table["storage"]
        if isinstance(symbol_table.get("auth"), dict):
            frozen_facts["auth"] = symbol_table["auth"]
        if "route_prefix" in symbol_table:
            frozen_facts["route_prefix"] = symbol_table.get("route_prefix")
        if frozen_facts:
            compact["frozen_facts"] = frozen_facts
        this_entry = (symbol_table.get("files") or {}).get(normalized)
        if isinstance(this_entry, dict) and this_entry:
            compact["this_file"]["must_implement"] = this_entry
    generated_signatures = project_context.get("generated_signatures")
    if isinstance(generated_signatures, dict) and generated_signatures:
        compact["already_generated"] = generated_signatures
    original_content = str(project_context.get("original_content") or "")
    if not original_content and isinstance(generation_contract, dict):
        original_content = str(generation_contract.get("original_content") or "")
    if original_content:
        compact["original_content"] = original_content[:8000]
        compact["is_modification"] = True
        compact["modification_reason"] = str(
            project_context.get("modification_reason")
            or (generation_contract.get("modification_reason") if isinstance(generation_contract, dict) else "")
            or ""
        )
    return json.dumps(compact, ensure_ascii=False)


def write_file_atomic(output_dir: Path, file_path: str, content: str, skip_placeholder_check: bool = False) -> bool:
    """原子写入文件：先写临时文件，完成后重命名

    包含统一的占位符检测，拒绝写入占位符代码。

    Args:
        output_dir: 项目输出目录
        file_path: 文件相对路径
        content: 文件内容
        skip_placeholder_check: 跳过占位符检测（仅用于 IntegrityValidator 的包初始化文件）

    Returns:
        是否成功
    """
    import uuid

    # 统一占位符检测
    if not skip_placeholder_check:
        is_ph, reason = is_placeholder_content(content, file_path)
        if is_ph:
            logger.error(f"拒绝写入占位符文件: {file_path} - {reason}")
            return False

    full_path = output_dir / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用唯一后缀避免并发写入同一 tmp 文件
    tmp_path = full_path.with_suffix(full_path.suffix + f'.tmp.{uuid.uuid4().hex[:8]}')

    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        tmp_path.rename(full_path)
        return True
    except Exception as e:
        logger.error(f"原子写入失败: {file_path}, {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def validate_content_quality(file_path: str, content: str) -> str:
    """验证文件内容质量，检测 LLM 思考过程泄漏等非代码内容

    返回警告信息（空字符串表示通过）。
    """
    if not content or len(content.strip()) < 10:
        return ""

    ext = Path(file_path).suffix.lower()
    stripped = content.strip()

    # 文档/文本文件的首行本来就是散文，不能据此判为思考过程泄漏。
    is_doc_file = _is_documentation_file(file_path)

    # 检测 LLM 思考过程泄漏（中英文描述性文本混入代码文件）
    thinking_patterns = [
        # 中文思考泄漏
        r'^最终答案',
        r'^任务执行',
        r'^基于.*?执行过程',
        r'^已成功完成',
        r'^以下是.*?总结',
        r'^✅',
        r'^###\s+✅',
        # 英文思考泄漏
        r'^Let me think about',
        r'^First, I need to',
        r'^Now I understand',
        r'^Here is the complete',
        r'^The following is',
        r'^This file contains',
        r'^I\'ll create',
        r'^Let me create',
        r'^Based on the requirements',
        r'^According to the',
        r'^The implementation includes',
        r'^This module provides',
        r'^This function is responsible',
        r'^Here\'s a summary',
        r'^In this file,',
        r'^The purpose of this',
    ]
    # 说明：原先的 r'^---\s*$' 已移除。该模式只在内容首行匹配，而首行 `---`
    # 是 YAML 文档分隔符/Markdown front matter 的合法写法，属于必然误报。
    if not is_doc_file:
        for pattern in thinking_patterns:
            if re.match(pattern, stripped, re.IGNORECASE | re.MULTILINE):
                return f"内容疑似 LLM 思考过程泄漏（匹配模式: {pattern[:30]}）"

    # CSS 文件内容校验
    if ext == '.css':
        # CSS 不应包含大段中文描述（先剥离注释，中文注释是合法内容）
        no_comments = re.sub(r'/\*.*?\*/', '', stripped, flags=re.DOTALL)
        lines = [l.strip() for l in no_comments.split('\n') if l.strip()]
        chinese_lines = sum(1 for l in lines if len(re.findall(r'[\u4e00-\u9fff]', l)) > 10)
        if chinese_lines > len(lines) * 0.3 and chinese_lines > 3:
            return f"CSS 文件包含大量中文文本（{chinese_lines}/{len(lines)} 行），疑似非代码内容"

    # Python 文件不应放在前端目录
    if ext == '.py':
        frontend_dirs = ['static/js', 'static/css', 'assets/js', 'assets/css', 'public/js', 'public/css']
        if any(d in file_path.replace('\\', '/') for d in frontend_dirs):
            return f"Python 文件不应出现在前端资源目录: {file_path}"

    return ""


def cleanup_temp_files(output_dir: Path, file_path: str):
    """清理未完成的临时文件"""
    import glob
    full_path = output_dir / file_path
    # 匹配所有 .tmp.* 后缀的临时文件
    pattern = str(full_path) + ".tmp.*"
    for tmp in glob.glob(pattern):
        tmp_path = Path(tmp)
        if tmp_path.exists():
            logger.warning(f"发现未完成的文件，删除: {tmp_path}")
            tmp_path.unlink()


def get_expected_language_for_file(file_path: str, project_language: str = "") -> str:
    """根据文件扩展名和项目语言，返回期望的内容语言

    Args:
        file_path: 文件路径
        project_language: 项目主语言（如 "python"、"javascript"）

    Returns:
        期望的内容语言（如 "Python"、"HTML"、"CSS"、"JavaScript"）
    """
    from pathlib import Path
    ext = Path(file_path).suffix.lower()
    name = Path(file_path).name.lower()

    # 配置文件
    if name in ('requirements.txt', 'pipfile', 'pyproject.toml', 'setup.py', 'setup.cfg'):
        return "TOML/INI"  # 配置类文件
    if name in ('package.json', 'package-lock.json', 'tsconfig.json'):
        return "JSON"
    if name in ('go.mod', 'cargo.toml', 'pom.xml'):
        return "TOML/XML"
    if name in ('dockerfile',):
        return "Dockerfile"
    if name in ('readme.md', 'readme.rst', 'changelog.md'):
        return "Markdown"
    if name in ('.gitignore', '.env', '.env.example'):
        return "Config"

    # 扩展名映射
    ext_map = {
        '.py': 'Python',
        '.pyi': 'Python',
        '.js': 'JavaScript',
        '.jsx': 'JavaScript/JSX',
        '.ts': 'TypeScript',
        '.tsx': 'TypeScript/TSX',
        '.mjs': 'JavaScript',
        '.cjs': 'JavaScript',
        '.go': 'Go',
        '.rs': 'Rust',
        '.java': 'Java',
        '.kt': 'Kotlin',
        '.rb': 'Ruby',
        '.php': 'PHP',
        '.c': 'C',
        '.cpp': 'C++',
        '.cc': 'C++',
        '.cxx': 'C++',
        '.h': 'C/C++ Header',
        '.hpp': 'C++ Header',
        '.cs': 'C#',
        '.swift': 'Swift',
        '.m': 'Objective-C',
        '.mm': 'Objective-C++',
        '.scala': 'Scala',
        '.r': 'R',
        '.lua': 'Lua',
        '.pl': 'Perl',
        '.sh': 'Shell Script',
        '.bash': 'Shell Script',
        '.zsh': 'Shell Script',
        '.ps1': 'PowerShell',
        '.sql': 'SQL',
        '.html': 'HTML',
        '.htm': 'HTML',
        '.xml': 'XML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'Sass',
        '.less': 'Less',
        '.vue': 'Vue',
        '.svelte': 'Svelte',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.json': 'JSON',
        '.toml': 'TOML',
        '.ini': 'INI',
        '.cfg': 'INI',
        '.md': 'Markdown',
        '.rst': 'reStructuredText',
        '.txt': 'Plain Text',
        '.proto': 'Protocol Buffer',
        '.graphql': 'GraphQL',
        '.dart': 'Dart',
        '.ex': 'Elixir',
        '.exs': 'Elixir',
        '.elm': 'Elm',
        '.clj': 'Clojure',
        '.cljs': 'ClojureScript',
        '.fs': 'F#',
        '.ml': 'OCaml',
        '.nim': 'Nim',
        '.zig': 'Zig',
        '.cr': 'Crystal',
        '.v': 'V',
        '.sol': 'Solidity',
    }

    if ext in ext_map:
        return ext_map[ext]

    # 未知扩展名，使用项目主语言
    if project_language:
        return project_language.capitalize()
    return ""
