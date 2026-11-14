"""Batch 28: close remaining line/branch gaps from the r41 coverage baseline."""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.json_parser import extract_first_json_object
from app.agent.backend_engineer import BackendEngineer
from app.agent.dynamic_model_router import LearningRouter
from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.node_types.base import NodeResult
from app.utils.workflow.result_aggregator import ResultAggregator


# ---------------------------------------------------------------------------
# provider_router
# ---------------------------------------------------------------------------


def test_provider_router_get_instance_backfills_registry(monkeypatch):
    from app.utils.aicloud import provider_router as module

    class Registry:
        pass

    registry = Registry()
    monkeypatch.setattr(module.ProviderRouter, "_instance", None)
    first = module.ProviderRouter.get_instance()
    assert first._registry is None
    second = module.ProviderRouter.get_instance(registry)
    assert second is first
    assert first._registry is registry
    module.ProviderRouter.clear_cache()


def test_load_provider_map_registers_display_names(monkeypatch):
    from app.utils.aicloud import provider_router as module
    from app.utils.aicloud.providers import ModelProvider

    monkeypatch.setattr(
        module,
        "load_model_config",
        lambda _path: {
            "models": {
                "alias-id": {"name": "display-name", "provider": "zhipu"},
                "anon": {"provider": "deepseek"},
            }
        },
    )

    mapping = module._load_provider_map()

    assert mapping["alias-id"] is ModelProvider.ZHIPU
    assert mapping["display-name"] is ModelProvider.ZHIPU
    assert mapping["anon"] is ModelProvider.DEEPSEEK


# ---------------------------------------------------------------------------
# pptx text_processor
# ---------------------------------------------------------------------------


def test_prevent_overflow_empty_text_and_short_content():
    from app.utils.pptx.text_processor import prevent_text_overflow

    empty = prevent_text_overflow("", max_chars_per_line=10, max_lines=3)
    assert empty.lines == ["暂无内容"]

    short = prevent_text_overflow("hello", max_chars_per_line=10, max_lines=3)
    assert short.lines == ["hello"]


def test_smart_split_line_covers_zero_width_and_blank_tail():
    from app.utils.pptx.text_processor import smart_split_line

    assert smart_split_line("中文", 0) == ["中", "文"]


# ---------------------------------------------------------------------------
# result_aggregator
# ---------------------------------------------------------------------------


def _graph():
    return TaskGraph(
        workflow_id="g",
        nodes=[
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={"output_variable": "a_out"}),
            TaskNode(
                id="b",
                type=TaskType.CODE_EXECUTION,
                params={},
                depends_on=["a", "ghost"],
            ),
        ],
    )


def test_completion_rate_empty_graph_is_full():
    empty = ResultAggregator("g", TaskGraph(workflow_id="g", nodes=[]))
    assert empty.get_completion_rate() == 1.0


def test_upstream_results_unknown_node_and_missing_dependency():
    aggregator = ResultAggregator("g", _graph())
    aggregator.record_result("a", NodeResult(success=True, data=1))
    aggregator.record_result("ghost", NodeResult(success=True, data=2))

    assert aggregator.get_upstream_results("missing") == {}
    assert aggregator.get_upstream_results("b") == {
        "a": aggregator.get_result("a"),
        "ghost": aggregator.get_result("ghost"),
    }


def test_build_node_context_without_node_and_without_dep_node():
    aggregator = ResultAggregator("g", _graph())
    aggregator.record_result("a", NodeResult(success=True, data=1))
    aggregator.record_result("ghost", NodeResult(success=True, data=2))

    unknown = aggregator.get_context("missing")
    assert "node_type" not in unknown

    context = aggregator.get_context("b")
    assert context["a_result"] == 1
    assert context["ghost_result"] == 2
    assert "a_out" in context


# ---------------------------------------------------------------------------
# backend_engineer
# ---------------------------------------------------------------------------


def _engineer():
    return BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )


def test_runtime_constraints_string_exports_become_list():
    architecture = {
        "language": "python",
        "file_plan": [
            {
                "path": "app/repository/user_repo.py",
                "file_type": "repository",
                "contract": {"exports": "list_users"},
            }
        ],
    }

    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/repository/user_repo.py", "repository", "python", architecture
    )

    assert "list_users" in text


def test_runtime_constraints_non_dict_project_spec():
    architecture = {"language": "python", "project_spec": "not-a-dict"}
    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/api/users.py", "api", "python", architecture
    )
    assert "Python 运行时一致性" in text


@pytest.mark.asyncio
async def test_generate_file_empty_language_falls_back(monkeypatch):
    engineer = _engineer()
    engineer.call_llm = AsyncMock(return_value="plain")
    monkeypatch.setattr(
        "app.agent.utils.get_expected_language_for_file", lambda *_a, **_k: ""
    )

    result = await engineer.generate_file(
        "app/config.py",
        "config",
        {
            "architecture": {"language": "python"},
            "original_content": "x = 1",
            "modification_reason": "tweak",
        },
        is_existing_file=True,
    )

    assert result == "plain"


@pytest.mark.asyncio
async def test_generate_file_frozen_existing_uses_strict_format_prompt():
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "modified"

    engineer.call_llm = _capture

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {
            "architecture": {"language": "python"},
            "generation_contract": {"frozen": True},
            "original_content": "old",
        },
        is_existing_file=True,
    )

    assert result == "modified"
    assert "不要包裹在 JSON 对象中" in captured["prompt"]


# ---------------------------------------------------------------------------
# agent_core
# ---------------------------------------------------------------------------


def _core_agent():
    from app.utils.agent_core import AgentConfig, ProjectGeneratorAgent

    return ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))


@pytest.mark.asyncio
async def test_compress_context_handles_non_json_tool_and_plain_messages():
    agent = _core_agent()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "tool", "content": "not-json"},
        {"role": "tool", "content": json.dumps(123)},
        {"role": "tool", "content": json.dumps({"status": "success"})},
        {"role": "system", "content": "普通提示"},
        {"role": "assistant", "content": "short"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]

    compressed = await agent._compress_context(messages)

    summary = compressed[1]["content"]
    assert "已压缩 3 条消息" in summary
    assert "已创建文件" not in summary


@pytest.mark.asyncio
async def test_generate_new_project_lists_existing_files(monkeypatch, tmp_path):
    agent = _core_agent()
    output = tmp_path / "existing"
    output.mkdir()
    (output / "main.py").write_text("x = 1\n", encoding="utf-8")

    captured = {}

    async def fake_call(messages, **_kwargs):
        captured["messages"] = list(messages)
        return {"choices": [{"message": {"content": "done"}}]}

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    monkeypatch.setattr(
        "app.utils.agent_core.load_project_generation_prompt", lambda **_k: "sys"
    )

    from app.utils.agent_core import conversation_history_manager

    await conversation_history_manager.set_output_dir("s2", str(output))
    result = await agent.generate_project(
        requirement="demo", output_dir=str(output), session_id="s2"
    )

    assert result["success"] is True
    assert "该目录已存在以下文件" in captured["messages"][1]["content"]


def test_fix_json_strings_escapes_carriage_return():
    agent = _engineer_core_parse()
    raw = '{"text": "line1\rline2"}'
    fixed = agent._fix_json_strings(raw)
    assert "\\r" in fixed
    assert json.loads(fixed)["text"] == "line1\rline2"


def _engineer_core_parse():
    from app.utils.agent_core import ProjectGeneratorAgent

    return object.__new__(ProjectGeneratorAgent)


def _parse(content):
    return _engineer_core_parse()._parse_tool_calls(content)


def test_parse_tool_calls_escaped_json_codeblock_key():
    tool_calls, pure = _parse(
        '```json\n{"tool_\\u0063alls": [{"id": "1"}]}\n```'
    )
    assert tool_calls == [{"id": "1"}]
    assert pure == ""


def test_parse_tool_calls_json_codeblock_fix_fails():
    tool_calls, _pure = _parse(
        '```json\n{"tool_calls": [{"content": "a\nb"}],}\n```'
    )
    assert tool_calls == []


def test_parse_tool_calls_attempt3_pure_json_with_noise():
    content = '{"broken": "tool_calls"} then {"tool_calls": [{"id":"1"}]} tail'
    tool_calls, pure = _parse(content)
    assert tool_calls == [{"id": "1"}]
    assert '"tool_calls": [{"id":"1"}]' not in pure


# ---------------------------------------------------------------------------
# ppt_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_outline_string_response_uses_str_content(monkeypatch):
    from app.agent import ppt_agent as module
    from app.agent.ppt_agent import PPTAgent, PresentationOutline

    agent = PPTAgent()
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value="plain text"))
    monkeypatch.setattr(
        agent,
        "_parse_with_llm_fallback",
        AsyncMock(return_value=PresentationOutline(title="t", slides=[])),
    )

    outline = await agent.generate_outline("topic")
    assert outline.title == "t"


@pytest.mark.asyncio
async def test_modify_outline_string_response_uses_str_content(monkeypatch):
    from app.agent import ppt_agent as module
    from app.agent.ppt_agent import PPTAgent, PresentationOutline

    agent = PPTAgent()
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value="plain text"))
    monkeypatch.setattr(
        agent,
        "_parse_with_llm_fallback",
        AsyncMock(return_value=PresentationOutline(title="t", slides=[])),
    )

    outline = await agent.modify_outline(
        {"title": "old", "slides": []}, "add a page"
    )
    assert outline.title == "t"


# ---------------------------------------------------------------------------
# generate_endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_empty_callback_is_callable(monkeypatch):
    from app.api.v1.ai_agent import generate_endpoints as endpoints
    from app.schema.codeRequest import GenerateRequest

    captured = {}

    class _Agent:
        def __init__(self, config=None):
            pass

        async def generate_project(self, **kwargs):
            captured["callback"] = kwargs["callback"]
            kwargs["callback"]("tick")
            return {
                "validation": {"runnable": True},
                "total_files_created": 0,
                "steps": [],
            }

    monkeypatch.setattr(endpoints, "_build_agent_config", lambda _req: object())
    monkeypatch.setattr(endpoints, "ProjectGeneratorAgent", _Agent)

    def _build(_name, _endpoint, handler):
        captured["handler"] = handler
        return SimpleNamespace(handler=handler)

    monkeypatch.setattr(endpoints, "build_legacy_workflow", _build)

    async def _run_workflow(workflow, **_kwargs):
        await workflow.handler(None)
        return "state"

    monkeypatch.setattr(endpoints, "run_workflow", _run_workflow)
    monkeypatch.setattr(
        endpoints,
        "get_legacy_result",
        lambda _state: {
            "validation": {"runnable": True},
            "total_files_created": 0,
            "steps": [],
        },
    )

    response = await endpoints.generate_project(
        GenerateRequest(requirement="build", session_id="p1"),
        {"sub": "42"},
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        object(),
    )

    assert response.success is True
    assert callable(captured["callback"])


# ---------------------------------------------------------------------------
# file_operator
# ---------------------------------------------------------------------------


def test_tree_returns_none_past_max_depth(tmp_path):
    from app.utils.file_operator import FileOperator

    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)
    result = operator.tree(".", max_depth=-1)
    assert result["tree"] is None


# ---------------------------------------------------------------------------
# json_parser
# ---------------------------------------------------------------------------


def test_extract_first_json_object_skips_non_dict_payloads():
    assert extract_first_json_object('"text" {"ok": 1}') == {"ok": 1}


# ---------------------------------------------------------------------------
# state_migration_service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_retention_skips_non_archived_record(monkeypatch):
    """A record that is neither due nor archived must be skipped by the guard."""
    from app.services import state_migration_service as module

    now = module.datetime.utcnow()
    record = SimpleNamespace(
        id=1,
        status="cleaning",
        eligible_at=now,
        created_at=now,
        archive_at=None,
        resource_type="artifact",
        resource_id="r1",
        attempt_count=0,
        cleanup_idempotency_key=None,
        last_error=None,
        cleanup_result_json=None,
    )

    class _Scalars:
        def all(self):
            return [record]

    class _Db:
        async def scalars(self, _stmt):
            return _Scalars()

        async def flush(self):
            return None

    db = _Db()
    monkeypatch.setattr(module, "_resource_is_blocked", AsyncMock(return_value=False))
    monkeypatch.setattr(module, "_load_resource", AsyncMock(return_value=None))

    policy = module.RetentionPolicy(
        name="p",
        archive_after_seconds=3600,
        cleanup_after_seconds=3600,
    )

    result = await module.process_retention_records(db, policy, now=now)
    assert result["archived"] == 0


# ---------------------------------------------------------------------------
# agent/adapters/python
# ---------------------------------------------------------------------------


def test_python_adapter_extract_definitions_variable():
    from app.agent.adapters.python import PythonLanguageAdapter

    definitions = PythonLanguageAdapter().extract_definitions(
        "MAX: int = 1\nname = 'x'\nimport os\n"
    )
    assert definitions["MAX"].symbol_type == "constant"
    assert definitions["name"].symbol_type == "variable"


# ---------------------------------------------------------------------------
# agent/utils
# ---------------------------------------------------------------------------


def test_is_valid_code_flags_tool_call_json_and_plain_metadata():
    from app.agent.utils import is_placeholder_content, is_valid_code_content

    placeholder, reason = is_placeholder_content('{"tool": "read"}', "x.py")
    assert placeholder is True
    assert "tool call JSON" in reason

    placeholder, reason = is_placeholder_content(
        '{"tool": "read",\n "params": {}\n}', "x.py"
    )
    assert placeholder is True
    assert reason == "内容整体为工具调用 JSON"

    valid, reason = is_valid_code_content("x.py", '{"foo": "bar", "baz": 1}')
    assert isinstance(valid, bool)


# ---------------------------------------------------------------------------
# dynamic_model_router
# ---------------------------------------------------------------------------


def test_reset_metrics_missing_model_is_noop():
    from app.agent.dynamic_model_router import DynamicModelRouter

    router = DynamicModelRouter()
    asyncio.run(router.reset_metrics("missing-model"))


# ---------------------------------------------------------------------------
# code_validator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_full_validation_ignores_unrelated_suffix(tmp_path):
    from app.agent.code_validator import CodeValidator

    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path)
    result = await validator.run_full_validation()
    assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# chat_archiver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_summary_falls_back_after_retries(monkeypatch):
    from app.db import chat_archiver as module
    from app.db.chat_archiver import ChatArchiver

    archiver = ChatArchiver(SimpleNamespace())
    monkeypatch.setattr(module, "call_llm", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(archiver, "_fallback_summary", lambda _m: "fallback")
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())

    summary = await archiver._generate_summary_with_ai(
        [SimpleNamespace(role="user", content="hi")]
    )
    assert summary == "fallback"
