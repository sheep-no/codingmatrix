"""PPTVisualAnalyzer 分支覆盖：渲染、视觉调用、布局检测与汇总。"""

from types import SimpleNamespace

import pytest

from app.utils.pptx import visual_analyzer as module
from app.utils.pptx.visual_analyzer import (
    PPTAnalysisResult,
    PPTVisualAnalyzer,
    SlideStyleInfo,
    analyze_ppt_visual,
)


class _Renderer:
    def __init__(self, preview=b"png", metadata=None, slide_count=2):
        self.preview = preview
        self.metadata = metadata if metadata is not None else {"elements": []}
        self.slide_count = slide_count
        self.prs = SimpleNamespace(slides=[object()] * slide_count)
        self.rendered = []

    def render_slide(self, number):
        self.rendered.append(number)
        return self.preview

    def get_slide_metadata(self, number):
        return self.metadata


def _make_analyzer(tmp_path, renderer=None):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    return _patch_renderer(path, renderer or _Renderer())


def _patch_renderer(path, renderer):
    original = module.SlideRenderer
    module.SlideRenderer = lambda _path: renderer
    try:
        analyzer = PPTVisualAnalyzer(str(path))
    finally:
        module.SlideRenderer = original
    return analyzer


def test_init_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        PPTVisualAnalyzer(str(tmp_path / "missing.pptx"))


def test_init_defaults(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "SlideRenderer", lambda _path: _Renderer())
    analyzer = PPTVisualAnalyzer(str(path))
    assert analyzer.model == module.DEFAULT_VISUAL_MODEL
    assert analyzer.api_key_token is None
    assert analyzer.user_id is None


@pytest.mark.asyncio
async def test_analyze_slide_success(tmp_path, monkeypatch):
    renderer = _Renderer(
        metadata={
            "fonts": ["Arial"],
            "font_sizes": [20],
            "colors": ["#fff"],
            "elements": [{"type": "text"}],
        }
    )
    analyzer = _make_analyzer(tmp_path, renderer)

    async def vision(_bytes, _number):
        return "描述"

    monkeypatch.setattr(analyzer, "_analyze_with_vision", vision)
    info = await analyzer.analyze_slide(1)
    assert info.layout_type == "content"
    assert info.visual_description == "描述"
    assert info.fonts == ["Arial"]


@pytest.mark.asyncio
async def test_analyze_slide_render_failure_returns_none(tmp_path, monkeypatch):
    analyzer = _make_analyzer(tmp_path, _Renderer(preview=b""))
    assert await analyzer.analyze_slide(1) is None


@pytest.mark.asyncio
async def test_analyze_slide_metadata_failure_returns_none(tmp_path, monkeypatch):
    analyzer = _make_analyzer(tmp_path, _Renderer(metadata={}))
    assert await analyzer.analyze_slide(1) is None


@pytest.mark.asyncio
async def test_analyze_slide_exception_returns_none(tmp_path, monkeypatch):
    renderer = _Renderer()

    def boom(_number):
        raise RuntimeError("render down")

    renderer.render_slide = boom
    analyzer = _make_analyzer(tmp_path, renderer)
    assert await analyzer.analyze_slide(1) is None


@pytest.mark.asyncio
async def test_analyze_all_slides_aggregates(tmp_path, monkeypatch):
    renderer = _Renderer(
        metadata={
            "fonts": ["Arial"],
            "colors": ["#000"],
            "elements": [{"type": "image"}, {"type": "text"}],
        },
        slide_count=2,
    )
    analyzer = _make_analyzer(tmp_path, renderer)

    async def vision(_bytes, _number):
        return "描述"

    monkeypatch.setattr(analyzer, "_analyze_with_vision", vision)
    result = await analyzer.analyze_all_slides()
    assert result.total_slides == 2
    assert result.global_fonts == ["Arial"]
    assert result.global_colors == ["#000"]
    assert "共 2 页幻灯片" in result.style_summary
    assert "使用字体" in result.style_summary
    assert "使用颜色" in result.style_summary


@pytest.mark.asyncio
async def test_analyze_all_slides_skips_failures(tmp_path, monkeypatch):
    renderer = _Renderer(preview=b"", slide_count=2)
    analyzer = _make_analyzer(tmp_path, renderer)
    result = await analyzer.analyze_all_slides()
    assert result.slides == []
    assert result.global_fonts == []
    assert result.global_colors == []
    assert "布局类型：" in result.style_summary


@pytest.mark.asyncio
async def test_analyze_with_vision_success(tmp_path, monkeypatch):
    analyzer = _make_analyzer(tmp_path)
    captured = {}

    async def fake_call(**kwargs):
        captured.update(kwargs)
        return "vision text"

    monkeypatch.setattr("app.utils.vision._call_vision_model", fake_call)
    text = await analyzer._analyze_with_vision(b"image-bytes", 1)
    assert text == "vision text"
    assert captured["image_base64"].startswith("data:image/png;base64,")
    assert captured["user_id"] is None


@pytest.mark.asyncio
async def test_analyze_with_vision_dict_and_other_responses(tmp_path, monkeypatch):
    analyzer = _make_analyzer(tmp_path)

    async def dict_response(**_kwargs):
        return {"choices": [{"message": {"content": "from dict"}}]}

    monkeypatch.setattr("app.utils.vision._call_vision_model", dict_response)
    assert await analyzer._analyze_with_vision(b"x", 1) == "from dict"

    async def other_response(**_kwargs):
        return 42

    monkeypatch.setattr("app.utils.vision._call_vision_model", other_response)
    assert await analyzer._analyze_with_vision(b"x", 1) == "42"


@pytest.mark.asyncio
async def test_analyze_with_vision_failure_returns_none(tmp_path, monkeypatch):
    analyzer = _make_analyzer(tmp_path)

    async def boom(**_kwargs):
        raise RuntimeError("vision down")

    monkeypatch.setattr("app.utils.vision._call_vision_model", boom)
    assert await analyzer._analyze_with_vision(b"x", 1) is None


def test_detect_layout_type_all_variants(tmp_path):
    analyzer = _make_analyzer(tmp_path)
    assert analyzer._detect_layout_type({}) == "blank"
    assert analyzer._detect_layout_type({"elements": []}) == "blank"
    assert (
        analyzer._detect_layout_type({"elements": [{"type": "text"}]}) == "content"
    )
    assert (
        analyzer._detect_layout_type(
            {"elements": [{"type": "text"}, {"type": "image"}]}
        )
        == "image_text"
    )
    assert (
        analyzer._detect_layout_type({"elements": [{"type": "image"}]})
        == "title_only"
    )


def test_generate_style_summary_minimal(tmp_path):
    analyzer = _make_analyzer(tmp_path)
    result = PPTAnalysisResult(total_slides=1)
    summary = analyzer._generate_style_summary(result)
    assert summary == "共 1 页幻灯片；布局类型："


def test_generate_style_summary_truncates_lists(tmp_path):
    analyzer = _make_analyzer(tmp_path)
    result = PPTAnalysisResult(
        total_slides=3,
        slides=[
            SlideStyleInfo(1, "content"),
            SlideStyleInfo(2, "content"),
            SlideStyleInfo(3, "image_text"),
        ],
        global_fonts=["f1", "f2", "f3", "f4"],
        global_colors=["c1", "c2", "c3", "c4"],
    )
    summary = analyzer._generate_style_summary(result)
    assert "content(2页)" in summary
    assert "f4" not in summary
    assert "c4" not in summary


@pytest.mark.asyncio
async def test_analyze_ppt_visual_single_slide(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "SlideRenderer", lambda _path: _Renderer())

    async def fake_slide(self, number):
        return SlideStyleInfo(
            slide_number=number,
            layout_type="content",
            fonts=["A"],
            font_sizes=[12],
            colors=["#fff"],
            elements=[{"type": "text"}],
            visual_description="d",
        )

    monkeypatch.setattr(PPTVisualAnalyzer, "analyze_slide", fake_slide)
    result = await analyze_ppt_visual(str(path), slide_number=2)
    assert result["slide_number"] == 2
    assert result["layout_type"] == "content"
    assert result["visual_description"] == "d"


@pytest.mark.asyncio
async def test_analyze_ppt_visual_single_slide_failure(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "SlideRenderer", lambda _path: _Renderer())

    async def fake_slide(self, number):
        return None

    monkeypatch.setattr(PPTVisualAnalyzer, "analyze_slide", fake_slide)
    result = await analyze_ppt_visual(str(path), slide_number=2)
    assert result == {"error": "分析幻灯片 2 失败"}


@pytest.mark.asyncio
async def test_analyze_ppt_visual_all_slides(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    monkeypatch.setattr(module, "SlideRenderer", lambda _path: _Renderer())

    async def fake_all(self):
        return PPTAnalysisResult(
            total_slides=1,
            slides=[SlideStyleInfo(1, "content", visual_description="d")],
            global_fonts=["A"],
            global_colors=["#fff"],
            style_summary="summary",
        )

    monkeypatch.setattr(PPTVisualAnalyzer, "analyze_all_slides", fake_all)
    result = await analyze_ppt_visual(str(path))
    assert result["total_slides"] == 1
    assert result["slides"][0]["visual_description"] == "d"
    assert result["style_summary"] == "summary"
