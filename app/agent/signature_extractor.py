"""
签名提取器

从源代码文件中提取函数/类签名，用于依赖上下文注入。
支持 8 种语言 + 冷门语言通用兜底。
"""

import re
from pathlib import Path
from typing import Optional


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
        "function": re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\("),
        "class": re.compile(r"^class\s+(\w+)(?:\s*\([^)]*\))?\s*:"),
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
    """从文件内容中提取函数/类签名，不包含函数体。

    返回格式化的签名文本，失败时返回 None（调用方退化为截断原文）。
    """
    try:
        ext = Path(file_path).suffix.lower()
        patterns = SIGNATURE_PATTERNS.get(ext)
        if patterns is None:
            fallback = {".jsx": ".js", ".tsx": ".ts"}.get(ext, ext)
            patterns = SIGNATURE_PATTERNS.get(fallback)

        lines = content.split('\n')

        # 有精确正则时：提取类和函数签名
        if patterns:
            result_parts = []
            current_class = None

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                    continue

                cls_match = patterns["class"].search(line)
                if cls_match:
                    name = next(g for g in cls_match.groups() if g is not None)
                    current_class = name
                    result_parts.append(stripped[:200])
                    continue

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
                    result_parts.append(f"  {sig[:200]}" if current_class else sig[:200])

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
