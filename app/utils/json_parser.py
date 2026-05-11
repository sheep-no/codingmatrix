"""
Robust JSON Parser - 容错 JSON 解析器

用于解析可能不完整或格式不规范的 JSON 字符串
"""
import json
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
        """从文本中提取 JSON 对象"""
        start = text.find('{')
        end = text.rfind('}')

        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            if self._looks_like_json(candidate):
                return candidate
        return None

    def _extract_json_array(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 数组"""
        start = text.find('[')
        end = text.rfind(']')

        if start != -1 and end != -1 and end > start:
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
        """修复常见的 JSON 错误"""
        text = text.replace('\ufeff', '')
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        text = re.sub(r"'([^']*)'", r'"\1"', text)
        text = re.sub(r'//[^\n]*\n', '\n', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        text = re.sub(r'(\s)([a-zA-Z_][a-zA-Z0-9_]*)(\s*):', r'\1"\2"\3:', text)
        return text


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

    # 策略 3: 提取第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
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
