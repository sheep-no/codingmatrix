"""ModelAdapter 配置、提示词构建与响应解析补测。"""

import pytest

from app.adapter.model_adapter import ModelAdapter, ModelAdapterConfig


def test_default_config_for_unknown_model():
    adapter = ModelAdapter("custom/model")
    assert adapter.get_config("max_tokens") == 4096
    assert adapter.get_config("temperature") == 0.7
    assert adapter.get_config("missing", "fallback") == "fallback"
    assert adapter.require_strict_json is True
    assert adapter.enable_few_shot is True
    assert repr(adapter) == "ModelAdapter(model_name='custom/model')"


@pytest.mark.parametrize(
    ("model_name", "max_tokens", "temperature"),
    [
        ("Qwen/Qwen3.5-4B", 4096, 0.7),
        ("Qwen/Qwen3-8B", 4096, 0.7),
        ("Qwen/Qwen2.5-7B-Instruct", 4096, 0.7),
        ("deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", 8192, 0.6),
        ("deepseek-ai/DeepSeek-OCR", 2048, 0.5),
        ("Kwai-Kolors/Kolors", 512, 0.8),
    ],
)
def test_known_model_configs(model_name, max_tokens, temperature):
    adapter = ModelAdapter(model_name)
    assert adapter.get_config("max_tokens") == max_tokens
    assert adapter.get_config("temperature") == temperature


def test_config_class_defaults():
    config = ModelAdapterConfig("m")
    assert config.require_strict_json is True
    assert config.enable_few_shot is True
    assert config.default_temperature == 0.7
    assert config.default_max_tokens == 4096


@pytest.mark.asyncio
async def test_chat_is_deprecated_and_returns_empty():
    adapter = ModelAdapter("m")
    assert await adapter.chat("hi") == ""


def test_system_prompt_without_tools():
    prompt = ModelAdapter("m").build_system_prompt()
    assert "暂无预定义工具" in prompt


def test_system_prompt_formats_tools_with_required_and_optional_params():
    schema = [
        {
            "name": "write_file",
            "description": "写入文件",
            "parameters": {
                "properties": {
                    "path": {"type": "string", "description": "目标路径"},
                    "content": {"description": "内容"},
                },
                "required": ["path"],
            },
        },
        {"name": "no_params"},
    ]
    prompt = ModelAdapter("m").build_system_prompt(schema)
    assert "### write_file" in prompt
    assert "描述：写入文件" in prompt
    assert "path: string (必需) - 目标路径" in prompt
    assert "content: any (可选) - 内容" in prompt
    assert "### no_params" in prompt
    assert "描述：无描述" in prompt


def test_parse_response_handles_empty_input():
    adapter = ModelAdapter("m")
    assert adapter.parse_response("") == ([], "", False)
    assert adapter.parse_response("   \n") == ([], "", False)


def test_parse_response_extracts_text_when_json_block_has_no_tool_calls():
    adapter = ModelAdapter("m")
    text = '说明\n```json\n{"answer": 1}\n```\n'
    tool_calls, content, ok = adapter.parse_response(text)
    assert tool_calls == []
    assert ok is False
    assert content == text.strip()


def test_parse_response_strips_invalid_json_block_safely():
    adapter = ModelAdapter("m")
    text = "```json\n{not valid}\n```"
    tool_calls, content, ok = adapter.parse_response(text)
    assert tool_calls == []
    assert ok is False
    assert content == text.strip()


def test_parse_response_keeps_tool_calls_without_id():
    adapter = ModelAdapter("m")
    text = '{"tool_calls": [{"function": {"name": "f"}}]}'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert ok is True
    assert tool_calls == [{"function": {"name": "f"}}]


def test_parse_response_dedups_calls_with_same_id():
    adapter = ModelAdapter("m")
    text = (
        '{"tool_calls": [{"id": "1", "function": {"name": "a"}},'
        ' {"id": "1", "function": {"name": "b"}},'
        ' {"id": "2", "function": {"name": "c"}}]}'
    )
    tool_calls, _content, ok = adapter.parse_response(text)
    assert ok is True
    assert [call["function"]["name"] for call in tool_calls] == ["a", "c"]


def test_parse_response_ignores_invalid_bracket_payload():
    adapter = ModelAdapter("m")
    text = '"tool_calls": [not json'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert tool_calls == []
    assert ok is False


def test_parse_response_handles_bare_list_payload():
    adapter = ModelAdapter("m")
    text = '"tool_calls": [{"id": "x", "function": {"name": "f"}}]'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert ok is True
    assert tool_calls[0]["id"] == "x"


def test_parse_response_wraps_non_object_fenced_payload():
    adapter = ModelAdapter("m")
    text = '```json\n[{"id": "x", "function": {"name": "f"}}]\n```'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert ok is True
    assert tool_calls[0]["id"] == "x"


def test_parse_response_reads_fenced_object_tool_calls():
    adapter = ModelAdapter("m")
    text = '```json\n{"tool_calls": [{"id": "x", "function": {"name": "f"}}]}\n```'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert ok is True
    assert tool_calls[0]["id"] == "x"


def test_parse_response_skips_invalid_bracket_block_with_closing_bracket():
    adapter = ModelAdapter("m")
    text = '"tool_calls": [not-json]'
    tool_calls, _content, ok = adapter.parse_response(text)
    assert tool_calls == []
    assert ok is False


def test_extract_text_content_removes_tool_call_block():
    adapter = ModelAdapter("m")
    text = 'before\n```json\n{"tool_calls": [{"id": "1"}]}\n```\nafter'
    assert adapter._extract_text_content(text) == "before\n\nafter"
