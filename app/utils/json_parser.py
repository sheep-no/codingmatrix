"""
Robust JSON Parser - 容错 JSON 解析器

用于解析可能不完整或格式不规范的 JSON 字符串
"""
import json
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _find_balanced_end(text: str, start: int, opener: str, closer: str) -> int:
    """从 start 处的 opener 开始，返回与之配对的 closer 下标。

    扫描时跳过字符串字面量，避免把值里的括号当成结构括号。找不到配对返回 -1。
    """
    depth = 0
    quote_char = ''
    i = start
    while i < len(text):
        ch = text[i]
        if quote_char:
            if ch == '\\':
                i += 2
                continue
            if ch == quote_char:
                quote_char = ''
            i += 1
            continue
        if ch == '"' or ch == "'":
            quote_char = ch
            i += 1
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


class RobustJSONParser:
    """
    容错 JSON 解析器

    当 JSON 格式不完整或包含噪声时，尝试提取有效 JSON 数据
    """

    def __init__(self, strict_mode: bool = False):
        """
        初始化解析器

        Args:
            strict_mode: 是否使用严格模式
        """
        self.strict_mode = strict_mode

    def parse(self, text: str) -> Any:
        """
        解析文本为 JSON

        尝试多种策略:
        1. 直接 json.loads
        2. 提取 JSON 对象/数组
        3. 修复常见 JSON 错误

        Args:
            text: 要解析的文本

        Returns:
            解析后的 Python 对象

        Raises:
            ValueError: 无法解析时
        """
        if not text or not text.strip():
            raise ValueError("Empty input")

        # 策略 1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略 2: 提取 JSON 对象
        json_str = self._extract_json_object(text)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # 策略 3: 尝试修复常见错误
        fixed_text = self._fix_common_errors(text)
        try:
            return json.loads(fixed_text)
        except json.JSONDecodeError:
            pass

        # 策略 4: 提取数组
        array_str = self._extract_json_array(text)
        if array_str:
            try:
                return json.loads(array_str)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Cannot parse JSON: {text[:100]}")

    def _extract_json_object(self, text: str) -> Optional[str]:
        """从文本中提取第一个完整 JSON 对象"""
        start = text.find('{')
        if start == -1:
            return None

        end = _find_balanced_end(text, start, '{', '}')
        if end != -1:
            candidate = text[start:end + 1]
            if self._looks_like_json(candidate):
                return candidate
        return None

    def _extract_json_array(self, text: str) -> Optional[str]:
        """从文本中提取第一个完整 JSON 数组"""
        start = text.find('[')
        if start == -1:
            return None

        end = _find_balanced_end(text, start, '[', ']')
        if end != -1:
            candidate = text[start:end + 1]
            if self._looks_like_json_array(candidate):
                return candidate
        return None

    def _looks_like_json(self, text: str) -> bool:
        """检查文本是否看起来像 JSON 对象"""
        text = text.strip()
        if not text:
            return False
        starts_correctly = text.startswith('{')
        has_balanced = text.count('{') == text.count('}')
        return starts_correctly and has_balanced

    def _looks_like_json_array(self, text: str) -> bool:
        """检查文本是否看起来像 JSON 数组"""
        text = text.strip()
        return text.startswith('[') and text.endswith(']')

    def _fix_common_errors(self, text: str) -> str:
        """修复常见的 JSON 错误。

        所有修复只在字符串字面量之外生效。旧实现用全局正则替换，会把值里的
        撇号/冒号/`,}` 也当作语法错误处理，例如把 `"a,}b"` 改成 `"a}b"`，
        静默篡改合法数据。这里改为单遍扫描，同时跟踪当前是否处于字符串中。
        """
        text = text.replace('\ufeff', '')
        out = []
        i = 0
        length = len(text)
        quote_char = ''

        while i < length:
            ch = text[i]

            if quote_char:
                if ch == '\\' and i + 1 < length:
                    nxt = text[i + 1]
                    if quote_char == "'" and nxt == "'":
                        out.append("'")
                    else:
                        out.append(ch)
                        out.append(nxt)
                    i += 2
                    continue
                if ch == quote_char:
                    out.append('"')
                    quote_char = ''
                    i += 1
                    continue
                # 单引号字符串转成双引号字符串时，内部裸双引号需要转义
                if quote_char == "'" and ch == '"':
                    out.append('\\"')
                    i += 1
                    continue
                out.append(ch)
                i += 1
                continue

            if ch == '"' or ch == "'":
                quote_char = ch
                out.append('"')
                i += 1
                continue

            # 行注释
            if ch == '/' and i + 1 < length and text[i + 1] == '/':
                newline = text.find('\n', i)
                i = length if newline == -1 else newline + 1
                continue
            # 块注释
            if ch == '/' and i + 1 < length and text[i + 1] == '*':
                end = text.find('*/', i + 2)
                i = length if end == -1 else end + 2
                continue

            # 尾部逗号（对象/数组最后一个元素后的逗号）
            if ch == ',':
                lookahead = i + 1
                while lookahead < length and text[lookahead] in ' \t\r\n':
                    lookahead += 1
                if lookahead < length and text[lookahead] in '}]':
                    i += 1
                    continue

            # 无引号 key 补引号（仅当其后紧跟冒号）
            if ch.isalpha() or ch == '_':
                key_end = i
                while key_end < length and (text[key_end].isalnum() or text[key_end] == '_'):
                    key_end += 1
                lookahead = key_end
                while lookahead < length and text[lookahead] in ' \t\r\n':
                    lookahead += 1
                if lookahead < length and text[lookahead] == ':':
                    out.append('"')
                    out.append(text[i:key_end])
                    out.append('"')
                    i = key_end
                    continue

            out.append(ch)
            i += 1

        return ''.join(out)


def parse_json(text: str, default: Any = None) -> Any:
    """安全解析 JSON，失败时返回默认值"""
    try:
        parser = RobustJSONParser(strict_mode=False)
        return parser.parse(text)
    except (ValueError, TypeError, RuntimeError) as e:
        logger.debug(f"JSON parse failed: {e}")
        return default


def extract_json_from_llm(text: str) -> Optional[Any]:
    """
    从 LLM 响应中提取 JSON

    尝试顺序：
    1. 从 ```json 代码块中提取
    2. 直接解析整个文本
    3. 提取第一个 { 到最后一个 } 之间的内容

    Args:
        text: LLM 响应文本

    Returns:
        解析后的对象，失败返回 None
    """
    if not text:
        return None

    # 策略 1: 从代码块中提取
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 策略 2: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略 3: 提取第一个完整的 JSON 对象（跳过字符串内的括号）
    start = text.find('{')
    end = _find_balanced_end(text, start, '{', '}') if start != -1 else -1
    if end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # 策略 4: 使用容错解析器
    try:
        parser = RobustJSONParser(strict_mode=False)
        return parser.parse(text)
    except (ValueError, TypeError, RuntimeError):
        pass

    return None


def extract_code_from_markdown(text: str, language: Optional[str] = None) -> Optional[str]:
    """
    从 Markdown 文本中提取代码块

    Args:
        text: Markdown 文本
        language: 语言标识（可选）

    Returns:
        提取的代码，失败返回 None
    """
    if not text:
        return None

    if language:
        pattern = rf'```{language}\s*(.*?)\s*```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # 尝试任何代码块
    pattern = r'```(?:\w+)?\s*(.*?)\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()


__all__ = ['RobustJSONParser', 'parse_json', 'extract_json_from_llm', 'extract_code_from_markdown']
