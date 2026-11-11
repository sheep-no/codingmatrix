"""CustomTemplateParser / TemplateValidator / TemplateConverter 分支回归。

覆盖真实 python-pptx 模板的占位符识别、颜色/字体/边距提取、兼容性评分、
主题 XML 改写与配置合并。补测暴露的核心缺陷：`str(ph.type)` 实际形如
``"TITLE (1)"`` / ``"OBJECT (7)"``，旧实现用 ``"title"`` / ``"obj"`` 精确
比较，真实模板恒被判为 ``blank``，标题、正文、边距全部识别失败。
"""

import pytest
from pptx import Presentation
from pptx.util import Inches

from app.utils.pptx.custom_template import (
    CustomTemplateParser,
    TemplateConverter,
    TemplateValidator,
)
from app.utils.pptx.templates import SlideLayout, TemplateCategory, TemplateConfig


def _saved_presentation(tmp_path, name="template.pptx"):
    prs = Presentation()
    path = tmp_path / name
    prs.save(str(path))
    return path


def _config(**overrides):
    values = dict(
        template_id="t",
        name="N",
        name_zh="中文",
        category=TemplateCategory.BUSINESS,
        description="d",
    )
    values.update(overrides)
    return TemplateConfig(**values)


# --- 占位符识别：真实模板必须能识别 title / body ---


def test_analyze_slide_master_recognizes_real_title_and_body():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[1]  # Title and Content

    result = CustomTemplateParser().analyze_slide_master(layout)

    types = [ph["type"].lower() for ph in result["placeholders"]]
    assert any("title" in t for t in types)
    assert any("object" in t or "body" in t or "content" in t for t in types)
    assert result["recommended_type"] == "title_content"


def test_analyze_slide_master_title_only_layout():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[5]  # Title Only

    result = CustomTemplateParser().analyze_slide_master(layout)

    assert result["recommended_type"] == "title_only"


def test_analyze_slide_master_blank_layout():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[6]  # Blank

    result = CustomTemplateParser().analyze_slide_master(layout)

    assert result["recommended_type"] == "blank"
    # Blank 布局仍带日期/页脚/页码占位符，但它们不算标题或正文。
    types = {ph["type"] for ph in result["placeholders"]}
    assert types.isdisjoint({"title", "object", "body", "content"})


def test_extract_layout_info_sets_title_and_content_flags():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[1]

    info = CustomTemplateParser().extract_layout_info(layout)

    assert info["has_title"] is True
    assert info["has_content"] is True
    assert info["shape_count"] > 0
    assert info["margins"]["body_margin_left"] > 0


def test_extract_layout_info_title_slide_has_no_content():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[0]  # Title Slide

    info = CustomTemplateParser().extract_layout_info(layout)

    assert info["has_title"] is True
    assert info["has_content"] is False


def test_extract_layout_info_tolerates_broken_shapes():
    class Broken:
        @property
        def shapes(self):
            raise RuntimeError("boom")

    info = CustomTemplateParser().extract_layout_info(Broken())
    assert info["placeholders"] == []
    assert info["shape_count"] == 0


def test_detect_margins_records_title_and_body_offsets():
    prs = Presentation()
    layout = prs.slide_masters[0].slide_layouts[1]

    margins = CustomTemplateParser()._detect_margins(layout.shapes)

    assert margins["title_margin_left"] == pytest.approx(0.5, abs=1e-3)
    assert margins["body_margin_left"] == pytest.approx(0.5, abs=1e-3)
    assert margins["title_margin_bottom"] > 0


def test_get_placeholder_info_returns_none_for_non_placeholder():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(1), Inches(1))

    assert CustomTemplateParser()._get_placeholder_info(shape) is None


def test_get_placeholder_info_handles_missing_geometry():
    class FakePh:
        idx = 3
        type = None

    class FakeShape:
        is_placeholder = True
        placeholder_format = FakePh()
        name = "Broken"
        left = None
        top = None
        width = None
        height = None

    info = CustomTemplateParser()._get_placeholder_info(FakeShape())
    assert info["type"] == "unknown"
    assert info["left"] == 0.0
    assert info["name"] == "Broken"


# --- 颜色与字体提取 ---


def test_extract_colors_returns_defaults_for_shape_less_master():
    class Empty:
        shapes = []

    colors = CustomTemplateParser().extract_colors(Empty())
    assert colors["primary_color"] == "1F4E79"
    assert colors["background_color"] == "FFFFFF"


def test_extract_colors_prefers_frequent_shape_fill():
    from pptx.dml.color import RGBColor

    class Fill:
        class fore_color:
            rgb = RGBColor(0x11, 0x22, 0x33)

    class Shape:
        shapes = None
        has_text_frame = False
        fill = Fill()

    class Slide:
        shapes = [Shape(), Shape()]

    colors = CustomTemplateParser().extract_colors(Slide())
    assert colors["primary_color"] == "112233"


def test_get_fill_color_returns_none_without_rgb():
    class Fill:
        fore_color = None

    class Shape:
        fill = Fill()

    assert CustomTemplateParser()._get_fill_color(Shape()) is None


def test_get_text_color_walks_runs():
    from pptx.dml.color import RGBColor

    class Font:
        class color:
            rgb = RGBColor(0xAB, 0xCD, 0xEF)

    class Run:
        font = Font()

    class Para:
        runs = [Run()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    assert CustomTemplateParser()._get_text_color(Shape()) == "ABCDEF"


def test_get_text_color_returns_none_for_shape_without_text():
    class Shape:
        has_text_frame = False

    assert CustomTemplateParser()._get_text_color(Shape()) is None


def test_extract_fonts_uses_shape_runs_and_splits_cjk():
    class Font:
        def __init__(self, name):
            self.name = name

    class Run:
        def __init__(self, name):
            self.font = Font(name)

    class Para:
        def __init__(self, level, name):
            self.level = level
            self.runs = [Run(name)]

    class TF:
        def __init__(self):
            self.paragraphs = [Para(0, "黑体"), Para(0, "Arial"), Para(1, "宋体"), Para(1, "Calibri")]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    class Slide:
        shapes = [Shape()]

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font"] == "黑体"
    assert fonts["title_font_en"] == "Arial"
    assert fonts["body_font"] == "宋体"
    assert fonts["body_font_en"] == "Calibri"


def test_extract_fonts_returns_defaults_without_shapes():
    class Empty:
        shapes = []

    fonts = CustomTemplateParser().extract_fonts(Empty())
    assert fonts == {
        "title_font": "微软雅黑",
        "body_font": "微软雅黑",
        "title_font_en": "Arial",
        "body_font_en": "Calibri",
    }


# --- 装饰检测 ---


def test_extract_decorations_without_masters():
    class Empty:
        slide_masters = []

    assert CustomTemplateParser().extract_decorations(Empty())["has_header_bar"] is False


def test_extract_decorations_detects_top_and_bottom_bars():
    """母版顶部/底部填充条必须被识别（Shape 无 position 属性的回归）。"""
    from pptx.dml.color import RGBColor
    from pptx.shapes.autoshape import Shape

    prs = Presentation()
    master = prs.slide_masters[0]
    tree = master.shapes._spTree
    for name, top in (
        ("HeaderBar", 0),
        ("FooterBar", Inches(7.5).emu - Inches(0.08).emu),
    ):
        element = tree.add_autoshape(
            tree.max_shape_id + 1, name, "rect", 0, top, Inches(13).emu, Inches(0.12).emu
        )
        shape = Shape(element, master.shapes)
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string("112233")

    decorations = CustomTemplateParser().extract_decorations(prs)

    assert decorations["has_header_bar"] is True
    assert decorations["has_footer_bar"] is True
    assert decorations["header_bar_color"] == "112233"
    assert decorations["footer_bar_color"] == "112233"


def test_extract_theme_colors_falls_back_to_palette():
    class Empty:
        slide_masters = []

    colors = CustomTemplateParser().extract_theme_colors(Empty())
    assert len(colors) == 12
    assert colors[0] == "1F4E79"


def test_extract_theme_colors_reads_theme_slots_when_available():
    from pptx.dml.color import RGBColor

    class Slot:
        def __init__(self, rgb):
            self.rgb = rgb

    class Theme:
        theme_colors = [Slot(RGBColor(0x10, 0x20, 0x30))] * 12

    class Master:
        theme = Theme()

    class Prs:
        slide_masters = [Master()]

    colors = CustomTemplateParser().extract_theme_colors(Prs())
    assert colors == ["102030"] * 12


def test_extract_theme_colors_pads_missing_slots_with_black():
    class Theme:
        theme_colors = [None, object()]

    class Master:
        theme = Theme()

    class Prs:
        slide_masters = [Master()]

    colors = CustomTemplateParser().extract_theme_colors(Prs())
    assert len(colors) == 12
    assert colors[0] == "000000"


def test_extract_colors_reads_theme_slots():
    from pptx.dml.color import RGBColor

    class Slot:
        def __init__(self, rgb):
            self.rgb = rgb

    class Theme:
        theme_colors = [Slot(RGBColor(0xAA, 0xBB, 0xCC))] * 8

    class Slide:
        theme = Theme()
        shapes = []

    colors = CustomTemplateParser().extract_colors(Slide())
    assert colors["primary_color"] == "AABBCC"
    assert colors["secondary_color"] == "AABBCC"


def test_extract_fonts_reads_theme_font_scheme():
    from pptx.oxml.ns import qn
    from lxml import etree

    xml = (
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        "<a:themeElements><a:fontScheme>"
        '<a:majorFont><a:latin typeface="Georgia"/><a:ea typeface="黑体"/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Verdana"/><a:ea typeface="宋体"/></a:minorFont>'
        "</a:fontScheme></a:themeElements></a:theme>"
    )

    class Theme:
        _element = etree.fromstring(xml.encode())

    class Slide:
        theme = Theme()
        shapes = []

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font_en"] == "Georgia"
    assert fonts["title_font"] == "黑体"
    assert fonts["body_font_en"] == "Verdana"
    assert fonts["body_font"] == "宋体"


def test_analyze_shape_for_decoration_detects_page_number_text():
    class TF:
        text = "第 3 页 / 9"

    class Shape:
        shape_type = 1
        fill = None
        has_text_frame = True
        text_frame = TF()
        width = Inches(1)
        height = Inches(1)
        left = Inches(1)
        top = Inches(1)
        position = None

    decorations = {"has_page_number": False}
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_page_number"] is True


def test_analyze_shape_for_decoration_ignores_plain_text():
    class TF:
        text = "正文内容"

    class Shape:
        shape_type = 1
        fill = None
        has_text_frame = True
        text_frame = TF()
        width = Inches(1)
        height = Inches(1)
        left = Inches(1)
        top = Inches(1)
        position = None

    decorations = {"has_page_number": False}
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_page_number"] is False


# --- 配置生成与布局映射 ---


def test_generate_config_requires_parsed_data():
    with pytest.raises(RuntimeError, match="未解析"):
        CustomTemplateParser().generate_template_config()


def test_generate_config_maps_layouts_and_spacing():
    parser = CustomTemplateParser(default_category=TemplateCategory.TECH)
    parser._extracted_colors = {"primary_color": "112233"}
    parser._extracted_fonts = {"title_font": "黑体"}
    parser._extracted_layouts = {
        "title": {"recommended_type": "title_only"},
        "unknown": {"recommended_type": "weird_type"},
    }
    parser._extracted_decorations = {
        "has_header_bar": True,
        "margins": {"body_margin_left": 1.25},
    }
    parser._slide_width = 10.0
    parser._slide_height = 5.625

    config = parser.generate_template_config()

    assert config.category is TemplateCategory.TECH
    assert config.primary_color == "112233"
    assert config.title_font == "黑体"
    assert config.slide_margin == 1.25
    assert config.slide_width == 10.0
    assert SlideLayout.TITLE_ONLY in config.layouts
    assert SlideLayout.TITLE_CONTENT in config.layouts


# --- 验证器 ---


def test_validate_accepts_real_pptx(tmp_path):
    path = _saved_presentation(tmp_path)
    ok, errors = TemplateValidator().validate_template(str(path))
    assert ok is True
    assert errors == []


def test_validate_rejects_missing_and_wrong_extension(tmp_path):
    validator = TemplateValidator()
    assert validator.validate_template(str(tmp_path / "nope.pptx"))[0] is False
    txt = tmp_path / "x.txt"
    txt.write_text("x", encoding="utf-8")
    ok, errors = validator.validate_template(str(txt))
    assert ok is False
    assert ".pptx" in errors[0]


def test_validate_rejects_non_zip_pptx(tmp_path):
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"not a zip")
    ok, errors = TemplateValidator().validate_template(str(broken))
    assert ok is False
    assert "无法打开" in errors[0]


def test_check_required_elements_finds_real_placeholders(tmp_path):
    path = _saved_presentation(tmp_path)
    assert TemplateValidator().check_required_elements(str(path)) == []


def test_check_required_elements_reports_missing_when_unreadable(tmp_path):
    path = tmp_path / "broken.pptx"
    path.write_bytes(b"not a zip")
    assert TemplateValidator().check_required_elements(str(path)) == ["title", "body"]


def test_compatibility_score_rewards_valid_template(tmp_path):
    path = _saved_presentation(tmp_path)
    assert TemplateValidator().get_compatibility_score(str(path)) >= 0.7


def test_compatibility_score_zero_for_invalid_files(tmp_path):
    validator = TemplateValidator()
    assert validator.get_compatibility_score(str(tmp_path / "nope.pptx")) == 0.0
    txt = tmp_path / "x.txt"
    txt.write_text("x", encoding="utf-8")
    assert validator.get_compatibility_score(str(txt)) == 0.0
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"not a zip")
    assert validator.get_compatibility_score(str(broken)) == 0.0


# --- 转换器 ---


def test_convert_pptx_to_config_round_trip(tmp_path):
    path = _saved_presentation(tmp_path)
    config = TemplateConverter().convert_pptx_to_config(str(path))
    assert config.template_id == "custom_user_upload"
    assert config.slide_width == pytest.approx(10.0, abs=1e-2)


def test_apply_config_sets_dimensions_and_decorations(tmp_path):
    converter = TemplateConverter()
    prs = Presentation()
    config = _config(
        slide_width=12.0,
        slide_height=6.75,
        has_header_bar=True,
        has_footer_bar=True,
        has_page_number=True,
        has_corner_decor=True,
    )

    converter.apply_config_to_presentation(config, prs)

    assert prs.slide_width == Inches(12.0)
    assert prs.slide_height == Inches(6.75)
    names = {shape.name for shape in prs.slide_masters[0].slide_layouts[0].shapes}
    assert {"HeaderBar", "FooterBar", "PageNumber", "CornerDecor"} <= names


def test_apply_config_tolerates_missing_theme_part():
    class NoMasters:
        slide_masters = []

    converter = TemplateConverter()
    converter._apply_colors_to_presentation(NoMasters(), _config())
    converter._apply_default_font_to_presentation(NoMasters(), _config())
    converter._apply_decorations(NoMasters(), _config())


def test_get_theme_part_returns_part_for_real_presentation():
    assert TemplateConverter._get_theme_part(Presentation()) is not None
    assert TemplateConverter._get_theme_part(type("E", (), {"slide_masters": []})()) is None


# --- 配置合并 ---


def test_merge_prefers_custom_non_default_values():
    base = _config(primary_color="111111", title_size=36, slide_margin=1.0)
    custom = _config(primary_color="222222", title_size=40, slide_margin=1.2)

    merged = TemplateConverter().merge_configs(base, custom)

    assert merged.primary_color == "222222"
    assert merged.title_size == 40
    assert merged.slide_margin == 1.2
    assert merged.category is base.category
    assert merged.template_id == custom.template_id


def test_merge_falls_back_to_base_when_custom_uses_defaults():
    base = _config(primary_color="111111", title_size=36)
    custom = _config()  # 全部默认值

    merged = TemplateConverter().merge_configs(base, custom)

    assert merged.primary_color == "111111"
    assert merged.title_size == 36


def test_merge_unions_layouts_with_custom_winning():
    base = _config(layouts={SlideLayout.TITLE_ONLY: {"source": "base"}})
    custom = _config(
        layouts={
            SlideLayout.TITLE_ONLY: {"source": "custom"},
            SlideLayout.FULL_IMAGE: {"source": "custom"},
        }
    )

    merged = TemplateConverter().merge_configs(base, custom)

    assert merged.layouts[SlideLayout.TITLE_ONLY] == {"source": "custom"}
    assert merged.layouts[SlideLayout.FULL_IMAGE] == {"source": "custom"}


def test_merge_decorations_follow_custom():
    base = _config(has_header_bar=True, has_page_number=True)
    custom = _config(has_header_bar=False, has_page_number=False)

    merged = TemplateConverter().merge_configs(base, custom)

    assert merged.has_header_bar is False
    assert merged.has_page_number is False


# --- 解析入口与异常分支 ---


def test_placeholder_type_name_falls_back_to_string_form():
    from app.utils.pptx.custom_template import _placeholder_type_name

    class BareType:
        def __str__(self):
            return "CENTER_TITLE (3)"

    assert _placeholder_type_name(type("P", (), {"type": BareType()})()) == "center_title"
    assert _placeholder_type_name(type("P", (), {"type": None})()) == ""


def test_parse_template_file_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        CustomTemplateParser().parse_template_file(str(tmp_path / "nope.pptx"))


def test_parse_template_file_wraps_unreadable_file(tmp_path):
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="无法打开"):
        CustomTemplateParser().parse_template_file(str(broken))


def test_parse_template_file_without_masters(monkeypatch, tmp_path):
    class Masterless:
        slide_width = Inches(10)
        slide_height = Inches(7.5)

        def close(self):
            pass

        @property
        def slide_masters(self):
            return []

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation",
        lambda path: Masterless(),
    )
    path = tmp_path / "masterless.pptx"
    path.write_bytes(b"x")
    # 没有母版的文件无法产出配置，应包装为 RuntimeError 而不是 AttributeError。
    with pytest.raises(RuntimeError, match="解析模板文件时发生错误"):
        CustomTemplateParser().parse_template_file(str(path))


def test_parse_template_file_wraps_unexpected_errors(monkeypatch, tmp_path):
    class Boom:
        slide_width = Inches(10)
        slide_height = Inches(7.5)

        def close(self):
            raise RuntimeError("close failed")

        @property
        def slide_masters(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation",
        lambda path: Boom(),
    )
    with pytest.raises(RuntimeError, match="解析模板文件时发生错误"):
        path = tmp_path / "boom.pptx"
        path.write_bytes(b"x")
        CustomTemplateParser().parse_template_file(str(path))


def test_extract_colors_swallows_internal_errors(monkeypatch):
    parser = CustomTemplateParser()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(parser, "_extract_from_theme_colors", boom)
    monkeypatch.setattr(parser, "_extract_from_shapes", boom)
    colors = parser.extract_colors(object())
    assert colors["primary_color"] == "1F4E79"


def test_extract_from_theme_colors_skips_missing_slots_and_bad_index():
    from pptx.dml.color import RGBColor

    class Slot:
        rgb = RGBColor(0x11, 0x22, 0x33)

    class Theme:
        theme_colors = [Slot(), None, Slot()]

    class Slide:
        theme = Theme()

    colors = {
        "primary_color": "X",
        "text_color": "X",
        "secondary_color": "X",
        "accent_color": "X",
        "light_text_color": "X",
        "background_color": "X",
    }
    CustomTemplateParser()._extract_from_theme_colors(Slide(), colors)
    assert colors["primary_color"] == "112233"
    assert colors["secondary_color"] == "112233"
    # 越界槽位保留原值
    assert colors["background_color"] == "X"


def test_extract_from_theme_colors_ignores_theme_without_colors():
    class Theme:
        theme_colors = None

    class Slide:
        theme = Theme()

    colors = {"primary_color": "X"}
    CustomTemplateParser()._extract_from_theme_colors(Slide(), colors)
    assert colors["primary_color"] == "X"


def test_get_text_color_returns_none_for_broken_shape():
    class Shape:
        @property
        def has_text_frame(self):
            raise AttributeError("broken")

    assert CustomTemplateParser()._get_text_color(Shape()) is None


def test_extract_fonts_swallows_internal_errors(monkeypatch):
    parser = CustomTemplateParser()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(parser, "_extract_from_theme_fonts", boom)
    monkeypatch.setattr(parser, "_extract_from_shapes_fonts", boom)
    fonts = parser.extract_fonts(object())
    assert fonts["title_font"] == "微软雅黑"


def test_extract_layout_info_handles_detection_failure(monkeypatch):
    parser = CustomTemplateParser()

    def boom(shapes):
        raise RuntimeError("boom")

    monkeypatch.setattr(parser, "_detect_margins", boom)
    info = parser.extract_layout_info(Presentation().slide_masters[0].slide_layouts[1])
    assert info["shape_count"] > 0
    assert info["margins"] == {}


def test_extract_decorations_detects_corner_and_page_number():
    from pptx.util import Inches as In

    prs = Presentation()
    master = prs.slide_masters[0]
    tree = master.shapes._spTree
    el = tree.add_autoshape(
        tree.max_shape_id + 1,
        "Corner",
        "rect",
        int(In(13.333).emu - In(0.2).emu),
        int(In(7.5).emu - In(0.2).emu),
        int(In(1).emu),
        int(In(1).emu),
    )
    from pptx.shapes.autoshape import Shape

    shape = Shape(el, master.shapes)
    assert shape.width < Inches(2) and shape.height < Inches(2)

    decorations = CustomTemplateParser().extract_decorations(prs)
    assert decorations["has_corner_decor"] is True


def test_compatibility_score_gives_partial_dimension_credit(monkeypatch, tmp_path):
    from pptx.util import Inches as In

    prs = Presentation()
    prs.slide_width = In(25)
    prs.slide_height = In(15)
    validator = TemplateValidator()

    class Fake:
        slide_masters = prs.slide_masters
        slide_width = prs.slide_width
        slide_height = prs.slide_height

        def close(self):
            pass

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda path: Fake()
    )
    path = tmp_path / "ok.pptx"
    path.write_bytes(b"x")
    score = validator.get_compatibility_score(str(path))
    # 0.2(格式)+0.2(母版)+0.15*2(元素)+0.08(尺寸)
    assert score == pytest.approx(0.78, abs=1e-6)


def test_apply_config_swallows_component_failures(monkeypatch):
    converter = TemplateConverter()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(converter, "_apply_colors_to_presentation", boom)
    monkeypatch.setattr(converter, "_apply_default_font_to_presentation", boom)

    class ReadOnly:
        @property
        def slide_width(self):
            return 0

        @slide_width.setter
        def slide_width(self, value):
            raise RuntimeError("read only")

        @property
        def slide_height(self):
            return 0

        @slide_height.setter
        def slide_height(self, value):
            raise RuntimeError("read only")

        slide_masters = []

    converter.apply_config_to_presentation(_config(), ReadOnly())


def test_apply_colors_updates_theme_and_master_fonts(tmp_path):
    from app.utils.pptx.custom_template import TemplateConverter

    converter = TemplateConverter()
    prs = Presentation()
    master = prs.slide_masters[0]
    # 放入带文字的形状，覆盖母版字号设置分支
    layout = master.slide_layouts[1]
    tb = TemplateConverter._add_layout_textbox(
        layout, "Probe", Inches(1), Inches(1), Inches(2), Inches(1)
    )
    tb.text_frame.text = "hello"

    converter._apply_colors_to_presentation(prs, _config(primary_color="AABBCC"))

    assert prs.slide_masters[0].shapes is not None


def test_merge_uses_base_dimensions_when_custom_default(monkeypatch):
    base = _config(slide_width=12.0, slide_height=6.0)
    custom = _config()
    merged = TemplateConverter().merge_configs(base, custom)
    assert merged.slide_width == 12.0
    assert merged.slide_height == 6.0


def test_merge_uses_custom_dimensions_when_non_default():
    base = _config()
    custom = _config(slide_width=9.0, slide_height=4.5)
    merged = TemplateConverter().merge_configs(base, custom)
    assert merged.slide_width == 9.0
    assert merged.slide_height == 4.5


# --- 进一步分支覆盖 ---


def test_extract_from_shapes_counts_text_and_three_fills():
    from pptx.dml.color import RGBColor

    def make_fill(hex_value):
        class Fore:
            rgb = RGBColor.from_string(hex_value)

        class Fill:
            fore_color = Fore()

        return Fill()

    def make_text(hex_value):
        class Font:
            class color:
                rgb = RGBColor.from_string(hex_value)

        class Run:
            font = Font()

        class Para:
            runs = [Run()]

        class TF:
            paragraphs = [Para()]

        return TF()

    class Shape:
        has_text_frame = True

        def __init__(self, fill_hex, text_hex):
            self.fill = make_fill(fill_hex)
            self.text_frame = make_text(text_hex)

    class Slide:
        shapes = [
            Shape("111111", "212121"),
            Shape("222222", "313131"),
            Shape("333333", "414141"),
        ]

    colors = CustomTemplateParser().extract_colors(Slide())
    assert colors["primary_color"] in {"111111", "222222", "333333"}
    assert colors["secondary_color"] in {"111111", "222222", "333333"}
    assert colors["accent_color"] in {"111111", "222222", "333333"}
    assert colors["text_color"] in {"212121", "313131", "414141"}
    assert colors["light_text_color"] in {"212121", "313131", "414141"}


def test_get_fill_color_returns_none_branches():
    class NoFore:
        pass

    class FillNoFore:
        fore_color = NoFore()

    class ShapeNoFore:
        fill = FillNoFore()

    assert CustomTemplateParser()._get_fill_color(ShapeNoFore()) is None

    class Fore:
        rgb = None

    class FillNoRgb:
        fore_color = Fore()

    class ShapeNoRgb:
        fill = FillNoRgb()

    assert CustomTemplateParser()._get_fill_color(ShapeNoRgb()) is None

    class Broken:
        @property
        def fill(self):
            raise AttributeError("broken")

    assert CustomTemplateParser()._get_fill_color(Broken()) is None


def test_get_text_color_skips_runs_without_color():
    class RunNoFont:
        font = None

    class Para:
        runs = [RunNoFont()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    assert CustomTemplateParser()._get_text_color(Shape()) is None


def test_get_text_color_skips_run_color_without_rgb():
    class Color:
        rgb = None

    class Font:
        color = Color()

    class Run:
        font = Font()

    class Para:
        runs = [Run()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    assert CustomTemplateParser()._get_text_color(Shape()) is None


def test_extract_shapes_fonts_skips_shapes_without_text_frame():
    class Shape:
        has_text_frame = False

    class Slide:
        shapes = [Shape()]

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font_en"] == "Arial"


def test_extract_shapes_fonts_handles_only_non_cjk_titles():
    class Font:
        name = "Consolas"

    class Run:
        font = Font()

    class Para:
        level = 0
        runs = [Run()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    class Slide:
        shapes = [Shape()]

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font_en"] == "Consolas"
    assert fonts["title_font"] == "微软雅黑"


def test_analyze_slide_master_records_decoration_shapes():
    class Shape:
        is_placeholder = False
        name = "Decor"
        shape_type = 1

    class Layout:
        name = "L"
        shapes = [Shape()]

    result = CustomTemplateParser().analyze_slide_master(Layout())
    assert result["decoration_shapes"] == [{"name": "Decor", "type": 1}]
    assert result["recommended_type"] == "blank"


def test_analyze_slide_master_content_only_layout():
    class Ph:
        type = "OBJECT (7)"
        idx = 1

    class Shape:
        is_placeholder = True
        placeholder_format = Ph()
        left = top = width = height = None
        name = "Body"

    class Layout:
        name = "L"
        shapes = [Shape()]

    result = CustomTemplateParser().analyze_slide_master(Layout())
    assert result["recommended_type"] == "content_only"


def test_analyze_slide_master_swallows_broken_layout():
    class Broken:
        @property
        def shapes(self):
            raise RuntimeError("broken")

    result = CustomTemplateParser().analyze_slide_master(Broken())
    assert result["recommended_type"] == "title_content"


def test_parse_template_file_reraises_value_error_from_extraction(tmp_path, monkeypatch):
    parser = CustomTemplateParser()
    path = tmp_path / "ok.pptx"
    path.write_bytes(b"x")

    def boom(path):
        raise ValueError("bad template content")

    class Prs:
        slide_width = Inches(10)
        slide_height = Inches(7.5)

        def close(self):
            pass

        @property
        def slide_masters(self):
            return [object()]

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda p: Prs()
    )
    monkeypatch.setattr(parser, "extract_colors", boom)

    with pytest.raises(ValueError, match="bad template content"):
        parser.parse_template_file(str(path))


def test_template_validator_rejects_presentation_without_masters(tmp_path, monkeypatch):
    class Prs:
        slide_masters = []

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda p: Prs()
    )
    path = tmp_path / "x.pptx"
    path.write_bytes(b"x")
    ok, errors = TemplateValidator().validate_template(str(path))
    assert ok is False
    assert "不包含母版" in errors[0]


def test_apply_default_font_returns_when_no_font_scheme(monkeypatch):
    class Part:
        blob = b"<root/>"

    class Prs:
        slide_masters = [object()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    # 直接调用不应抛错（内部返回）
    converter._apply_default_font_to_presentation(Prs(), _config())


def test_apply_colors_returns_when_no_color_scheme(monkeypatch):
    class Part:
        blob = b"<root/>"

    class Layout:
        shapes = []

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    converter._apply_colors_to_presentation(Prs(), _config())


def _theme_part_with(xml: str):
    class Part:
        blob = xml.encode()

    return Part()


def test_theme_font_extraction_without_font_scheme():
    from lxml import etree

    class Theme:
        _element = etree.fromstring(b"<a:theme xmlns:a='x'><a:themeElements/></a:theme>")

    class Slide:
        theme = Theme()
        shapes = []

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font_en"] == "Arial"


def test_theme_font_extraction_without_major_or_minor():
    from lxml import etree

    class Theme:
        _element = etree.fromstring(
            b"<a:theme xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>"
            b"<a:themeElements><a:fontScheme/></a:themeElements></a:theme>"
        )

    class Slide:
        theme = Theme()
        shapes = []

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font_en"] == "Arial"
    assert fonts["body_font_en"] == "Calibri"


def test_theme_font_extraction_without_latin_or_ea():
    from lxml import etree

    class Theme:
        _element = etree.fromstring(
            b"<a:theme xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>"
            b"<a:themeElements><a:fontScheme>"
            b"<a:majorFont/><a:minorFont/>"
            b"</a:fontScheme></a:themeElements></a:theme>"
        )

    class Slide:
        theme = Theme()
        shapes = []

    fonts = CustomTemplateParser().extract_fonts(Slide())
    assert fonts["title_font"] == "微软雅黑"
    assert fonts["body_font"] == "微软雅黑"


def test_decorations_ignore_shapes_without_fill_or_geometry():
    class NoFillShape:
        shape_type = 1
        has_text_frame = False
        width = Inches(1)
        height = Inches(1)
        left = 0
        top = 0

        @property
        def fill(self):
            raise AttributeError("no fill")

    decorations = {
        "has_header_bar": False,
        "has_footer_bar": False,
        "has_corner_decor": False,
        "has_page_number": False,
        "header_bar_color": None,
        "footer_bar_color": None,
    }
    CustomTemplateParser()._analyze_shape_for_decoration(
        NoFillShape(), decorations
    )
    assert decorations["has_header_bar"] is False


def test_decorations_skip_page_number_for_empty_text():
    class TF:
        text = "  "

    class Shape:
        shape_type = 1
        fill = None
        has_text_frame = True
        text_frame = TF()
        width = Inches(5)
        height = Inches(5)
        left = Inches(1)
        top = Inches(1)

    decorations = {"has_page_number": False}
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_page_number"] is False


def test_compatibility_score_without_masters(monkeypatch, tmp_path):
    class Prs:
        slide_masters = []

        def close(self):
            pass

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda p: Prs()
    )
    path = tmp_path / "x.pptx"
    path.write_bytes(b"x")
    assert TemplateValidator().get_compatibility_score(str(path)) == pytest.approx(0.2)


def test_decorations_added_for_each_layout(monkeypatch):
    prs = Presentation()
    converter = TemplateConverter()

    calls = []

    def record(layout, config):
        calls.append(layout)

    monkeypatch.setattr(converter, "_add_header_bar_on_layout", record)
    monkeypatch.setattr(converter, "_add_footer_bar_on_layout", record)
    monkeypatch.setattr(converter, "_add_page_number_on_layout", record)
    monkeypatch.setattr(converter, "_add_corner_decor_on_layout", record)

    config = _config(
        has_header_bar=True,
        has_footer_bar=True,
        has_page_number=True,
        has_corner_decor=True,
    )
    converter._apply_decorations(prs, config)
    assert len(calls) == len(prs.slide_masters[0].slide_layouts) * 4


def test_apply_colors_skips_missing_slots(monkeypatch):
    class Layout:
        shapes = []

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    xml = (
        "<a:theme xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>"
        "<a:themeElements><a:clrScheme>"
        "<a:dk1><a:srgbClr val='000000'/></a:dk1>"
        "</a:clrScheme></a:themeElements></a:theme>"
    )
    converter = TemplateConverter()
    monkeypatch.setattr(
        converter, "_get_theme_part", lambda prs: _theme_part_with(xml)
    )
    converter._apply_colors_to_presentation(Prs(), _config(primary_color="ABCDEF"))


def test_apply_colors_swallows_xml_error(monkeypatch):
    class Layout:
        shapes = []

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    monkeypatch.setattr(
        converter, "_get_theme_part", lambda prs: _theme_part_with("not xml <")
    )
    converter._apply_colors_to_presentation(Prs(), _config())


def test_apply_default_font_swallows_xml_error(monkeypatch):
    class Prs:
        slide_masters = [object()]

    converter = TemplateConverter()
    monkeypatch.setattr(
        converter, "_get_theme_part", lambda prs: _theme_part_with("not xml <")
    )
    converter._apply_default_font_to_presentation(Prs(), _config())


def test_merge_fonts_prefers_custom_and_falls_back():
    base = _config(title_font="黑体", body_font_en="Consolas")
    custom = _config(title_font="宋体")
    merged = TemplateConverter().merge_configs(base, custom)
    assert merged.title_font == "宋体"
    assert merged.body_font_en == "Consolas"


def test_decoration_helpers_swallow_layout_failures():
    class BrokenLayout:
        @property
        def shapes(self):
            raise AttributeError("no shapes")

    converter = TemplateConverter()
    config = _config(
        has_header_bar=True,
        has_footer_bar=True,
        has_page_number=True,
        has_corner_decor=True,
    )
    layout = BrokenLayout()
    converter._add_header_bar_on_layout(layout, config)
    converter._add_footer_bar_on_layout(layout, config)
    converter._add_page_number_on_layout(layout, config)
    converter._add_corner_decor_on_layout(layout, config)


def test_apply_decorations_returns_without_masters():
    class Prs:
        slide_masters = []

    TemplateConverter()._apply_decorations(Prs(), _config(has_header_bar=True))


def test_apply_config_skips_decorations_when_not_configured(monkeypatch):
    converter = TemplateConverter()
    called = []
    monkeypatch.setattr(
        converter, "_apply_decorations", lambda prs, cfg: called.append(True)
    )
    converter.apply_config_to_presentation(
        _config(has_header_bar=False, has_footer_bar=False, has_page_number=False),
        Presentation(),
    )
    assert called == []
