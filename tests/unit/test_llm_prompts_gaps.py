"""llm_prompts 文本降级、默认字段与摘要补测。"""

from app.agent.orchestrator_requirements.llm_prompts import (
    build_llm_prompt,
    llm_system_prompt,
    parse_llm_response,
    summarize_items,
)


def test_system_prompt_contains_contract():
    prompt = llm_system_prompt()
    assert "functional_requirements" in prompt
    assert "confidence" in prompt


def test_build_prompt_with_all_sections():
    prompt = build_llm_prompt("需求", "模板功能", "历史功能")
    assert "需求" in prompt
    assert "模板功能" in prompt
    assert "历史功能" in prompt


def test_build_prompt_without_optional_sections():
    prompt = build_llm_prompt("需求", "", "")
    assert "模板功能" not in prompt
    assert "历史功能" not in prompt


def test_parse_all_categories_with_defaults():
    response = (
        '{"functional_requirements":[{"item":"a"}],'
        '"architectural_impacts":[{"item":"b"}],'
        '"risks":[{"item":"c"}],'
        '"key_decisions":[{"item":"d"}]}'
    )
    items = parse_llm_response(response)

    assert [item.category for item in items] == [
        "functional", "architectural", "risk", "decision"
    ]
    assert items[0].confidence == 0.7
    assert items[1].sub_category == "medium"
    assert items[2].impact == "medium"
    assert items[3].sub_category == "key_decision"


def test_parse_non_json_falls_back_to_list_items():
    response = "说明文字\n- 支持登录\n2. 支持注册\n{json fragment}\n- ab"
    items = parse_llm_response(response)

    assert [item.content for item in items] == ["支持登录", "支持注册"]
    assert all(item.confidence == 0.5 for item in items)


def test_parse_non_json_without_list_returns_empty():
    assert parse_llm_response("只有一段说明") == []


def test_summarize_empty_and_filled():
    items = parse_llm_response('{"functional_requirements":[{"item":"a"}]}')
    assert summarize_items([], "联想") == ""
    summary = summarize_items(items, "联想")
    assert summary.startswith("联想 (1 项):")
    assert "[functional] a" in summary


def test_list_item_with_json_fragment_is_skipped():
    response = "说明\n- 包含 {json} 的条目\n- 正常条目内容"
    items = parse_llm_response(response)
    assert [item.content for item in items] == ["正常条目内容"]
