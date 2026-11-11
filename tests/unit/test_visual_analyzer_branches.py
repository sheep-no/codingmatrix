"""VisualAnalyzer 解析与规划分支回归。

覆盖 `_parse_analysis_response`、正则兜底提取与 `_build_visual_plan` 的
容错路径，锁定补测过程中暴露的 4 处缺陷：

1. 缺结尾围栏的 ```json 代码块会丢掉最后一个字符；
2. `keywords` / `highlight_words` 数组被首个逗号截断成截断字符串；
3. 正则兜底对含嵌套对象（images/title_style）的 slide 直接返回空；
4. 数组字段在嵌套对象下同样因非贪心匹配提前结束。
"""

import pytest

from app.utils.visual.visual_analyzer import (
    ImagePosition,
    ImageType,
    SlideVisualDecision,
    VisualAnalyzer,
)


def _content_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


# --- _parse_analysis_response 响应形态 ---


def test_parse_accepts_choices_response():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('{"slides_analysis": [{"slide_index": 1}]}')
    )
    assert result["slides_analysis"][0]["slide_index"] == 1


def test_parse_accepts_text_response():
    result = VisualAnalyzer()._parse_analysis_response(
        {"text": '{"overall_style": {"color_scheme": "green"}}'}
    )
    assert result["overall_style"]["color_scheme"] == "green"


def test_parse_falls_back_to_str_for_unknown_shape():
    """无 choices/text 时退化为字符串解析，返回原始键值。"""
    result = VisualAnalyzer()._parse_analysis_response(
        {"anything": '{"slides_analysis": []}'}
    )
    assert result["anything"] == '{"slides_analysis": []}'


def test_parse_falls_back_to_str_for_non_dict_response():
    result = VisualAnalyzer()._parse_analysis_response('{"slides_analysis": []}')
    assert result["slides_analysis"] == []


def test_parse_extracts_json_from_closed_json_fence():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('```json\n{"slides_analysis": []}\n```')
    )
    assert result["slides_analysis"] == []


def test_parse_extracts_json_from_generic_fence():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('```\n{"slides_analysis": []}\n```')
    )
    assert result["slides_analysis"] == []


def test_parse_handles_json_fence_without_closing_fence():
    """缺结尾围栏时不能丢掉最后一个字符。"""
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('```json\n{"slides_analysis": [], "overall_style": {"color_scheme": "blue"}}')
    )
    assert result["overall_style"]["color_scheme"] == "blue"


def test_parse_handles_generic_fence_without_closing_fence():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('```\n{"slides_analysis": [], "overall_style": {"color_scheme": "orange"}}')
    )
    assert result["overall_style"]["color_scheme"] == "orange"


def test_parse_repairs_python_literals_before_failing():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response("{'slides_analysis': [], 'overall_style': {'color_scheme': 'green'}}")
    )
    assert result["overall_style"]["color_scheme"] == "green"


def test_parse_uses_regex_when_repair_fails():
    result = VisualAnalyzer()._parse_analysis_response(
        _content_response('"slides_analysis": [{"slide_index": 2, "text_layout": "left"}] broken-tail')
    )
    assert result["slides_analysis"][0]["slide_index"] == 2


def test_parse_returns_empty_shape_on_unexpected_error(monkeypatch):
    analyzer = VisualAnalyzer()

    def _boom(_content):
        raise RuntimeError("boom")

    monkeypatch.setattr(analyzer, "_extract_json_by_regex", _boom)
    result = analyzer._parse_analysis_response(_content_response("{not-json"))
    assert result == {"slides_analysis": [], "overall_style": {}}


# --- 正则兜底提取：数组与嵌套对象 ---


def test_regex_fallback_parses_nested_slide_objects():
    """含 images / title_style 的合法结构必须能被兜底解析。"""
    content = (
        '{"slides_analysis": [{"slide_index": 1, '
        '"images": [{"image_type": "photo", "position": "left", "width_ratio": 0.3}], '
        '"title_style": {"font_family": "黑体", "font_size": 40}, '
        '"text_layout": "left"}], "overall_style": {}}'
    )
    result = VisualAnalyzer()._extract_json_by_regex(content)
    assert result["slides_analysis"][0]["images"][0]["image_type"] == "photo"
    assert result["slides_analysis"][0]["title_style"]["font_size"] == 40


def test_regex_fallback_keeps_multiple_slides():
    content = (
        '{"slides_analysis": ['
        '{"slide_index": 1, "images": [], "text_layout": "left"}, '
        '{"slide_index": 2, "images": [], "text_layout": "right"}]}'
    )
    result = VisualAnalyzer()._extract_json_by_regex(content)
    assert [s["slide_index"] for s in result["slides_analysis"]] == [1, 2]


def test_regex_fallback_returns_empty_when_field_absent():
    assert VisualAnalyzer()._extract_json_by_regex('{"other": 1}') == {
        "slides_analysis": [],
        "overall_style": {},
    }


def test_regex_fallback_maps_bool_and_string_fields():
    content = (
        '{"slides_analysis": [{"slide_index": 1, "images": [], '
        '"has_separator_line": false, "add_decoration": true, '
        '"separator_color": "FF0000", "reasoning": "理由"}]}'
    )
    slide = VisualAnalyzer()._extract_json_by_regex(content)["slides_analysis"][0]
    assert slide["has_separator_line"] is False
    assert slide["add_decoration"] is True
    assert slide["separator_color"] == "FF0000"
    assert slide["reasoning"] == "理由"


def test_regex_fallback_parses_highlight_words_array():
    """highlight_words 数组不能被首个逗号截断。"""
    content = (
        '{"slides_analysis": [{"slide_index": 1, "images": [], '
        '"highlight_words": ["重点", "增长"]}]}'
    )
    slide = VisualAnalyzer()._extract_json_by_regex(content)["slides_analysis"][0]
    assert slide["highlight_words"] == ["重点", "增长"]


def test_regex_fallback_invalid_array_falls_back_to_empty():
    content = (
        '{"slides_analysis": [{"slide_index": 1, "images": [], '
        '"highlight_words": [broken]}]}'
    )
    slide = VisualAnalyzer()._extract_json_by_regex(content)["slides_analysis"][0]
    assert slide["highlight_words"] == []


def test_extract_images_parses_keywords_array():
    """keywords 数组不能被逗号截断。"""
    images = VisualAnalyzer()._extract_images(
        '{"image_type": "photo", "keywords": ["云", "天空"], "width_ratio": 0.35}'
    )
    assert images[0]["keywords"] == ["云", "天空"]


def test_extract_images_invalid_width_ratio_falls_back():
    images = VisualAnalyzer()._extract_images('{"image_type": "photo", "width_ratio": "wide"}')
    assert images[0]["width_ratio"] == 0.4


def test_extract_images_uses_string_branch_for_other_fields():
    images = VisualAnalyzer()._extract_images(
        '{"image_type": "icon", "description": "图标", "position": "corner", "is_decoration": "true"}'
    )
    assert images[0]["description"] == "图标"
    assert images[0]["is_decoration"] is True


def test_extract_images_skips_empty_object_fragments():
    assert VisualAnalyzer()._extract_images("{}") == []


def test_extract_style_parses_numeric_and_string_fields():
    style = VisualAnalyzer()._extract_style(
        '{"font_family": "微软雅黑", "font_size": "22", "font_color": "333333"}'
    )
    assert style == {"font_family": "微软雅黑", "font_size": 22, "font_color": "333333"}


def test_extract_style_invalid_number_falls_back():
    style = VisualAnalyzer()._extract_style('{"font_size": "big"}')
    assert style["font_size"] == 24


def test_extract_style_ignores_absent_fields():
    assert VisualAnalyzer()._extract_style("{}") == {}


# --- 归一化与括号配对的转义边界 ---


def test_normalize_preserves_escaped_character_in_double_quoted_string():
    content = '{"quote": "say \\"hi\\"", "flag": True}'
    import json

    assert json.loads(VisualAnalyzer()._fix_json_format(content)) == {
        "quote": 'say "hi"',
        "flag": True,
    }


def test_line_comment_with_following_content_is_removed():
    content = '{"a": 1} // note\n'
    import json

    assert json.loads(VisualAnalyzer()._fix_json_format(content)) == {"a": 1}


def test_balanced_objects_ignore_braces_inside_escaped_strings():
    images = VisualAnalyzer()._extract_images(
        '{"image_type": "photo", "description": "a \\"}\\" b", "width_ratio": 0.3}'
    )
    # JSON 解码会还原转义，关键是括号没被误当成对象边界
    assert images[0]["description"] == 'a "}" b'
    assert images[0]["width_ratio"] == 0.3


def test_as_bool_accepts_real_booleans():
    assert VisualAnalyzer._as_bool(True) is True
    assert VisualAnalyzer._as_bool("TRUE") is True
    assert VisualAnalyzer._as_bool('"true"') is True
    assert VisualAnalyzer._as_bool("yes") is False


def test_json_field_value_returns_raw_text_when_not_parseable():
    assert VisualAnalyzer._json_field_value('"text_layout": left}', "text_layout") == "left"


def test_json_field_value_reports_missing_field():
    from app.utils.visual.visual_analyzer import _MISSING

    assert VisualAnalyzer._json_field_value('{"a": 1}', "b") is _MISSING


def test_regex_fallback_parses_style_and_scalar_fields_when_array_is_broken():
    """数组带尾随逗号无法整体解析时，逐对象提取样式/布尔/字符串字段。"""
    content = (
        '{"slides_analysis": [{"slide_index": 1, '
        '"images": [{"image_type": "photo", "width_ratio": 0.3}], '
        '"title_style": {"font_size": 40}, '
        '"has_separator_line": false, "text_layout": left},]}'
    )
    slides = VisualAnalyzer()._extract_json_by_regex(content)["slides_analysis"]
    assert slides[0]["slide_index"] == 1
    assert slides[0]["images"][0]["image_type"] == "photo"
    assert slides[0]["title_style"]["font_size"] == 40
    assert slides[0]["has_separator_line"] is False
    assert slides[0]["text_layout"] == "left"


def test_regex_fallback_handles_missing_slides_key():
    assert VisualAnalyzer()._extract_json_by_regex("no slides here") == {
        "slides_analysis": [],
        "overall_style": {},
    }


# --- _build_visual_plan 组装 ---


def test_build_plan_maps_images_and_styles():
    analyzer = VisualAnalyzer()
    plan = analyzer._build_visual_plan(
        "标题",
        [{"title": "第一页", "content": ["a", "b"]}],
        {
            "slides_analysis": [
                {
                    "slide_index": 1,
                    "images": [
                        {
                            "image_type": "illustration",
                            "description": "desc",
                            "keywords": ["k"],
                            "position": "top-left",
                            "width_ratio": 0.5,
                            "opacity": 0.8,
                            "is_decoration": False,
                        }
                    ],
                    "title_style": {"font_family": "黑体", "font_size": 40, "font_color": "112233", "font_weight": "medium"},
                    "content_style": {"font_family": "楷体", "font_size": 20, "font_color": "445566"},
                    "bullet_style": {"style": "number", "color": "778899"},
                    "text_layout": "left",
                    "has_separator_line": False,
                    "separator_color": "ABCDEF",
                    "highlight_words": ["重点"],
                    "highlight_color": "FEDCBA",
                    "add_decoration": False,
                    "decoration_style": "rich",
                    "corner_decoration": False,
                    "reasoning": "理由",
                }
            ],
            "overall_style": {"color_scheme": "green", "font_preference": "classic", "layout_pattern": "same"},
        },
        "business",
    )

    slide = plan.slides[0]
    assert plan.color_scheme == "green"
    assert plan.font_preference == "classic"
    assert plan.use_same_layout_pattern is True
    assert slide.get_main_image().position is ImagePosition.TOP_LEFT
    assert slide.title_style.font_family == "黑体"
    assert slide.content_style.font_color == "445566"
    assert slide.bullet_style.style == "number"
    assert slide.text_layout == "left"
    assert slide.has_separator_line is False
    assert slide.highlight_words == ["重点"]
    assert slide.reasoning == "理由"


def test_build_plan_invalid_enums_fall_back_to_neutral_values():
    plan = VisualAnalyzer()._build_visual_plan(
        "标题",
        [{"title": "页", "content": []}],
        {"slides_analysis": [{"slide_index": 1, "images": [{"image_type": "weird", "position": "nowhere"}]}]},
        "education",
    )
    image = plan.slides[0].images[0]
    assert image.image_type is ImageType.NONE
    assert image.position is ImagePosition.RIGHT
    assert plan.slides_needing_images == 0


def test_build_plan_without_matching_analysis_uses_defaults():
    plan = VisualAnalyzer()._build_visual_plan(
        "标题",
        [{"title": "未分析页", "content": "纯文本"}],
        {"slides_analysis": [{"slide_index": 9}]},
        "education",
    )
    slide = plan.slides[0]
    assert slide.slide_index == 1
    assert slide.images == []
    assert slide.need_image is False
    assert plan.slides_needing_images == 0


def test_build_plan_uses_fallback_titles():
    plan = VisualAnalyzer()._build_visual_plan("标题", [{"content": []}], {}, "education")
    assert plan.slides[0].title == "第1页"


def test_build_plan_defaults_overall_style():
    plan = VisualAnalyzer()._build_visual_plan("标题", [], {}, "minimal")
    assert plan.color_scheme == "blue"
    assert plan.font_preference == "modern"
    assert plan.use_same_layout_pattern is False


# --- 提示词、摘要与默认规划 ---


def test_build_prompt_handles_non_list_content():
    prompt = VisualAnalyzer()._build_analysis_prompt(
        "标题", [{"title": "页", "content": "纯文本内容"}], "education"
    )
    assert "纯文本内容" in prompt


def test_build_prompt_truncates_list_content():
    prompt = VisualAnalyzer()._build_analysis_prompt(
        "标题", [{"title": "页", "content": [f"条目{i}" for i in range(9)]}], "education"
    )
    assert "条目4" in prompt
    assert "条目5" not in prompt


def test_summarize_content_handles_list_and_scalar():
    analyzer = VisualAnalyzer()
    assert analyzer._summarize_content(["a", "b", "c", "d"]) == "a b c"
    assert analyzer._summarize_content(12345) == "12345"


def test_summarize_content_truncates_to_100_chars():
    summary = VisualAnalyzer()._summarize_content("x" * 300)
    assert len(summary) == 100


def test_default_plan_has_no_images_but_keeps_decoration():
    plan = VisualAnalyzer()._create_default_plan(
        "标题", [{"title": "页", "content": ["a"]}], "education"
    )
    slide = plan.slides[0]
    assert slide.images == []
    assert slide.add_decoration is True
    assert slide.corner_decoration is True
    assert slide.title_style.font_size == 44


@pytest.mark.asyncio
async def test_analyze_ppt_content_uses_llm_response(monkeypatch):
    """成功路径：解析模型响应并组装视觉规划。"""
    import app.utils as utils_pkg

    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"slides_analysis": [{"slide_index": 1, '
                        '"images": [{"image_type": "photo", "width_ratio": 0.4}]}], '
                        '"overall_style": {"color_scheme": "purple"}}'
                    }
                }
            ]
        }

    monkeypatch.setattr(utils_pkg, "call_llm", fake_call_llm)

    plan = await VisualAnalyzer().analyze_ppt_content(
        "标题",
        [{"title": "页", "content": ["a"]}],
        theme="creative",
        api_key_token="token-1",
    )

    assert captured["api_key_token"] == "token-1"
    assert captured["stream"] is False
    assert plan.color_scheme == "purple"
    assert plan.slides[0].need_image is True


@pytest.mark.asyncio
async def test_analyze_ppt_content_falls_back_when_llm_fails(monkeypatch):
    """失败路径：调用异常时返回无图片的默认规划。"""
    import app.utils as utils_pkg

    async def failing_llm(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(utils_pkg, "call_llm", failing_llm)

    plan = await VisualAnalyzer().analyze_ppt_content(
        "标题",
        [{"title": "页", "content": ["a"]}],
    )

    assert plan.slides[0].images == []
    assert plan.slides_needing_images == 0
    assert plan.theme == "education"


def test_need_image_ignores_decoration_only_slides():
    decision = SlideVisualDecision(
        slide_index=1,
        title="标题",
        content_summary="正文",
        images=[],
    )
    assert decision.need_image is False
    assert decision.get_main_image() is None
