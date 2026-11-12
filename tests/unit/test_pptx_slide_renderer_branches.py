"""SlideRenderer 分支覆盖：解析、绘制、元数据与模块级封装。"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches, Pt

from app.utils.pptx import slide_renderer as module
from app.utils.pptx.slide_renderer import (
    SlideElement,
    SlidePreview,
    SlideRenderer,
    render_all_previews,
    render_slide_preview,
)


class _Font:
    def __init__(self, size=None, name=None, rgb=None):
        self.size = size
        self.name = name
        self.color = SimpleNamespace(rgb=rgb, type=None if rgb is None else "rgb")


class _Para:
    def __init__(self, text="", size=None, runs=None, bullet=False, rgb=None):
        self.text = text
        self.font = _Font(size=size, rgb=rgb)
        self.runs = runs or []
        self._p = SimpleNamespace(pPr=None)
        if bullet:
            self._p = SimpleNamespace(
                pPr=[SimpleNamespace(tag="{ns}buChar")]
            )


class _TextFrame:
    def __init__(self, paras):
        self.paragraphs = paras


class _Shape:
    def __init__(
        self,
        shape_type=MSO_SHAPE_TYPE.TEXT_BOX,
        text_frame=None,
        top=Inches(3),
        fill_type=None,
        line_rgb=None,
    ):
        self.shape_type = shape_type
        self.has_text_frame = text_frame is not None
        self.text_frame = text_frame
        self.left = Inches(1)
        self.top = top
        self.width = Inches(4)
        self.height = Inches(2)
        self.fill = SimpleNamespace(
            type=fill_type,
            fore_color=SimpleNamespace(rgb=(1, 2, 3)),
        )
        self.line = SimpleNamespace(
            color=SimpleNamespace(rgb=line_rgb),
        )


class _Background:
    def __init__(self, fill_type=None, rgb=(9, 8, 7)):
        self.fill = SimpleNamespace(
            type=fill_type,
            fore_color=SimpleNamespace(rgb=rgb),
        )


class _BrokenBackground:
    @property
    def fill(self):
        raise AttributeError("no background")


class _Slide:
    def __init__(self, shapes, background=None):
        self.shapes = shapes
        self.background = background or _Background()


class _Slides(list):
    def index(self, value):
        return super().index(value)


class _Prs:
    def __init__(self, slides):
        self.slides = _Slides(slides)
        self.slide_width = Inches(13.333)
        self.slide_height = Inches(7.5)


def _renderer(tmp_path, slides=None):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    original = module.Presentation
    module.Presentation = lambda _path: _Prs(slides or [])
    try:
        return SlideRenderer(str(path))
    finally:
        module.Presentation = original


def test_init_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        SlideRenderer(str(tmp_path / "missing.pptx"))


def test_render_slide_out_of_range(tmp_path):
    renderer = _renderer(tmp_path)
    assert renderer.render_slide(1) is None
    assert renderer.render_slide(0) is None
    assert renderer.render_slide(-2) is None


def test_render_slide_success_all_element_types(tmp_path):
    title = _Shape(
        text_frame=_TextFrame([_Para("标题", size=Pt(32))]),
        top=Inches(0.5),
    )
    body = _Shape(
        text_frame=_TextFrame([_Para("正文", size=Pt(18), bullet=True)]),
        top=Inches(3),
    )
    image = _Shape(shape_type=MSO_SHAPE_TYPE.PICTURE)
    shape = _Shape(shape_type=MSO_SHAPE_TYPE.AUTO_SHAPE, fill_type="solid")
    slide = _Slide([title, body, image, shape])
    renderer = _renderer(tmp_path, [slide])

    data = renderer.render_slide(1)
    assert data and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_slide_error_returns_none(tmp_path):
    renderer = _renderer(tmp_path, [object()])
    assert renderer.render_slide(1) is None


def test_render_all_slides_filters_failures(tmp_path, monkeypatch):
    renderer = _renderer(tmp_path, [object(), object()])
    results = iter([b"a", None])
    monkeypatch.setattr(renderer, "render_slide", lambda _i: next(results))
    assert renderer.render_all_slides() == [b"a"]


def test_get_slide_metadata_invalid_and_success(tmp_path):
    slide = _Slide([_Shape(text_frame=_TextFrame([_Para("t", size=Pt(20))]))])
    renderer = _renderer(tmp_path, [slide])
    assert renderer.get_slide_metadata(0) is None
    assert renderer.get_slide_metadata(9) is None
    metadata = renderer.get_slide_metadata(1)
    assert metadata["slide_number"] == 1
    assert metadata["elements"][0]["type"] == "text"


def test_get_slide_metadata_exception(tmp_path, monkeypatch):
    renderer = _renderer(tmp_path, [object()])
    monkeypatch.setattr(
        renderer, "_extract_metadata", lambda _slide: (_ for _ in ()).throw(RuntimeError())
    )
    assert renderer.get_slide_metadata(1) is None


def test_parse_slide_background_and_layout(tmp_path):
    title = _Shape(
        text_frame=_TextFrame([_Para("标题", size=Pt(32))]),
        top=Inches(0.5),
    )
    slide = _Slide([title], background=_Background(fill_type="solid"))
    renderer = _renderer(tmp_path, [slide])
    preview = renderer._parse_slide(slide, 1)
    assert preview.background_color == (9, 8, 7)
    assert preview.layout_type == "title_only"


def test_parse_slide_broken_background_is_ignored(tmp_path):
    slide = _Slide([], background=_BrokenBackground())
    renderer = _renderer(tmp_path, [slide])
    preview = renderer._parse_slide(slide, 2)
    assert preview.background_color == (255, 255, 255)
    assert preview.layout_type == "blank"


def test_parse_shape_image_and_auto_shape(tmp_path):
    renderer = _renderer(tmp_path)
    image = renderer._parse_shape(_Shape(shape_type=MSO_SHAPE_TYPE.PICTURE))
    assert image[0].type == "image"

    auto = renderer._parse_shape(
        _Shape(shape_type=MSO_SHAPE_TYPE.AUTO_SHAPE, fill_type="solid")
    )
    assert auto[0].type == "shape"
    assert auto[0].fill_color == (1, 2, 3)


def test_parse_shape_text_title_and_multiple_paragraphs(tmp_path):
    renderer = _renderer(tmp_path)
    shape = _Shape(
        text_frame=_TextFrame(
            [
                _Para("标题", size=Pt(32)),
                _Para("正文", size=Pt(20)),
                _Para("", size=Pt(20)),
            ]
        ),
        top=Inches(0.5),
    )
    elements = renderer._parse_shape(shape)
    assert elements[0].type == "title"
    assert elements[1].type == "title"
    assert len(elements) == 2
    assert elements[1].y > elements[0].y


def test_parse_shape_text_without_title(tmp_path):
    renderer = _renderer(tmp_path)
    shape = _Shape(
        text_frame=_TextFrame([_Para("正文", size=Pt(20))]),
        top=Inches(5),
    )
    elements = renderer._parse_shape(shape)
    assert [element.type for element in elements] == ["text"]


def test_parse_shape_text_frame_without_text(tmp_path):
    renderer = _renderer(tmp_path)
    shape = _Shape(text_frame=_TextFrame([_Para("")]))
    assert renderer._parse_shape(shape) == []


def test_get_paragraph_font_size_variants():
    assert SlideRenderer._get_paragraph_font_size(_Para(size=Pt(30)), True) == 40
    run = SimpleNamespace(font=_Font(size=Pt(12)))
    para = _Para(size=None, runs=[run])
    assert SlideRenderer._get_paragraph_font_size(para, False) == 16
    assert SlideRenderer._get_paragraph_font_size(_Para(size=None), True) == 32
    assert SlideRenderer._get_paragraph_font_size(_Para(size=None), False) == 20


def test_has_bullet_variants():
    assert SlideRenderer._has_bullet(_Para(bullet=True)) is True
    assert SlideRenderer._has_bullet(_Para()) is False


def test_get_paragraph_color_variants():
    assert SlideRenderer._get_paragraph_color(_Para(rgb=(10, 20, 30))) == (10, 20, 30)

    run_font = _Font(rgb=(40, 50, 60))
    para = _Para(rgb=None, runs=[SimpleNamespace(font=run_font)])
    assert SlideRenderer._get_paragraph_color(para) == (40, 50, 60)
    assert SlideRenderer._get_paragraph_color(_Para(rgb=None)) is None

    class _RaisingFont:
        @property
        def color(self):
            raise ValueError("bad color")

    para_with_bad_run = SimpleNamespace(
        font=_RaisingFont(),
        runs=[SimpleNamespace(font=SimpleNamespace(color=SimpleNamespace(rgb=(7, 8, 9))))],
    )
    assert SlideRenderer._get_paragraph_color(para_with_bad_run) == (7, 8, 9)


def test_get_shape_color_variants():
    shape = _Shape(line_rgb=(1, 2, 3))
    assert SlideRenderer._get_shape_color(shape, "fill") == (1, 2, 3)
    assert SlideRenderer._get_shape_color(shape, "line") == (1, 2, 3)

    broken = SimpleNamespace(fill=None, line=None)
    assert SlideRenderer._get_shape_color(broken, "fill") is None


def test_is_title_shape_variants(tmp_path):
    renderer = _renderer(tmp_path)
    title = _Shape(text_frame=_TextFrame([_Para(size=Pt(30))]), top=Inches(0.5))
    assert renderer._is_title_shape(title) is True

    small = _Shape(text_frame=_TextFrame([_Para(size=Pt(10))]), top=Inches(0.5))
    assert renderer._is_title_shape(small) is False

    low = _Shape(text_frame=_TextFrame([_Para(size=Pt(30))]), top=Inches(5))
    assert renderer._is_title_shape(low) is False

    broken = SimpleNamespace(top="bad")
    assert renderer._is_title_shape(broken) is False


def test_detect_layout_type_variants(tmp_path):
    renderer = _renderer(tmp_path)
    title = SlideElement("title", 0, 0, 10, 10)
    text = SlideElement("text", 0, 0, 10, 10)
    image = SlideElement("image", 100, 0, 10, 10)

    assert renderer._detect_layout_type([]) == "blank"
    assert renderer._detect_layout_type([title]) == "title_only"
    assert renderer._detect_layout_type([title, text]) == "content"
    assert (
        renderer._detect_layout_type([title, text, image])
        == "left_text_right_image"
    )
    image_left = SlideElement("image", 0, 0, 10, 10)
    text_right = SlideElement("text", 100, 0, 10, 10)
    assert (
        renderer._detect_layout_type([title, image_left, text_right])
        == "left_image_right_text"
    )


def test_draw_methods_cover_all_branches(tmp_path):
    from PIL import Image, ImageDraw

    renderer = _renderer(tmp_path)
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    renderer._draw_background(draw, SlidePreview(1, background_color=(1, 2, 3)))
    renderer._draw_element(
        draw, SlideElement("title", 1, 1, 10, 10, text="x" * 40, text_color=(0, 0, 0))
    )
    renderer._draw_element(
        draw,
        SlideElement(
            "text",
            1,
            1,
            10,
            10,
            text="y" * 50,
            is_bullet=True,
            text_color=(0, 0, 0),
        ),
    )
    renderer._draw_element(draw, SlideElement("image", 1, 1, 10, 10))
    renderer._draw_element(draw, SlideElement("shape", 1, 1, 10, 10))
    renderer._draw_element(draw, SlideElement("unknown", 1, 1, 10, 10))
    assert img.size == (100, 100)


def test_extract_metadata_fonts_colors_and_picture(tmp_path):
    rich_para = _Para("rich", size=Pt(22), rgb=(1, 1, 1))
    rich_para.font.name = "Arial"
    rich_shape = _Shape(text_frame=_TextFrame([rich_para]))
    picture = _Shape(shape_type=MSO_SHAPE_TYPE.PICTURE)
    unknown = _Shape(shape_type=MSO_SHAPE_TYPE.CHART)
    slide = _Slide([rich_shape, picture, unknown])
    renderer = _renderer(tmp_path, [slide])

    metadata = renderer._extract_metadata(slide)
    assert metadata["elements"][0]["type"] == "text"
    assert metadata["elements"][1]["type"] == "image"
    assert metadata["elements"][2]["type"] == "unknown"
    assert metadata["font_sizes"] == [22]
    assert metadata["colors"] == ["(1, 1, 1)"]
    assert metadata["fonts"] == ["Arial"]


def test_extract_metadata_color_errors_are_ignored(tmp_path):
    class _BadColorFont:
        size = None
        name = None

        @property
        def color(self):
            raise ValueError("bad")

    para = _Para("x")
    para.font = _BadColorFont()
    slide = _Slide([_Shape(text_frame=_TextFrame([para]))])
    renderer = _renderer(tmp_path, [slide])
    metadata = renderer._extract_metadata(slide)
    assert metadata["colors"] == []


def test_load_preview_font_fallback(monkeypatch):
    module._load_preview_font.cache_clear()
    monkeypatch.setattr(module.Path, "is_file", lambda _self: False)
    font = module._load_preview_font(12)
    assert font is not None
    module._load_preview_font.cache_clear()


def test_load_preview_font_first_candidate_oserror(monkeypatch):
    from PIL import ImageFont

    module._load_preview_font.cache_clear()
    monkeypatch.setattr(module.Path, "is_file", lambda _self: True)
    calls = []

    def fake_truetype(path, size):
        calls.append(path)
        if len(calls) == 1:
            raise OSError("bad font")
        return "font"

    monkeypatch.setattr(ImageFont, "truetype", fake_truetype)
    assert module._load_preview_font(99) == "font"
    assert len(calls) == 2
    module._load_preview_font.cache_clear()


def test_module_level_helpers(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"x")
    slide = _Slide([_Shape(text_frame=_TextFrame([_Para("t", size=Pt(20))]))])
    monkeypatch.setattr(module, "Presentation", lambda _path: _Prs([slide]))
    assert render_slide_preview(str(path), 1).startswith(b"\x89PNG")
    assert len(render_all_previews(str(path))) == 1
    metadata = module.get_slide_metadata(str(path), 1)
    assert metadata["slide_number"] == 1
