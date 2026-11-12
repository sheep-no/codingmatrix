"""LayoutOptimizer/LayoutUtils 分支覆盖：字号、分栏、溢出与格式化。"""

from types import SimpleNamespace

import pytest

from app.utils.pptx.layout_engine import LayoutOptimizer, LayoutUtils, TextAnalyzer


def _config(**overrides):
    defaults = dict(
        slide_width=13.333,
        slide_height=7.5,
        slide_margin=0.8,
        title_size=32,
        body_size=18,
        line_spacing=1.3,
        paragraph_spacing=0.3,
        subtitle_size=24,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_text_analyzer_empty_and_mixed():
    assert TextAnalyzer.analyze_text_density("")["total_chars"] == 0
    assert TextAnalyzer.count_chinese_chars("") == 0
    density = TextAnalyzer.analyze_text_density("中文abc 123")
    assert density["chinese_count"] == 2
    assert density["ascii_count"] == 6
    assert 0 < density["density_score"] <= 1.0


def test_estimate_display_height_branches():
    assert TextAnalyzer.estimate_display_height("", 18) == 0.0
    latin = TextAnalyzer.estimate_display_height("abcdef", 18, max_width=1.0)
    chinese = TextAnalyzer.estimate_display_height("中文中文中文", 18, max_width=1.0)
    assert latin > 0 and chinese > 0


def test_optimize_slide_content_dict_config_with_all_parts():
    optimizer = LayoutOptimizer()
    slide = {
        "title": "标题",
        "body": "正文内容" * 200,
        "images": ["a.png", "b.png", "c.png", "d.png"],
    }
    result = optimizer.optimize_slide_content(slide, _config())
    assert result["title"]["font_size"] > 0
    assert result["body"]["font_size"] >= 12
    assert result["images"]
    assert result["layout"]["images"]["columns"] == 3
    assert result["spacing"]["margin"] == 0.8


def test_optimize_slide_content_dict_config_branch():
    optimizer = LayoutOptimizer()
    config = {
        "slide_width": 10,
        "slide_height": 7,
        "slide_margin": 0.5,
        "title_size": 40,
        "body_size": 20,
        "line_spacing": 1.2,
        "paragraph_spacing": 0.2,
    }
    result = optimizer.optimize_slide_content({"title": "T", "body": "B"}, config)
    assert result["title"]["text"] == "T"
    assert result["body"]["line_spacing"] == 1.2
    assert result["layout"]["body"]["top"] >= 0.5


def test_optimize_slide_content_skips_empty_parts():
    optimizer = LayoutOptimizer()
    result = optimizer.optimize_slide_content(
        {"title": "", "body": "", "images": []}, _config()
    )
    assert "title" in result and result["title"] == ""
    assert "body" in result and result["body"] == ""
    assert result["images"] == []


def test_optimize_slide_content_title_only_shrinks_available_height():
    optimizer = LayoutOptimizer()
    result = optimizer.optimize_slide_content(
        {"title": "很长的标题" * 10}, _config(title_size=44)
    )
    assert result["title"]["font_size"] >= 36
    assert "body" not in result


def test_adjust_font_size_empty_returns_max():
    optimizer = LayoutOptimizer()
    assert optimizer.adjust_font_size("", min_size=10, max_size=30) == 30
    assert optimizer.adjust_font_size("abc", min_size=10, max_size=30) == 30
    assert optimizer.adjust_font_size("中" * 500, min_size=10, max_size=30) <= 30


def test_adjust_font_size_multiline_and_overflow_paths():
    optimizer = LayoutOptimizer()
    medium = optimizer.adjust_font_size("abcdefghij" * 3, max_width=4.0)
    large = optimizer.adjust_font_size("abcdefghij" * 30, max_width=1.0)
    assert large <= medium


def test_split_to_columns_paragraph_and_sentence_paths():
    optimizer = LayoutOptimizer()
    assert optimizer.split_to_columns("", 2) == [{"text": "", "width_ratio": 1.0}]
    assert optimizer.split_to_columns("abc", 1) == [{"text": "abc", "width_ratio": 1.0}]

    paragraph_columns = optimizer.split_to_columns("第一段\n\n第二段", 2)
    assert len(paragraph_columns) == 2
    assert paragraph_columns[0]["text"] == "第一段"

    sentence_columns = optimizer.split_to_columns("一句话。两句话。三句话。四句话。", 2)
    assert len(sentence_columns) >= 2
    assert all(column["width_ratio"] == pytest.approx(0.5) for column in sentence_columns)


def test_split_to_columns_pads_and_handles_single_paragraph():
    optimizer = LayoutOptimizer()
    columns = optimizer.split_to_columns("只有一段内容", 3)
    assert len(columns) == 3
    assert columns[0]["text"] == "只有一段内容"
    assert columns[1]["text"] == ""
    assert columns[2]["text"] == ""


def test_split_to_columns_force_split_branch():
    optimizer = LayoutOptimizer()
    # 多个极短段落时按段落数分配，触发剩余项强制换栏
    columns = optimizer.split_to_columns("a\n\nb\n\nc\n\nd", 2)
    assert len(columns) == 2
    assert columns[0]["text"] and columns[1]["text"]


def test_prevent_overflow_empty_and_fits():
    optimizer = LayoutOptimizer()
    empty = optimizer.prevent_overflow("", max_height=1, font_size=18)
    assert empty["will_overflow"] is False
    fits = optimizer.prevent_overflow("短文本", max_height=10, font_size=18)
    assert fits["will_overflow"] is False
    assert fits["text_to_display"] == "短文本"


def test_prevent_overflow_shrinks_font():
    optimizer = LayoutOptimizer()
    result = optimizer.prevent_overflow("短文本", max_height=0.4, font_size=40)
    assert result["will_overflow"] is True
    assert result["recommended_font_size"] < 40
    assert result["adjusted"] is False


def test_prevent_overflow_truncates_when_still_too_tall():
    optimizer = LayoutOptimizer()
    long_text = "第一段内容。\n\n第二段内容。\n\n第三段内容。" * 20
    result = optimizer.prevent_overflow(
        long_text, max_height=0.4, font_size=40, max_width=1.0
    )
    assert result["will_overflow"] is True
    assert result["truncate_position"] is not None
    assert result["text_to_display"].endswith("...")


def test_optimize_whitespace_non_dict_layout_and_parts():
    optimizer = LayoutOptimizer()
    data = {
        "layout": "not-a-dict",
        "title": {"font_size": 20},
        "body": {"text": "b"},
        "images": ["a", "b", "c", "d"],
    }
    result = optimizer.optimize_whitespace(data, _config())
    assert isinstance(result["layout"], dict)
    assert result["layout"]["images"]["columns"] == 3


def test_optimize_whitespace_without_sections():
    optimizer = LayoutOptimizer()
    result = optimizer.optimize_whitespace({}, _config())
    assert result["layout"] == {}
    assert result["spacing"]["element_spacing"] == 0.3


def test_optimize_whitespace_empty_image_list():
    optimizer = LayoutOptimizer()
    result = optimizer.optimize_whitespace({"images": []}, _config())
    assert "images" not in result["layout"]


def test_optimize_image_layout_variants():
    optimizer = LayoutOptimizer()
    assert optimizer._optimize_image_layout([], 5, 5, _config()) == []

    single = optimizer._optimize_image_layout(["a"], 10, 5, _config())
    assert single[0]["position"] == "center"
    assert single[0]["height"] == "auto"

    grid = optimizer._optimize_image_layout(
        ["a", "b", "c", "d", "e"], 10, 3, _config()
    )
    assert len(grid) == 5
    assert grid[-1]["position"].startswith("grid-")


def test_optimize_image_layout_zero_height_guard():
    optimizer = LayoutOptimizer()
    grid = optimizer._optimize_image_layout(["a", "b"], 4, 0, _config())
    assert len(grid) == 2


def test_truncate_at_boundary_paths():
    truncate = LayoutOptimizer._truncate_at_boundary
    assert truncate("short", 100) == "short"

    paragraph_text = "aaaa\n\n" + "b" * 40
    assert truncate(paragraph_text, 6) == "aaaa..."

    sentence_text = "abcdefg。" + "b" * 40
    assert truncate(sentence_text, 10) == "abcdefg。..."

    word_text = "abcdefg " + "b" * 40
    assert truncate(word_text, 10) == "abcdefg..."

    assert truncate("x" * 50, 20) == "x" * 20 + "..."


def test_layout_utils_text_fits_and_font_size():
    assert LayoutUtils.text_fits("", 18, 5) is True
    assert LayoutUtils.text_fits("a", 18, 5) is True
    assert LayoutUtils.text_fits("a" * 500, 18, 1) is False

    assert LayoutUtils.calculate_optimal_font_size(0, 5) == 44
    assert LayoutUtils.calculate_optimal_font_size(-1, 5) == 44
    assert 10 <= LayoutUtils.calculate_optimal_font_size(100, 5) <= 44
    assert LayoutUtils.calculate_optimal_font_size(1000, 1) == 10


def test_layout_utils_slide_type_and_area():
    assert LayoutUtils.get_layout_for_slide_type("TITLE") == "TITLE_SLIDE"
    assert LayoutUtils.get_layout_for_slide_type("content") == "CONTENT_SLIDE"
    assert LayoutUtils.get_layout_for_slide_type("section") == "SECTION_DIVIDER"
    assert LayoutUtils.get_layout_for_slide_type("end") == "END_SLIDE"
    assert LayoutUtils.get_layout_for_slide_type("unknown") == "CONTENT_SLIDE"
    assert LayoutUtils.calculate_content_area(10, 8, 1) == {"width": 8, "height": 6}


def test_format_slide_content_dispatch():
    config = _config()
    title = LayoutUtils.format_slide_content(
        "title", {"title": "T", "subtitle": "S"}, config
    )
    assert title["type"] == "title"
    assert title["subtitle"]["text"] == "S"

    title_no_sub = LayoutUtils.format_slide_content("title", {"title": "T"}, config)
    assert title_no_sub["subtitle"] is None

    content = LayoutUtils.format_slide_content(
        "content", {"title": "T", "text": "body"}, config
    )
    assert content["body"]["text"] == "body"

    two_column = LayoutUtils.format_slide_content(
        "two_column",
        {"column_1": "L", "column_2": "R", "left_ratio": 0.6, "right_ratio": 0.4},
        config,
    )
    assert two_column["columns"]["left"]["text"] == "L"
    assert two_column["columns"]["left"]["width_ratio"] == 0.6

    image_text = LayoutUtils.format_slide_content(
        "image_text", {"image": "a.png", "body": "b"}, config
    )
    assert image_text["image"]["source"] == "a.png"
    assert image_text["text"]["text"] == "b"

    image_text_empty = LayoutUtils.format_slide_content(
        "image_text", {"text": "b"}, config
    )
    assert image_text_empty["image"] is None

    custom = LayoutUtils.format_slide_content("weird", {"k": "v"}, config)
    assert custom["type"] == "custom"
    assert custom["template"] is config
