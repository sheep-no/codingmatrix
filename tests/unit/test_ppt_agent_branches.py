"""PPTAgent 分支覆盖：流式解析、降级与验证路径。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.ppt_agent import (
    AUTO_SLIDE_MAX,
    PPTAgent,
    PresentationOutline,
    SlideOutline,
    decode_llm_stream_delta,
    extract_completed_slide_objects,
)


def _llm_response(content):
    return {"choices": [{"message": {"content": content}}]}


def _outline(slides, title="演示"):
    return {"title": title, "slides": slides}


def _slide(title, slide_type="content", **extra):
    return {"type": slide_type, "title": title, "bullets": [f"{title}-要点"], **extra}


def test_extract_completed_slide_objects_handles_empty_and_missing_key():
    assert extract_completed_slide_objects("") == []
    assert extract_completed_slide_objects('{"other": []}') == []
    assert extract_completed_slide_objects('"slides" no bracket') == []


def test_extract_completed_slide_objects_skips_non_objects_and_partial():
    buffer = '{"slides": [1, , {"type": "content", "title": "完整"}, {"type": "cont'
    assert extract_completed_slide_objects(buffer) == [{"type": "content", "title": "完整"}]


def test_extract_completed_slide_objects_ignores_invalid_object_json():
    buffer = '{"slides": [{"type": "content", "title": "bad" "x"}]}'
    assert extract_completed_slide_objects(buffer) == []


def test_extract_completed_slide_objects_handles_escaped_quotes_and_nesting():
    buffer = (
        '{"slides": [{"type": "content", "title": "say \\"hi\\"", '
        '"meta": {"nested": {"deep": true}}}]}'
    )
    objects = extract_completed_slide_objects(buffer)
    assert objects[0]["title"] == 'say "hi"'
    assert objects[0]["meta"]["nested"]["deep"] is True


def test_extract_completed_slide_objects_stops_at_closing_bracket():
    buffer = '{"slides": [{"title": "a"}]}'
    assert extract_completed_slide_objects(buffer) == [{"title": "a"}]


@pytest.mark.parametrize(
    "chunk, expected",
    [
        (None, ""),
        ({"not": "str"}, ""),
        ("", ""),
        ("[DONE]", ""),
        ("data: [DONE]", ""),
        ("data: ", ""),
        ("not json", "not json"),
        ("{bad json", ""),
        ('{"choices": []}', ""),
        ('{"choices": [{}]}', ""),
        ('{"choices": [{"delta": {"content": "hi"}}]}', "hi"),
    ],
)
def test_decode_llm_stream_delta_variants(chunk, expected):
    assert decode_llm_stream_delta(chunk) == expected


def test_decode_llm_stream_delta_handles_non_dict_payload():
    assert decode_llm_stream_delta("data: [1, 2, 3]") == ""


def test_outline_dataclasses_serialize():
    slide = SlideOutline(type="content", title="标题", key_message="结论")
    outline = PresentationOutline(title="演示", slides=[slide])

    assert slide.to_dict()["key_message"] == "结论"
    assert outline.to_dict()["slides"][0]["title"] == "标题"
    assert "演示" in outline.to_json()


@pytest.mark.asyncio
async def test_generate_outline_returns_parsed_outline(monkeypatch):
    payload = _outline([_slide("封面", "title"), _slide("谢谢", "end")])
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=_llm_response(json.dumps(payload))),
    )

    outline = await PPTAgent().generate_outline("主题")

    assert [s.title for s in outline.slides] == ["封面", "谢谢"]


@pytest.mark.asyncio
async def test_generate_outline_uses_custom_system_prompt(monkeypatch):
    captured = {}

    async def _llm(**kwargs):
        captured.update(kwargs)
        payload = _outline([_slide("封面", "title"), _slide("谢谢", "end")])
        return _llm_response(json.dumps(payload))

    monkeypatch.setattr("app.agent.ppt_agent.call_llm", _llm)
    monkeypatch.setattr(
        "app.services.skill_registry.get_skill",
        lambda name: "custom ppt prompt",
    )

    await PPTAgent().generate_outline("主题")

    assert captured["system_prompt"] == "custom ppt prompt"


@pytest.mark.asyncio
async def test_generate_outline_handles_dict_without_choices(monkeypatch):
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value={"choices": []}),
    )
    monkeypatch.setattr(PPTAgent, "MAX_RETRIES", 1)

    outline = await PPTAgent().generate_outline("主题", num_slides=2)

    assert len(outline.slides) == 2


@pytest.mark.asyncio
async def test_generate_outline_raises_api_key_error_without_retry(monkeypatch):
    error = RuntimeError("unauthorized")
    error.status_code = 401
    llm = AsyncMock(side_effect=error)
    monkeypatch.setattr("app.agent.ppt_agent.call_llm", llm)

    with pytest.raises(RuntimeError, match="unauthorized"):
        await PPTAgent().generate_outline("主题")
    assert llm.await_count == 1


@pytest.mark.asyncio
async def test_generate_outline_retries_then_returns_fallback(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(PPTAgent, "MAX_RETRIES", 2)

    outline = await PPTAgent().generate_outline("主题", num_slides=3)

    assert len(outline.slides) == 3


def test_outline_system_prompt_custom_and_default(monkeypatch):
    monkeypatch.setattr("app.services.skill_registry.get_skill", lambda name: "custom")
    assert PPTAgent()._outline_system_prompt() == "custom"

    def _broken(_name):
        raise RuntimeError("down")

    monkeypatch.setattr("app.services.skill_registry.get_skill", _broken)
    assert "PPT 制作助手" in PPTAgent()._outline_system_prompt()


def test_outline_system_prompt_default_when_no_custom(monkeypatch):
    monkeypatch.setattr("app.services.skill_registry.get_skill", lambda name: None)
    assert "PPT 制作助手" in PPTAgent()._outline_system_prompt()


@pytest.mark.asyncio
async def test_stream_outline_yields_slides_from_async_chunks(monkeypatch):
    payload = _outline([_slide("封面", "title"), _slide("谢谢", "end")])
    raw = json.dumps(payload)
    # Split inside the slides array so completed objects arrive one by one.
    cut = raw.index('}, {')
    chunks = [
        "data: " + json.dumps({"choices": [{"delta": {"content": raw[:cut + 1]}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": raw[cut + 1:]}}]}),
        "[DONE]",
    ]

    async def _stream():
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=_stream()),
    )

    events = [event async for event in PPTAgent().stream_outline("主题")]

    assert [event["type"] for event in events] == ["slide", "slide", "complete"]
    assert events[-1]["outline"].slides[-1].type == "end"


@pytest.mark.asyncio
async def test_stream_outline_handles_dict_and_plain_responses(monkeypatch):
    payload = _outline([_slide("封面", "title"), _slide("谢谢", "end")])
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=_llm_response(json.dumps(payload))),
    )
    events = [event async for event in PPTAgent().stream_outline("主题")]
    assert events[-1]["type"] == "complete"

    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=json.dumps(payload)),
    )
    events = [event async for event in PPTAgent().stream_outline("主题")]
    assert any(event["type"] == "slide" for event in events)


@pytest.mark.asyncio
async def test_stream_outline_retries_and_falls_back(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(PPTAgent, "MAX_RETRIES", 2)

    events = [event async for event in PPTAgent().stream_outline("主题", num_slides=3)]

    assert [event["type"] for event in events] == ["retry", "complete"]
    assert len(events[-1]["outline"].slides) == 3


@pytest.mark.asyncio
async def test_stream_outline_raises_api_key_error(monkeypatch):
    error = RuntimeError("unauthorized")
    error.status_code = 401
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(RuntimeError, match="unauthorized"):
        async for _ in PPTAgent().stream_outline("主题"):
            pass


def test_build_prompt_auto_and_fixed_page_counts():
    agent = PPTAgent()
    assert "页数: 自动" in agent._build_prompt("主题", "描述", None)
    assert "页数: 5" in agent._build_prompt("主题", "描述", 5)
    assert "自由发挥" in agent._build_prompt("主题", "", None)


@pytest.mark.asyncio
async def test_parse_with_llm_fallback_uses_second_pass(monkeypatch):
    agent = PPTAgent()
    payload = json.dumps(_outline([_slide("封面", "title"), _slide("谢谢", "end")]))
    monkeypatch.setattr(
        agent,
        "_extract_json_with_llm",
        AsyncMock(return_value=_outline([_slide("封面", "title"), _slide("谢谢", "end")])),
    )

    outline = await agent._parse_with_llm_fallback("bad json", "主题", 2)

    assert [s.title for s in outline.slides] == ["封面", "谢谢"]


@pytest.mark.asyncio
async def test_parse_with_llm_fallback_returns_none_when_extraction_fails(monkeypatch):
    agent = PPTAgent()
    monkeypatch.setattr(agent, "_extract_json_with_llm", AsyncMock(return_value=None))

    assert await agent._parse_with_llm_fallback("bad json", "主题", 2) is None


@pytest.mark.asyncio
async def test_extract_json_with_llm_handles_dict_and_plain(monkeypatch):
    agent = PPTAgent()
    payload = _outline([_slide("封面", "title"), _slide("谢谢", "end")])
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=_llm_response(json.dumps(payload))),
    )
    assert await agent._extract_json_with_llm("text") is not None

    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value={"choices": []}),
    )
    assert await agent._extract_json_with_llm("text") is None

    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value=json.dumps(payload)),
    )
    assert await agent._extract_json_with_llm("text") is not None


@pytest.mark.asyncio
async def test_extract_json_with_llm_returns_none_on_failure(monkeypatch):
    agent = PPTAgent()
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    assert await agent._extract_json_with_llm("text") is None


def test_validate_outline_handles_none_and_single_slide():
    agent = PPTAgent()
    assert agent._validate_outline(None, "主题", 3) is None

    outline = agent._validate_outline({"title": "单页"}, "主题", 1)
    assert len(outline.slides) == 1
    assert outline.slides[0].type == "title"


def test_validate_outline_adds_cover_and_end_and_normalizes_types():
    agent = PPTAgent()
    data = _outline([
        _slide("正文", "content"),
        _slide("未知", "unknown-type"),
    ])
    outline = agent._validate_outline(data, "主题", None)

    assert outline.slides[0].type == "title"
    assert outline.slides[-1].type == "end"
    assert all(slide.type != "unknown-type" for slide in outline.slides)


def test_validate_outline_uses_topic_when_slides_empty():
    outline = PPTAgent()._validate_outline({"title": "T", "slides": []}, "主题", 2)
    assert outline.slides[0].title == "主题"
    assert outline.slides[-1].type == "end"


def test_validate_outline_caps_auto_slides():
    slides = [_slide("封面", "title")] + [
        _slide(f"页{i}") for i in range(AUTO_SLIDE_MAX + 5)
    ] + [_slide("谢谢", "end")]
    outline = PPTAgent()._validate_outline(_outline(slides), "主题", None)
    assert len(outline.slides) == AUTO_SLIDE_MAX


def test_validate_outline_trims_excess_and_pads_short_deck():
    trimmed = PPTAgent()._validate_outline(
        _outline([_slide("封面", "title"), _slide("一"), _slide("二"), _slide("谢谢", "end")]),
        "主题",
        3,
    )
    assert len(trimmed.slides) == 3

    padded = PPTAgent()._validate_outline(
        _outline([_slide("封面", "title"), _slide("谢谢", "end")]),
        "主题",
        5,
    )
    assert len(padded.slides) == 5


def test_validate_outline_returns_none_on_unexpected_error(monkeypatch):
    agent = PPTAgent()

    class _BrokenSlides(list):
        def __iter__(self):
            raise RuntimeError("bad data")

    def _broken(*args, **kwargs):
        raise RuntimeError("bad data")

    monkeypatch.setattr(
        "app.agent.ppt_agent.SlideOutline",
        _broken,
    )
    assert agent._validate_outline({"slides": [{"type": "content"}]}, "主题", 2) is None


def test_validate_outline_keeps_valid_narrative_role_and_truncates_lists():
    data = _outline([{
        "type": "content",
        "title": "页",
        "bullets": [f"b{i}" for i in range(10)],
        "content_blocks": [{"type": "text", "content": f"c{i}"} for i in range(10)],
        "image_keywords": ["a", "b", "c", "d"],
        "narrative_role": "opportunity_map",
        "key_message": None,
    }])
    outline = PPTAgent()._validate_outline(data, "主题", 3)
    slide = outline.slides[1]

    assert len(slide.bullets) == 6
    assert len(slide.content_blocks) == 6
    assert len(slide.image_keywords) == 3
    assert slide.narrative_role == "opportunity_map"
    assert slide.key_message == ""


def test_fallback_outline_without_page_count_uses_blueprint_length(monkeypatch):
    agent = PPTAgent()
    monkeypatch.setattr("app.agent.ppt_agent.build_commercial_page_blueprint", lambda topic: ["a"] * 4)
    outline = agent._fallback_outline("主题", None)

    assert len(outline.slides) == 6


def test_adapt_for_pptx_engine_falls_back_to_title_for_empty_bullets():
    outline = PresentationOutline(
        title="演示",
        slides=[SlideOutline(type="title", title="封面", bullets=[])],
    )
    adapted = PPTAgent.adapt_for_pptx_engine(outline)
    assert adapted["slides"][0]["content"] == ["封面"]


@pytest.mark.asyncio
async def test_modify_outline_retries_and_returns_existing(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(PPTAgent, "MAX_RETRIES", 2)
    existing = _outline([_slide("封面", "title"), _slide("谢谢", "end")])

    outline = await PPTAgent().modify_outline(existing, "改一下")

    assert [s.title for s in outline.slides] == ["封面", "谢谢"]


@pytest.mark.asyncio
async def test_modify_outline_handles_dict_without_choices(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "app.agent.ppt_agent.call_llm",
        AsyncMock(return_value={"choices": []}),
    )
    monkeypatch.setattr(PPTAgent, "MAX_RETRIES", 1)
    existing = _outline([_slide("封面", "title"), _slide("谢谢", "end")])

    outline = await PPTAgent().modify_outline(existing, "改一下")

    assert [s.title for s in outline.slides] == ["封面", "谢谢"]


def test_dict_to_outline_applies_defaults():
    outline = PPTAgent()._dict_to_outline({"slides": [{}]})
    assert outline.title == "PPT"
    assert outline.slides[0].type == "content"
    assert outline.slides[0].title == ""
