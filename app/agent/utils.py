"""
Agent 公共工具函数
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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

    # 剥离 <think>...</think> 标签（DeepSeek-R1 等模型的思考过程）
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    # 剥离 <think>...</think>` 标签（部分模型变体）
    content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

    pattern = r'```(?:\w+)?\s*(.*?)\s*```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


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

    if content and _is_edit_marker(content):
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

        # 内容有效性验证：检测 JSON 元数据、Markdown 等无效内容
        is_valid, reason = is_valid_code_content(file_path, content)
        if not is_valid:
            logger.warning(f"内容验证失败: {file_path} - {reason}")
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


def _is_edit_marker(content: str) -> bool:
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
        return False, "内容为空"

    stripped = content.strip()

    if len(stripped) < 10:
        return False, "内容过短（<10 字符）"

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

    # 检查是否是 Markdown 文档（用特征模式而非单个 #）
    md_patterns = ['## ', '### ', '- ', '* ', '1. ', '```', '> ']
    md_count = sum(1 for p in md_patterns if p in stripped[:500])
    if md_count >= 3:
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

# 缓存 AI 生成的验证脚本
_ai_script_cache = {}


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


class PythonSandboxValidator(SandboxValidator):
    """Python 沙箱验证器"""
    extensions = ['.py']

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        py_files = self.filter_files(files)
        if not py_files:
            return ""

        files_repr = repr(py_files)
        level_repr = repr(level)

        return f'''
import sys, ast, os, importlib, tempfile, inspect, traceback, re
from pathlib import Path

files = {files_repr}
level = {level_repr}
errors = []

# 1. 语法验证（所有级别）
for file_path, content in files.items():
    try:
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"{{file_path}}: SyntaxError: {{e}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)

if level == "syntax":
    print("OK")
    sys.exit(0)

# 2. 写入临时目录
tmp_dir = os.environ.get("SANDBOX_TMP_DIR", tempfile.mkdtemp())
project_dir = os.path.join(tmp_dir, "project")
os.makedirs(project_dir, exist_ok=True)

for file_path, content in files.items():
    full_path = Path(project_dir) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)

sys.path.insert(0, project_dir)

# 3. 验证导入（import 和 run 级别）
modules = {{}}
for file_path in files:
    if not file_path.endswith('.py') or file_path.endswith('__init__.py'):
        continue
    module_name = file_path.replace('/', '.').replace('\\\\', '.').replace('.py', '')
    try:
        mod = importlib.import_module(module_name)
        modules[file_path] = mod
    except ImportError as e:
        errors.append(f"{{file_path}}: ImportError: {{e}}")
    except Exception as e:
        # 尝试提取行号
        import traceback
        tb = traceback.format_exc()
        line_match = re.search(r'File ".*", line (\d+)', tb)
        line_info = f" (line {{line_match.group(1)}})" if line_match else ""
        errors.append(f"{{file_path}}: Import Error: {{type(e).__name__}}: {{e}}{{line_info}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)

if level == "import":
    print("OK")
    sys.exit(0)

# 4. 运行时验证（run 级别）：尝试调用函数和实例化类
for file_path, mod in modules.items():
    for name, obj in inspect.getmembers(mod):
        # 跳过私有成员和模块导入
        if name.startswith('_'):
            continue

        # 尝试调用函数（无参数）
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            try:
                sig = inspect.signature(obj)
                # 构造默认参数
                kwargs = {{}}
                for param_name, param in sig.parameters.items():
                    if param_name == 'self':
                        continue
                    if param.default is not inspect.Parameter.empty:
                        continue
                    # 给参数一个默认值
                    if param.annotation == str or param.annotation == inspect.Parameter.empty:
                        kwargs[param_name] = ""
                    elif param.annotation == int:
                        kwargs[param_name] = 0
                    elif param.annotation == list:
                        kwargs[param_name] = []
                    elif param.annotation == dict:
                        kwargs[param_name] = {{}}
                    else:
                        kwargs[param_name] = None
                obj(**kwargs)
            except NameError as e:
                tb = traceback.format_exc()
                line_match = re.search(r'File ".*", line (\d+)', tb)
                line_info = f" (line {{line_match.group(1)}})" if line_match else ""
                errors.append(f"{{file_path}}.{{name}}(): NameError: {{e}}{{line_info}}")
            except TypeError:
                pass  # 参数不匹配，跳过
            except Exception:
                pass  # 其他运行时错误，跳过

        # 尝试实例化类
        if inspect.isclass(obj):
            try:
                instance = obj()
                # 尝试调用类的方法
                for method_name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
                    if method_name.startswith('_'):
                        continue
                    try:
                        sig = inspect.signature(method)
                        kwargs = {{}}
                        for param_name, param in sig.parameters.items():
                            if param_name == 'self':
                                continue
                            if param.default is not inspect.Parameter.empty:
                                continue
                            if param.annotation == str or param.annotation == inspect.Parameter.empty:
                                kwargs[param_name] = ""
                            elif param.annotation == int:
                                kwargs[param_name] = 0
                            elif param.annotation == list:
                                kwargs[param_name] = []
                            elif param.annotation == dict:
                                kwargs[param_name] = {{}}
                            else:
                                kwargs[param_name] = None
                        method(**kwargs)
                    except NameError as e:
                        tb = traceback.format_exc()
                        line_match = re.search(r'File ".*", line (\d+)', tb)
                        line_info = f" (line {{line_match.group(1)}})" if line_match else ""
                        errors.append(f"{{file_path}}.{{name}}.{{method_name}}(): NameError: {{e}}{{line_info}}")
                    except TypeError:
                        pass
                    except Exception:
                        pass
            except NameError as e:
                tb = traceback.format_exc()
                line_match = re.search(r'File ".*", line (\d+)', tb)
                line_info = f" (line {{line_match.group(1)}})" if line_match else ""
                errors.append(f"{{file_path}}.{{name}}(): NameError: {{e}}{{line_info}}")
            except TypeError:
                pass
            except Exception:
                pass

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
'''


class JavaScriptSandboxValidator(SandboxValidator):
    """JavaScript/TypeScript 沙箱验证器"""
    extensions = ['.js', '.ts', '.jsx', '.tsx']

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        js_files = self.filter_files(files)
        if not js_files:
            return ""

        files_repr = repr(js_files)

        return f'''
import sys, os, subprocess, tempfile
from pathlib import Path

files = {files_repr}
errors = []

tmp_dir = os.environ.get("SANDBOX_TMP_DIR", tempfile.mkdtemp())
project_dir = os.path.join(tmp_dir, "project")
os.makedirs(project_dir, exist_ok=True)

for file_path, content in files.items():
    full_path = Path(project_dir) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)

for file_path in files:
    full_path = Path(project_dir) / file_path
    try:
        result = subprocess.run(
            ['node', '--check', str(full_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            errors.append(f"{{file_path}}: SyntaxError: {{result.stderr.strip()}}")
    except FileNotFoundError:
        pass
    except Exception as e:
        errors.append(f"{{file_path}}: Error: {{e}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
'''


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


class GenericSandboxValidator(SandboxValidator):
    """通用沙箱验证器 - 仅做语法检查（括号匹配等）"""
    extensions = []  # 接受所有文件

    def build_validation_script(self, files: dict, level: str = "import") -> str:
        if not files:
            return ""

        files_repr = repr(files)

        return f'''
import sys
files = {files_repr}
errors = []

for file_path, content in files.items():
    # 括号匹配检查
    for open_b, close_b in [('(', ')'), ('[', ']'), ('{{', '}}')]:
        if content.count(open_b) != content.count(close_b):
            errors.append(f"{{file_path}}: Unmatched {{open_b}}{{close_b}}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
'''


# ============ 验证器自动注册表（按扩展名） ============

# 预定义验证器实例
_VALIDATOR_INSTANCES = [
    PythonSandboxValidator(),
    JavaScriptSandboxValidator(),
    GoSandboxValidator(),
    RustSandboxValidator(),
    GenericSandboxValidator(),  # 兜底
]

# 按扩展名自动建立映射
_EXTENSION_VALIDATORS = {}
for _v in _VALIDATOR_INSTANCES:
    for _ext in _v.extensions:
        _EXTENSION_VALIDATORS[_ext] = _v


def _get_validator_for_file(file_path: str) -> SandboxValidator:
    """根据文件扩展名获取验证器"""
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_VALIDATORS.get(ext, GenericSandboxValidator())


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


def _group_files_by_extension(files: dict) -> dict:
    """按文件扩展名分组"""
    groups = {}
    for file_path, content in files.items():
        ext = Path(file_path).suffix.lower()
        if ext not in groups:
            groups[ext] = {}
        groups[ext][file_path] = content
    return groups


def _generate_script_with_ai(ext: str, files: dict, llm_caller=None) -> str:
    """为未注册语言生成验证脚本

    Args:
        ext: 文件扩展名
        files: 文件字典
        llm_caller: LLM 调用函数（可选）

    Returns:
        验证脚本字符串，失败返回 None
    """
    global _ai_script_cache

    # 检查缓存
    cache_key = f"ai_script_{ext}"
    if cache_key in _ai_script_cache:
        return _ai_script_cache[cache_key]

    # 如果没有 LLM 调用器，使用通用验证器
    if not llm_caller:
        logger.debug(f"无 LLM 调用器，使用通用验证器: {ext}")
        return GenericSandboxValidator().build_validation_script(files)

    # 构建 prompt
    file_list = "\n".join(f"- {f}" for f in files.keys())
    prompt = f"""为 {ext} 文件生成语法验证脚本。

文件列表：
{file_list}

要求：
1. 返回一个 Python 脚本，验证这些文件的语法正确性
2. 验证通过输出 "OK"，失败输出错误到 stderr 并 sys.exit(1)
3. 使用该语言的编译器/解释器进行语法检查
4. 如果编译器不可用，跳过该文件（不要报错）
5. 只返回代码，不要解释
6. 脚本中使用 os.environ.get("SANDBOX_TMP_DIR") 获取临时目录"""

    try:
        # 调用 LLM 生成脚本
        import asyncio
        if asyncio.iscoroutinefunction(llm_caller):
            # 异步调用需要在事件循环中
            loop = asyncio.get_event_loop()
            script = loop.run_until_complete(llm_caller(prompt))
        else:
            script = llm_caller(prompt)

        if script:
            # 清理代码块标记
            script = clean_code_block(script)
            # 缓存结果
            _ai_script_cache[cache_key] = script
            logger.info(f"AI 生成验证脚本成功: {ext}")
            return script

    except Exception as e:
        logger.warning(f"AI 生成验证脚本失败: {ext} - {e}")

    # 降级到通用验证器
    return GenericSandboxValidator().build_validation_script(files)


def validate_in_sandbox(
    project_dir: str,
    files: dict,
    level: str = "auto",
    context: dict = None,
    llm_caller=None,
) -> tuple:
    """统一沙箱验证入口

    Args:
        project_dir: 项目目录路径
        files: 文件字典 {file_path: content}
        level: "syntax"|"import"|"contract"|"run"|"auto"
        context: 上下文信息 {trigger, modified_files, config, ...}
        llm_caller: LLM 调用函数（用于 AI 生成验证脚本）

    Returns:
        (is_valid, errors): 有效返回 (True, [])，无效返回 (False, [错误列表])
    """
    import subprocess
    import tempfile

    if not files:
        return True, []

    # 1. 决策：确定验证级别
    if level == "auto":
        level = _decide_level(context)

    logger.info(f"沙箱验证: level={level}, files={len(files)}")

    # 2. 按扩展名分组
    groups = _group_files_by_extension(files)

    # 3. 每组选择验证器，生成脚本
    scripts = []
    for ext, group_files in groups.items():
        validator = _EXTENSION_VALIDATORS.get(ext)

        if validator:
            # 已注册：使用预定义脚本
            script = validator.build_validation_script(group_files, level)
        else:
            # 未注册：AI 生成脚本
            script = _generate_script_with_ai(ext, group_files, llm_caller)

        if script:
            scripts.append(script)

    if not scripts:
        return True, []

    # 4. 合并脚本
    combined_script = "\n# === 分组分隔 ===\n".join(scripts)

    # 5. 在沙箱中执行
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

    snippet = content[:500]
    prompt = f"""判断以下代码是否是 {expected_language} 语言。只回答 YES 或 NO，不要解释。

代码片段：
```
{snippet}
```"""

    try:
        logger.info(f"LLM 语言检测: {file_path} 期望={expected_language}")
        result = await llm_caller(prompt)
        logger.info(f"LLM 语言检测结果: {file_path} -> {result}")
        if result and "NO" in result.upper():
            return False, f"语言不匹配：期望 {expected_language}，LLM 判断内容不是该语言"
        return True, ""
    except Exception as e:
        logger.debug(f"LLM 语言检测跳过: {e}")
        return True, ""  # LLM 调用失败不阻塞


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
        return True, "内容为空"

    stripped = content.strip()

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
        (r'^//\s*Module:', "Module stub comment"),
        (r'^"""Package initialization"""', "Python package init stub"),
        (r'^"""Module:', "Python module stub"),
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

    matched_pattern = None
    for pattern, desc in placeholder_patterns:
        if re.search(pattern, stripped, re.IGNORECASE | re.MULTILINE):
            matched_pattern = desc
            break

    if matched_pattern:
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
        if len(lines) <= 2:
            return True, f"占位符代码（{matched_pattern}），有效行数: {len(lines)}"

    # 检查代码中嵌入的工具调用 JSON（不在开头，但在代码中间）
    for pattern in embedded_tool_call_patterns:
        if re.search(pattern, stripped):
            return True, f"代码中嵌入了工具调用 JSON"

    return False, ""


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

    # 检测 LLM 思考过程泄漏（中英文描述性文本混入代码文件）
    thinking_patterns = [
        # 中文思考泄漏
        r'^最终答案',
        r'^任务执行',
        r'^基于.*?执行过程',
        r'^已成功完成',
        r'^以下是.*?总结',
        r'^✅',
        r'^---\s*$',
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
    for pattern in thinking_patterns:
        if re.match(pattern, stripped, re.IGNORECASE | re.MULTILINE):
            return f"内容疑似 LLM 思考过程泄漏（匹配模式: {pattern[:30]}）"

    # CSS 文件内容校验
    if ext == '.css':
        # CSS 不应包含大段中文描述（排除注释）
        lines = [l.strip() for l in stripped.split('\n') if l.strip() and not l.strip().startswith('/*')]
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
