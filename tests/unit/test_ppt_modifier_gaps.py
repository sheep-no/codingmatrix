"""ppt_modifier 元素判定、颜色解析与异常分支补测。"""

from types import SimpleNamespace

import pytest
from pptx.dml.color import RGBColor
from pptx.util import Pt

from app.utils.pptx import ppt_modifier as module
from app.utils.pptx.modify_intent_parser import ModifyIntent, ModifyTarget
from app.utils.pptx.ppt_modifier import PPTModifier


class _Font:
    def __init__(self, size=None, bold=False):
        self.size = size
        self.bold = bold
        self.name = None
        self.color = SimpleNamespace(rgb=None)


class _Para:
    def __init__(self, text="正文", size=None, bold=False):
        self.text = text
        self.font = _Font(size, bold)


def _target(**kwargs):
    base = {"property_name": "font", "property_value": "Arial"}
    base.update(kwargs)
    return ModifyTarget(**base)


def _modifier():
    return PPTModifier.__new__(PPTModifier)


def test_apply_modifications_returns_false_when_save_fails(tmp_path):
    modifier = _modifier()
    modifier.prs = SimpleNamespace(
        slides=[], save=lambda path: (_ for _ in ()).throw(OSError("disk full"))
    )
    intent = ModifyIntent(raw_text="x", targets=[_target(slide_number=None)])
    modifier.prs.slides = [SimpleNamespace(shapes=[])]

    assert modifier.apply_modifications(intent, str(tmp_path / "out.pptx")) is False


def test_apply_target_without_slide_number_iterates_all():
    modifier = _modifier()
    seen = []
    modifier.prs = SimpleNamespace(slides=[object(), object()])
    modifier._modify_slide = lambda slide, target: seen.append(slide)

    assert modifier._apply_target(_target()) is True
    assert len(seen) == 2


def test_modify_slide_skips_shapes_without_text_frame():
    modifier = _modifier()
    seen = []
    modifier._modify_text_frame = lambda frame, target: seen.append(frame)
    slide = SimpleNamespace(shapes=[
        SimpleNamespace(has_text_frame=False),
        SimpleNamespace(has_text_frame=True, text_frame="frame"),
    ])

    modifier._modify_slide(slide, _target())

    assert seen == ["frame"]


def test_is_target_element_returns_true_without_element_type():
    modifier = _modifier()
    assert modifier._is_target_element(_Para(), _target()) is True


def test_is_target_element_rejects_blank_text():
    modifier = _modifier()
    assert modifier._is_target_element(_Para(text="  "), _target(element_type="title")) is False


def test_title_detected_by_large_font():
    modifier = _modifier()
    assert modifier._is_target_element(_Para(size=Pt(24)), _target(element_type="title")) is True


def test_title_detected_by_bold_and_medium_font():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=Pt(18), bold=True), _target(element_type="title")
    ) is True


def test_title_detected_by_bold_without_size():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=None, bold=True), _target(element_type="title")
    ) is True


def test_title_rejected_when_plain_small_text():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=Pt(12), bold=False), _target(element_type="title")
    ) is False


def test_body_rejected_when_large_font():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=Pt(30)), _target(element_type="text")
    ) is False


def test_body_rejected_when_bold_without_size():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=None, bold=True), _target(element_type="text")
    ) is False


def test_body_accepted_for_regular_text():
    modifier = _modifier()
    assert modifier._is_target_element(
        _Para(size=Pt(12)), _target(element_type="text")
    ) is True


def test_unknown_element_type_matches():
    modifier = _modifier()
    assert modifier._is_target_element(_Para(), _target(element_type="other")) is True


def test_apply_font_logs_failure():
    modifier = _modifier()

    class BadFont:
        def __setattr__(self, name, value):
            raise RuntimeError("locked")

    para = SimpleNamespace(font=BadFont())
    modifier._apply_font(para, "Arial")


def test_apply_font_size_ignores_text_without_digits():
    modifier = _modifier()
    para = _Para()
    modifier._apply_font_size(para, "无数字")
    assert para.font.size is None


def test_apply_font_size_logs_failure():
    modifier = _modifier()

    class BadFont:
        def __setattr__(self, name, value):
            raise RuntimeError("locked")

    modifier._apply_font_size(SimpleNamespace(font=BadFont()), "20")


@pytest.mark.parametrize("color", ["", None])
def test_apply_color_returns_for_empty(color):
    modifier = _modifier()
    para = _Para()
    modifier._apply_color(para, color)
    assert para.font.color.rgb is None


def test_apply_color_named_and_hex_values():
    modifier = _modifier()
    para = _Para()
    modifier._apply_color(para, "红色")
    assert para.font.color.rgb == RGBColor(0xFF, 0x00, 0x00)
    modifier._apply_color(para, "#00FF00")
    assert para.font.color.rgb == RGBColor(0x00, 0xFF, 0x00)


def test_apply_color_rejects_bad_hex_length():
    modifier = _modifier()
    para = _Para()
    modifier._apply_color(para, "#FFF")
    assert para.font.color.rgb is None


def test_apply_color_rejects_invalid_hex_digits():
    modifier = _modifier()
    para = _Para()
    modifier._apply_color(para, "#GGGGGG")
    assert para.font.color.rgb is None


def test_apply_color_rejects_unknown_name():
    modifier = _modifier()
    para = _Para()
    modifier._apply_color(para, "chartreuse")
    assert para.font.color.rgb is None


def test_apply_color_logs_unexpected_failure():
    modifier = _modifier()

    class BadColor:
        def __setattr__(self, name, value):
            raise RuntimeError("locked")

    para = SimpleNamespace(font=SimpleNamespace(color=BadColor()))
    modifier._apply_color(para, "红色")


def test_modify_text_frame_skips_unsupported_property():
    modifier = _modifier()
    frame = SimpleNamespace(paragraphs=[_Para()])

    modifier._modify_text_frame(frame, _target(property_name="layout", property_value="x"))

    assert frame.paragraphs[0].font.name is None
