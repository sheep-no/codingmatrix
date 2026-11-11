"""PPTVisualModifier 视觉修改流程测试。"""

from dataclasses import dataclass, field

import pytest
from pptx import Presentation

import app.utils.pptx.visual_modifier as vm
from app.utils.pptx.modify_intent_parser import ModifyIntent, ModifyTarget
from app.utils.pptx.visual_analyzer import PPTAnalysisResult, SlideStyleInfo
from app.utils.pptx.visual_modifier import (
    ModifyResult,
    PPTVisualModifier,
    analyze_ppt_for_modification,
    modify_ppt_visual,
)


@pytest.fixture
def pptx_path(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "标题"
    slide.placeholders[1].text = "正文"
    path = tmp_path / "deck.pptx"
    prs.save(str(path))
    return str(path)


def _intent(*targets, confidence=0.9):
    return ModifyIntent(
        raw_text="修改第一页字体",
        targets=list(targets) or [ModifyTarget(slide_number=1, property_name="font")],
        confidence=confidence,
    )


class TestInit:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="PPTX 文件不存在"):
            PPTVisualModifier(str(tmp_path / "absent.pptx"))

    def test_constructor_stores_options(self, pptx_path):
        modifier = PPTVisualModifier(pptx_path, "token", "user")

        assert modifier.api_key_token == "token"
        assert modifier.user_id == "user"
        assert modifier.intent_parser is not None

    def test_chinese_slide_numbers_stay_scoped(self, pptx_path):
        modifier = PPTVisualModifier(pptx_path)

        third = modifier.intent_parser.parse("修改第三页的字体为微软雅黑")
        twelfth = modifier.intent_parser.parse("第十二页标题字号改成24")

        assert [t.slide_number for t in third.targets] == [3]
        assert [t.slide_number for t in twelfth.targets] == [12]


class TestModify:
    @pytest.mark.asyncio
    async def test_no_targets_returns_hint(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        monkeypatch.setattr(modifier.intent_parser, "parse", lambda text: ModifyIntent(text))

        result = await modifier.modify("随便", "out.pptx")

        assert result.success is False
        assert result.message.startswith("无法识别修改意图")

    @pytest.mark.asyncio
    async def test_successful_modify_with_analysis(self, pptx_path, tmp_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        intent = _intent()
        monkeypatch.setattr(modifier.intent_parser, "parse", lambda text: intent)

        async def fake_analysis(_intent):
            return {"slide_1": {"fonts": ["微软雅黑"]}}

        monkeypatch.setattr(modifier, "_analyze_target_slides", fake_analysis)
        monkeypatch.setattr(modifier, "_generate_previews", lambda path, i: [b"img"])

        class FakeModifier:
            def __init__(self, path):
                self.path = path

            def apply_modifications(self, i, output):
                return True

        monkeypatch.setattr(vm, "PPTModifier", FakeModifier)
        output = str(tmp_path / "out.pptx")

        result = await modifier.modify("改字体", output)

        assert result.success is True
        assert result.output_path == output
        assert result.preview_images == [b"img"]
        assert result.analysis == {"slide_1": {"fonts": ["微软雅黑"]}}
        assert "修改完成" in result.message

    @pytest.mark.asyncio
    async def test_modify_without_analysis(self, pptx_path, tmp_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        monkeypatch.setattr(modifier.intent_parser, "parse", lambda text: _intent())

        async def fail(_intent):
            raise AssertionError("analysis should be skipped")

        monkeypatch.setattr(modifier, "_analyze_target_slides", fail)
        monkeypatch.setattr(modifier, "_generate_previews", lambda path, i: [])

        class FakeModifier:
            def __init__(self, path):
                pass

            def apply_modifications(self, i, output):
                return True

        monkeypatch.setattr(vm, "PPTModifier", FakeModifier)

        result = await modifier.modify(
            "改字体", str(tmp_path / "out.pptx"), analyze_before_modify=False
        )

        assert result.success is True
        assert result.analysis is None

    @pytest.mark.asyncio
    async def test_modify_failure_keeps_intent_and_analysis(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        intent = _intent()
        monkeypatch.setattr(modifier.intent_parser, "parse", lambda text: intent)

        async def fake_analysis(_intent):
            return {"slide_1": {}}

        monkeypatch.setattr(modifier, "_analyze_target_slides", fake_analysis)

        class FakeModifier:
            def __init__(self, path):
                pass

            def apply_modifications(self, i, output):
                return False

        monkeypatch.setattr(vm, "PPTModifier", FakeModifier)

        result = await modifier.modify("改字体", "out.pptx")

        assert result.success is False
        assert result.message == "修改应用失败"
        assert result.intent is intent
        assert result.analysis == {"slide_1": {}}

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_wrapped(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        errors = []
        monkeypatch.setattr(vm.logger, "error", lambda message: errors.append(message))

        def boom(_text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(modifier.intent_parser, "parse", boom)

        result = await modifier.modify("x", "out.pptx")

        assert result.success is False
        assert result.message == "修改失败：parser exploded"
        assert errors == ["修改失败：parser exploded"]


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_single_slide_success(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        style = SlideStyleInfo(
            slide_number=2,
            layout_type="content",
            fonts=["Arial"],
            font_sizes=[18],
            colors=["#000"],
            elements=[{"type": "text"}],
            visual_description="desc",
        )

        class FakeAnalyzer:
            def __init__(self, *_args, **_kwargs):
                pass

            async def analyze_slide(self, number):
                return style

        monkeypatch.setattr(vm, "PPTVisualAnalyzer", FakeAnalyzer)

        result = await modifier.analyze(2)

        assert result == {
            "slide_number": 2,
            "layout_type": "content",
            "fonts": ["Arial"],
            "font_sizes": [18],
            "colors": ["#000"],
            "elements": [{"type": "text"}],
            "visual_description": "desc",
        }

    @pytest.mark.asyncio
    async def test_single_slide_failure(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)

        class FakeAnalyzer:
            def __init__(self, *_args, **_kwargs):
                pass

            async def analyze_slide(self, number):
                return None

        monkeypatch.setattr(vm, "PPTVisualAnalyzer", FakeAnalyzer)

        assert await modifier.analyze(3) == {"error": "分析幻灯片 3 失败"}

    @pytest.mark.asyncio
    async def test_all_slides(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        result = PPTAnalysisResult(
            total_slides=2,
            slides=[
                SlideStyleInfo(slide_number=1, layout_type="title"),
                SlideStyleInfo(slide_number=2, layout_type="content"),
            ],
            global_fonts=["Arial"],
            global_colors=["#fff"],
            style_summary="summary",
        )

        class FakeAnalyzer:
            def __init__(self, *_args, **_kwargs):
                pass

            async def analyze_all_slides(self):
                return result

        monkeypatch.setattr(vm, "PPTVisualAnalyzer", FakeAnalyzer)

        output = await modifier.analyze()

        assert output["total_slides"] == 2
        assert output["global_fonts"] == ["Arial"]
        assert output["global_colors"] == ["#fff"]
        assert output["style_summary"] == "summary"
        assert [s["slide_number"] for s in output["slides"]] == [1, 2]


class TestAnalyzeTargetSlides:
    @pytest.mark.asyncio
    async def test_explicit_slide_numbers(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        seen = []
        style = SlideStyleInfo(slide_number=2, layout_type="content", fonts=["A"])

        class FakeAnalyzer:
            def __init__(self, *_args, **_kwargs):
                pass

            async def analyze_slide(self, number):
                seen.append(number)
                return style

        monkeypatch.setattr(vm, "PPTVisualAnalyzer", FakeAnalyzer)

        analysis = await modifier._analyze_target_slides(
            _intent(ModifyTarget(slide_number=2))
        )

        assert seen == [2]
        assert analysis["slide_2"]["fonts"] == ["A"]

    @pytest.mark.asyncio
    async def test_no_slide_numbers_defaults_to_first_three(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        seen = []

        class FakeAnalyzer:
            def __init__(self, *_args, **_kwargs):
                pass

            async def analyze_slide(self, number):
                seen.append(number)
                return None

        monkeypatch.setattr(vm, "PPTVisualAnalyzer", FakeAnalyzer)

        analysis = await modifier._analyze_target_slides(
            _intent(ModifyTarget(element_type="title"))
        )

        assert seen == [1]
        assert analysis == {}


class TestGeneratePreviews:
    def test_explicit_targets_render(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        rendered = []

        class FakeRenderer:
            def __init__(self, path):
                self.prs = type("P", (), {"slides": [1, 2]})()

            def render_slide(self, number):
                rendered.append(number)
                return b"img" if number == 1 else None

        monkeypatch.setattr(vm, "SlideRenderer", FakeRenderer)

        images = modifier._generate_previews("out.pptx", _intent(ModifyTarget(slide_number=1)))

        assert rendered == [1]
        assert images == [b"img"]

    def test_default_slides_when_unspecified(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        rendered = []

        class FakeRenderer:
            def __init__(self, path):
                self.prs = type("P", (), {"slides": [1, 2, 3, 4, 5]})()

            def render_slide(self, number):
                rendered.append(number)
                return b"img"

        monkeypatch.setattr(vm, "SlideRenderer", FakeRenderer)

        images = modifier._generate_previews("out.pptx", _intent(ModifyTarget()))

        assert rendered == [1, 2, 3]
        assert len(images) == 3

    def test_multiple_explicit_targets_loop(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        rendered = []

        class FakeRenderer:
            def __init__(self, path):
                self.prs = type("P", (), {"slides": [1, 2, 3]})()

            def render_slide(self, number):
                rendered.append(number)
                return b"img"

        monkeypatch.setattr(vm, "SlideRenderer", FakeRenderer)
        intent = _intent(ModifyTarget(slide_number=1), ModifyTarget(slide_number=3))

        images = modifier._generate_previews("out.pptx", intent)

        assert sorted(rendered) == [1, 3]
        assert len(images) == 2

    def test_loop_continues_after_empty_render(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        rendered = []

        class FakeRenderer:
            def __init__(self, path):
                self.prs = type("P", (), {"slides": [1, 2]})()

            def render_slide(self, number):
                rendered.append(number)
                return None if number == 3 else b"img"

        monkeypatch.setattr(vm, "SlideRenderer", FakeRenderer)
        intent = _intent(ModifyTarget(slide_number=3), ModifyTarget(slide_number=4))

        images = modifier._generate_previews("out.pptx", intent)

        assert sorted(rendered) == [3, 4]
        assert images == [b"img"]

    def test_renderer_failure_returns_empty(self, pptx_path, monkeypatch):
        modifier = PPTVisualModifier(pptx_path)
        warnings = []
        monkeypatch.setattr(vm.logger, "warning", lambda message: warnings.append(message))

        def boom(_path):
            raise RuntimeError("render failed")

        monkeypatch.setattr(vm, "SlideRenderer", boom)

        assert modifier._generate_previews("out.pptx", _intent()) == []
        assert warnings == ["生成预览图失败：render failed"]


class TestModuleFunctions:
    @pytest.mark.asyncio
    async def test_modify_ppt_visual_payload(self, pptx_path, monkeypatch):
        expected = ModifyResult(
            success=True,
            message="ok",
            intent=_intent(),
            analysis={"a": 1},
            output_path="out.pptx",
            preview_images=[b"1", b"2"],
        )

        class FakeModifier:
            def __init__(self, path, token=None, user=None):
                pass

            async def modify(self, user_input, output_path, analyze):
                return expected

        monkeypatch.setattr(vm, "PPTVisualModifier", FakeModifier)

        payload = await modify_ppt_visual(pptx_path, "改", "out.pptx")

        assert payload["success"] is True
        assert payload["output_path"] == "out.pptx"
        assert payload["intent"]["raw_text"] == "修改第一页字体"
        assert payload["intent"]["targets"][0]["slide_number"] == 1
        assert payload["intent"]["confidence"] == 0.9
        assert payload["analysis"] == {"a": 1}
        assert payload["preview_count"] == 2

    @pytest.mark.asyncio
    async def test_modify_ppt_visual_without_intent(self, pptx_path, monkeypatch):
        expected = ModifyResult(success=False, message="fail")

        class FakeModifier:
            def __init__(self, path, token=None, user=None):
                pass

            async def modify(self, user_input, output_path, analyze):
                return expected

        monkeypatch.setattr(vm, "PPTVisualModifier", FakeModifier)

        payload = await modify_ppt_visual(pptx_path, "x", "out.pptx")

        assert payload["intent"] is None
        assert payload["preview_count"] == 0

    @pytest.mark.asyncio
    async def test_analyze_ppt_for_modification(self, pptx_path, monkeypatch):
        captured = {}

        class FakeModifier:
            def __init__(self, path, token=None, user=None):
                captured["args"] = (path, token, user)

            async def analyze(self, slide_number):
                captured["slide"] = slide_number
                return {"total_slides": 1}

        monkeypatch.setattr(vm, "PPTVisualModifier", FakeModifier)

        result = await analyze_ppt_for_modification(pptx_path, 2, "t", "u")

        assert result == {"total_slides": 1}
        assert captured["args"] == (pptx_path, "t", "u")
        assert captured["slide"] == 2
