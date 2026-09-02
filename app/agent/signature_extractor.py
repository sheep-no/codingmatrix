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

# 签名提取正则（与 specialist_base._SYMBOL_PATTERNS 一致）
SIGNATURE_PATTERNS = {
    ".py": {
        "function": re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),
        "class": re.compile(r"^\s*class\s+(\w+)(?:\s*\([^)]*\))?\s*:"),
    },
    ".js": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?class\s+(\w+)"),
    },
    ".ts": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[<(]|(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
    },
    ".vue": {
        "function": re.compile(r"(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class": re.compile(r"class\s+(\w+)"),
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
            current_class = None
            class_indent = 0
            collecting_class_body = False

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                    continue

                # 计算当前行的缩进
                indent = len(line) - len(line.lstrip())

                cls_match = patterns["class"].search(line)
                if cls_match:
                    name = next(g for g in cls_match.groups() if g is not None)
                    current_class = name
                    class_indent = indent
                    collecting_class_body = True
                    result_parts.append(stripped[:200])
                    continue

                # 在类体内：收集字段定义和方法签名
                if collecting_class_body and indent > class_indent:
                    # 方法签名行
                    fn_match = patterns["function"].search(line)
                    if fn_match:
                        paren_idx = line.find('(')
                        if paren_idx >= 0:
                            depth, end = 0, paren_idx
                            for j in range(paren_idx, min(paren_idx + 500, len(line))):
                                if line[j] == '(':
                                    depth += 1
                                elif line[j] == ')':
                                    depth -= 1
                                    if depth == 0:
                                        end = j + 1
                                        break
                            sig = stripped[:end - len(line) + len(stripped) + 1]
                        else:
                            sig = stripped
                        result_parts.append(f"  {sig[:200]}")
                        continue

                    # 字段定义行（Python: name: Type = default, JS: name = value）
                    # 匹配 "identifier: type" 或 "identifier = value" 模式
                    if _is_class_field(stripped, ext):
                        result_parts.append(f"  {stripped[:200]}")
                        continue

                    # 装饰器行（@property, @classmethod 等）
                    if stripped.startswith('@'):
                        result_parts.append(f"  {stripped[:200]}")
                        continue

                    # 跳过方法体内的其他行（pass, return, if 等）
                    continue

                # 遇到新的顶层定义，退出类体收集模式
                if collecting_class_body and indent <= class_indent:
                    collecting_class_body = False
                    current_class = None

                # 顶层函数
                fn_match = patterns["function"].search(line)
                if fn_match and not collecting_class_body:
                    paren_idx = line.find('(')
                    if paren_idx >= 0:
                        depth, end = 0, paren_idx
                        for j in range(paren_idx, min(paren_idx + 500, len(line))):
                            if line[j] == '(':
                                depth += 1
                            elif line[j] == ')':
                                depth -= 1
                                if depth == 0:
                                    end = j + 1
                                    break
                        sig = stripped[:end - len(line) + len(stripped) + 1]
                    else:
                        sig = stripped
                    result_parts.append(sig[:200])

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
                imports.append(stripped[:200])
            elif _GENERIC_DEF.search(line):
                sig = stripped
                for sep in ['{', ':']:
                    idx = sig.find(sep)
                    if idx > 0:
                        sig = sig[:idx].rstrip()
                        break
                defs.append(sig[:200])

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
        # JS/TS 字段: name = value 或 name: type (in interface)
        if '=' in stripped:
            before_eq = stripped.split('=')[0].strip()
            if before_eq and before_eq.replace('_', '').isalnum():
                return True
        # TypeScript 接口字段: name: type;
        if ':' in stripped and stripped.endswith(';'):
            before_colon = stripped.split(':')[0].strip()
            if before_colon and before_colon.replace('_', '').isalnum():
                return True
        return False

    # 其他语言：尝试通用匹配
    if ':' in stripped:
        before_colon = stripped.split(':')[0].strip()
        if before_colon and before_colon.replace('_', '').isalnum() and len(before_colon) < 50:
            return True
    return False
