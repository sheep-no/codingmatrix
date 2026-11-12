"""AnimationEngine 分支覆盖：异常路径、模板预设、速度与 XML 容器复用。"""

from types import SimpleNamespace

import pytest
from lxml import etree

from app.utils.pptx import animation_engine as module
from app.utils.pptx.animation_engine import (
    AnimationEngine,
    AnimationPresets,
    EntranceEffect,
    NS_MAP,
    TransitionEffect,
)


P = f"{{{NS_MAP['p']}}}"


class _Slide:
    def __init__(self, title=None, shapes=None):
        self._element = etree.Element(f"{P}sld")
        self._shapes = list(shapes or [])
        self.shapes = _Shapes(title, self._shapes)

    def __iter__(self):
        return iter([])


class _Shapes:
    def __init__(self, title, shapes):
        self.title = title
        self._shapes = shapes

    def __iter__(self):
        return iter(self._shapes)


class _Shape:
    def __init__(self, shape_id=1, text=""):
        self._element = etree.Element(f"{P}sp")
        self.shape_id = shape_id
        self.has_text_frame = True
        self.text_frame = SimpleNamespace(text=text)


def _prs(slides):
    return SimpleNamespace(slides=slides)


def test_apply_transition_creates_and_replaces(monkeypatch):
    engine = AnimationEngine()
    slide = _Slide()

    assert engine.apply_slide_transition(slide, TransitionEffect.FADE, 0.4) is True
    transition = slide._element.find(f"{P}transition")
    assert transition is not None
    assert transition.get("spd") == "fast"
    assert transition.find(f"{P}fade") is not None

    assert engine.apply_slide_transition(slide, TransitionEffect.PUSH, 1.0) is True
    assert transition.get("spd") == "med"
    children = [etree.QName(c).localname for c in transition]
    assert "fade" not in children and "push" in children

    assert engine.apply_slide_transition(slide, TransitionEffect.RANDOM, 3.0) is True
    assert transition.get("spd") == "slow"


def test_apply_transition_unknown_effect(monkeypatch):
    engine = AnimationEngine()
    slide = _Slide()
    monkeypatch.setattr(engine, "_TRANSITION_MAP", {})
    assert engine.apply_slide_transition(slide, TransitionEffect.FADE, 1.0) is False


def test_apply_transition_exception_returns_false(monkeypatch):
    engine = AnimationEngine()

    class _Broken:
        @property
        def _element(self):
            raise RuntimeError("broken")

    assert engine.apply_slide_transition(_Broken(), TransitionEffect.FADE) is False


def test_apply_shape_entrance_variants(monkeypatch):
    engine = AnimationEngine()
    shape = _Shape(shape_id=7)

    assert engine.apply_shape_entrance(shape, EntranceEffect.NONE) is True
    assert engine.apply_shape_entrance(shape, EntranceEffect.ZOOM, delay=0.25) is True

    ctn = shape._element.find(f"{P}timing/{P}tn")
    assert ctn is not None
    seq = ctn.find(f"{P}seq")
    assert seq.get("presetID") == "3"
    cond = seq.find(f"{P}cond")
    assert cond.get("delay") == "250"


def test_apply_shape_entrance_reuses_timing_container(monkeypatch):
    engine = AnimationEngine()
    shape = _Shape()
    engine.apply_shape_entrance(shape, EntranceEffect.FADE_IN)
    engine.apply_shape_entrance(shape, EntranceEffect.FLY_IN)

    timings = shape._element.findall(f"{P}timing")
    assert len(timings) == 1
    assert len(timings[0].findall(f"{P}tn")) == 1
    assert len(timings[0].find(f"{P}tn").findall(f"{P}seq")) == 2


def test_apply_shape_entrance_unknown_effect():
    engine = AnimationEngine()
    shape = _Shape()
    assert engine.apply_shape_entrance(shape, TransitionEffect.FADE) is False


def test_apply_shape_entrance_exception():
    engine = AnimationEngine()

    class _Broken:
        shape_id = 1

        @property
        def _element(self):
            raise RuntimeError("boom")

    assert engine.apply_shape_entrance(_Broken(), EntranceEffect.FADE_IN) is False


def test_apply_title_animation_success_and_missing():
    engine = AnimationEngine()
    title = _Shape(shape_id=2)
    slide = SimpleNamespace(shapes=SimpleNamespace(title=title))
    assert engine.apply_title_animation(slide, delay=0.1) is True

    empty_slide = SimpleNamespace(shapes=SimpleNamespace(title=None))
    assert engine.apply_title_animation(empty_slide) is False


def test_apply_title_animation_exception():
    engine = AnimationEngine()

    class _BrokenShapes:
        @property
        def title(self):
            raise RuntimeError("broken")

    slide = SimpleNamespace(shapes=_BrokenShapes())
    assert engine.apply_title_animation(slide) is False


def test_apply_content_animation_variants():
    engine = AnimationEngine()
    slide = _Slide()
    assert engine.apply_content_animation(slide, []) is False

    shapes = [_Shape(1), _Shape(2)]
    assert engine.apply_content_animation(slide, shapes, stagger=0.1) is True


def test_apply_content_animation_failure_path():
    engine = AnimationEngine()
    slide = _Slide()
    results = iter([False, True])
    engine.apply_shape_entrance = lambda *a, **k: next(results)
    assert engine.apply_content_animation(slide, [_Shape(), _Shape()]) is True

    engine.apply_shape_entrance = lambda *a, **k: False
    assert engine.apply_content_animation(slide, [_Shape()]) is False


def test_apply_content_animation_exception():
    engine = AnimationEngine()

    class _Shapes(list):
        def __iter__(self):
            raise RuntimeError("iter")

    assert engine.apply_content_animation(_Slide(), _Shapes([_Shape()])) is False


def test_apply_template_animations(monkeypatch):
    engine = AnimationEngine()
    slide = _Slide(shapes=[_Shape(1, "text"), _Shape(2, "")])
    called = []

    engine.set_default_transition = lambda *a, **k: called.append("transition")
    engine.apply_content_animation = lambda *a, **k: called.append("content") or True

    assert engine.apply_template_animations(_prs([slide]), "Professional") is True
    assert called == ["transition", "content"]

    empty_slide = _Slide(shapes=[_Shape(1, "")])
    called.clear()
    assert engine.apply_template_animations(_prs([empty_slide]), "creative") is True
    assert called == ["transition"]


def test_apply_template_animations_unknown_and_exception():
    engine = AnimationEngine()
    assert engine.apply_template_animations(_prs([]), "missing") is False

    engine.set_default_transition = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    assert engine.apply_template_animations(_prs([]), "minimal") is False


def test_set_default_transition_variants():
    engine = AnimationEngine()
    slide = _Slide()
    assert engine.set_default_transition(_prs([slide]), TransitionEffect.FADE) is True
    assert engine.set_default_transition(_prs([]), TransitionEffect.FADE) is False

    engine.apply_slide_transition = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    assert engine.set_default_transition(_prs([slide]), TransitionEffect.FADE) is False


def test_animate_slide_sequence_variants():
    engine = AnimationEngine()
    slide = _Slide()
    assert engine.animate_slide_sequence(slide, []) is False
    assert engine.animate_slide_sequence(slide, [_Shape(1), _Shape(2)]) is True

    engine.apply_shape_entrance = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    assert engine.animate_slide_sequence(slide, [_Shape(1)]) is False


def test_get_or_create_timing_ctn_new_tn():
    engine = AnimationEngine()
    element = etree.Element(f"{P}sp")
    ctn = engine._get_or_create_timing_ctn(element)
    assert ctn.get("id") == "main_seq"


def test_generate_seq_id_unique():
    engine = AnimationEngine()
    first = engine._generate_seq_id()
    second = engine._generate_seq_id()
    assert first.startswith("seq_") and first != second


def test_get_preset_id_unknown():
    engine = AnimationEngine()
    assert engine._get_preset_id(EntranceEffect.NONE) == "0"
    assert engine._get_preset_id(EntranceEffect.ZOOM) == "3"


def test_speed_from_duration_boundaries():
    engine = AnimationEngine()
    assert engine._speed_from_duration(0.5) == "fast"
    assert engine._speed_from_duration(0.6) == "med"
    assert engine._speed_from_duration(1.0) == "med"
    assert engine._speed_from_duration(1.5) == "slow"
    assert engine._speed_from_duration(2.0) == "slow"
    assert engine._speed_from_duration(5.0) == "slow"


def test_presets_all_themes_and_case_insensitive():
    for theme in ("corporate", "creative", "minimal", "dynamic", "elegant"):
        assert AnimationPresets.get_preset_for_theme(theme.upper())[
            "transition"
        ] in list(TransitionEffect)


def test_presets_apply_fade_transition_failure(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(AnimationEngine, "set_default_transition", boom)
    assert AnimationPresets.apply_fade_transition(_prs([])) is False


def test_presets_apply_professional_full_flow(monkeypatch):
    title = _Shape(1, "Title")
    body = _Shape(2, "Body")
    empty = _Shape(3, "")
    slide = _Slide(title=title, shapes=[title, body, empty])

    engine = AnimationEngine()
    calls = []
    monkeypatch.setattr(engine, "apply_slide_transition", lambda *a: True)
    monkeypatch.setattr(engine, "apply_title_animation", lambda *a, **k: True)
    monkeypatch.setattr(
        engine, "apply_content_animation", lambda *a, **k: calls.append(a[1]) or True
    )

    class _FakeEngine:
        def __new__(cls):
            return engine

    monkeypatch.setattr(module, "AnimationEngine", _FakeEngine)

    assert AnimationPresets.apply_professional_animations(_prs([slide])) is True
    assert calls and calls[0] == [body]


def test_presets_apply_professional_partial_failure(monkeypatch):
    title = _Shape(1, "Title")
    body = _Shape(2, "Body")
    slide = _Slide(title=title, shapes=[title, body])

    engine = AnimationEngine()
    monkeypatch.setattr(engine, "apply_slide_transition", lambda *a: False)
    monkeypatch.setattr(engine, "apply_title_animation", lambda *a, **k: False)
    monkeypatch.setattr(engine, "apply_content_animation", lambda *a, **k: False)

    class _FakeEngine:
        def __new__(cls):
            return engine

    monkeypatch.setattr(module, "AnimationEngine", _FakeEngine)
    assert AnimationPresets.apply_professional_animations(_prs([slide])) is False


def test_presets_apply_professional_exception(monkeypatch):
    engine = AnimationEngine()
    monkeypatch.setattr(
        engine,
        "apply_slide_transition",
        lambda *a: (_ for _ in ()).throw(RuntimeError()),
    )

    class _FakeEngine:
        def __new__(cls):
            return engine

    monkeypatch.setattr(module, "AnimationEngine", _FakeEngine)
    assert AnimationPresets.apply_professional_animations(_prs([_Slide()])) is False
