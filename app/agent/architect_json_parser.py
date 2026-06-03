"""
Architect JSON 解析器

处理 LLM 输出的 JSON 格式问题，包括：
- 移除 thinking tags
- 提取代码块
- 修复常见 JSON 格式错误
- 修复复杂 JSON 问题
- 修复缺少闭合括号
"""

import json
import re
import tempfile
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ArchitectJsonParser:
    """Architect JSON 解析器"""

    def safe_parse_json(self, text: str) -> Dict:
        """
        安全解析 JSON，处理各种格式问题

        Args:
            text: 原始文本

        Returns:
            解析后的 JSON 字典

        Raises:
            ValueError: 无法解析 JSON
        """
        text = text.strip()

        # 1. 移除 thinking tags（深度思考模型输出）
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        # 2. 提取 ```json 或 ``` 代码块
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()

        # 3. 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 4. 查找第一个 { 和最后一个 } 之间的内容
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # 5. 尝试修复常见 JSON 问题
            fixed = self._fix_common_json_issues(json_str)
            if fixed:
                return fixed

        # 6. 尝试更激进的修复（处理嵌套对象、多 JSON 块）
        fixed = self._fix_complex_json_issues(text)
        if fixed:
            return fixed

        # 7. 尝试修复缺少闭合括号的情况
        fixed = self._fix_missing_closing_braces(text)
        if fixed:
            return fixed

        # 8. 最终兜底：逐行修复 + 控制字符清理
        fixed = self._fix_ultimate_json(text)
        if fixed:
            return fixed

        # 9. 记录解析失败的文本到文件，便于调试
        try:
            debug_dir = Path(tempfile.gettempdir()) / "architect_debug"
            debug_dir.mkdir(exist_ok=True)
            debug_file = debug_dir / f"parse_fail_{hash(text) % 10000}.txt"
            debug_file.write_text(text[:5000], encoding='utf-8')
            logger.error(f"JSON 解析失败，原始文本已保存到: {debug_file}")
        except Exception:
            logger.error(f"JSON 解析失败，原始文本前 200 字符: {text[:200]}")

        raise ValueError(f"无法解析 JSON: {text[:200]}...")

    def _fix_common_json_issues(self, text: str) -> Optional[Dict]:
        """修复常见 JSON 格式问题"""
        try:
            # 移除行尾注释
            text = self._remove_line_comments(text)
            # 修复单引号
            text = self._fix_single_quotes(text)
            # 修复未转义的换行符
            text = self._fix_unescaped_newlines(text)
            # 修复尾随逗号
            text = re.sub(r',\s*([\]}])', r'\1', text)
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return None

    def _fix_complex_json_issues(self, text: str) -> Optional[Dict]:
        """修复复杂 JSON 问题（嵌套对象、多 JSON 块）"""
        try:
            # 尝试找到最外层的 JSON 对象
            depth = 0
            start = -1
            for i, char in enumerate(text):
                if char == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0 and start != -1:
                        json_str = text[start:i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            # 尝试修复
                            fixed = self._fix_common_json_issues(json_str)
                            if fixed:
                                return fixed
                            start = -1
            return None
        except Exception:
            return None

    def _fix_missing_closing_braces(self, text: str) -> Optional[Dict]:
        """修复缺少闭合括号的 JSON"""
        try:
            # 计算需要的闭合括号
            open_braces = text.count('{') - text.count('}')
            open_brackets = text.count('[') - text.count(']')

            if open_braces > 0 or open_brackets > 0:
                # 移除行尾注释
                text = self._remove_line_comments(text)
                # 添加缺少的闭合括号
                text = text.rstrip()
                if text.endswith(','):
                    text = text[:-1]
                text += ']' * open_brackets + '}' * open_braces
                return json.loads(text)
            return None
        except (json.JSONDecodeError, Exception):
            return None

    def _fix_ultimate_json(self, text: str) -> Optional[Dict]:
        """最终兜底：逐行修复 + 控制字符清理"""
        try:
            # 移除行尾注释
            text = self._remove_line_comments(text)
            # 清理控制字符
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
            # 修复单引号
            text = self._fix_single_quotes(text)
            # 修复未转义的换行符
            text = self._fix_unescaped_newlines(text)
            # 修复尾随逗号
            text = re.sub(r',\s*([\]}])', r'\1', text)
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return None

    def _remove_line_comments(self, text: str) -> str:
        """移除行尾注释"""
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # 移除 // 注释（但不移除字符串中的 //）
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
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def _fix_single_quotes(self, text: str) -> str:
        """将单引号替换为双引号（处理 Python 字典格式）"""
        # 简单的单引号替换（不处理嵌套）
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
                    if char == "'":
                        result.append('"')
                    else:
                        result.append(char)
                elif char == quote_char:
                    in_string = False
                    if char == "'":
                        result.append('"')
                    else:
                        result.append(char)
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

    def _fix_unescaped_newlines(self, text: str) -> str:
        """修复字符串中的未转义换行符"""
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
