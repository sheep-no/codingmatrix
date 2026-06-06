"""
统一 JSON 解析层

替代所有文件中自行实现的 JSON 解析逻辑。
5 层解析链：thinking清理 → 直接解析 → 格式修复 → 截断修复 → json_repair库兜底

用法：
    from app.agent.json_parser import safe_parse_json, parse_tool_call

    data = safe_parse_json(llm_output)
    tool = parse_tool_call(llm_output)
"""

import json
import re
import logging
from typing import Dict, Optional, Any, Union

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

logger = logging.getLogger(__name__)

_parser_instance = None


def _get_parser():
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = _JsonParser()
    return _parser_instance


def safe_parse_json(text: str) -> Union[Dict, list]:
    """安全解析 JSON，5 层解析链

    Args:
        text: LLM 原始输出

    Returns:
        解析后的 dict 或 list

    Raises:
        ValueError: 无法解析
    """
    return _get_parser().safe_parse_json(text)


def parse_tool_call(content: str) -> Optional[Dict]:
    """从 LLM 回复中解析工具调用

    格式: {"tool": "tool_name", "params": {...}}

    Returns:
        工具调用 dict 或 None
    """
    return _get_parser().parse_tool_call(content)


def extract_json_field(text: str, field: str, default=None):
    """从 LLM 输出中提取指定 JSON 字段

    Args:
        text: LLM 原始输出
        field: 字段名
        default: 默认值

    Returns:
        字段值或默认值
    """
    try:
        data = safe_parse_json(text)
        if isinstance(data, dict):
            return data.get(field, default)
    except (ValueError, Exception):
        pass
    return default


class _JsonParser:
    """JSON 解析器（内部实现）"""

    def safe_parse_json(self, text: str) -> Union[Dict, list]:
        text = text.strip()
        if not text:
            raise ValueError("空文本无法解析")

        # 层 1: 移除 thinking tags + 提取代码块
        text = self._clean_thinking(text)
        text = self._extract_code_block(text)

        # 层 2: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 层 3: 提取 { 到 } + 常见格式修复
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            fixed = self._apply_common_fixes(json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        # 层 3b: 提取 [ 到 ]（数组格式）
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            fixed = self._apply_common_fixes(json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        # 层 4: 状态机截断修复
        fixed = self._fix_truncation(text)
        if fixed is not None:
            return fixed

        # 层 5: json_repair 库兜底
        if HAS_JSON_REPAIR:
            fixed = self._fix_json_repair(text)
            if fixed is not None:
                return fixed

        raise ValueError(f"无法解析 JSON: {text[:200]}...")

    def parse_tool_call(self, content: str) -> Optional[Dict]:
        """解析工具调用 JSON"""
        cleaned = self._clean_thinking(content).strip()

        # 策略 1: 代码块中的 JSON
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # 策略 2: 正则匹配完整 tool 调用
        brace_match = re.search(
            r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:\s*\{[^}]*\}\s*\}',
            cleaned
        )
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # 策略 3: 状态机匹配嵌套 JSON
        tool_match = re.search(r'\{\s*"tool"\s*:\s*"([^"]+)"', cleaned)
        if tool_match:
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

    @staticmethod
    def _clean_thinking(text: str) -> str:
        """移除 thinking tags"""
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    @staticmethod
    def _extract_code_block(text: str) -> str:
        """提取 markdown 代码块内容"""
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        return match.group(1).strip() if match else text

    def _apply_common_fixes(self, text: str) -> str:
        """常见格式修复"""
        text = self._remove_line_comments(text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        text = self._fix_single_quotes(text)
        text = self._fix_unescaped_newlines(text)
        text = re.sub(r',\s*([\]}])', r'\1', text)
        return text

    @staticmethod
    def _remove_line_comments(text: str) -> str:
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            in_string = False
            quote_char = None
            i = 0
            while i < len(line):
                char = line[i]
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        quote_char = char
                    elif char == quote_char:
                        in_string = False
                elif char == '/' and not in_string and i + 1 < len(line) and line[i + 1] == '/':
                    line = line[:i].rstrip()
                    break
                i += 1
            cleaned.append(line)
        return '\n'.join(cleaned)

    @staticmethod
    def _fix_single_quotes(text: str) -> str:
        result = []
        in_string = False
        quote_char = None
        i = 0
        while i < len(text):
            char = text[i]
            if char in '"\'':
                if not in_string:
                    in_string = True
                    quote_char = char
                    result.append('"' if char == "'" else char)
                elif char == quote_char:
                    in_string = False
                    result.append('"' if char == "'" else char)
                else:
                    result.append(char)
            elif char == '\\' and in_string and i + 1 < len(text):
                result.append(char)
                i += 1
                result.append(text[i])
            else:
                result.append(char)
            i += 1
        return ''.join(result)

    @staticmethod
    def _fix_unescaped_newlines(text: str) -> str:
        result = []
        in_string = False
        quote_char = None
        i = 0
        while i < len(text):
            char = text[i]
            if char in '"\'':
                if not in_string:
                    in_string = True
                    quote_char = char
                    result.append(char)
                elif char == quote_char:
                    in_string = False
                    result.append(char)
                else:
                    result.append(char)
            elif char == '\n' and in_string:
                result.append('\\n')
            elif char == '\\' and in_string and i + 1 < len(text):
                result.append(char)
                i += 1
                result.append(text[i])
            else:
                result.append(char)
            i += 1
        return ''.join(result)

    def _fix_truncation(self, text: str) -> Optional[Any]:
        """状态机截断修复"""
        try:
            text = self._remove_line_comments(text).rstrip()
            if text.endswith(','):
                text = text[:-1]

            stack = []
            in_string = False
            escape = False
            quote_char = None

            for char in text:
                if in_string:
                    if escape:
                        escape = False
                    elif char == '\\':
                        escape = True
                    elif char == quote_char:
                        in_string = False
                else:
                    if char in '"\'':
                        in_string = True
                        quote_char = char
                    elif char in '{[':
                        stack.append('}' if char == '{' else ']')
                    elif char in '}]':
                        if stack and stack[-1] == char:
                            stack.pop()

            if in_string:
                text += quote_char

            if text.rstrip().endswith(':'):
                text += ' null'

            if stack:
                text += ''.join(reversed(stack))

            return json.loads(text)
        except Exception as e:
            logger.debug(f"JSON 解析失败：{e}")
            return None

    @staticmethod
    def _fix_json_repair(text: str) -> Optional[Any]:
        """json_repair 库兜底"""
        try:
            result = json_repair.loads(text)
            if isinstance(result, (dict, list)):
                return result
            return None
        except Exception as e:
            logger.debug(f"深度 JSON 修复失败：{e}")
            return None
