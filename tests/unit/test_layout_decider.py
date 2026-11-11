import logging

import pytest
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.utils.pptx.ppt_style import PPTStyle
from app.utils.visual.image_manager import ImageAsset, ImageSource
from app.utils.visual.layout_decider import (
    LayoutDecider,
    LayoutElement,
    LayoutType,
    SlideLayoutPlan,
    layout_type_for_slide_type,
)
from app.utils.visual.visual_analyzer import (
    ImageDecision,
    ImagePosition,
    ImageType,
    SlideVisualDecision,
)


SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5


def _decision(*, images=None, content="正文", add_decoration=False):
    return SlideVisualDecision(
        slide_index=1,
        title="标题",
        content_summary=content,
        images=images or [],
        add_decoration=add_decoration,
    )


def _plan(decision, semantic_slide_type=None):
    return LayoutDecider().plan_slide_layout(
        decision,
        page_number=2,
        total_pages=9,
        semantic_slide_type=semantic_slide_type,
    )


def _presentation():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH)
    prs.slide_height = Inches(SLIDE_HEIGHT)
    return prs


def _elements(plan, element_type):
    return [element for element in plan.elements if element.element_type == element_type]


@pytest.mark.parametrize(
    ("slide_type", "has_image", "expected"),
    [
        ("cover", False, LayoutType.TITLE_SLIDE),
        ("title", False, LayoutType.TITLE_SLIDE),
        ("section", False, LayoutType.TITLE_SLIDE),
        ("closing", False, LayoutType.TITLE_SLIDE),
        ("comparison", False, LayoutType.TWO_COLUMN),
        ("timeline", False, LayoutType.TWO_COLUMN),
        ("process", False, LayoutType.TWO_COLUMN),
        ("summary", False, LayoutType.CENTER_FOCUS),
        ("image_text", True, LayoutType.CONTENT_WITH_IMAGE),
        ("image_text", False, LayoutType.CONTENT_ONLY),
        ("key_points", False, LayoutType.CONTENT_ONLY),
        (None, False, LayoutType.CONTENT_ONLY),
        ("unknown-type", False, LayoutType.CONTENT_ONLY),
    ],
)
def test_layout_type_mapping(slide_type, has_image, expected):
    assert layout_type_for_slide_type(slide_type, has_image=has_image) == expected


def test_content_only_plan_contains_title_separator_and_content():
    plan = _plan(_decision())
    assert plan.layout_type == LayoutType.CONTENT_ONLY
    assert [element.element_type for element in plan.elements] == ["title", "line", "content"]
    assert plan.page_number == 2
    assert plan.total_pages == 9


def test_content_only_plan_can_omit_separator():
    decision = _decision()
    decision.has_separator_line = False
    plan = _plan(decision)
    assert _elements(plan, "line") == []


@pytest.mark.parametrize(
    "position",
    [
        ImagePosition.LEFT,
        ImagePosition.RIGHT,
        ImagePosition.CENTER,
        ImagePosition.TOP,
        ImagePosition.TOP_RIGHT,
        ImagePosition.TOP_LEFT,
        ImagePosition.BOTTOM,
        ImagePosition.INLINE,
    ],
)
def test_image_positions_keep_elements_inside_slide(position):
    image = ImageDecision(image_type=ImageType.PHOTO, position=position, width_ratio=0.4)
    plan = _plan(_decision(images=[image]))
    image_elements = _elements(plan, "image")
    assert len(image_elements) == 1
    for element in plan.elements:
        assert element.left >= 0
        assert element.top >= 0
        assert element.width > 0
        assert element.height > 0
        assert element.left + element.width <= Inches(SLIDE_WIDTH)
        assert element.top + element.height <= Inches(SLIDE_HEIGHT)


def test_background_image_is_not_rendered_as_foreground_element():
    image = ImageDecision(image_type=ImageType.PHOTO, position=ImagePosition.BACKGROUND)
    plan = _plan(_decision(images=[image]))
    assert _elements(plan, "image") == []
    content = _elements(plan, "content")[0]
    assert content.width == Inches(12.333)


@pytest.mark.parametrize("ratio", [-0.5, 0, 1.5, 5, float("nan"), "bad"])
def test_invalid_width_ratio_never_produces_negative_geometry(ratio):
    image = ImageDecision(image_type=ImageType.PHOTO, position=ImagePosition.LEFT, width_ratio=ratio)
    plan = _plan(_decision(images=[image]))
    image_element = _elements(plan, "image")[0]
    content = _elements(plan, "content")[0]
    assert image_element.width > 0
    assert content.width > 0
    assert content.left >= 0
    assert content.left + content.width <= Inches(SLIDE_WIDTH)


def test_centered_image_content_stays_inside_slide():
    image = ImageDecision(image_type=ImageType.PHOTO, position=ImagePosition.CENTER)
    content = _elements(_plan(_decision(images=[image])), "content")[0]
    assert content.top + content.height <= Inches(SLIDE_HEIGHT)


def test_inline_image_content_stays_inside_slide():
    image = ImageDecision(image_type=ImageType.PHOTO, position=ImagePosition.INLINE)
    content = _elements(_plan(_decision(images=[image])), "content")[0]
    assert content.top + content.height <= Inches(SLIDE_HEIGHT)


def test_decoration_only_image_is_not_treated_as_main_image():
    decoration = ImageDecision(
        image_type=ImageType.ICON,
        position=ImagePosition.CORNER,
        is_decoration=True,
    )
    decision = _decision(images=[decoration])
    assert decision.need_image is False
    assert decision.get_main_image() is None

    plan = _plan(decision, semantic_slide_type="image_text")
    assert plan.layout_type == LayoutType.CONTENT_ONLY
    image_elements = _elements(plan, "image")
    assert len(image_elements) == 1
    assert image_elements[0].properties["opacity"] == pytest.approx(0.3)


def test_main_image_skips_decorations():
    decoration = ImageDecision(image_type=ImageType.ICON, is_decoration=True)
    photo = ImageDecision(image_type=ImageType.PHOTO, position=ImagePosition.RIGHT)
    decision = _decision(images=[decoration, photo])
    assert decision.need_image is True
    assert decision.get_main_image() is photo


@pytest.mark.parametrize(
    ("position", "expected_left", "expected_top"),
    [
        (ImagePosition.CORNER, SLIDE_WIDTH - 0.4 * SLIDE_WIDTH, SLIDE_HEIGHT - 0.4 * SLIDE_HEIGHT),
        (ImagePosition.TOP_RIGHT, SLIDE_WIDTH - 0.4 * SLIDE_WIDTH, 0),
        (ImagePosition.TOP_LEFT, 0, 0),
        (ImagePosition.BOTTOM, (SLIDE_WIDTH - 0.4 * SLIDE_WIDTH) / 2, SLIDE_HEIGHT - 0.4 * SLIDE_HEIGHT),
        (ImagePosition.TOP, (SLIDE_WIDTH - 0.4 * SLIDE_WIDTH) / 2, 0),
        (ImagePosition.RIGHT, SLIDE_WIDTH - 0.4 * SLIDE_WIDTH, SLIDE_HEIGHT - 0.4 * SLIDE_HEIGHT),
    ],
)
def test_decoration_positions(position, expected_left, expected_top):
    decoration = ImageDecision(
        image_type=ImageType.ICON,
        position=position,
        width_ratio=0.4,
        description="装饰",
        keywords=["deco"],
        is_decoration=True,
    )
    plan = _plan(_decision(images=[decoration]))
    element = _elements(plan, "image")[0]
    assert element.left.inches == pytest.approx(expected_left, abs=1e-4)
    assert element.top.inches == pytest.approx(expected_top, abs=1e-4)
    assert element.properties["image_description"] == "装饰"
    assert element.properties["image_keywords"] == ["deco"]
    assert element.properties["opacity"] == pytest.approx(0.3)


def test_semantic_cover_geometry_centers_title_and_content():
    plan = _plan(_decision(content="副标题"), semantic_slide_type="cover")
    title = _elements(plan, "title")[0]
    content = _elements(plan, "content")[0]
    assert title.properties["alignment"] == "center"
    assert title.properties["font_size"] >= 32
    assert title.left == Inches(1.2)
    assert title.top == Inches(2.0)
    assert content.properties["alignment"] == "center"
    assert content.left == Inches(2.0)
    assert content.top == Inches(4.0)


def test_semantic_center_focus_geometry():
    plan = _plan(_decision(content=["结论"]), semantic_slide_type="summary")
    title = _elements(plan, "title")[0]
    content = _elements(plan, "content")[0]
    assert title.left == Inches(1.6)
    assert title.width == Inches(10.1)
    assert content.top == Inches(2.0)
    assert content.properties["alignment"] == "center"


def test_semantic_two_column_splits_odd_items():
    plan = _plan(_decision(content=["一", "二", "三"]), semantic_slide_type="comparison")
    columns = _elements(plan, "content")
    assert len(columns) == 2
    assert columns[0].properties["items"] == ["一", "二"]
    assert columns[1].properties["items"] == ["三"]


def test_semantic_two_column_wraps_string_content():
    plan = _plan(_decision(content="单条"), semantic_slide_type="comparison")
    columns = _elements(plan, "content")
    assert columns[0].properties["items"] == ["单条"]
    assert columns[1].properties["items"] == []


def test_semantic_geometry_without_title_or_content_is_safe():
    plan = SlideLayoutPlan(slide_index=1, layout_type=LayoutType.TITLE_SLIDE, elements=[])
    assert LayoutDecider()._apply_semantic_geometry(plan.elements, LayoutType.TITLE_SLIDE) == []
    assert LayoutDecider()._apply_semantic_geometry([], LayoutType.CENTER_FOCUS) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("FF0000", RGBColor(0xFF, 0, 0)),
        ("#00ff00", RGBColor(0, 0xFF, 0)),
        ("#fff", RGBColor(0xFF, 0xFF, 0xFF)),
        ("000", RGBColor(0, 0, 0)),
        ("#GGGGGG", RGBColor(0x33, 0x33, 0x33)),
        ("12345", RGBColor(0x33, 0x33, 0x33)),
        ("", RGBColor(0x33, 0x33, 0x33)),
        (None, RGBColor(0x33, 0x33, 0x33)),
        ((1, 2, 3), RGBColor(0x33, 0x33, 0x33)),
    ],
)
def test_parse_color(value, expected):
    assert LayoutDecider()._parse_color(value) == expected


def test_parse_color_passes_through_rgbcolor():
    color = RGBColor(1, 2, 3)
    assert LayoutDecider()._parse_color(color) is color


@pytest.mark.parametrize(
    ("style", "index", "expected"),
    [
        ("circle", 0, "●"),
        ("square", 0, "■"),
        ("arrow", 0, "→"),
        ("number", 0, "1."),
        ("number", 4, "5."),
        ("icon", 0, "◆"),
        ("unknown", 0, "●"),
    ],
)
def test_bullet_symbols(style, index, expected):
    assert LayoutDecider()._get_bullet_symbol(style, index) == expected


def test_render_slide_with_title_content_line_and_page_number():
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        page_number=3,
        total_pages=7,
        elements=[
            LayoutElement(
                "title",
                Inches(0.5),
                Inches(0.3),
                Inches(12),
                Inches(1),
                {"text": "标题", "alignment": "center", "font_weight": "medium", "font_size": 48},
            ),
            LayoutElement(
                "content",
                Inches(0.5),
                Inches(1.5),
                Inches(12),
                Inches(5),
                {
                    "items": ["第一点", "包含重点"],
                    "highlight_points": ["重点"],
                    "bullet_style": "number",
                    "font_size": 18,
                },
            ),
            LayoutElement(
                "line",
                Inches(0.5),
                Inches(1.3),
                Inches(12),
                Inches(0.03),
                {"color": "#4A90D9"},
            ),
        ],
    )
    decider = LayoutDecider()
    decider.render_slide(prs, plan, style=PPTStyle())

    slide = prs.slides[0]
    texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
    assert "标题" in texts
    assert "1. 第一点\n2. 包含『重点』" in texts
    assert "3 / 7" in texts

    title = next(shape for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text == "标题")
    paragraph = title.text_frame.paragraphs[0]
    assert paragraph.alignment == PP_ALIGN.CENTER
    assert paragraph.font.bold is True
    assert paragraph.font.size == Pt(48)


def test_render_slide_accepts_pt_font_and_right_alignment():
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "title",
                Inches(0.5),
                Inches(0.3),
                Inches(12),
                Inches(1),
                {"text": "右对齐", "alignment": "right", "font_weight": "normal", "font_size": Pt(20)},
            )
        ],
    )
    LayoutDecider().render_slide(prs, plan)
    slide = prs.slides[0]
    title = next(shape for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text == "右对齐")
    paragraph = title.text_frame.paragraphs[0]
    assert paragraph.alignment == PP_ALIGN.RIGHT
    assert paragraph.font.bold is False
    assert paragraph.font.size == Pt(20)


def test_render_line_with_invalid_color_falls_back_instead_of_crashing():
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "line",
                Inches(0.5),
                Inches(1.3),
                Inches(12),
                Inches(0.03),
                {"color": "#GGGGGG"},
            )
        ],
    )
    LayoutDecider().render_slide(prs, plan)
    line = prs.slides[0].shapes[1]
    assert line.fill.fore_color.rgb == RGBColor(0x33, 0x33, 0x33)


def test_render_line_with_rgb_tuple():
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "line",
                Inches(0.5),
                Inches(1.3),
                Inches(12),
                Inches(0.03),
                {"color": (10, 20, 30)},
            )
        ],
    )
    LayoutDecider().render_slide(prs, plan)
    assert prs.slides[0].shapes[1].fill.fore_color.rgb == RGBColor(10, 20, 30)


@pytest.mark.parametrize(
    ("size", "width", "height", "crop_attr"),
    [
        ((160, 90), 2, 2, "crop_left"),
        ((90, 160), 2, 2, "crop_top"),
        ((100, 100), 2, 2, None),
    ],
)
def test_render_image_crops_to_box(tmp_path, size, width, height, crop_attr):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", size, (255, 0, 0)).save(image_path)
    asset = ImageAsset(source=ImageSource.LOCAL, local_path=str(image_path))

    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_WITH_IMAGE,
        add_decorations=False,
        elements=[
            LayoutElement(
                "image",
                Inches(1),
                Inches(1),
                Inches(width),
                Inches(height),
                {},
            )
        ],
    )
    LayoutDecider().render_slide(prs, plan, image_asset=asset)
    picture = next(shape for shape in prs.slides[0].shapes if shape.shape_type == 13)
    if crop_attr:
        assert getattr(picture, crop_attr) > 0
    else:
        assert picture.crop_left == 0
        assert picture.crop_top == 0


def test_render_missing_image_file_is_logged_and_skipped(tmp_path, caplog):
    asset = ImageAsset(source=ImageSource.LOCAL, local_path=str(tmp_path / "missing.png"))
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_WITH_IMAGE,
        add_decorations=False,
        elements=[
            LayoutElement("image", Inches(1), Inches(1), Inches(2), Inches(2), {})
        ],
    )
    # app.main 导入时 setup_logging() 把 app 日志器设为 propagate=False，
    # 全量运行下 caplog 挂在 root 上收不到记录，直接挂到目标日志器。
    target = logging.getLogger("app.utils.visual.layout_decider")
    with caplog.at_level(logging.ERROR, logger=target.name):
        target.addHandler(caplog.handler)
        try:
            LayoutDecider().render_slide(prs, plan, image_asset=asset)
        finally:
            target.removeHandler(caplog.handler)
    assert "图片渲染失败" in caplog.text
    assert not [shape for shape in prs.slides[0].shapes if shape.shape_type == 13]


def test_render_slide_applies_design_tokens():
    from types import SimpleNamespace

    tokens = SimpleNamespace(
        colors={
            "primary": "#112233",
            "secondary": "#445566",
            "accent": "#778899",
            "background": "#FFFFFF",
            "text": "#010203",
            "muted_text": "#040506",
        },
        typography={"body_font": "TokenFont", "title_font": "TokenTitle"},
    )
    prs = _presentation()
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        elements=[
            LayoutElement(
                "title",
                Inches(0.5),
                Inches(0.3),
                Inches(12),
                Inches(1),
                {"text": "令牌标题"},
            )
        ],
    )
    LayoutDecider().render_slide(prs, plan, style=PPTStyle(), tokens=tokens)
    title = next(
        shape for shape in prs.slides[0].shapes
        if shape.has_text_frame and shape.text_frame.text == "令牌标题"
    )
    assert title.text_frame.paragraphs[0].font.name == "TokenFont"
