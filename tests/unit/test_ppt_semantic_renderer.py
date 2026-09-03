import pytest

from app.utils.pptx.semantic_renderer import SLIDE_TYPES, build_render_metadata, fit_image, normalize_slide_type, select_chart_type
from app.utils.visual.layout_decider import LayoutDecider, LayoutType, layout_type_for_slide_type
from app.utils.visual.visual_analyzer import SlideVisualDecision


@pytest.mark.parametrize("slide_type", SLIDE_TYPES)
def test_all_supported_slide_types_have_stable_render_metadata(slide_type):
    metadata = build_render_metadata({"id": f"{slide_type}-1", "slide_type": slide_type})
    assert metadata["slide_type"] == slide_type
    assert metadata["token_version"] == "1.0"
    assert metadata["grid"]["safe_area"] == 0.5


def test_render_metadata_normalizes_types_and_includes_source_placeholder():
    metadata = build_render_metadata({"id": "s1", "slide_type": "chart", "content_blocks": [{"text": "x"}], "data": {"relationship": "trend"}})
    assert metadata["slide_type"] == "data"
    assert metadata["chart_type"] == "line"
    assert metadata["source_placeholder"] == "数据来源：待补充"
    assert metadata["hierarchy"]["body"] == 14


def test_image_fit_preserves_ratio_and_centers_crop():
    placement = fit_image(16, 9, 4, 4)
    assert round(placement.width / placement.height, 5) == round(16 / 9, 5)
    assert placement.crop_top == 0
    assert placement.crop_left > 0


def test_missing_image_uses_box_fallback():
    placement = fit_image(0, 0, 4, 3, available=False)
    assert placement.fallback is True
    assert (placement.width, placement.height) == (4, 3)


def test_type_and_chart_fallbacks_are_stable():
    assert normalize_slide_type("unknown") == "key_points"
    assert select_chart_type({"relationship": "composition"}) == "donut"
    assert select_chart_type(None) == "bar"


@pytest.mark.parametrize(
    ("slide_type", "expected"),
    [("cover", LayoutType.TITLE_SLIDE), ("comparison", LayoutType.TWO_COLUMN), ("summary", LayoutType.CENTER_FOCUS)],
)
def test_semantic_types_are_wired_to_legacy_layouts(slide_type, expected):
    assert layout_type_for_slide_type(slide_type) == expected


def _plan(slide_type, content):
    return LayoutDecider().plan_slide_layout(
        SlideVisualDecision(slide_index=1, title="标题", content_summary=content),
        page_number=1,
        total_pages=1,
        semantic_slide_type=slide_type,
    )


def test_cover_uses_centered_title_geometry():
    plan = _plan("cover", "副标题")
    title = next(element for element in plan.elements if element.element_type == "title")
    assert plan.layout_type == LayoutType.TITLE_SLIDE
    assert title.properties["alignment"] == "center"
    assert title.left == 1.2 * 914400
    assert title.top == 2.0 * 914400


def test_comparison_splits_content_into_two_columns():
    plan = _plan("comparison", ["左侧一", "左侧二", "右侧一", "右侧二"])
    columns = [element for element in plan.elements if element.element_type == "content"]
    assert plan.layout_type == LayoutType.TWO_COLUMN
    assert len(columns) == 2
    assert columns[0].properties["items"] == ["左侧一", "左侧二"]
    assert columns[1].properties["items"] == ["右侧一", "右侧二"]
    assert columns[0].left < columns[1].left


def test_summary_uses_center_focus_geometry():
    plan = _plan("summary", ["结论一", "结论二"])
    content = next(element for element in plan.elements if element.element_type == "content")
    assert plan.layout_type == LayoutType.CENTER_FOCUS
    assert content.properties["alignment"] == "center"
    assert content.top == 2.0 * 914400
