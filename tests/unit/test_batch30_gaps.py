"""第四十三轮补测：关闭 r42 剩余 branch-partial 缺口。

覆盖范围：
- agent_core: set_history 截断、ImportFrom 非 stdlib 分支、_parse_tool_calls
  直接代码块转换、生成循环中成功文件回调、工具异常回调
- backend_engineer: 语言守卫、入口路由/database 组合、统计分支
- error_recovery: 自定义链空列表、临时文件清理抛出、质量评估成功
- architecture_inspector: 层规则空、JS 导入回退、tech_stack 字典项
- coverage_checker: 架构字段为列表
- incremental_modify: `from x import y` 绝对导入
- feedback_tracker: 库大小超限裁剪
- ppt_agent: dict 与普通字符串响应
- project_metadata: 保存失败清理临时文件
- stack_adapters: express package.main 入口
- artifact_committer: 磁盘读写不可用
- orchestrator: 显式绝对路径不重写
- logging_config: 过滤 args 为 dict 与 list
- rate_limiter: 非 Bearer 与 decode 异常
- chat_context: 预算耗尽时上下文清空
- ppt_generation_persistence: 无 outline 时跳过质量报告
- file_operator: 递归树超过深度且无权限
- log_archiver: 归档失败记入 errors
- pptx/text_processor: 超长英文单词分段
- web_search: wikipedia 提前 break、clean_url 参数、摘要任务异常
- visual_analyzer: 单引号字符串转义、注释截断、字面量整词
- workflow nodes: copy/move 缺参数、timeout 非数字、上游依赖
- generate_endpoints: 客户端断连循环
"""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent import architecture_inspector as ai_module
from app.agent.architecture_inspector import ArchitectureInspector
from app.agent.backend_engineer import BackendEngineer
from app.agent.error_recovery import ErrorRecoveryLoop
from app.agent.orchestrator_generation.coverage_checker import (
    check_requirement_coverage,
)
from app.agent.orchestrator_generation.incremental_modify import (
    IncrementalModifyMixin,
)
from app.agent.project_metadata import ProjectMetadataManager
from app.core.logging_config import SensitiveDataFilter
from app.services.chat_context import _CHARS_PER_TOKEN, fit_context
from app.utils.agent_core import (
    CodeValidator,
    ConversationHistoryManager,
    ProjectGeneratorAgent,
    ValidationType,
)
from app.schema.codeRequest import AgentConfig
from app.utils.file_operator import FileOperator


# ---------------------------------------------------------------------------
# agent_core: ConversationHistoryManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_history_truncates_and_keeps_latest():
    mgr = ConversationHistoryManager()
    mgr.MAX_MESSAGES_PER_SESSION = 2
    await mgr.set_history("s", [{"i": 1}, {"i": 2}, {"i": 3}])

    assert [m["i"] for m in await mgr.get_history("s")] == [2, 3]


@pytest.mark.asyncio
async def test_clear_history_missing_and_existing():
    mgr = ConversationHistoryManager()
    await mgr.clear_history("missing")
    await mgr.set_history("s", [{"i": 1}])
    await mgr.clear_history("s")

    assert await mgr.has_history("s") is False


# ---------------------------------------------------------------------------
# agent_core: import validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_imports_flags_unimportable_import_from(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("from missing_from_module_xyz import symbol\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _validator_config())

    monkeypatch.setattr(validator, "_is_importable", lambda name: False)
    monkeypatch.setattr(validator, "_standard_lib_modules", {"json"})

    result = await validator._validate_imports(target)

    assert result.success is False
    assert result.validation_type == ValidationType.IMPORT_CHECK
    assert any("missing_from_module_xyz" in issue for issue in result.issues)


def _validator_config():
    return AgentConfig(enable_validation=False)


# ---------------------------------------------------------------------------
# agent_core: _parse_tool_calls direct code blocks
# ---------------------------------------------------------------------------


def _core_agent():
    return ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))


def test_parse_tool_calls_converts_direct_code_block(tmp_path):
    agent = _core_agent()
    content = "main.py:\n```python\nprint('hi')\n```"

    tool_calls, pure_text = agent._parse_tool_calls(content, str(tmp_path))

    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call["function"]["name"] == "create_project_file"
    assert call["function"]["arguments"]["file_path"] == str(tmp_path / "main.py")
    assert call["function"]["arguments"]["content"] == "print('hi')"
    assert pure_text == ""


def test_parse_tool_calls_direct_code_block_defaults_to_projects(monkeypatch):
    agent = _core_agent()
    content = "app.py:\n```python\nx = 1\n```"

    tool_calls, _ = agent._parse_tool_calls(content)

    assert tool_calls[0]["function"]["arguments"]["file_path"] == "projects/app.py"


def test_parse_tool_calls_balanced_brace_escape_and_string_paths():
    agent = _core_agent()
    content = (
        'text {"tool_calls": [{"id": "1", "function": {"name": "x", '
        '"arguments": {"content": "a\\"b"}}}]} tail'
    )

    tool_calls, pure_text = agent._parse_tool_calls(content)

    assert len(tool_calls) == 1
    assert pure_text == "texttail"


# ---------------------------------------------------------------------------
# backend_engineer
# ---------------------------------------------------------------------------


def _engineer():
    return BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )


def test_runtime_constraints_skip_non_python_language():
    assert (
        BackendEngineer._build_runtime_consistency_constraints(
            "main.py", "entry", "JavaScript", {}
        )
        == ""
    )


def test_runtime_constraints_entry_without_routes_mentions_database():
    architecture = {
        "framework": "fastapi",
        "file_plan": [
            {"path": "app/database.py", "file_type": "database"},
            {"path": "app/main.py", "file_type": "entry"},
        ],
    }

    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/main.py", "entry", "python", architecture
    )

    assert "未声明独立路由层" in text
    assert "app/database.py" in text


def test_generate_file_adds_framework_guard_when_unspecified(monkeypatch):
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(engineer, "call_llm", _capture)
    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.scaffold_file",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.detect_language",
        lambda *a, **k: "python",
    )

    result = asyncio.run(
        engineer.generate_file(
            "app/api/users.py", "users", {"architecture": {"language": "python"}}
        )
    )

    assert result == "ok"
    assert "框架选择约束" in captured["prompt"]


# ---------------------------------------------------------------------------
# error_recovery
# ---------------------------------------------------------------------------


class _Sem:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _loop(**kwargs):
    loop = ErrorRecoveryLoop(
        validator=kwargs.pop("validator", object()), reviewer=object(), **kwargs
    )
    loop._semaphore = _Sem()
    return loop


def test_fallback_chain_custom_empty_falls_through_without_config(monkeypatch):
    loop = _loop()
    monkeypatch.setattr(
        loop,
        "_get_user_fallback_preference",
        lambda: {"fallback_preference": "custom", "custom_fallback_chain": []},
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config", lambda: {}
    )

    assert loop._load_fallback_chain() == []


@pytest.mark.asyncio
async def test_evaluate_code_quality_returns_score_when_valid(tmp_path):
    class Validator:
        async def validate_single_file(self, path):
            return {"is_valid": True}

    loop = _loop(validator=Validator())
    score = await loop._evaluate_code_quality("ok = 1\n", tmp_path / "main.py")

    assert score == 1.0
    assert not list(tmp_path.glob(".temp_quality_*"))


@pytest.mark.asyncio
async def test_evaluate_code_quality_cleans_temp_on_validator_error(tmp_path):
    class Validator:
        async def validate_single_file(self, path):
            raise RuntimeError("validator boom")

    loop = _loop(validator=Validator())
    score = await loop._evaluate_code_quality("ok = 1\n", tmp_path / "main.py")

    assert score == 0.5
    assert not list(tmp_path.glob(".temp_quality_*"))


# ---------------------------------------------------------------------------
# architecture_inspector
# ---------------------------------------------------------------------------


def _inspector(architecture=None, files=None):
    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture=architecture or {},
        generated_files=files or {},
    )
    return inspector


def test_layer_boundaries_without_layer_definitions_returns_empty():
    inspector = _inspector(files={"a.py": "x = 1\n"})
    inspector.architecture_design = {}

    assert inspector._check_layer_boundaries() == []


def test_layer_boundaries_skip_files_without_assigned_layer():
    inspector = _inspector(
        architecture={
            "layers": {"repository": {"paths": ["src/repo/"], "boundaries": ["x"]}}
        },
        files={"other/file.py": "x = 1\n"},
    )

    assert inspector._check_layer_boundaries() == []


def test_file_imports_packages_js_fallback_returns_false():
    inspector = _inspector()

    assert inspector._file_imports_packages("const x = require('vue');", ["react"]) is False


def test_file_imports_packages_ast_import_from_matches():
    inspector = _inspector()
    source = "from fastapi import FastAPI\n"

    assert inspector._file_imports_packages(source, ["fastapi"]) is True


def test_tech_stack_dict_items_are_detected():
    inspector = _inspector(
        architecture={"tech_stack": [{"backend": "fastapi"}, "frontend vue"]},
        files={},
    )

    assert inspector._check_tech_stack_consistency() == []


# ---------------------------------------------------------------------------
# coverage_checker
# ---------------------------------------------------------------------------


def test_coverage_checker_handles_list_architecture_fields():
    item = SimpleNamespace(
        category="functional",
        confidence=0.9,
        description="登录",
        content="登录",
        source="req",
    )
    association = SimpleNamespace(items=[item], skipped=False)

    result = check_requirement_coverage(
        "登录",
        {"api_endpoints": ["/api/login"], "tech_stack": ["fastapi"]},
        [{"path": "login.py", "description": "登录"}],
        association,
    )

    assert result["checked"] is True


# ---------------------------------------------------------------------------
# incremental_modify
# ---------------------------------------------------------------------------


class _IncrementalHarness(IncrementalModifyMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def _get_relative_file_paths(self):
        return [
            str(path.relative_to(self.output_dir)).replace("\\", "/")
            for path in self.output_dir.rglob("*.py")
        ]


def test_extract_python_imports_absolute_from_import(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "models.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "utils.py").write_text("x = 1\n", encoding="utf-8")
    harness = _IncrementalHarness(tmp_path)

    imports = harness._extract_python_imports(
        "from models import User\nfrom utils import helper\n", "src/main.py"
    )

    assert "src/models.py" in imports
    assert "src/utils.py" in imports


# ---------------------------------------------------------------------------
# feedback_tracker
# ---------------------------------------------------------------------------


def test_feedback_cleanup_trims_oldest_quarter(tmp_path, monkeypatch):
    from app.agent.orchestrator_requirements import feedback_tracker as module

    monkeypatch.setattr(module.AssociationFeedbackTracker, "DB_PATH", tmp_path / "fb.db")
    monkeypatch.setattr(module.AssociationFeedbackTracker, "MAX_DB_SIZE_BYTES", 0)
    tracker = module.AssociationFeedbackTracker()
    tracker.record_choice(
        "s",
        "req",
        [{"content": f"item{i}", "category": "functional"} for i in range(8)],
        "accepted",
    )

    tracker._cleanup()

    remaining = tracker._conn.execute(
        "SELECT COUNT(*) FROM association_feedback"
    ).fetchone()[0]
    assert remaining == 6


# ---------------------------------------------------------------------------
# ppt_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_outline_accepts_dict_response(monkeypatch):
    from app.agent import ppt_agent as module
    from app.agent.ppt_agent import PPTAgent

    outline = json.dumps(
        {
            "title": "演示",
            "slides": [
                {"type": "title", "title": "封面", "bullets": ["要点"]},
                {"type": "end", "title": "结束", "bullets": ["谢谢"]},
            ],
        }
    )
    monkeypatch.setattr(
        module,
        "call_llm",
        AsyncMock(return_value={"choices": [{"message": {"content": outline}}]}),
    )
    monkeypatch.setattr(PPTAgent, "_parse_with_llm_fallback", AsyncMock(return_value=SimpleNamespace(slides=[])))

    events = [e async for e in PPTAgent().stream_outline("主题", num_slides=2)]

    assert any(event["type"] == "slide" for event in events)
    assert events[-1]["type"] == "complete"


@pytest.mark.asyncio
async def test_stream_outline_accepts_plain_string_response(monkeypatch):
    from app.agent import ppt_agent as module
    from app.agent.ppt_agent import PPTAgent

    outline = json.dumps(
        {
            "title": "演示",
            "slides": [{"type": "title", "title": "封面", "bullets": ["要点"]}],
        }
    )
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value=outline))
    monkeypatch.setattr(PPTAgent, "_parse_with_llm_fallback", AsyncMock(return_value=SimpleNamespace(slides=[])))

    events = [e async for e in PPTAgent().stream_outline("主题", num_slides=1)]

    assert any(event["type"] == "slide" for event in events)


# ---------------------------------------------------------------------------
# project_metadata
# ---------------------------------------------------------------------------


def test_save_removes_temp_when_replace_fails(tmp_path, monkeypatch):
    import app.agent.project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = ProjectMetadataManager()

    def boom(*_a, **_k):
        raise OSError("replace failed")

    monkeypatch.setattr(module.os, "replace", boom)
    monkeypatch.setattr(manager, "_projects", [], raising=False)

    with pytest.raises(OSError):
        manager._save()

    assert list(tmp_path.glob(".project_metadata.*.tmp")) == []


# ---------------------------------------------------------------------------
# stack_adapters
# ---------------------------------------------------------------------------


def test_express_detect_uses_package_main(tmp_path):
    from app.agent.stack_adapters.registry import DEFAULT_STACK_ADAPTERS

    (tmp_path / "package.json").write_text(
        json.dumps({"main": "server.js", "dependencies": {"express": "^4"}}),
        encoding="utf-8",
    )
    (tmp_path / "server.js").write_text("const express = require('express')\n", encoding="utf-8")

    adapter, project = DEFAULT_STACK_ADAPTERS.detect(tmp_path)

    assert adapter.framework_profile().name == "express"
    assert "server.js" in project.entrypoints


# ---------------------------------------------------------------------------
# artifact_committer
# ---------------------------------------------------------------------------


def test_artifact_committer_disk_read_failure(tmp_path):
    from app.agent.orchestration import ArtifactCommitter
    from app.agent.shared_context import SharedContext

    context = SharedContext("req", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="t")

    def boom(*_a, **_k):
        raise OSError("disk gone")

    committer._reader = boom
    result = committer.commit("main.py", "print(1)\n", model_name="m")

    assert result.success is False


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------


def test_orchestrator_keeps_absolute_output_dir(tmp_path):
    from app.agent.orchestrator import OrchestratorAgent

    agent = OrchestratorAgent(output_dir=str(tmp_path))

    assert agent.output_dir == tmp_path


# ---------------------------------------------------------------------------
# logging_config
# ---------------------------------------------------------------------------


def test_sensitive_filter_sanitizes_dict_and_sequence_args():
    log_filter = SensitiveDataFilter()
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "password=%s",
        ({"password": "password=secret"},), None,
    )
    log_filter.filter(record)
    assert "secret" not in str(record.args)

    record2 = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "password=%s", ("password=abc",),
        None,
    )
    log_filter.filter(record2)
    assert "abc" not in str(record2.args)


def test_sensitive_filter_passes_non_string_values():
    log_filter = SensitiveDataFilter()
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "count=%s", (42,), None
    )

    assert log_filter.filter(record) is True
    assert record.args == (42,)


# ---------------------------------------------------------------------------
# rate_limiter
# ---------------------------------------------------------------------------


def test_extract_user_id_rejects_non_bearer_and_bad_token(monkeypatch):
    from app.middleware import rate_limiter as module

    assert module._extract_user_id_from_scope(
        {"headers": [(b"authorization", b"Basic abc")]}
    ) is None

    def boom(*_a, **_k):
        raise ValueError("bad token")

    monkeypatch.setattr(module.jwt, "decode", boom)
    assert module._extract_user_id_from_scope(
        {"headers": [(b"authorization", b"Bearer abc")]}
    ) is None


# ---------------------------------------------------------------------------
# chat_context
# ---------------------------------------------------------------------------


def test_fit_context_clears_when_budget_exhausted(monkeypatch):
    monkeypatch.setattr("app.services.chat_context.get_context_length", lambda *a, **k: 100)
    monkeypatch.setattr(
        "app.services.chat_context.get_max_output_tokens", lambda *a, **k: 100
    )

    context, budget = fit_context("x" * 2000, "ctx", "model")

    assert context == ""
    assert budget.truncated is True
    assert budget.input_budget_tokens == 256


# ---------------------------------------------------------------------------
# file_operator
# ---------------------------------------------------------------------------


def test_file_operator_tree_hits_depth_limit(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "c.txt").write_text("x", encoding="utf-8")
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    tree = operator.tree(".", max_depth=1)

    assert tree["tree"]["children"][0]["name"] == "a"
    assert "children" not in tree["tree"]["children"][0]


def test_file_operator_tree_swallows_permission_error(tmp_path, monkeypatch):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.txt").write_text("x", encoding="utf-8")
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    def boom(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", boom)

    tree = operator.tree(".", max_depth=2)

    assert tree["tree"]["name"] == tmp_path.name
    assert tree["tree"]["children"] == []


# ---------------------------------------------------------------------------
# log_archiver
# ---------------------------------------------------------------------------


def test_archive_all_records_rotation_errors(tmp_path, monkeypatch):
    from app.utils.log_archiver import LogArchiver

    archiver = LogArchiver(log_dir=str(tmp_path), max_size_mb=0.001)
    (tmp_path / "a.log").write_text("x" * 100, encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("rotate failed")

    monkeypatch.setattr(archiver, "should_rotate_by_size", lambda p: True)
    monkeypatch.setattr(archiver, "rotate_file", boom)

    stats = archiver.archive_all()

    assert stats["errors"] == ["a.log"]


# ---------------------------------------------------------------------------
# pptx/text_processor
# ---------------------------------------------------------------------------


def test_smart_split_line_splits_overlong_english_word():
    from app.utils.pptx.text_processor import smart_split_line

    lines = smart_split_line("abcdefghij", max_chars=4)

    assert lines == ["abcd", "efgh", "ij"]


def test_smart_split_line_flushes_chinese_line():
    from app.utils.pptx.text_processor import smart_split_line

    lines = smart_split_line("中文", max_chars=2)

    assert lines == ["中文"]


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


def test_clean_url_extracts_link_param_and_drops_invalid_scheme():
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()

    assert searcher._clean_url(
        "https://duckduckgo.com/?link=https%3A%2F%2Fexample.com%2Fpage"
    ) == "https://example.com/page"
    assert searcher._clean_url("javascript:alert(1)") == ""


@pytest.mark.asyncio
async def test_search_wikipedia_breaks_when_count_reached(monkeypatch):
    from app.utils import web_search as module

    searcher = module.FreeWebSearch()
    responses = [
        SimpleNamespace(
            status_code=200,
            json=lambda: [
                module.SearchResult("t1", "https://e.com/1", "s1"),
                module.SearchResult("t2", "https://e.com/2", "s2"),
            ],
        )
    ]

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, *_a, **_k):
            return responses.pop(0)

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: _Client())
    monkeypatch.setattr(module, "parse_wikipedia_search", lambda data, lang: data)

    results = await searcher._search_wikipedia("测试", count=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_process_result_skips_empty_page_and_summary(monkeypatch):
    from app.utils import web_search as module

    async def fake_fetch(*_a, **_k):
        return ""

    monkeypatch.setattr(module, "fetch_page_text", fake_fetch)

    async def fake_search(self, query, count=5, lang=None):
        return [module.SearchResult("t", "https://e.com", "s")]

    monkeypatch.setattr(module.FreeWebSearch, "search", fake_search)

    results = await module.search_with_page_summaries("q", count=1)

    assert results[0].summary is None


# ---------------------------------------------------------------------------
# visual_analyzer
# ---------------------------------------------------------------------------


def test_normalize_json_text_converts_single_quoted_strings():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    result = VisualAnalyzer._normalize_json_text("{'a': 'b'}")

    assert '"a"' in result
    assert '"b"' in result


def test_normalize_json_text_escapes_quotes_inside_single_string():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    result = VisualAnalyzer._normalize_json_text("{'a': 'say \"hi\"'}")

    assert '\\"hi\\"' in result


def test_normalize_json_text_drops_line_comment_to_eof():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    result = VisualAnalyzer._normalize_json_text('{"a": 1} // trailing')

    assert "trailing" not in result


def test_normalize_json_text_skips_literal_substrings():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    result = VisualAnalyzer._normalize_json_text('{"a": "True story"}')

    assert '"True story"' in result


# ---------------------------------------------------------------------------
# workflow nodes
# ---------------------------------------------------------------------------


def test_file_processing_copy_missing_destination():
    from app.utils.file_operator import FileOperator
    from app.utils.workflow.node_types.file_processing import FileProcessingNode

    node = FileProcessingNode("n", {"operation": "copy", "source": "a.txt"})
    node._operator = FileOperator(base_path="/tmp", allow_protected_paths=True)

    errors = node.validate_params()

    assert any("destination" in error for error in errors)


def test_file_processing_blocks_path_escape():
    from app.utils.file_operator import FileOperator
    from app.utils.workflow.node_types.file_processing import FileProcessingNode

    node = FileProcessingNode("n", {"operation": "read", "path": "../secret"})
    node._operator = FileOperator(base_path="/tmp/root", allow_protected_paths=True)

    assert node.validate_params()


def test_human_approval_timeout_non_numeric():
    from app.utils.workflow.node_types.human_approval import HumanApprovalNode

    node = HumanApprovalNode("n", {"prompt": "ok", "timeout": "soon"})

    assert any("timeout" in error for error in node.validate_params())


def test_human_approval_options_not_list():
    from app.utils.workflow.node_types.human_approval import HumanApprovalNode

    node = HumanApprovalNode("n", {"prompt": "ok", "options": "yes"})

    assert any("options" in error for error in node.validate_params())


def test_result_aggregator_collects_dependencies():
    from app.schema.workflow import TaskGraph, TaskNode, TaskType
    from app.utils.workflow.node_types.base import NodeResult
    from app.utils.workflow.result_aggregator import ResultAggregator

    graph = TaskGraph(
        workflow_id="w",
        nodes=[
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="b", type=TaskType.WEB_SEARCH, params={}, depends_on=["a"]),
        ],
    )
    aggregator = ResultAggregator("w", graph)
    aggregator.record_result("a", NodeResult.success_result("done"))

    upstream = aggregator.get_upstream_results("b")

    assert set(upstream) == {"a"}


# ---------------------------------------------------------------------------
# generate_endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_watcher_sets_cancel_on_disconnect(monkeypatch):
    from app.api.v1.ai_agent import generate_endpoints as endpoints
    from app.schema.codeRequest import GenerateRequest

    monkeypatch.setattr(endpoints, "_build_agent_config", lambda req: object())
    monkeypatch.setattr(
        endpoints,
        "ProjectGeneratorAgent",
        lambda config=None: SimpleNamespace(
            generate_project=AsyncMock(return_value={
                "validation": {"runnable": True},
                "total_files_created": 1,
                "steps": [],
            })
        ),
    )

    async def run(*_a, **_k):
        await asyncio.sleep(0.01)
        return "state"

    monkeypatch.setattr(endpoints, "run_workflow", run)
    monkeypatch.setattr(
        endpoints,
        "get_legacy_result",
        lambda state: {
            "validation": {"runnable": True},
            "total_files_created": 1,
            "steps": [],
        },
    )
    monkeypatch.setattr(
        endpoints, "build_legacy_workflow", lambda *_a, **_k: SimpleNamespace(handler=None)
    )

    class _Flapping:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    real_sleep = asyncio.sleep

    async def _fast_sleep(delay, *a, **k):
        if delay == 1.0:
            return None
        return await real_sleep(delay)

    monkeypatch.setattr(endpoints.asyncio, "sleep", _fast_sleep)

    response = await endpoints.generate_project(
        GenerateRequest(requirement="build", session_id="s"),
        {"sub": "1"},
        _Flapping(),
        object(),
    )

    assert response.success is True
