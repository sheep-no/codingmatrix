"""`app.utils.agent_core.ProjectGeneratorAgent` 生成主流程与内部辅助分支覆盖。

通过替换 `_call_llm` / `_parse_tool_calls` / `ProjectValidator` 等外部依赖，
在无网络、无真实 LLM 的前提下覆盖生成循环、取消、重规划、验证汇总、流式
解析、上下文压缩与工具并发执行等分支。
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schema.codeRequest import AgentConfig, ToolDefinition
from app.utils import agent_core
from app.utils.agent_core import (
    ConversationHistoryManager,
    ProjectGeneratorAgent,
    ProgressType,
    ToolRegistry,
)


def _agent(**config) -> ProjectGeneratorAgent:
    return ProjectGeneratorAgent(config=AgentConfig(**config))


def _completion():
    return {"choices": [{"message": {"content": "项目生成完成"}}]}


def _tool_msg(tool_id: str, payload) -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(tool_call_id=tool_id, content=content)


# ==================== 参数校验与空响应 ====================


@pytest.mark.asyncio
async def test_generate_rejects_blank_and_oversized_requirement():
    agent = _agent(enable_validation=False)
    for requirement in ["", "   ", "x" * 100_001]:
        result = await agent.generate_project(requirement, output_dir="./tmp/never")
        assert result["success"] is False
        assert result["total_files_created"] == 0


@pytest.mark.asyncio
async def test_generate_stops_when_llm_returns_no_choices(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)

    async def fake_call(messages, **kwargs):
        return {"choices": []}

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert result["success"] is False
    assert result["steps"] == []


@pytest.mark.asyncio
async def test_generate_retries_on_empty_content(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "   "}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert result["success"] is True
    assert result["steps"][0]["type"] == "final"


@pytest.mark.asyncio
async def test_generate_cancelled_before_first_step(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    cancel_event = asyncio.Event()
    cancel_event.set()

    async def fake_call(messages, **kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("cancelled run must not call LLM")

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo",
        output_dir=str(tmp_path / "p"),
        cancel_event=cancel_event,
    )
    assert result["cancelled"] is True
    assert result["success"] is False


# ==================== 新生成 / 继续生成 ====================


@pytest.mark.asyncio
async def test_generate_new_session_with_fallback_prompt_and_disabled_validation(
    monkeypatch, tmp_path
):
    agent = _agent(enable_validation=False)
    monkeypatch.setattr(agent_core, "load_project_generation_prompt", None)

    async def fake_call(messages, **kwargs):
        assert messages[0]["role"] == "system"
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    output = tmp_path / "proj"
    result = await agent.generate_project(
        requirement="生成一个 CLI 工具",
        output_dir=str(output),
        session_id="sess-new",
    )
    assert result["success"] is True
    assert result["validation"]["status"] == "skipped"
    assert output.exists()
    assert result["session_id"] == "sess-new"


@pytest.mark.asyncio
async def test_generate_resume_uses_history_and_directory_status(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    mgr = ConversationHistoryManager()
    monkeypatch.setattr(agent_core, "conversation_history_manager", mgr)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "main.py").write_text("x = 1\n", encoding="utf-8")
    await mgr.set_output_dir("sess-old", str(output))
    await mgr.set_history("sess-old", [{"role": "system", "content": "old"}])

    monkeypatch.setattr(agent_core, "load_project_generation_prompt", lambda **k: "sys")
    monkeypatch.setattr(agent_core, "load_resume_prompt", lambda **k: None)
    monkeypatch.setattr(agent_core, "load_directory_status_prompt", lambda files: None)

    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="改成 Web 版",
        output_dir=str(tmp_path / "ignored"),
        session_id="sess-old",
    )
    assert result["success"] is True
    assert output.name == result["output_dir"]
    # 继续生成复用了历史并追加用户需求与目录状态
    assert captured["messages"][0]["content"] == "old"
    assert any("改成 Web 版" in m.get("content", "") for m in captured["messages"])
    assert any("main.py" in m.get("content", "") for m in captured["messages"])


@pytest.mark.asyncio
async def test_generate_resume_with_failed_prompt_loads(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    mgr = ConversationHistoryManager()
    monkeypatch.setattr(agent_core, "conversation_history_manager", mgr)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "app.py").write_text("x = 1\n", encoding="utf-8")
    await mgr.set_output_dir("s", str(output))
    await mgr.set_history("s", [{"role": "system", "content": "old"}])

    monkeypatch.setattr(agent_core, "load_project_generation_prompt", lambda **k: "sys")
    monkeypatch.setattr(agent_core, "load_resume_prompt", lambda **k: "resume")
    monkeypatch.setattr(agent_core, "load_directory_status_prompt", lambda files: "dir-status")

    async def fake_call(messages, **kwargs):
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="继续", output_dir=str(output), session_id="s"
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_new_session_with_loaded_system_prompt(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    monkeypatch.setattr(agent_core, "load_project_generation_prompt", lambda **k: "loaded-sys")
    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p"), session_id="new"
    )
    assert captured["messages"][0]["content"] == "loaded-sys"


# ==================== 验证汇总 ====================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report",
    [
        {"runnable": True, "errors": ["e"], "warnings": []},
        {"runnable": True, "errors": [], "warnings": ["w"]},
        {
            "runnable": False,
            "errors": ["boom"],
            "warnings": [],
            "server_environment": {"missing": ["pkg"]},
        },
    ],
)
async def test_generate_validation_report_variants(monkeypatch, tmp_path, report):
    agent = _agent(enable_validation=True)
    events = []

    async def fake_call(messages, **kwargs):
        return _completion()

    async def fake_validate(self, callback=None):
        return report

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    monkeypatch.setattr(agent_core.ProjectValidator, "run_full_validation", fake_validate)

    result = await agent.generate_project(
        requirement="demo",
        output_dir=str(tmp_path / "p"),
        callback=events.append,
    )
    assert result["validation"] is report
    validation_events = [
        json.loads(e) for e in events if json.loads(e)["type"] == "validation"
    ]
    assert validation_events


@pytest.mark.asyncio
async def test_generate_compresses_context_when_tokens_high(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False, max_thinking_tokens=1)

    async def fake_call(messages, **kwargs):
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert result["success"] is True


# ==================== 工具执行循环 ====================


@pytest.mark.asyncio
async def test_generate_tool_flow_appends_snapshot_and_step(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    output = tmp_path / "p"
    output.mkdir()
    created = output / "main.py"
    created.write_text("print('hi')\n", encoding="utf-8")

    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": str(created), "content": "x"}}}
    ]
    monkeypatch.setattr(agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content))

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [
            _tool_msg("c1", {"status": "success", "file_path": str(created)}),
            _tool_msg("c2", {"status": "skipped", "file_path": "a.py"}),
        ]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    events = []
    result = await agent.generate_project(
        requirement="demo", output_dir=str(output), callback=events.append
    )
    assert result["success"] is True
    assert result["steps"][0]["type"] == "tool_calls"
    assert result["total_files_created"] == 1
    types = {json.loads(e)["type"] for e in events}
    assert "file_created" in types
    assert "file_skipped" in types


@pytest.mark.asyncio
async def test_generate_tool_failure_triggers_replan(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": "x.py", "content": "x"}}}
    ]
    monkeypatch.setattr(agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content))

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", {"status": "error", "message": "boom"})]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    # 失败步未记录，第 2 步收到完成信号
    assert [s["type"] for s in result["steps"]] == ["final"]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_tool_failure_after_nine_steps_is_recorded(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = [_completion() for _ in range(1)]
    # 前 9 次纯文本推进 steps，第 10 次工具失败，第 11 次完成
    responses = (
        [{"choices": [{"message": {"content": "working"}}]} for _ in range(9)]
        + [{"choices": [{"message": {"content": "TOOL"}}]}]
        + [_completion()]
    )
    iterator = iter(responses)

    async def fake_call(messages, **kwargs):
        return next(iterator)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": "x.py", "content": "x"}}}
    ]
    monkeypatch.setattr(agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content))

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", {"status": "error", "message": "late boom"})]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert result["steps"][9]["type"] == "tool_calls"
    assert result["steps"][-1]["type"] == "final"


@pytest.mark.asyncio
async def test_generate_tool_result_processing_exception_replans(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": "x.py", "content": "x"}}}
    ]
    monkeypatch.setattr(agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content))

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", "not-json")]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert [s["type"] for s in result["steps"]] == ["final"]


@pytest.mark.asyncio
async def test_generate_tool_success_but_file_missing_replans(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": "x.py", "content": "x"}}}
    ]
    monkeypatch.setattr(agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content))

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", {"status": "success", "file_path": str(tmp_path / "gone.py")})]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert [s["type"] for s in result["steps"]] == ["final"]


@pytest.mark.asyncio
async def test_generate_non_completion_text_step_keeps_looping(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "still working"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert [s["type"] for s in result["steps"]] == ["message", "final"]


# ==================== _call_llm ====================


class _FakeAdapter:
    def __init__(self, model):
        self.model = model

    def get_config(self, key, default):
        return {"thinking_budget": 111, "max_tokens": 222, "temperature": 0.3}.get(key, default)


@pytest.mark.asyncio
async def test_call_llm_non_stream(monkeypatch):
    agent = _agent()
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(agent_core, "ModelAdapter", _FakeAdapter)
    monkeypatch.setattr(agent_core, "call_llm", fake_call_llm)

    result = await agent._call_llm([{"role": "user", "content": "hi"}])
    assert result["choices"][0]["message"]["content"] == "ok"
    assert captured["max_tokens"] == 222
    assert captured["thinking_budget"] == 111
    assert captured["temperature"] == 0.3
    assert "【USER】" in captured["prompt"]


@pytest.mark.asyncio
async def test_call_llm_stream_collects_content_and_thinking(monkeypatch):
    agent = _agent()
    events = []

    async def fake_call_llm(**kwargs):
        async def stream():
            yield json.dumps({"choices": [{"delta": {"reasoning_content": "think"}}]})
            yield json.dumps({"choices": [{"delta": {"content": "hello "}}]})
            yield json.dumps({"choices": [{"delta": {"content": "world"}}]})
            yield "not json"
            yield "[DONE]"
            yield json.dumps({"choices": [{"delta": {"content": "ignored"}}]})

        return stream()

    monkeypatch.setattr(agent_core, "ModelAdapter", _FakeAdapter)
    monkeypatch.setattr(agent_core, "call_llm", fake_call_llm)

    result = await agent._call_llm(
        [{"role": "user", "content": "hi"}], stream=True, callback=events.append
    )
    assert result["choices"][0]["message"]["content"] == "hello world"
    assert any(json.loads(e)["type"] == "thinking" for e in events)


@pytest.mark.asyncio
async def test_call_llm_stream_without_callback(monkeypatch):
    agent = _agent()

    async def fake_call_llm(**kwargs):
        async def stream():
            yield json.dumps({"choices": [{"delta": {"reasoning_content": "t", "content": "x"}}]})
            yield json.dumps({"choices": []})
            yield "[DONE]"

        return stream()

    monkeypatch.setattr(agent_core, "ModelAdapter", _FakeAdapter)
    monkeypatch.setattr(agent_core, "call_llm", fake_call_llm)
    result = await agent._call_llm([{"role": "user", "content": "hi"}], stream=True)
    assert result["choices"][0]["message"]["content"] == "x"


@pytest.mark.asyncio
async def test_call_llm_reraises_errors(monkeypatch):
    agent = _agent()

    async def boom(**kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(agent_core, "ModelAdapter", _FakeAdapter)
    monkeypatch.setattr(agent_core, "call_llm", boom)
    with pytest.raises(RuntimeError):
        await agent._call_llm([{"role": "user", "content": "hi"}])


# ==================== 压缩 / 回调 / token 估算 / 工具描述 ====================


@pytest.mark.asyncio
async def test_compress_context_short_messages_returned_as_is():
    agent = _agent()
    messages = [{"role": "system", "content": "a"}]
    assert await agent._compress_context(messages) is messages


@pytest.mark.asyncio
async def test_compress_context_summarises_middle_messages():
    agent = _agent()
    events = []
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "tool", "content": json.dumps({"status": "success", "file_path": "a.py"})},
        {"role": "tool", "content": json.dumps({"status": "error", "message": "boom"})},
        {"role": "system", "content": "目录状态: x"},
        {"role": "assistant", "content": "z" * 60},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "u2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "u4"},
    ]
    compressed = await agent._compress_context(messages, events.append)
    summary = compressed[1]["content"]
    assert "已创建文件" in summary
    assert "错误记录" in summary
    assert "关键决策" in summary
    assert json.loads(events[-1])["type"] == "status"


@pytest.mark.asyncio
async def test_compress_context_without_middle_messages():
    agent = _agent()
    messages = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": str(i)} for i in range(4)
    ]
    compressed = await agent._compress_context(messages)
    # len == 5 时 middle_messages 为空，只保留 system + 最近 4 条
    assert len(compressed) == 5


@pytest.mark.asyncio
async def test_safe_callback_swallows_exception(monkeypatch):
    agent = _agent()
    errors = []
    monkeypatch.setattr(agent_core.logger, "error", lambda msg: errors.append(msg))

    def bad(msg):
        raise RuntimeError("client gone")

    await agent._safe_callback("m", bad)
    await agent._safe_callback("m", None)
    assert len(errors) == 1


def test_estimate_tokens_counts_tool_calls():
    agent = _agent()
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "ok", "tool_calls": [{"id": "1"}]},
    ]
    assert agent._estimate_tokens(messages) > agent._estimate_tokens(messages[:1])


def test_generate_tools_prompt_union_and_error():
    agent = _agent()
    schema = [
        {
            "function": {
                "name": "demo",
                "description": "desc",
                "parameters": {
                    "properties": {
                        "a": {"anyOf": [{"type": "string"}, "raw"]},
                        "b": {"type": "integer"},
                        "c": "not-a-dict",
                    },
                    "required": ["a"],
                },
            }
        }
    ]
    prompt = agent._generate_tools_prompt(schema)
    assert "string | raw" in prompt
    assert "a: string | raw (必填)" in prompt
    assert "c: 类型解析失败" in prompt


def test_model_selection_switch_logs(monkeypatch):
    agent = _agent()
    records = []
    monkeypatch.setattr(agent_core.logger, "info", lambda msg: records.append(msg))
    agent._current_model = "old-model"
    agent._model_router.frontend_model = "front-new"
    agent._model_router.backend_model = "back-new"
    assert agent._select_model_for_file("a.py") == "back-new"
    assert agent._select_model_for_task("create a vue page") == "front-new"
    # 从 front-new 切回 back-new 记一次切换
    agent._select_model_for_file("a.py")
    # 再次选择相同模型不再记录切换
    agent._select_model_for_file("a.py")
    assert len([r for r in records if "模型切换" in r]) == 3


def test_fallback_prompts_include_inputs():
    agent = _agent()
    assert "out" in agent._get_fallback_system_prompt("out", "tools")
    assert "(暂无文件)" in agent._get_fallback_resume_prompt("req", [])
    assert "- a.py" in agent._get_fallback_resume_prompt("req", ["a.py"])
    assert "a.py" in agent._get_fallback_directory_status(["a.py"])
    assert "当前目录已有文件" in agent._get_fallback_directory_status([])


# ==================== JSON 修复 / 工具调用解析 ====================


def test_fix_json_strings_escapes_control_chars():
    agent = _agent()
    raw = '{"content": "line1\nline2\t\u0001", "path": "a\\nb"}'
    fixed = agent._fix_json_strings(raw)
    assert "\\n" in fixed
    assert "\\t" in fixed
    assert "\\u0001" in fixed
    # 字符串外的转义序列保持原样
    assert json.loads(fixed)["path"] == "a\nb"


def _parse(content: str, output_dir=None):
    agent = object.__new__(ProjectGeneratorAgent)
    return agent._parse_tool_calls(content, output_dir)


def test_parse_strips_think_tags_and_reads_json_block():
    content = 'before\n<think>hidden</think>\n```json\n{"tool_calls": [{"id": "1"}]}\n```\nafter'
    calls, text = _parse(content)
    assert calls == [{"id": "1"}]
    assert "hidden" not in text
    assert "after" in text


def test_parse_balanced_braces_with_escaped_quotes():
    tool_call = {
        "id": "1",
        "function": {"name": "create_project_file", "arguments": {"content": 'a "quoted" }\\ value'}},
    }
    content = "prefix " + json.dumps({"tool_calls": [tool_call]}) + " suffix"
    calls, text = _parse(content)
    assert calls[0]["id"] == "1"
    assert text == "prefixsuffix"


def test_parse_json_code_block_fallback_repairs_newlines():
    raw = '```json\n{"tool_calls": [{"id": "1", "function": {"name": "create_project_file", "arguments": {"content": "line1\nline2"}}}]}\n```'
    calls, _ = _parse(raw)
    assert calls[0]["function"]["arguments"]["content"] == "line1\nline2"


def test_parse_invalid_json_code_block_returns_text():
    calls, text = _parse("```json\n{broken}\n```")
    assert calls == []
    assert "{broken}" in text


def test_parse_plain_json_object():
    content = 'here {"tool_calls": [{"id": "1"}]} end'
    calls, text = _parse(content)
    assert calls == [{"id": "1"}]
    assert text == "hereend"


def test_parse_no_matches_returns_clean_text():
    calls, text = _parse("nothing here")
    assert calls == []
    assert text == "nothing here"


def test_parse_balanced_braces_invalid_json_then_falls_back():
    content = 'x {"tool_calls": [broken]} y'
    calls, text = _parse(content)
    assert calls == []
    assert text == content


def test_parse_json_block_without_tool_calls_falls_through():
    content = '```json\n{"tool_calls": []}\n```'
    calls, text = _parse(content)
    assert calls == []
    assert text == content


# ==================== _execute_tools / _run_single_tool ====================


@pytest.mark.asyncio
async def test_execute_tools_variants(tmp_path, monkeypatch):
    agent = _agent()
    events = []
    created = tmp_path / "main.py"

    monkeypatch.chdir(tmp_path)
    calls = [
        {"id": "ok", "function": {"name": "create_project_file", "arguments": json.dumps({"file_path": str(created), "content": "x = 1\n"})}},
        {"id": "missing", "function": {"name": "no_such_tool", "arguments": {}}},
        {"id": "badargs", "function": {"name": "create_project_file", "arguments": {"file_path": 1, "content": "x"}}},
        {"function": {"name": "list_directory"}},
    ]
    results = await agent._execute_tools(
        calls, session_id="s", callback=events.append, output_dir=str(tmp_path)
    )
    assert len(results) == 4
    assert json.loads(results[0].content)["status"] == "success"
    assert "工具不存在" in results[1].content
    assert "参数验证失败" in results[2].content
    assert "结构畸形" in results[3].content
    assert any(json.loads(e)["type"] == "tool_start" for e in events)


@pytest.mark.asyncio
async def test_execute_tools_handles_empty_list():
    agent = _agent()
    assert await agent._execute_tools([], None) == []


@pytest.mark.asyncio
async def test_run_single_tool_async_and_sync_and_error(tmp_path):
    agent = _agent()
    events = []

    async def async_tool(value: int):
        return {"value": value}

    async_def = ToolDefinition(
        name="async_tool", func=async_tool, description="d", parameters=dict
    )
    result = await agent._run_single_tool(async_def, {"value": 1}, "t1", events.append)
    assert json.loads(result.content) == {"value": 1}

    def sync_tool(value: int):
        return f"value={value}"

    sync_def = ToolDefinition(
        name="sync_tool", func=sync_tool, description="d", parameters=dict
    )
    result = await agent._run_single_tool(sync_def, {"value": 2}, "t2")
    assert result.content == "value=2"

    def broken():
        raise RuntimeError("tool broke")

    broken_def = ToolDefinition(
        name="broken_tool", func=broken, description="d", parameters=dict
    )
    result = await agent._run_single_tool(broken_def, {}, "t3", events.append)
    assert "错误: tool broke" in result.content
    statuses = [json.loads(e) for e in events]
    assert any(e.get("status") == "error" for e in statuses)


@pytest.mark.asyncio
async def test_create_error_message():
    message = await ProjectGeneratorAgent._create_error_message("id", "boom")
    assert message.tool_call_id == "id"
    assert message.content == "boom"


# ==================== 补充：提示词兜底 / 40 步上限 / 回调缺失 ====================


@pytest.mark.asyncio
async def test_generate_resume_falls_back_when_prompts_return_none(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    mgr = ConversationHistoryManager()
    monkeypatch.setattr(agent_core, "conversation_history_manager", mgr)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "main.py").write_text("x = 1\n", encoding="utf-8")
    await mgr.set_output_dir("s", str(output))
    await mgr.set_history("s", [{"role": "system", "content": "old"}])

    monkeypatch.setattr(agent_core, "load_project_generation_prompt", lambda **k: None)
    monkeypatch.setattr(agent_core, "load_resume_prompt", lambda **k: None)
    monkeypatch.setattr(agent_core, "load_directory_status_prompt", lambda files: None)

    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = list(messages)
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    # 无 session_id，走新生成但缺省提示词分支
    result = await agent.generate_project(requirement="demo", output_dir=str(output))
    assert result["success"] is True
    assert "你是一位资深Python软件工程师" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_resume_without_loaded_prompts(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)
    mgr = ConversationHistoryManager()
    monkeypatch.setattr(agent_core, "conversation_history_manager", mgr)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "main.py").write_text("x = 1\n", encoding="utf-8")
    await mgr.set_output_dir("s", str(output))
    await mgr.set_history("s", [{"role": "system", "content": "old"}])

    monkeypatch.setattr(agent_core, "load_project_generation_prompt", None)
    monkeypatch.setattr(agent_core, "load_resume_prompt", None)
    monkeypatch.setattr(agent_core, "load_directory_status_prompt", None)

    async def fake_call(messages, **kwargs):
        return _completion()

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="继续", output_dir=str(output), session_id="s"
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_stops_at_forty_steps(monkeypatch, tmp_path):
    agent = _agent(enable_validation=False)

    async def fake_call(messages, **kwargs):
        return {"choices": [{"message": {"content": "still working"}}]}

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert len(result["steps"]) == 40
    assert result["success"] is False


@pytest.mark.asyncio
async def test_generate_tool_call_without_arguments(tmp_path, monkeypatch):
    agent = _agent(enable_validation=False)
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [{"id": "c1", "function": {"name": "list_directory"}}]
    monkeypatch.setattr(
        agent, "_parse_tool_calls",
        lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content),
    )

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", {"status": "ok"})]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(tmp_path / "p")
    )
    assert result["steps"][0]["type"] == "tool_calls"


@pytest.mark.asyncio
async def test_generate_snapshot_json_error_is_ignored(tmp_path, monkeypatch):
    agent = _agent(enable_validation=False)
    output = tmp_path / "p"
    output.mkdir()
    created = output / "main.py"
    created.write_text("x = 1\n", encoding="utf-8")
    # 前 9 步纯文本推进 steps，之后工具失败不再触发重规划，才会进入快照
    # 循环；非 JSON 工具结果在那里被 JSONDecodeError 分支忽略。
    responses = iter(
        [{"choices": [{"message": {"content": "working"}}]} for _ in range(9)]
        + [{"choices": [{"message": {"content": "TOOL"}}]}, _completion()]
    )

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": str(created), "content": "x"}}}
    ]
    monkeypatch.setattr(
        agent, "_parse_tool_calls",
        lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content),
    )

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [
            _tool_msg("c1", {"status": "success", "file_path": str(created)}),
            _tool_msg("c2", "not-json"),
        ]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(output)
    )
    assert result["steps"][9]["type"] == "tool_calls"


@pytest.mark.asyncio
async def test_generate_snapshot_failure_is_logged(tmp_path, monkeypatch):
    agent = _agent(enable_validation=False)
    output = tmp_path / "p"
    output.mkdir()
    created = output / "main.py"
    created.write_text("x = 1\n", encoding="utf-8")
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        _completion(),
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {"file_path": str(created), "content": "x"}}}
    ]
    monkeypatch.setattr(
        agent, "_parse_tool_calls",
        lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content),
    )

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [_tool_msg("c1", {"status": "success", "file_path": str(created)})]

    async def boom(path):
        raise OSError("tree failed")

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)
    monkeypatch.setattr(agent_core, "list_directory", boom)
    result = await agent.generate_project(
        requirement="demo", output_dir=str(output)
    )
    assert result["steps"][0]["type"] == "tool_calls"


def test_parse_json_block_direct_parse_branch():
    content = '```json\n{"tool_calls": [{"id": "1"}]}\n```'
    calls, text = _parse(content)
    assert calls == [{"id": "1"}]
    assert text == ""


def test_parse_balanced_with_braces_inside_string():
    payload = {"tool_calls": [{"id": "1", "function": {"name": "create_project_file", "arguments": {"content": "if x { y }"}}}]}
    content = "before " + json.dumps(payload) + " after"
    calls, text = _parse(content)
    assert calls[0]["id"] == "1"
    assert text == "beforeafter"


@pytest.mark.asyncio
async def test_execute_tools_invalid_string_arguments(tmp_path, monkeypatch):
    agent = _agent()
    monkeypatch.chdir(tmp_path)
    calls = [
        {"id": "bad", "function": {"name": "create_project_file", "arguments": "{not-json"}},
    ]
    results = await agent._execute_tools(calls, None, output_dir=str(tmp_path))
    assert "参数验证失败" in results[0].content


@pytest.mark.asyncio
async def test_execute_tools_non_string_file_path_error_message(tmp_path):
    agent = _agent()
    calls = [
        {"id": "num", "function": {"name": "create_project_file", "arguments": {"file_path": 123, "content": "x"}}},
    ]
    results = await agent._execute_tools(calls, None, output_dir=str(tmp_path))
    assert "参数验证失败" in results[0].content
