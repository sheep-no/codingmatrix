"""
签名提取器

从源代码文件中提取函数/类签名，用于依赖上下文注入。
支持 8 种语言 + 冷门语言通用兜底。
"""

import re
import logging
import ast
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_context_budget(context_length: int) -> int:
    """根据模型上下文窗口计算注入预算（字节）

    小上下文 (<=32K)：取 5%，下限 3000，上限 6000
    中上下文 (32K-64K)：取 4%，下限 5000，上限 10000
    大上下文 (>64K)：取 3%，下限 8000，上限 15000
    """
    if context_length <= 32768:
        return max(3000, min(6000, int(context_length * 0.05)))
    elif context_length <= 65536:
        return max(5000, min(10000, int(context_length * 0.04)))
    else:
        return max(8000, min(15000, int(context_length * 0.03)))

# JS/TS 类体方法：允许访问/静态等修饰符、get/set 访问器与泛型，
# 并用负向前瞻排除方法体内可能出现的控制流/调用关键字。
_JS_METHOD_MODIFIERS = (
    r"(?:(?:public|private|protected|static|async|readonly|abstract|override|declare)\s+)*"
)
_JS_METHOD_NAME = (
    r"(?!(?:if|for|while|switch|catch|return|function|typeof|new|super|await"
    r"|throw|do|else|case|default|delete|void|yield)\b)"
    r"([A-Za-z_$][\w$]*)"
)
_JS_METHOD_PATTERN = re.compile(
    rf"^\s*{_JS_METHOD_MODIFIERS}(?:(?:get|set)\s+)?{_JS_METHOD_NAME}"
    r"\s*(?:<[^>]*>)?\s*\("
)

_SIGNATURE_LIMIT = 200
_TRUNCATION_MARKER = " ...[truncated]"


def _clip_signature(text: str, limit: int = _SIGNATURE_LIMIT) -> str:
    """截断超长签名并附可见标记，下游可感知信息被截断（SE7）。"""
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_MARKER


def _line_signature(line: str) -> str:
    """截取单行签名：从行首到闭括号，含同行返回类型，最多 200 字符。

    原实现用行内括号深度定位后按 ``end - len(line) + len(stripped) + 1``
    换算，会多带闭括号后的一个字符（如 ``run():`` 而非 ``run(): void``），
    且返回类型被丢弃。这里直接在 ``line`` 上取值，并在闭括号后截到 ``{``/``;``
    以保留同行返回类型。
    """
    stripped = line.strip()
    paren_idx = line.find('(')
    if paren_idx < 0:
        return _clip_signature(stripped)

    depth = 0
    end = None
    for j in range(paren_idx, min(paren_idx + 500, len(line))):
        if line[j] == '(':
            depth += 1
        elif line[j] == ')':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        return _clip_signature(stripped)

    sig = line[len(line) - len(line.lstrip()):end]
    tail = line[end:]
    cut = len(tail)
    for sep in ('{', ';'):
        idx = tail.find(sep)
        if idx != -1:
            cut = min(cut, idx)
    tail = tail[:cut].strip()
    if tail:
        sig = f"{sig}{'' if tail.startswith(':') else ' '}{tail}"
    return _clip_signature(sig)


def _joined_signature_line(lines: list, start: int, max_lines: int = 50) -> tuple:
    """把跨行的函数/方法签名合并为单行文本，返回 (text, consumed)。

    首行括号已闭合时原样返回。否则向后拼接后续行（最多 ``max_lines`` 行）
    直到括号深度归零，避免多行参数签名被截成 ``function foo(``（SE5 的
    JS/TS 剩余场景）。仅按 ``(``/``)`` 计数做启发式，与 ``_line_signature``
    的括号匹配保持一致。
    """
    first = lines[start]
    depth = first.count('(') - first.count(')')
    if depth <= 0:
        return first, 1

    parts = [first.strip()]
    j = start + 1
    while j < len(lines) and (j - start) < max_lines and depth > 0:
        part = lines[j].strip()
        parts.append(part)
        depth += part.count('(') - part.count(')')
        j += 1
    return ' '.join(parts), j - start


# 签名提取正则（与 specialist_base._SYMBOL_PATTERNS 一致）
SIGNATURE_PATTERNS = {
    ".py": {
        "function": re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),
        "class": re.compile(r"^\s*class\s+(\w+)(?:\s*\([^)]*\))?\s*:"),
    },
    ".js": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?class\s+(\w+)"),
        "method": _JS_METHOD_PATTERN,
    },
    ".ts": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[<(]|(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
        "method": _JS_METHOD_PATTERN,
    },
    ".vue": {
        "function": re.compile(r"(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"class\s+(\w+)"),
        "method": _JS_METHOD_PATTERN,
    },
    ".go": {
        "function": re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\("),
        "class": re.compile(r"^type\s+(\w+)\s+struct\s*\{"),
    },
    ".java": {
        "function": re.compile(r"(?:public|private|protected|static|\s)+\s+\w+\s+(\w+)\s*\("),
        "class": re.compile(r"(?:public|private|protected|\s)*\s*(?:class|interface|enum)\s+(\w+)"),
    },
    ".rs": {
        "function": re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
        "class": re.compile(r"(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?enum\s+(\w+)|(?:pub\s+)?trait\s+(\w+)"),
    },
    ".rb": {
        "function": re.compile(r"^\s*def\s+(\w+)"),
        "class": re.compile(r"^\s*class\s+(\w+)|^\s*module\s+(\w+)"),
    },
}

# 冷门语言兜底：匹配常见的 import 和定义模式
_GENERIC_IMPORT = re.compile(r"^\s*(?:import |from |#include |using |use |require |package\s+\w+)", re.IGNORECASE)
_GENERIC_DEF = re.compile(r"^\s*(?:(?:pub\s+)?(?:async\s+)?(?:fn|func|function|def|class|struct|enum|trait|interface|type|module)\s+\w+)", re.IGNORECASE)


def extract_signatures(file_path: str, content: str) -> Optional[str]:
    """从文件内容中提取函数/类签名及类字段定义，不包含函数体。

    提取内容包括：
    - 类定义行（class Foo(BaseModel):）
    - 类的字段定义（amount: float, category: str）
    - 类的方法签名（def get_total(self):）
    - 顶层函数签名

    返回格式化的签名文本，失败时返回 None（调用方退化为截断原文）。
    """
    try:
        ext = Path(file_path).suffix.lower()
        if ext in (".py", ".pyi"):
            python_signatures = _extract_python_signatures(content)
            if python_signatures:
                return python_signatures
        patterns = SIGNATURE_PATTERNS.get(ext)
        if patterns is None:
            fallback = {".jsx": ".js", ".tsx": ".ts"}.get(ext, ext)
            patterns = SIGNATURE_PATTERNS.get(fallback)

        lines = content.split('\n')

        # 有精确正则时：提取类签名 + 字段 + 方法签名
        if patterns:
            result_parts = []
            # 类体用缩进栈跟踪，支持嵌套类：进入类时入栈，缩进回到某个类的
            # 同级或更浅时出栈，避免嵌套类覆盖外层类的缩进状态（SE6）。
            class_indents = []
            method_body_indent = None
            skip_until = -1

            for idx, line in enumerate(lines):
                # 多行签名合并时后续行已并入签名，跳过，避免被当作字段/方法重复收集
                if idx <= skip_until:
                    continue
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                    continue

                # 计算当前行的缩进
                indent = len(line) - len(line.lstrip())

                # 先按缩进收敛类栈：缩进 <= 栈顶说明已离开该层类体
                while class_indents and indent <= class_indents[-1]:
                    class_indents.pop()
                    method_body_indent = None

                cls_match = patterns["class"].search(line)
                if cls_match:
                    class_indents.append(indent)
                    method_body_indent = None
                    result_parts.append(_clip_signature(stripped))
                    continue

                # 在类体内：收集字段定义和方法签名
                if class_indents and indent > class_indents[-1]:
                    # 跳过方法体：方法签名行之后的更深缩进行属于函数体，
                    # 其内的函数调用/局部变量不应被当作方法或字段。
                    if method_body_indent is not None:
                        if indent > method_body_indent:
                            continue
                        method_body_indent = None

                    # 方法签名行
                    fn_match = patterns.get("method", patterns["function"]).search(line)
                    if fn_match:
                        sig_src, span = _joined_signature_line(lines, idx)
                        result_parts.append(f"  {_line_signature(sig_src)}")
                        method_body_indent = indent
                        skip_until = idx + span - 1
                        continue

                    # 字段定义行（Python: name: Type = default, JS: name = value）
                    # 匹配 "identifier: type" 或 "identifier = value" 模式
                    if _is_class_field(stripped, ext):
                        result_parts.append(f"  {_clip_signature(stripped)}")
                        continue

                    # 装饰器行（@property, @classmethod 等）
                    if stripped.startswith('@'):
                        result_parts.append(f"  {_clip_signature(stripped)}")
                        continue

                    # 跳过方法体内的其他行（pass, return, if 等）
                    continue

                # 顶层函数
                fn_match = patterns["function"].search(line)
                if fn_match and not class_indents:
                    sig_src, span = _joined_signature_line(lines, idx)
                    result_parts.append(_line_signature(sig_src))
                    skip_until = idx + span - 1

            if result_parts:
                return '\n'.join(result_parts)

        # 冷门语言兜底：import 行 + 看起来像定义的行
        imports = []
        defs = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
            if _GENERIC_IMPORT.search(line):
                imports.append(_clip_signature(stripped))
            elif _GENERIC_DEF.search(line):
                sig = stripped
                for sep in ['{', ':']:
                    idx = sig.find(sep)
                    if idx > 0:
                        sig = sig[:idx].rstrip()
                        break
                defs.append(_clip_signature(sig))

        if imports or defs:
            parts = imports[:30] + defs[:50]
            return '\n'.join(parts)

        return None
    except Exception as e:
        logger.debug(f"签名提取失败：{e}")
        return None


def _extract_python_signatures(content: str) -> Optional[str]:
    """使用 AST 提取完整 Python 签名，保留返回类型和类字段。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    result_parts = []

    def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        arguments = ast.unparse(node.args)
        return_annotation = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"{prefix} {node.name}({arguments}){return_annotation}:"

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result_parts.append(function_signature(node))
        elif isinstance(node, ast.ClassDef):
            bases = f"({', '.join(ast.unparse(base) for base in node.bases)})" if node.bases else ""
            result_parts.append(f"class {node.name}{bases}:")
            for member in node.body:
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                    annotation = ast.unparse(member.annotation)
                    result_parts.append(f"  {member.target.id}: {annotation}")
                elif isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result_parts.append(f"  {function_signature(member)}")

    return "\n".join(result_parts) or None


def _is_class_field(stripped: str, ext: str) -> bool:
    """判断是否为类字段定义行"""
    # 跳过空行、注释、装饰器、pass、return 等
    if not stripped or stripped.startswith('#') or stripped.startswith('//'):
        return False
    if stripped.startswith('@') or stripped in ('pass', '...', 'continue', 'break'):
        return False
    # 跳过控制流语句
    if stripped.startswith(('if ', 'for ', 'while ', 'try:', 'except', 'finally:', 'elif ', 'else:', 'return ', 'raise ', 'yield ', 'with ', 'assert ', 'print(')):
        return False

    if ext in ('.py', '.pyi'):
        # Python 字段定义: name: Type 或 name: Type = value
        # 排除 import、from、def、class 等
        if stripped.startswith(('import ', 'from ', 'def ', 'class ', 'async def ', 'async def ')):
            return False
        # 匹配 "identifier: " 模式
        if ':' in stripped:
            before_colon = stripped.split(':')[0].strip()
            # 字段名应该是简单的标识符（可能含下划线）
            if before_colon and before_colon.replace('_', '').replace('[', '').replace(']', '').isalnum():
                # 排除 dict 字面量和 type alias
                after_colon = stripped.split(':', 1)[1].strip() if ':' in stripped else ''
                if after_colon and not after_colon.startswith(('=', '(', '{', '[')):
                    return True
        return False

    if ext in ('.js', '.ts', '.jsx', '.tsx', '.vue'):
        # 去掉访问/静态等修饰符前缀，使 `private name: string;` 也能识别为字段
        rest = stripped
        while True:
            parts = rest.split(None, 1)
            if len(parts) == 2 and parts[0] in (
                'public', 'private', 'protected', 'readonly',
                'static', 'declare', 'abstract', 'override', 'async',
            ):
                rest = parts[1]
            else:
                break
        # JS/TS 字段: name = value 或 name: type (in interface)
        if '=' in rest:
            before_eq = rest.split('=')[0].strip()
            if before_eq and before_eq.replace('_', '').isalnum():
                return True
        # TypeScript 接口字段: name: type;
        if ':' in rest and rest.endswith(';'):
            before_colon = rest.split(':')[0].strip()
            if before_colon and before_colon.replace('_', '').isalnum():
                return True
        return False

    # 其他语言：尝试通用匹配
    if ':' in stripped:
        before_colon = stripped.split(':')[0].strip()
        if before_colon and before_colon.replace('_', '').isalnum() and len(before_colon) < 50:
            return True
    return False
