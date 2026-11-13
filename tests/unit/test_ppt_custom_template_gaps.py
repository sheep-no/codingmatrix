"""Additional branch coverage for custom_template parser/validator/converter."""

import pytest
from pptx import Presentation
from pptx.util import Inches

from app.utils.pptx.custom_template import (
    CustomTemplateParser,
    TemplateConverter,
    TemplateValidator,
)
from app.utils.pptx.templates import TemplateCategory, TemplateConfig


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


# --- _get_fill_color ---


def test_get_fill_color_returns_none_when_fill_missing():
    class Shape:
        fill = None

    assert CustomTemplateParser()._get_fill_color(Shape()) is None


def test_get_fill_color_returns_none_without_fore_color_attr():
    class Shape:
        fill = object()

    assert CustomTemplateParser()._get_fill_color(Shape()) is None


# --- _get_placeholder_info ---


def test_get_placeholder_info_swallows_geometry_errors():
    class Ph:
        idx = 1
        type = "TITLE (1)"

    class Shape:
        is_placeholder = True
        placeholder_format = Ph()
        name = "T"

        @property
        def left(self):
            raise AttributeError("no geometry")

        top = width = height = None

    info = CustomTemplateParser()._get_placeholder_info(Shape())
    assert info["left"] == 0.0
    assert info["type"] == "title"


def test_get_placeholder_info_returns_none_for_broken_shape():
    class Shape:
        @property
        def is_placeholder(self):
            raise AttributeError("broken")

    assert CustomTemplateParser()._get_placeholder_info(Shape()) is None


# --- _detect_margins ---


def test_detect_margins_skips_shapes_raising_attribute_error():
    class Shape:
        @property
        def is_placeholder(self):
            raise AttributeError("broken")

    assert CustomTemplateParser()._detect_margins([Shape()]) == {}


# --- _analyze_shape_for_decoration ---


def test_analyze_shape_for_decoration_swallows_errors():
    class Shape:
        @property
        def shape_type(self):
            raise AttributeError("broken")

    decorations = {"has_header_bar": False}
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_header_bar"] is False


# --- generate_template_config ---


def test_generate_template_config_skips_unmappable_layout(monkeypatch):
    parser = CustomTemplateParser()
    parser._extracted_colors = {"primary_color": "112233"}
    parser._extracted_layouts = {"custom": {"recommended_type": "nope"}}

    def boom(_rec_type):
        raise ValueError("unmapped")

    monkeypatch.setattr(parser, "_map_layout_type", boom)
    config = parser.generate_template_config()
    assert config.layouts == {}


# --- compatibility score ---


def _fake_prs(*, width=Inches(10), height=Inches(7.5), layouts=None):
    class Shape:
        is_placeholder = False
        has_text_frame = True

        class TF:
            class Para:
                class Run:
                    class Font:
                        name = "Arial"

                    font = Font()

                runs = [Run()]

            paragraphs = [Para()]

        text_frame = TF()

    class Layout:
        def __init__(self, shapes):
            self.shapes = shapes

    class Master:
        def __init__(self, items):
            self.slide_layouts = items

    class Prs:
        slide_width = width
        slide_height = height
        slide_masters = [Master(layouts if layouts is not None else [Layout([Shape()])])]

        def close(self):
            pass

    return Prs()


def test_compatibility_score_credits_valid_font(monkeypatch, tmp_path):
    def fake(path):
        prs = _fake_prs()
        for layout in prs.slide_masters[0].slide_layouts:
            for shape in layout.shapes:
                shape.has_text_frame = True
        return prs

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", fake
    )
    path = tmp_path / "ok.pptx"
    path.write_bytes(b"x")
    score = TemplateValidator().get_compatibility_score(str(path))
    # 0.2 + 0.2 + 0.15(尺寸) + 0.15(字体) = 0.7
    assert score == pytest.approx(0.7)


def test_compatibility_score_without_title_placeholder(monkeypatch, tmp_path):
    class Shape:
        is_placeholder = False
        has_text_frame = False

    class Layout:
        shapes = [Shape()]

    class Master:
        slide_layouts = [Layout()]

    prs = _fake_prs(layouts=[Layout()])
    prs.slide_masters = [Master()]
    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda path: prs
    )
    path = tmp_path / "ok.pptx"
    path.write_bytes(b"x")
    score = TemplateValidator().get_compatibility_score(str(path))
    # 0.2 + 0.2 + 0.15(尺寸) = 0.55
    assert score == pytest.approx(0.55)


def test_compatibility_score_oversized_dimensions_get_no_size_credit(monkeypatch, tmp_path):
    class Shape:
        is_placeholder = False
        has_text_frame = False

    class Layout:
        shapes = [Shape()]

    class Master:
        slide_layouts = [Layout()]

    prs = _fake_prs(width=Inches(40), height=Inches(30), layouts=[Layout()])
    prs.slide_masters = [Master()]
    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda path: prs
    )
    path = tmp_path / "ok.pptx"
    path.write_bytes(b"x")
    score = TemplateValidator().get_compatibility_score(str(path))
    assert score == pytest.approx(0.4)


# --- apply colors / fonts ---


def test_apply_colors_returns_without_theme_part(monkeypatch):
    class Layout:
        shapes = []

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: None)
    converter._apply_colors_to_presentation(Prs(), _config())


def test_apply_colors_swallows_layout_iteration_error(monkeypatch):
    class Part:
        blob = (
            b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            b"<a:themeElements><a:clrScheme>"
            b"<a:dk1><a:srgbClr val=\"000000\"/></a:dk1>"
            b"</a:clrScheme></a:themeElements></a:theme>"
        )

    class Master:
        @property
        def slide_layouts(self):
            raise RuntimeError("broken layouts")

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    converter._apply_colors_to_presentation(Prs(), _config())


def test_apply_default_font_returns_without_theme_part(monkeypatch):
    class Prs:
        slide_masters = [object()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: None)
    converter._apply_default_font_to_presentation(Prs(), _config())


def test_get_theme_part_returns_none_without_theme_rel():
    class Rel:
        reltype = "http://example.com/other"

    class Part:
        rels = {"rId1": Rel()}

    class Master:
        part = Part()

    class Prs:
        slide_masters = [Master()]

    assert TemplateConverter._get_theme_part(Prs()) is None


# --- decoration flag combinations ---


@pytest.mark.parametrize(
    "flags",
    [
        dict(has_header_bar=True, has_footer_bar=False, has_page_number=False, has_corner_decor=False),
        dict(has_header_bar=False, has_footer_bar=True, has_page_number=False, has_corner_decor=False),
        dict(has_header_bar=False, has_footer_bar=False, has_page_number=True, has_corner_decor=False),
        dict(has_header_bar=False, has_footer_bar=False, has_page_number=False, has_corner_decor=True),
    ],
)
def test_apply_decorations_handles_each_flag(monkeypatch, flags):
    converter = TemplateConverter()
    calls = []

    for name in ("_add_header_bar_on_layout", "_add_footer_bar_on_layout",
                 "_add_page_number_on_layout", "_add_corner_decor_on_layout"):
        monkeypatch.setattr(converter, name, lambda layout, config, n=name: calls.append(n))

    class Layout:
        pass

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    converter._apply_decorations(Prs(), _config(**flags))
    assert len(calls) == 1


# --- merge ---


def test_merge_uses_base_values_when_custom_matches_defaults():
    base = _config(primary_color="AABBCC", title_font="BaseFont")
    custom = _config(primary_color="1F4E79", title_font="微软雅黑")
    merged = TemplateConverter().merge_configs(base, custom)
    assert merged.primary_color == "AABBCC"
    assert merged.title_font == "BaseFont"


# --- extra conditional branches ---


def test_extract_shapes_uses_single_text_color_without_light_fallback():
    from pptx.dml.color import RGBColor

    class Font:
        class color:
            rgb = RGBColor(0x12, 0x34, 0x56)

    class Run:
        font = Font()

    class Para:
        runs = [Run()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()
        fill = None

    class Slide:
        shapes = [Shape()]

    colors = CustomTemplateParser().extract_colors(Slide())
    assert colors["text_color"] == "123456"
    assert colors["light_text_color"] == "666666"


def test_extract_from_theme_fonts_ignores_slide_without_theme():
    fonts = {
        "title_font": "微软雅黑",
        "body_font": "微软雅黑",
        "title_font_en": "Arial",
        "body_font_en": "Calibri",
    }

    class Slide:
        pass

    CustomTemplateParser()._extract_from_theme_fonts(Slide(), fonts)
    assert fonts["title_font"] == "微软雅黑"


def test_extract_theme_colors_falls_back_when_theme_colors_none():
    class Master:
        class theme:
            theme_colors = None

    class Prs:
        slide_masters = [Master()]

    colors = CustomTemplateParser().extract_theme_colors(Prs())
    assert len(colors) == 12
    assert colors[0] == "1F4E79"


def test_apply_colors_leaves_blob_when_no_slots_match(monkeypatch):
    class Part:
        blob = (
            b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            b"<a:themeElements><a:clrScheme/></a:themeElements></a:theme>"
        )

    class Layout:
        shapes = []

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    part = Part()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: part)
    converter._apply_colors_to_presentation(Prs(), _config())
    assert b"<a:clrScheme/>" in part.blob


def _font_scheme_xml(body: str) -> bytes:
    return (
        b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        b"<a:themeElements><a:fontScheme>"
        + body.encode()
        + b"</a:fontScheme></a:themeElements></a:theme>"
    )


def test_apply_default_font_skips_missing_font_element(monkeypatch):
    class Part:
        blob = _font_scheme_xml("")

    class Prs:
        slide_masters = [object()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    converter._apply_default_font_to_presentation(Prs(), _config())


def test_apply_default_font_handles_missing_latin_and_ea(monkeypatch):
    body = '<a:majorFont><a:latin typeface="X"/></a:majorFont><a:minorFont><a:ea typeface="Y"/></a:minorFont>'

    class Part:
        blob = _font_scheme_xml(body)

    class Prs:
        slide_masters = [object()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    converter._apply_default_font_to_presentation(Prs(), _config())


def test_generate_template_config_maps_layers_and_spacing():
    parser = CustomTemplateParser()
    parser._extracted_colors = {"primary_color": "112233"}
    parser._extracted_decorations = {"margins": {"body_margin_left": 1.2}}
    parser._extracted_layouts = {"main": {"recommended_type": "title_content"}}

    config = parser.generate_template_config()

    assert config.slide_margin == 1.2
    assert config.layouts


def test_extract_shapes_fonts_cjk_only_title_and_non_cjk_body():
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
        def __init__(self, paras):
            self.paragraphs = paras

    class Shape:
        has_text_frame = True

        def __init__(self, paras):
            self.text_frame = TF(paras)

    class Slide:
        shapes = [Shape([Para(0, "微软雅黑"), Para(1, "Arial")])]

    fonts = {}
    CustomTemplateParser()._extract_from_shapes_fonts(Slide(), fonts)
    assert fonts["title_font"] == "微软雅黑"
    assert "title_font_en" not in fonts
    assert fonts["body_font_en"] == "Arial"
    assert "body_font" not in fonts


def test_detect_margins_zero_offsets_skips_both_fields():
    class Ph:
        type = "TITLE (1)"

    class Shape:
        is_placeholder = True
        placeholder_format = Ph()
        left = 0
        top = 0
        height = 0

    margins = CustomTemplateParser()._detect_margins([Shape()])
    assert margins == {}


def test_analyze_shape_without_position_skips_bar_detection():
    class Shape:
        shape_type = 1
        fill = object()
        has_text_frame = False
        width = 10
        height = 10

    decorations = {
        "has_header_bar": False,
        "has_footer_bar": False,
        "has_page_number": False,
        "has_corner_decor": False,
    }
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_header_bar"] is False


def test_analyze_shape_at_top_without_fill_color():
    class Shape:
        shape_type = 1
        top = 0
        has_text_frame = False
        width = 10 ** 8
        height = 10 ** 8

        class fill:
            class fore_color:
                rgb = None

    decorations = {
        "has_header_bar": False,
        "has_footer_bar": False,
        "has_page_number": False,
        "has_corner_decor": False,
    }
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_header_bar"] is False


def test_analyze_shape_at_bottom_without_fill_color():
    class Shape:
        shape_type = 1
        top = 10 ** 9
        has_text_frame = False
        width = 10 ** 8
        height = 10 ** 8

        class fill:
            class fore_color:
                rgb = None

    decorations = {
        "has_header_bar": False,
        "has_footer_bar": False,
        "has_page_number": False,
        "has_corner_decor": False,
    }
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_footer_bar"] is False


def test_analyze_slide_master_skips_placeholder_without_info(monkeypatch):
    parser = CustomTemplateParser()
    monkeypatch.setattr(parser, "_get_placeholder_info", lambda shape: None)

    class Shape:
        is_placeholder = True

    class Layout:
        name = "L"
        shapes = [Shape()]

    result = parser.analyze_slide_master(Layout())
    assert result["placeholders"] == []


def test_check_required_elements_reports_missing_for_empty_placeholders(monkeypatch, tmp_path):
    class Shape:
        is_placeholder = False

    class Layout:
        shapes = [Shape()]

    class Master:
        slide_layouts = [Layout()]

    class Prs:
        slide_masters = [Master()]

    monkeypatch.setattr(
        "app.utils.pptx.custom_template.PptxPresentation", lambda path: Prs()
    )
    path = tmp_path / "empty.pptx"
    path.write_bytes(b"x")
    assert TemplateValidator().check_required_elements(str(path)) == ["title", "body"]


def test_apply_colors_skips_shapes_without_text_and_runs_without_font(monkeypatch):
    class Run:
        font = None

    class Para:
        runs = [Run()]

    class TF:
        paragraphs = [Para()]

    class TextShape:
        has_text_frame = True
        text_frame = TF()

    class PlainShape:
        has_text_frame = False

    class Layout:
        shapes = [TextShape(), PlainShape()]

    class Master:
        slide_layouts = [Layout()]

    class Part:
        blob = (
            b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            b"<a:themeElements><a:clrScheme/>"
            b"</a:themeElements></a:theme>"
        )

    class Prs:
        slide_masters = [Master()]

    converter = TemplateConverter()
    monkeypatch.setattr(converter, "_get_theme_part", lambda prs: Part())
    converter._apply_colors_to_presentation(Prs(), _config())


def test_merge_with_empty_base_colors_and_fonts_keeps_defaults():
    base = _config()
    base.primary_color = ""
    base.title_font = ""
    custom = _config(primary_color="1F4E79", title_font="微软雅黑")
    merged = TemplateConverter().merge_configs(base, custom)
    assert merged.primary_color == "1F4E79"
    assert merged.title_font == "微软雅黑"


def test_extract_shapes_uses_second_and_third_colors():
    from pptx.dml.color import RGBColor

    class Fill:
        def __init__(self, rgb):
            class Fore:
                pass

            fore = Fore()
            fore.rgb = rgb
            self.fore_color = fore

    class Shape:
        has_text_frame = False

        def __init__(self, rgb):
            self.fill = Fill(rgb)

    class Slide:
        shapes = [
            Shape(RGBColor(0x11, 0x11, 0x11)),
            Shape(RGBColor(0x22, 0x22, 0x22)),
            Shape(RGBColor(0x33, 0x33, 0x33)),
        ]

    colors = CustomTemplateParser().extract_colors(Slide())
    assert colors["primary_color"] == "111111"
    assert colors["secondary_color"] == "222222"
    assert colors["accent_color"] == "333333"


def test_get_text_color_continues_after_run_without_color():
    from pptx.dml.color import RGBColor

    class NoColorFont:
        pass

    class ColorFont:
        class color:
            rgb = RGBColor(0xAB, 0xCD, 0xEF)

    class RunA:
        font = NoColorFont()

    class RunB:
        font = ColorFont()

    class Para:
        runs = [RunA(), RunB()]

    class TF:
        paragraphs = [Para()]

    class Shape:
        has_text_frame = True
        text_frame = TF()

    assert CustomTemplateParser()._get_text_color(Shape()) == "ABCDEF"


def test_extract_from_theme_fonts_skips_theme_without_element():
    class Theme:
        pass

    class Slide:
        theme = Theme()

    fonts = {"title_font": "原值"}
    CustomTemplateParser()._extract_from_theme_fonts(Slide(), fonts)
    assert fonts["title_font"] == "原值"


def test_extract_shapes_fonts_body_cjk_without_english():
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
        def __init__(self, paras):
            self.paragraphs = paras

    class Shape:
        has_text_frame = True

        def __init__(self, paras):
            self.text_frame = TF(paras)

    class Slide:
        shapes = [Shape([Para(1, "微软雅黑")])]

    fonts = {}
    CustomTemplateParser()._extract_from_shapes_fonts(Slide(), fonts)
    assert fonts["body_font"] == "微软雅黑"
    assert "body_font_en" not in fonts


def test_extract_layout_info_skips_placeholder_without_info(monkeypatch):
    parser = CustomTemplateParser()
    monkeypatch.setattr(parser, "_get_placeholder_info", lambda shape: None)

    class Shape:
        is_placeholder = True

    class Slide:
        shapes = [Shape()]

    info = parser.extract_layout_info(Slide())
    assert info["placeholders"] == []


def test_detect_margins_continues_after_non_placeholder():
    class Plain:
        is_placeholder = False

    class BodyPh:
        type = "OBJECT (7)"

    class Body:
        is_placeholder = True
        placeholder_format = BodyPh()
        left = 0
        top = 0

    margins = CustomTemplateParser()._detect_margins([Plain(), Body()])
    assert margins == {}


def test_detect_margins_body_with_left_only():
    class BodyPh:
        type = "OBJECT (7)"

    class Body:
        is_placeholder = True
        placeholder_format = BodyPh()
        left = Inches(1)
        top = 0

    margins = CustomTemplateParser()._detect_margins([Body()])
    assert margins["body_margin_left"] == pytest.approx(1.0)
    assert "body_margin_top" not in margins


def test_analyze_shape_without_dimensions_skips_corner_detection():
    class Shape:
        shape_type = None
        has_text_frame = False

    decorations = {"has_corner_decor": False}
    CustomTemplateParser()._analyze_shape_for_decoration(Shape(), decorations)
    assert decorations["has_corner_decor"] is False
