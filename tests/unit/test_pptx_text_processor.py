"""PPT 文本处理工具回归。

覆盖智能换行、字号计算、溢出截断与文本清理。历史缺陷：
`truncate_text(max_length<3)` 负切片后反而变长；`smart_split_line` 对超长
英文单词直接丢弃 `max_chars` 之后的内容。
"""

import pytest

from app.utils.pptx.text_processor import (
    calculate_font_size,
    clean_text_for_ppt,
    is_cjk_char,
    prevent_text_overflow,
    prevent_text_overflow_simple,
    smart_split_line,
    truncate_text,
)


def test_is_cjk_char_covers_ranges():
    assert is_cjk_char("中")
    assert is_cjk_char("あ")
    assert is_cjk_char("ア")
    assert is_cjk_char("、")
    assert not is_cjk_char("a")
    assert not is_cjk_char("1")


def test_smart_split_line_empty_and_short():
    assert smart_split_line("", 10) == []
    assert smart_split_line("short", 10) == ["short"]


def test_smart_split_line_chinese_by_char():
    result = smart_split_line("一二三四五六", 3)
    assert result == ["一二三", "四五六"]


def test_smart_split_line_english_by_word():
    result = smart_split_line("alpha beta gamma delta", 11)
    assert all(len(line) <= 11 for line in result)
    assert " ".join(result).split() == ["alpha", "beta", "gamma", "delta"]


def test_smart_split_line_preserves_long_word_tail():
    """超长单词必须分段保留，不能丢弃 max_chars 之后的内容。"""
    word = "supercalifragilisticexpialidocious"
    result = smart_split_line(f"{word} end", 10)

    assert all(len(line) <= 10 for line in result)
    assert result[-1].endswith("end")
    assert word in "".join(result)


@pytest.mark.parametrize(
    "num_lines,max_lines,expected",
    [
        (0, 10, 18.0),
        (-3, 10, 18.0),
        (5, 10, 18.0),
        (20, 10, 12.0),
    ],
)
def test_calculate_font_size(num_lines, max_lines, expected):
    assert calculate_font_size(num_lines, max_lines, 18.0, 12.0) == expected


def test_calculate_font_size_scales_between_bounds():
    size = calculate_font_size(12, 10, 18.0, 12.0)
    assert 12.0 < size < 18.0


def test_prevent_text_overflow_empty():
    layout = prevent_text_overflow("   ")
    assert layout.lines == ["暂无内容"]
    assert layout.needs_overflow_warning is False


def test_prevent_text_overflow_only_blank_paragraphs():
    layout = prevent_text_overflow("\n\n   \n")
    assert layout.lines == ["暂无内容"]


def test_prevent_text_overflow_truncates_multi_line():
    text = "\n".join(f"line{i}" for i in range(10))
    layout = prevent_text_overflow(text, max_chars_per_line=50, max_lines=3)

    assert layout.needs_overflow_warning is True
    assert len(layout.lines) == 3
    assert layout.lines[-1].startswith("...")
    # 10 行保留前 2 行，省略 8 行。
    assert "8" in layout.overflow_message


def test_prevent_text_overflow_minimum_one_line():
    layout = prevent_text_overflow("a\nb\nc", max_lines=0)
    assert len(layout.lines) == 1
    assert layout.needs_overflow_warning is True


def test_prevent_text_overflow_simple_matches_layout():
    text = "hello world " * 40
    simple = prevent_text_overflow_simple(text, max_chars_per_line=20, max_lines=3)
    layout = prevent_text_overflow(text, max_chars_per_line=20, max_lines=3)
    assert simple == layout.lines


@pytest.mark.parametrize(
    "text,max_length,expected",
    [
        ("", 10, ""),
        ("abc", 10, "abc"),
        ("abcdef", 6, "abcdef"),
        ("abcdef", 10, "abcdef"),
        ("abcdefghij", 7, "abcd..."),
        # 以下三组回归负切片缺陷：结果长度不得超过 max_length。
        ("abcdef", 3, "..."),
        ("abcdef", 2, ".."),
        ("abcdef", 1, "."),
        ("abcdef", 0, ""),
    ],
)
def test_truncate_text_respects_max_length(text, max_length, expected):
    result = truncate_text(text, max_length)
    assert result == expected
    assert len(result) <= max_length


def test_clean_text_for_ppt():
    assert clean_text_for_ppt("") == ""
    assert clean_text_for_ppt("  hello   world  ") == "hello world"
    assert clean_text_for_ppt("a\tb\rc") == "a b c"
