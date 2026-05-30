"""
PPT 文本处理模块

功能:
- 智能换行: 中文按字数，英文按单词
- 字号自动调整: 根据文本量自动缩放
- 文本截断: 超出限制时优雅截断
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TextLayout:
    """文本布局结果"""
    lines: List[str]
    font_size: float
    needs_overflow_warning: bool = False
    overflow_message: str = ""


def is_cjk_char(char: str) -> bool:
    """判断是否是中日韩字符"""
    cp = ord(char)
    return (
        (0x4E00 <= cp <= 0x9FFF) or    # CJK Unified Ideographs
        (0x3400 <= cp <= 0x4DBF) or    # CJK Extension A
        (0xF900 <= cp <= 0xFAFF) or    # CJK Compatibility
        (0x3000 <= cp <= 0x303F) or    # CJK Symbols
        (0xFF00 <= cp <= 0xFFEF) or    # Halfwidth and Fullwidth
        (0x3040 <= cp <= 0x309F) or    # Hiragana
        (0x30A0 <= cp <= 0x30FF)       # Katakana
    )


def smart_split_line(text: str, max_chars: int) -> List[str]:
    """
    智能换行: 中文按字数，英文按单词边界
    
    Args:
        text: 要分割的文本
        max_chars: 每行最大字符数（英文字符数）
        
    Returns:
        分割后的行列表
    """
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    lines = []
    current_line = ""

    # 按空格分割单词
    words = text.split()

    for word in words:
        # 检查是否包含中文字符
        has_cjk = any(is_cjk_char(c) for c in word)

        if has_cjk:
            # 中文: 逐字处理
            for char in word:
                # 中文字符算 1 个字符位置
                if len(current_line) + 1 > max_chars:
                    if current_line:
                        lines.append(current_line.strip())
                    current_line = char
                else:
                    current_line += char
        else:
            # 英文: 按单词处理
            test_line = f"{current_line} {word}" if current_line else word
            if len(test_line) > max_chars:
                if current_line:
                    lines.append(current_line.strip())
                # 如果单词本身超过限制，强制截断
                if len(word) > max_chars:
                    lines.append(word[:max_chars])
                    current_line = ""
                else:
                    current_line = word
            else:
                current_line = test_line

    if current_line.strip():
        lines.append(current_line.strip())

    return lines


def calculate_font_size(
    num_lines: int,
    max_lines: int = 10,
    base_font_size: float = 18.0,
    min_font_size: float = 12.0,
) -> float:
    """
    根据文本行数自动计算字号
    
    Args:
        num_lines: 文本行数
        max_lines: 最大行数限制
        base_font_size: 基准字号
        min_font_size: 最小字号
        
    Returns:
        推荐字号
    """
    if num_lines <= max_lines:
        return base_font_size

    # 行数超出时，按比例缩小字号
    scale = max_lines / num_lines
    font_size = base_font_size * scale

    # 限制最小字号
    return max(font_size, min_font_size)


def prevent_text_overflow(
    text: str,
    max_chars_per_line: int = 70,
    max_lines: int = 6,
    base_font_size: float = 18.0,
    min_font_size: float = 12.0,
) -> TextLayout:
    """
    防止文本在 PPT 幻灯片中溢出
    
    Args:
        text: 原始文本
        max_chars_per_line: 每行最大字符数
        max_lines: 最大行数限制
        base_font_size: 基准字号
        min_font_size: 最小字号
        
    Returns:
        TextLayout 对象
    """
    if not text:
        return TextLayout(lines=["暂无内容"], font_size=base_font_size)

    # 按原始换行分割
    paragraphs = text.strip().split('\n')
    all_lines = []

    for para in paragraphs:
        if not para.strip():
            continue
        split_lines = smart_split_line(para.strip(), max_chars_per_line)
        all_lines.extend(split_lines)

    if not all_lines:
        return TextLayout(lines=["暂无内容"], font_size=base_font_size)

    # 检查是否需要截断
    needs_overflow = len(all_lines) > max_lines
    overflow_message = ""

    if needs_overflow:
        # 保留前 max_lines - 1 行，最后一行显示省略提示
        truncated_lines = all_lines[:max_lines - 1]
        remaining = len(all_lines) - (max_lines - 1)
        truncated_lines.append(f"... (还有 {remaining} 行内容已省略)")
        all_lines = truncated_lines
        overflow_message = f"文本内容超出 {remaining} 行，已自动截断"

    # 计算字号
    font_size = calculate_font_size(len(all_lines), max_lines, base_font_size, min_font_size)

    if font_size < base_font_size:
        logger.debug(f"文本行数 ({len(all_lines)}) 超出限制，字号从 {base_font_size} 缩小到 {font_size:.1f}")

    return TextLayout(
        lines=all_lines,
        font_size=font_size,
        needs_overflow_warning=needs_overflow,
        overflow_message=overflow_message,
    )


def prevent_text_overflow_simple(
    text: str,
    max_chars_per_line: int = 70,
    max_lines: int = 6,
) -> List[str]:
    """
    简化版文本溢出防护 (兼容旧接口)
    
    Returns:
        处理后的文本行列表
    """
    layout = prevent_text_overflow(text, max_chars_per_line, max_lines)
    return layout.lines


def truncate_text(text: str, max_length: int = 200) -> str:
    """截断文本到指定长度"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def clean_text_for_ppt(text: str) -> str:
    """清理文本，移除不适合 PPT 显示的字符"""
    if not text:
        return ""

    # 移除多余空白
    text = " ".join(text.split())

    # 移除特殊字符
    text = text.replace("\t", " ")
    text = text.replace("\r", "")

    return text.strip()
