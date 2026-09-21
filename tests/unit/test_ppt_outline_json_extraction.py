"""AJP6：大纲 JSON 提取不应被尾随文本中的括号带偏。

原先 `re.search(r'...|(\{[\s\S]*\}|\[[\s\S]*\])', content)` 的贪婪匹配会从
第一个 `{` 一直吞到最后一个 `}`，若模型在 JSON 之后附带了任何含括号的说明文字，
整段就变成非法 JSON，解析失败并静默降级为模板大纲。
"""

import pytest

import app.api.v1.aiGeneratorPptx as pptx_api


async def _fake_call_llm(model=None, prompt=None, api_key_token=None):
    return {"choices": [{"message": {"content": _fake_call_llm.content}}]}


async def _generate(content: str, monkeypatch):
    _fake_call_llm.content = content
    monkeypatch.setattr(pptx_api, "call_llm", _fake_call_llm)
    req = pptx_api.PPTGenerationRequest(topic="季度经营复盘", slide_count=5)
    return await pptx_api.generate_ppt_outline(req, user_id="u1")


@pytest.mark.asyncio
async def test_plain_json_with_trailing_braces(monkeypatch):
    content = (
        '{"title":"季度经营复盘","slides":[{"title":"概览","content":"营收增长"}]}'
        "\n\n说明：模板中的 {变量} 会被替换。"
    )
    outline = await _generate(content, monkeypatch)
    assert outline["title"] == "季度经营复盘"
    assert outline["slides"][0]["title"] == "概览"


@pytest.mark.asyncio
async def test_fenced_json_with_trailing_braces(monkeypatch):
    content = (
        "```json\n"
        '{"title":"产品发布","slides":[{"title":"亮点","content":"新特性"}]}\n'
        "```\n"
        "补充：注意 {占位符} 用法。"
    )
    outline = await _generate(content, monkeypatch)
    assert outline["title"] == "产品发布"
