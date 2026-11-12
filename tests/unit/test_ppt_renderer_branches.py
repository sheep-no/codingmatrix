"""Branch coverage for PPT renderers and pure helpers in aiGeneratorPptx."""

from types import SimpleNamespace

import pytest
from pptx import Presentation

from app.api.v1 import aiGeneratorPptx as pptx
from app.api.v1.aiGeneratorPptx import (
    PPTGenerationRequest,
    OutputFormat,
    _add_academic_note,
    _add_clinical_card,
    _add_creative_block,
    _add_cropped_picture,
    _add_elegant_note,
    _add_learning_card,
    _add_modern_tile,
    _add_tech_panel,
    _chrome,
    _commercial_slide_items,
    _content_slides_for_total,
    _cover_kicker,
    _cover_tagline,
    _ensure_commercial_role_diversity,
    _ensure_content_diversity,
    _extract_json_payload,
    _is_zh_style,
    _item_at,
    _normalize_approved_outline,
    _normalize_slide_items,
    _preview_url,
    _role_kicker,
    _slide_role,
    _split_commercial_item,
    _validate_ppt_id,
    _verify_ppt_owner,
    _register_ppt_owner,
    generate_pptx_file_enhanced,
    generate_html_ppt,
    generate_markdown_ppt,
    generate_preview_html,
)
from app.utils.pptx.ppt_style import PPTStyle


ROLES = (
    "opportunity_map",
    "evidence_story",
    "strategic_choice",
    "execution_roadmap",
    "decision_close",
)


def _slide(role, **extra):
    data = {
        "title": f"页面 {role}",
        "key_message": "关键结论",
        "narrative_role": role,
        "content": ["第一项", "第二项", "第三项", "第四项"],
        "evidence_sources": [{"title": "来源A"}],
        "asset_intent": {},
    }
    data.update(extra)
    return data


def _request(template="modern", language="zh-CN", **options):
    return PPTGenerationRequest(
        prompt="季度经营复盘与下一步行动",
        template=template,
        language=language,
        slide_count=8,
        options=options,
    )


class TestPureHelpers:
    def test_normalize_slide_items_from_list_and_prose(self):
        assert _normalize_slide_items(["- 一", "2. 二"]) == ["一", "二"]
        assert _normalize_slide_items("一；二\n三") == ["一", "二", "三"]
        assert _normalize_slide_items("") == ["待补充内容"]
        assert _normalize_slide_items(None) == ["待补充内容"]

    def test_commercial_slide_items_prefers_blocks(self):
        slide = {
            "narrative_role": "evidence_story",
            "content_blocks": [
                {"content": "信号", "metadata": {"metric": "转化率", "target": "30%"}},
                {"content": "无元数据"},
                "not-a-dict",
                {"content": ""},
            ],
            "content": ["fallback"],
        }
        items = _commercial_slide_items(slide)
        assert items[0].startswith("信号")
        assert "转化率" in items[0]
        assert items[1] == "无元数据"

    def test_commercial_slide_items_falls_back_for_bad_blocks(self):
        assert _commercial_slide_items(
            {"content_blocks": "oops", "content": ["回退"]}
        ) == ["回退"]
        assert _commercial_slide_items(
            {"content_blocks": [{"content": ""}], "content": ["回退"]}
        ) == ["回退"]

    def test_slide_role_defaults_and_mapping(self):
        assert _slide_role({"narrative_role": "evidence_story"}) == "evidence_story"
        assert _slide_role({"slide_type": "data"}) == "evidence_story"
        assert _slide_role({"slide_type": "comparison"}) == "strategic_choice"
        assert _slide_role({"slide_type": "timeline"}) == "execution_roadmap"
        assert _slide_role({"slide_type": "summary"}) == "decision_close"
        assert _slide_role({"slide_type": "unknown"}) == "opportunity_map"

    def test_language_helpers(self):
        assert _is_zh_style(SimpleNamespace(language="zh-CN")) is True
        assert _is_zh_style(SimpleNamespace(language="en-US")) is False
        assert _is_zh_style(SimpleNamespace(language=None)) is False
        assert _chrome(SimpleNamespace(language="en"), "中", "EN") == "EN"
        assert _chrome(SimpleNamespace(language="zh"), "中", "EN") == "中"

    def test_kicker_helpers(self):
        zh_style = SimpleNamespace(language="zh-CN", template_name="medical")
        en_style = SimpleNamespace(language="en-US", template_name="unknown")
        assert _role_kicker(zh_style, "evidence_story") == "证据叙事"
        assert _role_kicker(zh_style, "evidence_story", 2) == "02 / 证据叙事"
        assert _role_kicker(zh_style, "unknown") == "内容"
        assert _cover_kicker(zh_style) == "临床简报"
        assert _cover_kicker(en_style) == "STRATEGY BRIEF"

    def test_cover_tagline_prefers_fields(self):
        assert _cover_tagline({"subtitle": "副标题"}) == "副标题"
        assert _cover_tagline({"tagline": "标语"}) == "标语"
        assert _cover_tagline({"summary": "摘要"}) == "摘要"
        assert _cover_tagline(
            {"slides": [{"key_message": "首页结论"}]}
        ) == "首页结论"
        assert "下一步" in _cover_tagline({"slides": []})
        assert "下一步" in _cover_tagline({"slides": ["bad"]})

    def test_item_at_bounds(self):
        assert _item_at(["a"], 0) == "a"
        assert _item_at(["a"], 1) == ""
        assert _item_at(["a"], -1) == ""

    def test_split_commercial_item(self):
        assert _split_commercial_item("标题\n详情") == ("标题", "详情")
        assert _split_commercial_item("只有标题") == ("只有标题", "")

    def test_preview_url_keeps_format(self):
        assert _preview_url("abc", OutputFormat.PDF).endswith("?format=pdf")

    def test_validate_ppt_id_rejects_bad_values(self):
        with pytest.raises(Exception):
            _validate_ppt_id("")
        with pytest.raises(Exception):
            _validate_ppt_id("../etc/passwd")
        valid = "12345678-1234-1234-1234-123456789abc"
        assert _validate_ppt_id(valid) == valid

    def test_owner_registration_and_verification(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pptx, "PPT_OWNER_DIR", tmp_path)
        _register_ppt_owner("p1", 7)
        _verify_ppt_owner("p1", "7")
        with pytest.raises(Exception):
            _verify_ppt_owner("p1", "8")
        with pytest.raises(Exception):
            _verify_ppt_owner("missing", "7")
        (tmp_path / "broken.json").write_text("{not json")
        with pytest.raises(Exception):
            _verify_ppt_owner("broken", "7")

    def test_extract_json_payload(self):
        assert _extract_json_payload('```json\n{"a": 1}\n```') == '{"a": 1}'
        assert _extract_json_payload('前缀 {"a": 1} 后缀') == '{"a": 1}'
        assert _extract_json_payload("前缀 [1, 2] 后缀") == "[1, 2]"
        with pytest.raises(ValueError):
            _extract_json_payload("no json here")

    def test_content_slides_for_total(self):
        slides = [
            {"slide_type": "cover"},
            {"slide_type": "content"},
            {"slide_type": "end"},
        ]
        assert len(_content_slides_for_total(slides, 3)) == 2
        assert len(_content_slides_for_total(slides, None)) == 2
        assert _content_slides_for_total(slides, 1) == []
        assert _content_slides_for_total([{"type": "title"}], 5) == []

    def test_normalize_approved_outline_builds_contract(self):
        outline = {
            "title": "标题",
            "subtitle": "副",
            "tagline": "标",
            "summary": "摘要",
            "slides": [
                {
                    "content_blocks": [{"content": "块内容"}],
                    "key_message": "块内容",
                    "narrative_role": "evidence_story",
                }
            ],
        }
        normalized = _normalize_approved_outline(outline)
        assert normalized["title"] == "标题"
        assert normalized["slides"][0]["content"] == ["块内容"]
        assert normalized["slides"][0]["key_message"] == ""
        assert normalized["slides"][0]["layout_variant"] == 0

    def test_normalize_approved_outline_preserves_given_variant(self):
        normalized = _normalize_approved_outline(
            {
                "slides": [
                    {
                        "narrative_role": "evidence_story",
                        "layout_variant": 5,
                        "evidence_sources": [{"title": "x"}],
                    }
                ]
            }
        )
        assert normalized["slides"][0]["layout_variant"] == 5
        assert normalized["slides"][0]["evidence_sources"] == [{"title": "x"}]

    def test_ensure_role_diversity(self):
        slides = [{"narrative_role": "evidence_story", "slide_type": "data"} for _ in range(5)]
        _ensure_commercial_role_diversity(slides)
        assert {s["narrative_role"] for s in slides} == set(ROLES)
        assert slides[0]["slide_type"] == "data"

    def test_ensure_role_diversity_noop(self):
        slides = [{"narrative_role": "evidence_story"}]
        _ensure_commercial_role_diversity(slides)
        assert slides[0]["narrative_role"] == "evidence_story"
        mixed = [
            {"narrative_role": "evidence_story"},
            {"narrative_role": "strategic_choice"},
        ]
        _ensure_commercial_role_diversity(mixed)
        assert mixed[0]["narrative_role"] == "evidence_story"

    def test_ensure_content_diversity_replaces_duplicate(self):
        slides = [
            {
                "title": "重复",
                "content": ["同一内容"],
                "content_blocks": [{"content": "同一内容"}],
                "narrative_role": "evidence_story",
            }
            for _ in range(2)
        ]
        _ensure_content_diversity(slides, "年度经营复盘")
        assert slides[1]["title"] != "重复"
        assert slides[1]["content_blocks"]
        assert slides[1]["asset_intent"] is not None

    def test_ensure_content_diversity_noop_for_single(self):
        slides = [{"title": "唯一", "content": ["x"]}]
        _ensure_content_diversity(slides, "主题")
        assert slides[0]["title"] == "唯一"


class TestShapeHelpers:
    @pytest.fixture
    def slide(self):
        prs = Presentation()
        prs.slide_width = pptx.Inches(13.333)
        prs.slide_height = pptx.Inches(7.5)
        return prs.slides.add_slide(prs.slide_layouts[6])

    @pytest.fixture
    def style(self):
        return PPTStyle("modern")

    def test_notes_and_cards_both_sizes(self, slide, style):
        for height in (1.2, 2.5):
            _add_academic_note(
                slide, "标签", "标题\n细节", 0.5, 0.5, 3.0, height, style,
                featured=True,
            )
            _add_learning_card(
                slide, "标签", "标题\n细节", 4.0, 0.5, 3.0, height, style,
                featured=False,
            )
            _add_clinical_card(
                slide, "标签", "标题\n细节", 0.5, 3.5, 3.0, height, style,
            )
            _add_elegant_note(
                slide, "标签", "标题\n细节", 4.0, 3.5, 3.0, height, style,
            )
            _add_tech_panel(
                slide, "标签", "标题\n细节", 7.5, 0.5, 3.0, height, style,
                featured=True,
            )
            _add_modern_tile(
                slide, "标签", "标题\n细节", 7.5, 3.5, 3.0, height, style,
            )
            _add_creative_block(
                slide, "标题", "正文", 0.5, 6.0, 4.0, height, style, style.ACCENT_COLOR,
            )

    def test_creative_block_not_inverted(self, slide, style):
        _add_creative_block(
            slide, "标题", "正文", 0.5, 0.5, 4.0, 2.0, style,
            style.BG_WHITE, inverted=False,
        )

    def test_modern_tile_small_and_large(self, slide, style):
        _add_modern_tile(slide, "小", "短", 0.5, 0.5, 3.0, 1.2, style)
        _add_modern_tile(slide, "宽", "长正文", 0.5, 2.0, 5.5, 2.5, style, True)

    def test_cropped_picture_wide_and_tall(self, slide, tmp_path):
        from PIL import Image

        wide = tmp_path / "wide.png"
        Image.new("RGB", (200, 100), (255, 0, 0)).save(wide)
        tall = tmp_path / "tall.png"
        Image.new("RGB", (100, 200), (0, 255, 0)).save(tall)
        _add_cropped_picture(slide, str(wide), 0.5, 0.5, 3.0, 4.0)
        _add_cropped_picture(slide, str(tall), 4.0, 0.5, 4.0, 3.0)


class TestTemplateRendering:
    @pytest.mark.parametrize(
        "template",
        ["academic", "education", "medical", "elegant", "modern", "minimal", "tech", "creative", "business"],
    )
    @pytest.mark.parametrize("role", ROLES)
    async def test_generate_every_template_and_role(self, tmp_path, template, role):
        outline = {
            "title": "经营复盘",
            "slides": [_slide(role)],
        }
        filepath = tmp_path / f"{template}-{role}.pptx"
        await generate_pptx_file_enhanced(filepath, outline, _request(template))
        assert filepath.exists()

    @pytest.mark.parametrize("variant", list(range(1, 11)))
    async def test_modern_layout_variants(self, tmp_path, variant):
        slide = _slide(ROLES[variant % len(ROLES)], layout_variant=variant)
        outline = {"title": "变体", "slides": [slide]}
        filepath = tmp_path / f"variant-{variant}.pptx"
        await generate_pptx_file_enhanced(filepath, outline, _request("modern"))
        assert filepath.exists()

    @pytest.mark.parametrize("language", ["en-US", "zh-CN"])
    async def test_english_and_chinese_chrome(self, tmp_path, language):
        outline = {"title": "Review", "slides": [_slide("opportunity_map")]}
        filepath = tmp_path / f"lang-{language}.pptx"
        await generate_pptx_file_enhanced(
            filepath, outline, _request("modern", language=language)
        )
        assert filepath.exists()

    @pytest.mark.parametrize("variant", [1, 2, 3])
    async def test_non_modern_cover_variants(self, tmp_path, monkeypatch, variant):
        monkeypatch.setattr(pptx, "select_cover_variant", lambda _topic: variant)
        outline = {"title": "封面", "slides": [_slide("opportunity_map")]}
        filepath = tmp_path / f"cover-{variant}.pptx"
        await generate_pptx_file_enhanced(filepath, outline, _request("business"))
        assert filepath.exists()

    @pytest.mark.parametrize("variant", [0, 1, 2, 3])
    async def test_modern_cover_variants(self, tmp_path, monkeypatch, variant):
        monkeypatch.setattr(pptx, "select_cover_variant", lambda _topic: variant)
        outline = {"title": "封面", "slides": [_slide("opportunity_map")]}
        filepath = tmp_path / f"mcover-{variant}.pptx"
        await generate_pptx_file_enhanced(filepath, outline, _request("modern"))
        assert filepath.exists()

    async def test_progress_callback_and_animation(self, tmp_path, monkeypatch):
        calls = []

        async def progress(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "app.utils.pptx.animation_engine.AnimationEngine.set_default_transition",
            lambda self, prs, effect: None,
        )
        outline = {"title": "进度", "slides": [_slide("opportunity_map")]}
        filepath = tmp_path / "progress.pptx"
        await generate_pptx_file_enhanced(
            filepath,
            outline,
            _request("modern", enable_animation=True),
            update_progress=progress,
        )
        assert calls
        assert filepath.exists()

    async def test_visual_plan_and_asset_intent_paths(self, tmp_path, monkeypatch):
        async def fake_analyze(**kwargs):
            decision = SimpleNamespace(
                need_image=True,
                get_main_image=lambda: SimpleNamespace(
                    image_type=SimpleNamespace(value="illustration"),
                    description="图",
                    keywords=["a"],
                ),
            )
            return SimpleNamespace(slides=[decision])

        async def fake_image(**kwargs):
            return SimpleNamespace(local_path=None)

        monkeypatch.setattr(pptx.visual_analyzer, "analyze_ppt_content", fake_analyze)
        monkeypatch.setattr(pptx.image_manager, "get_image_for_slide", fake_image)
        outline = {
            "title": "视觉",
            "slides": [_slide("opportunity_map", asset_intent={"asset_type": "illustration"})],
        }
        req = _request("modern", auto_images=True)
        req = req.model_copy(update={"api_key_token": "token"})
        filepath = tmp_path / "visual.pptx"
        await generate_pptx_file_enhanced(filepath, outline, req)
        assert filepath.exists()

    async def test_visual_analysis_failure_is_tolerated(self, tmp_path, monkeypatch):
        async def boom(**_kwargs):
            raise RuntimeError("vision down")

        monkeypatch.setattr(pptx.visual_analyzer, "analyze_ppt_content", boom)
        outline = {"title": "视觉", "slides": [_slide("opportunity_map")]}
        req = _request("modern", auto_images=True).model_copy(
            update={"api_key_token": "token"}
        )
        filepath = tmp_path / "visual-fail.pptx"
        await generate_pptx_file_enhanced(filepath, outline, req)
        assert filepath.exists()

    async def test_image_asset_errors_are_tolerated(self, tmp_path, monkeypatch):
        async def boom(**_kwargs):
            raise RuntimeError("no image")

        monkeypatch.setattr(pptx.image_manager, "get_image_for_slide", boom)
        outline = {
            "title": "配图失败",
            "slides": [_slide("opportunity_map", asset_intent={"description": "x"})],
        }
        req = _request("modern", auto_images=True)
        filepath = tmp_path / "image-fail.pptx"
        await generate_pptx_file_enhanced(filepath, outline, req)
        assert filepath.exists()

    async def test_unknown_theme_uses_default_renderer(self, tmp_path):
        prs = Presentation()
        prs.slide_width = pptx.Inches(13.333)
        prs.slide_height = pptx.Inches(7.5)
        style = PPTStyle("modern")
        style.template_name = "unknown"
        for role in ROLES:
            pptx._render_slide_default(
                prs, prs.slide_layouts[6], style, _slide(role), 1, 2
            )
        assert len(prs.slides) == len(ROLES)

    async def test_default_renderer_with_local_image(self, tmp_path):
        from PIL import Image

        image = tmp_path / "local.png"
        Image.new("RGB", (200, 100), (0, 0, 255)).save(image)
        prs = Presentation()
        prs.slide_width = pptx.Inches(13.333)
        prs.slide_height = pptx.Inches(7.5)
        style = PPTStyle("modern")
        style.template_name = "unknown"
        slide = _slide("opportunity_map", local_images=[str(image)])
        pptx._render_slide_default(prs, prs.slide_layouts[6], style, slide, 1, 2)
        assert len(prs.slides) == 1


class TestExportFormats:
    async def test_html_export_escapes_and_renders(self, tmp_path):
        outline = {
            "title": "<PPT>",
            "slides": [
                {"title": "<标题>", "content": "第一行\n第二行", "slide_number": 1}
            ],
        }
        filepath = tmp_path / "out.html"
        await generate_html_ppt(filepath, outline, _request())
        text = filepath.read_text(encoding="utf-8")
        assert "&lt;PPT&gt;" in text
        assert "第一行<br>第二行" in text

    async def test_markdown_export_with_notes(self, tmp_path):
        outline = {
            "title": "标题",
            "slides": [
                {"title": "页", "content": "内容", "notes": "备注"},
                {"title": "无备注", "content": "内容"},
            ],
        }
        filepath = tmp_path / "out.md"
        await generate_markdown_ppt(filepath, outline, _request())
        text = filepath.read_text(encoding="utf-8")
        assert "**备注**: 备注" in text
        assert text.count("## ") == 2

    def test_preview_html_escapes_id(self):
        page = generate_preview_html("<script>")
        assert "&lt;script&gt;" in page
        assert "slides-container" in page
