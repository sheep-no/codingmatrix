from app.agent.ppt_agent import PPTAgent


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
