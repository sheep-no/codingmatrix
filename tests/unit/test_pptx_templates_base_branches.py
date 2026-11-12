"""Branch coverage for app/utils/pptx/templates/base.py."""

from unittest.mock import MagicMock

import pytest

from app.utils.pptx.templates.base import (
    SlideLayout,
    TemplateBase,
    TemplateCategory,
    TemplateConfig,
)


def _config(**kwargs) -> TemplateConfig:
    defaults = dict(
        template_id="tpl",
        name="Template",
        name_zh="模板",
        category=TemplateCategory.BUSINESS,
        description="desc",
    )
    defaults.update(kwargs)
    return TemplateConfig(**defaults)


class _Template(TemplateBase):
    def __init__(self, config: TemplateConfig):
        self._config = config

    @property
    def config(self) -> TemplateConfig:
        return self._config


# ---------------------------------------------------------------------------
# TemplateConfig
# ---------------------------------------------------------------------------


def test_to_dict_converts_category_and_layout_keys() -> None:
    config = _config(
        layouts={
            SlideLayout.TITLE_ONLY: {"x": 1},
            "custom": {"y": 2},
        }
    )

    data = config.to_dict()

    assert data["category"] == "business"
    assert data["layouts"] == {"title_only": {"x": 1}, "custom": {"y": 2}}


def test_to_dict_is_json_safe_for_defaults() -> None:
    data = _config().to_dict()

    assert data["layouts"] == {}
    assert data["colors"] == {}


def test_copy_prefixes_identifiers_and_suffixes_names() -> None:
    config = _config(
        layouts={SlideLayout.TITLE_ONLY: {"x": 1}},
        colors={"primary": "ABCDEF"},
        typography={"font": "Arial"},
        spacing={"gap": 1},
        shapes={"shape": "rect"},
        image={"fit": "cover"},
        chart={"type": "bar"},
    )

    copied = config.copy()

    assert copied.template_id == "custom_tpl"
    assert copied.name == "Template (Custom)"
    assert copied.name_zh == "模板 (自定义)"
    assert copied.layouts == config.layouts
    assert copied.layouts is not config.layouts
    assert copied.colors is not config.colors
    assert copied.typography is not config.typography
    assert copied.spacing is not config.spacing
    assert copied.shapes is not config.shapes
    assert copied.image is not config.image
    assert copied.chart is not config.chart


def test_copy_preserves_scalar_fields() -> None:
    config = _config(
        title_size=44,
        has_header_bar=False,
        has_corner_decor=True,
        slide_width=10.0,
    )

    copied = config.copy()

    assert copied.title_size == 44
    assert copied.has_header_bar is False
    assert copied.has_corner_decor is True
    assert copied.slide_width == 10.0
    assert copied.version == config.version


# ---------------------------------------------------------------------------
# TemplateBase
# ---------------------------------------------------------------------------


def test_base_config_property_raises() -> None:
    with pytest.raises(NotImplementedError):
        TemplateBase().config


def test_get_layout_returns_configured_layout() -> None:
    template = _Template(_config(layouts={SlideLayout.TITLE_BULLET: {"bullets": 3}}))

    assert template.get_layout(SlideLayout.TITLE_BULLET) == {"bullets": 3}


def test_get_layout_missing_returns_empty_dict() -> None:
    assert _Template(_config()).get_layout(SlideLayout.TITLE_CHART) == {}


def test_apply_decorations_invokes_all_configured_elements(monkeypatch) -> None:
    template = _Template(_config())
    calls = []
    monkeypatch.setattr(template, "_add_header_bar", lambda *a: calls.append("header"))
    monkeypatch.setattr(template, "_add_footer_bar", lambda *a: calls.append("footer"))
    monkeypatch.setattr(template, "_add_page_number", lambda *a: calls.append("page"))
    monkeypatch.setattr(template, "_add_corner_decor", lambda *a: calls.append("corner"))

    template.apply_decorations(
        MagicMock(),
        MagicMock(),
        _config(
            has_header_bar=True,
            has_footer_bar=True,
            has_page_number=True,
            has_corner_decor=True,
        ),
        page_num=2,
        total_pages=5,
    )

    assert calls == ["header", "footer", "page", "corner"]


def test_apply_decorations_disabled_elements_are_skipped(monkeypatch) -> None:
    template = _Template(_config())
    calls = []
    monkeypatch.setattr(template, "_add_header_bar", lambda *a: calls.append("header"))
    monkeypatch.setattr(template, "_add_footer_bar", lambda *a: calls.append("footer"))
    monkeypatch.setattr(template, "_add_page_number", lambda *a: calls.append("page"))
    monkeypatch.setattr(template, "_add_corner_decor", lambda *a: calls.append("corner"))

    template.apply_decorations(
        MagicMock(),
        MagicMock(),
        _config(
            has_header_bar=False,
            has_footer_bar=False,
            has_page_number=False,
            has_corner_decor=False,
        ),
        page_num=1,
        total_pages=1,
    )

    assert calls == []


# ---------------------------------------------------------------------------
# shape decorators
# ---------------------------------------------------------------------------


def _slide():
    slide = MagicMock()
    slide.shapes.add_shape.return_value = MagicMock()
    slide.shapes.add_textbox.return_value = MagicMock()
    return slide


def test_add_header_bar_draws_two_shapes() -> None:
    slide = _slide()
    template = _Template(_config())

    template._add_header_bar(MagicMock(), slide, _config())

    assert slide.shapes.add_shape.call_count == 2
    header = slide.shapes.add_shape.return_value
    header.fill.solid.assert_called()
    header.line.fill.background.assert_called()


def test_add_footer_bar_draws_shape() -> None:
    slide = _slide()
    template = _Template(_config())

    template._add_footer_bar(MagicMock(), slide, _config())

    slide.shapes.add_shape.assert_called_once()
    bar = slide.shapes.add_shape.return_value
    bar.fill.solid.assert_called()
    bar.line.fill.background.assert_called()


def test_add_page_number_sets_text_and_alignment() -> None:
    slide = _slide()
    textbox = slide.shapes.add_textbox.return_value
    paragraph = textbox.text_frame.paragraphs[0]
    template = _Template(_config())

    template._add_page_number(slide, MagicMock(), _config(), page_num=3, total_pages=9)

    assert textbox.text_frame.word_wrap is True
    assert paragraph.text == "3 / 9"


def test_add_corner_decor_sets_brightness() -> None:
    slide = _slide()
    decor = slide.shapes.add_shape.return_value
    template = _Template(_config())

    template._add_corner_decor(slide, MagicMock(), _config())

    decor.fill.solid.assert_called()
    assert decor.fill.fore_color.brightness == 0.85
    decor.line.fill.background.assert_called()
