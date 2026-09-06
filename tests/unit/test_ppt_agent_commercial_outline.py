from app.agent.ppt_agent import PPTAgent
from app.utils.pptx.commercial_content import (
    build_expanded_commercial_page_blueprint,
    resolve_topic_template,
)


def test_agent_validation_preserves_commercial_fields():
    data = {
        "title": "业务增长",
        "slides": [
            {"type": "title", "title": "业务增长"},
            {
                "type": "content",
                "title": "机会判断",
                "bullets": ["两周内验证 ROI"],
                "narrative_role": "opportunity_map",
                "content_blocks": [{
                    "type": "metric",
                    "content": "两周内验证 ROI",
                    "metadata": {"roi": "≥3.0", "validation_period": "2 周"},
                }],
            },
            {"type": "end", "title": "谢谢"},
        ],
    }

    outline = PPTAgent()._validate_outline(data, "业务增长", 3)
    adapted = PPTAgent.adapt_for_pptx_engine(outline)

    assert adapted["slides"][1]["narrative_role"] == "opportunity_map"
    assert adapted["slides"][1]["content_blocks"][0]["metadata"]["roi"] == "≥3.0"


def test_agent_fallback_has_exact_length_and_commercial_metadata():
    outline = PPTAgent()._fallback_outline("业务增长", 7)

    assert len(outline.slides) == 7
    assert outline.slides[1].narrative_role == "opportunity_map"
    assert outline.slides[1].content_blocks[3]["metadata"]["roi"] == "≥3.0"
    assert outline.slides[-2].narrative_role == "decision_close"


def test_agent_fallback_respects_single_slide_request():
    outline = PPTAgent()._fallback_outline("业务增长", 1)

    assert len(outline.slides) == 1
    assert outline.slides[0].type == "title"


def test_agent_validation_normalizes_roles_and_fills_missing_slides():
    outline = PPTAgent()._validate_outline(
        {
            "title": "业务增长",
            "slides": [
                {"type": "title", "title": "业务增长"},
                {"type": "content", "title": "机会", "bullets": ["验证机会"]},
                {"type": "end", "title": "谢谢"},
            ],
        },
        "业务增长",
        5,
    )

    assert len(outline.slides) == 5
    assert outline.slides[0].narrative_role == ""
    assert outline.slides[1].narrative_role == "opportunity_map"
    assert outline.slides[2].content_blocks
    assert outline.slides[-1].type == "end"


def test_fallback_has_unique_content_pages_for_long_decks():
    outline = PPTAgent()._fallback_outline("主题分享", 12)
    content_slides = outline.slides[1:-1]

    assert len(content_slides) == 10
    assert len({slide.title for slide in content_slides}) == 10
    assert len({tuple(slide.bullets) for slide in content_slides}) == 10
    assert {slide.narrative_role for slide in content_slides} == {
        "opportunity_map",
        "evidence_story",
        "strategic_choice",
        "execution_roadmap",
        "decision_close",
    }


def test_expanded_blueprint_supports_arbitrary_topics_and_lengths():
    for topic, count in (("产品发布", 3), ("年度复盘", 11), ("课程介绍", 17)):
        pages = build_expanded_commercial_page_blueprint(topic, count)
        assert len(pages) == count
        assert len({page["title"] for page in pages}) == count
        assert len({tuple(block["content"] for block in page["blocks"]) for page in pages}) == count


def test_game_ai_fallback_is_domain_specific_and_non_repetitive():
    pages = build_expanded_commercial_page_blueprint("论游戏在AI时代的发展方向", 15)
    text = " ".join(
        page["title"] + " " + page["key_message"] + " " + " ".join(
            block["content"] for block in page["blocks"]
        )
        for page in pages
    )

    assert len(pages) == 15
    assert len({page["title"] for page in pages}) == 15
    assert "NPC" in text
    assert "UGC" in text
    assert "玩家" in text
    assert "程序化内容" in text
    assert "重复录入构成体验损耗" not in text


def test_topic_template_resolution_is_semantic_and_honors_explicit_choice():
    assert resolve_topic_template("谦虚与自我成长", "auto") == "minimal"
    assert resolve_topic_template("公共责任与社区文化", "auto") == "academic"
    assert resolve_topic_template("谦虚与自我成长", "modern") == "modern"
    assert resolve_topic_template("谦虚与自我成长", "creative") == "creative"
    assert resolve_topic_template("完全未知的主题", "") in {
        "modern", "minimal", "elegant", "education", "academic"
    }
