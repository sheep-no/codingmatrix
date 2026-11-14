"""第四十四轮补测：关闭 r43 剩余的 branch-partial 缺口。

本轮优先补齐真实可达的两侧分支；对 coverage.py 在 `async with` 末尾等
结构位置无法记录的退出 arc，保留在源码处用 `# pragma: no branch` 归因。
"""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# adapters / architecture_inspector
# ---------------------------------------------------------------------------


def test_python_adapter_skips_assignment_named_like_keyword():
    from app.agent.adapters.python import PythonLanguageAdapter

    definitions = PythonLanguageAdapter().extract_definitions(
        "import = 1\nfrom = 2\nreal_name: int = 3\n"
    )

    assert "import" not in definitions
    assert "from" not in definitions
    assert definitions["real_name"].symbol_type == "variable"


def test_layer_boundary_rule_without_match_advances_rule_loop():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture={
            "layers": {
                "repository": {
                    "paths": ["repositories"],
                    "boundaries": ["no_business_logic"],
                }
            }
        },
        generated_files={"app/repositories/user.py": "x = 1\n"},
    )

    assert inspector._check_layer_boundaries() == []


def test_tech_stack_list_ignores_unrecognized_string_entry():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture={"tech_stack": ["mobile flutter"]},
        generated_files={},
    )

    assert inspector._check_tech_stack_consistency() == []


def test_tech_stack_list_skips_non_dict_non_str_entry():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture={"tech_stack": [42, "backend python"]},
        generated_files={},
    )

    assert inspector._check_tech_stack_consistency() == []


# ---------------------------------------------------------------------------
# backend_engineer
# ---------------------------------------------------------------------------


def test_spec_constraints_without_storage_skips_storage_block():
    from app.agent.backend_engineer import BackendEngineer

    text = BackendEngineer._build_spec_constraints("api", {"framework": "FastAPI"})

    assert "FastAPI" in text
    assert "存储约束" not in text


@pytest.mark.asyncio
async def test_generate_file_skips_framework_guard_when_framework_declared(monkeypatch):
    from app.agent.backend_engineer import BackendEngineer

    engineer = BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )
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

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {"architecture": {"language": "python", "framework": "fastapi"}},
    )

    assert result == "ok"
    assert "框架选择约束" not in captured["prompt"]


@pytest.mark.asyncio
async def test_react_path_skips_preverification_without_read_symbols_tool(monkeypatch):
    from app.agent.backend_engineer import BackendEngineer

    engineer = BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )
    engineer.call_llm = AsyncMock(return_value="plain")
    engineer.call_llm_with_tools = AsyncMock(return_value="generated")
    monkeypatch.setattr(
        "app.agent.tools.SPECIALIST_TOOLS",
        {"read_file": {"fn": MagicMock()}},
    )

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {"architecture": {"language": "python"}, "requirement": "build"},
        dep_context="## 依赖文件: app/models.py\ncode",
        project_path="/tmp/project",
    )

    assert result == "generated"
    kwargs = engineer.call_llm_with_tools.await_args.kwargs
    assert kwargs["preverified_tool_names"] == set()
    assert kwargs["required_tool_names"] == {"read_symbols"}


@pytest.mark.asyncio
async def test_react_path_moves_to_next_dependency_when_symbol_read_fails(monkeypatch):
    from app.agent.backend_engineer import BackendEngineer

    engineer = BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )
    engineer.call_llm_with_tools = AsyncMock(return_value="generated")
    read_symbols = MagicMock(return_value={"success": False})
    monkeypatch.setattr(
        "app.agent.tools.SPECIALIST_TOOLS",
        {"read_symbols": {"fn": read_symbols}},
    )

    await engineer.generate_file(
        "app/api/users.py",
        "users",
        {"architecture": {"language": "python"}, "requirement": "build"},
        dep_context="## 依赖文件: app/models.py\n## 依赖文件: app/db.py\ncode",
        project_path="/tmp/project",
    )

    assert read_symbols.call_count == 2
    kwargs = engineer.call_llm_with_tools.await_args.kwargs
    assert kwargs["preverified_tool_names"] == set()


@pytest.mark.asyncio
async def test_analyze_skips_list_files_without_tool(monkeypatch):
    from app.agent.backend_engineer import BackendEngineer

    engineer = BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )
    engineer.call_llm = AsyncMock(return_value="analysis")
    monkeypatch.setattr(
        "app.agent.tools.SPECIALIST_TOOLS",
        {"read_file": {"fn": MagicMock()}},
    )

    result = await engineer.analyze("what?", "/tmp/project")

    assert result == "analysis"


@pytest.mark.asyncio
async def test_analyze_ignores_empty_list_files_result(monkeypatch):
    from app.agent.backend_engineer import BackendEngineer

    engineer = BackendEngineer(
        role_name="backend", model_name="test-model", task_type="generate"
    )
    engineer.call_llm = AsyncMock(return_value="analysis")
    monkeypatch.setattr(
        "app.agent.tools.SPECIALIST_TOOLS",
        {"list_files": {"fn": MagicMock(return_value={})}},
    )

    result = await engineer.analyze("what?", "/tmp/project")

    assert result == "analysis"


# ---------------------------------------------------------------------------
# error_recovery
# ---------------------------------------------------------------------------


class _ImmediateSem:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _AlwaysBudget:
    def consume(self, _category):
        return True

    def can_consume(self, _category):
        return True


def _checking_loop(validator):
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=validator, reviewer=object())
    loop._semaphore = _ImmediateSem()
    loop.repair_budget = _AlwaysBudget()
    loop.MAX_FIX_ATTEMPTS = 1
    return loop


def test_fallback_chain_skips_non_custom_preference(monkeypatch):
    from app.agent import error_recovery as module

    loop = _checking_loop(object())
    monkeypatch.setattr(
        loop,
        "_get_user_fallback_preference",
        lambda: {"fallback_preference": "use_admin_default"},
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config", lambda: {}
    )

    assert loop._load_fallback_chain() == []


@pytest.mark.asyncio
async def test_fix_validation_success_without_strategy_returns_result(tmp_path, monkeypatch):
    from app.agent import error_recovery as module
    from app.agent.error_classifier import ErrorClassification

    class Validator:
        async def validate_single_file(self, path):
            Path(path).unlink(missing_ok=True)
            return {"is_valid": True}

    loop = _checking_loop(Validator())

    async def fake_classify(*_a, **_k):
        return ErrorClassification(
            error_type="SyntaxError",
            error_subtype="sub",
            description="bad",
            suggested_fix_strategy="fix",
            confidence=0.9,
        )

    monkeypatch.setattr(
        module,
        "error_classifier",
        SimpleNamespace(classify_error=fake_classify, add_to_history=lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
    )
    monkeypatch.setattr(
        module.RepairRouter,
        "route",
        lambda *_a, **_k: SimpleNamespace(auto_apply=True, category="syntax", max_attempts=1),
    )

    async def fake_llm(**_kwargs):
        return {"choices": [{"message": {"content": "a = 1\n"}}]}

    monkeypatch.setattr(module, "call_llm", fake_llm)

    result = await loop._smart_fix_loop(
        file_path=tmp_path / "main.py",
        content="a = 2\n",
        errors={"syntax_errors": ["bad"]},
        backend_model="model-a",
    )

    assert result == {"success": True, "fixed_content": "a = 1\n"}
    assert not list(tmp_path.glob(".temp_fix_*"))


@pytest.mark.asyncio
async def test_fix_exception_without_strategy_retries_next_attempt(tmp_path, monkeypatch):
    from app.agent import error_recovery as module
    from app.agent.error_classifier import ErrorClassification

    loop = _checking_loop(object())
    loop.MAX_FIX_ATTEMPTS = 2

    async def fake_classify(*_a, **_k):
        return ErrorClassification(
            error_type="SyntaxError",
            error_subtype="sub",
            description="bad",
            suggested_fix_strategy="fix",
            confidence=0.9,
        )

    monkeypatch.setattr(
        module,
        "error_classifier",
        SimpleNamespace(classify_error=fake_classify, add_to_history=lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        module.strategy_evaluator, "get_strategy_template", lambda _t: (None, None)
    )
    monkeypatch.setattr(
        module.RepairRouter,
        "route",
        lambda *_a, **_k: SimpleNamespace(auto_apply=True, category="syntax", max_attempts=2),
    )
    calls = {"n": 0}

    async def fake_llm(**_kwargs):
        calls["n"] += 1
        raise RuntimeError("llm down")

    monkeypatch.setattr(module, "call_llm", fake_llm)

    result = await loop._smart_fix_loop(
        file_path=tmp_path / "main.py",
        content="a = 2\n",
        errors={"syntax_errors": ["bad"]},
        backend_model="model-a",
    )

    assert result["success"] is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_quality_evaluation_continues_when_temp_file_removed(tmp_path):
    class Validator:
        async def validate_single_file(self, path):
            Path(path).unlink(missing_ok=True)
            return {"is_valid": True}

    loop = _checking_loop(Validator())

    score = await loop._evaluate_code_quality("ok = 1\n", tmp_path / "main.py")

    assert score == 1.0
    assert not list(tmp_path.glob(".temp_quality_*"))


# ---------------------------------------------------------------------------
# artifact_committer / coverage_checker / incremental_modify
# ---------------------------------------------------------------------------


def test_artifact_commit_rewrites_when_disk_content_differs(tmp_path):
    from app.agent.orchestration import ArtifactCommitter
    from app.agent.shared_context import SharedContext

    context = SharedContext("rewrite", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="t")
    first = committer.commit("main.py", "print('ok')\n", model_name="m")
    assert first.success is True

    reads = {"count": 0}
    real_read = Path.read_bytes

    def stale_then_fresh(path):
        reads["count"] += 1
        if reads["count"] == 1:
            return b"different"
        return real_read(path)

    tampered = ArtifactCommitter(tmp_path, context, task_id="t", reader=stale_then_fresh)
    second = tampered.commit("main.py", "print('ok')\n", model_name="m")

    assert second.success is True
    assert second.idempotent is False


def test_coverage_checker_skips_non_str_non_list_architecture_value():
    from app.agent.orchestrator_generation.coverage_checker import check_requirement_coverage

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
        {"database": 3, "api_endpoints": ["/api/login"]},
        [{"path": "login.py", "description": "登录"}],
        association,
    )

    assert result["checked"] is True


def test_extract_python_imports_ignores_unmatched_from_line(tmp_path):
    from app.agent.orchestrator_generation.incremental_modify import IncrementalModifyMixin

    class Harness(IncrementalModifyMixin):
        def __init__(self, output_dir):
            self.output_dir = output_dir

        def _get_relative_file_paths(self):
            return []

    harness = Harness(tmp_path)

    assert harness._extract_python_imports("from ( import x\n", "main.py") == []


# ---------------------------------------------------------------------------
# project_metadata / stack_adapters / utils / logging / chat_context
# ---------------------------------------------------------------------------


def test_project_metadata_save_reraises_without_existing_temp(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = module.ProjectMetadataManager()
    manager._projects = {"a": {}}

    def boom(*_a, **_k):
        raise RuntimeError("replace failed")

    monkeypatch.setattr(module.os, "replace", boom)
    monkeypatch.setattr(module.os.path, "exists", lambda _p: False)

    with pytest.raises(RuntimeError):
        manager._save()


def test_express_detect_with_missing_main_entrypoint(tmp_path):
    from app.agent.stack_adapters.adapters import ExpressStackAdapter

    (tmp_path / "package.json").write_text(
        '{"main": "missing.js", "dependencies": {"express": "^4.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "server.js").write_text(
        "const app = express()\n", encoding="utf-8"
    )

    project = ExpressStackAdapter().detect(tmp_path)

    assert "server.js" in project.entrypoints


def test_is_valid_content_rejects_json_array():
    from app.agent.utils import is_valid_code_content

    valid, reason = is_valid_code_content("data.txt", '["a", "b"]')

    assert valid is False
    assert "JSON 数组" in reason


def test_sensitive_filter_skips_empty_msg_and_non_sequence_args():
    from app.core.logging_config import SensitiveDataFilter

    data_filter = SensitiveDataFilter()
    empty = logging.LogRecord("n", logging.INFO, "f", 1, "", None, None)
    assert data_filter.filter(empty) is True

    numeric = logging.LogRecord("n", logging.INFO, "f", 1, "hello %s", ("x",), None)
    numeric.args = 5
    assert data_filter.filter(numeric) is True


def test_fit_context_keeps_short_context(monkeypatch):
    from app.services.chat_context import fit_context

    monkeypatch.setattr("app.services.chat_context.get_context_length", lambda *_: 4096)
    monkeypatch.setattr(
        "app.services.chat_context.get_max_output_tokens",
        lambda *_a, **_k: 256,
    )

    context, budget = fit_context("hi", "short context", "test-model")

    assert context == "short context"
    assert budget.truncated is False


# ---------------------------------------------------------------------------
# ppt persistence / ppt_agent
# ---------------------------------------------------------------------------


@pytest.fixture
async def persistence_db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_without_outline_skips_quality_report(persistence_db, tmp_path):
    from app.services.ppt_generation_persistence import persist_ppt_generation_result
    from app.services.unified_state_service import create_task
    from app.utils.pptx.quality import QualityReport

    task = await create_task(persistence_db, 1, "ppt_generation", task_id="ppt-no-outline")
    output = tmp_path / "no-outline.pptx"
    output.write_bytes(b"ppt")
    trace = {"outline_id": None, "outline_version": None}

    ids = await persist_ppt_generation_result(
        persistence_db,
        task.task_id,
        1,
        output,
        "pptx",
        {"filename": output.name, "preview_url": "/api/v1/pptx/preview/x"},
        trace,
        [],
        QualityReport(),
    )

    assert ids["quality_report"] is None


@pytest.mark.asyncio
async def test_stream_outline_retries_after_unparsable_response(monkeypatch):
    from app.agent import ppt_agent as module
    from app.agent.ppt_agent import PPTAgent

    valid = module.PresentationOutline(
        title="演示",
        slides=[
            module.SlideOutline(type="title", title="封面"),
            module.SlideOutline(type="end", title="谢谢"),
        ],
    )
    responses = iter([
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": "also not json"}}]},
    ])

    async def fake_llm(**_kwargs):
        return next(responses)

    parsed = iter([None, valid])

    async def fake_parse(*_a, **_k):
        return next(parsed)

    async def fast_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(module, "call_llm", fake_llm)
    monkeypatch.setattr(module.asyncio, "sleep", fast_sleep)
    agent = PPTAgent()
    monkeypatch.setattr(agent, "_parse_with_llm_fallback", fake_parse)

    events = [event async for event in agent.stream_outline("主题", num_slides=2)]

    assert any(event["type"] == "retry" for event in events)
    assert events[-1]["type"] == "complete"


# ---------------------------------------------------------------------------
# file_operator / log_archiver / pptx text / result_aggregator
# ---------------------------------------------------------------------------


def test_file_operator_tree_skips_unexpected_falsy_child(tmp_path, monkeypatch):
    from app.utils.file_operator import FileOperator

    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.txt").write_text("x", encoding="utf-8")
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        entries = list(real_iterdir(self))
        if self == tmp_path / "d":
            entries.append(tmp_path / "d" / "ghost")
        return iter(entries)

    def fake_build_tree(path, depth):
        if path.name == "ghost":
            return None
        if path.is_dir():
            return {"name": path.name, "type": "directory", "children": []}
        return {"name": path.name, "type": "file"}

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    tree = operator.tree(".", max_depth=2)

    assert tree["tree"]["name"] == tmp_path.name


def test_log_archiver_advances_when_rotation_returns_none(tmp_path, monkeypatch):
    from app.utils.log_archiver import LogArchiver

    archiver = LogArchiver(log_dir=str(tmp_path), max_size_mb=0.001)
    (tmp_path / "a.log").write_text("x" * 100, encoding="utf-8")
    (tmp_path / "b.log").write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(archiver, "should_rotate_by_size", lambda p: True)
    monkeypatch.setattr(archiver, "rotate_file", lambda p: None)

    stats = archiver.archive_all()

    assert stats["rotated"] == []


def test_smart_split_line_with_only_whitespace_returns_empty():
    from app.utils.pptx.text_processor import smart_split_line

    assert smart_split_line("     ", max_chars=2) == []


def test_get_upstream_results_skips_missing_dependency():
    from app.schema.workflow import TaskGraph, TaskNode, TaskType
    from app.utils.workflow.node_types.base import NodeResult
    from app.utils.workflow.result_aggregator import ResultAggregator

    simple_graph = TaskGraph(
        workflow_id="test_workflow",
        nodes=[
            TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}),
            TaskNode(
                id="node_4",
                type=TaskType.FILE_PROCESSING,
                params={},
                depends_on=["node_2", "node_3"],
            ),
        ],
    )
    aggregator = ResultAggregator("test_workflow", simple_graph)
    aggregator.record_result("node_2", NodeResult.success_result(data="r2"))

    upstream = aggregator.get_upstream_results("node_4")

    assert set(upstream) == {"node_2"}


# ---------------------------------------------------------------------------
# workflow node validation
# ---------------------------------------------------------------------------


def test_human_approval_accepts_valid_timeout_and_options():
    from app.utils.workflow.node_types.human_approval import HumanApprovalNode

    node = HumanApprovalNode(
        "n", {"prompt": "confirm?", "timeout": 5, "options": ["yes", "no"]}
    )

    assert node.validate_params() == []


def test_file_processing_accepts_copy_with_all_params(tmp_path):
    from app.utils.file_operator import FileOperator
    from app.utils.workflow.node_types.file_processing import FileProcessingNode

    node = FileProcessingNode(
        "n", {"operation": "copy", "source": "a.txt", "destination": "b.txt"}
    )
    node._operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    assert node.validate_params() == []


# ---------------------------------------------------------------------------
# web_search / visual_analyzer
# ---------------------------------------------------------------------------


def test_search_result_to_dict_omits_missing_summary():
    from app.utils.web_search import SearchResult

    assert "summary" not in SearchResult("t", "https://e.com", "s").to_dict()


@pytest.mark.asyncio
async def test_wikipedia_moves_to_second_language_when_first_short(monkeypatch):
    from app.utils import web_search as module

    searcher = module.FreeWebSearch()
    calls = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, url, **_kwargs):
            calls.append(url)
            if "zh." in url:
                return SimpleNamespace(status_code=200, json=lambda: [])
            return SimpleNamespace(
                status_code=200,
                json=lambda: [module.SearchResult("t", "https://e.com", "s")],
            )

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: _Client())
    monkeypatch.setattr(module, "parse_wikipedia_search", lambda data, lang: data)

    results = await searcher._search_wikipedia("测试", count=1)

    assert len(results) == 1
    assert any("zh." in url for url in calls)
    assert any("en." in url for url in calls)


def test_clean_url_returns_duckduckgo_url_without_redirect_param():
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()

    assert searcher._clean_url("https://duckduckgo.com/?q=test") == (
        "https://duckduckgo.com/?q=test"
    )


def test_normalize_json_text_keeps_literal_adjacent_to_word_char():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    result = VisualAnalyzer._normalize_json_text('{"a": Truex}')

    assert '{"a": Truex}' == result


def test_normalize_json_text_handles_unterminated_strings():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    assert VisualAnalyzer._normalize_json_text('{"a": "abc') == '{"a": "abc'
    assert VisualAnalyzer._normalize_json_text("{'a': 'abc") == '{"a": "abc'


# ---------------------------------------------------------------------------
# agent_core
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_imports_skips_stdlib_import_from_when_unimportable(tmp_path, monkeypatch):
    from app.schema.codeRequest import AgentConfig
    from app.utils.agent_core import CodeValidator

    target = tmp_path / "a.py"
    target.write_text("from json import loads\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, AgentConfig(enable_validation=False))
    monkeypatch.setattr(validator, "_is_importable", lambda name: False)
    monkeypatch.setattr(validator, "_standard_lib_modules", {"json"})

    result = await validator._validate_imports(target)

    assert result.success is True


@pytest.mark.asyncio
async def test_create_project_file_reuses_existing_lock(tmp_path, monkeypatch):
    from app.utils import agent_core

    monkeypatch.chdir(tmp_path)
    agent_core._file_locks["reuse"] = asyncio.Lock()

    result = await agent_core.create_project_file(
        "projects/demo/main.py",
        "p = 1\n",
        output_dir="./projects/demo",
        session_id="reuse",
    )

    assert result["status"] == "success"
    assert "reuse" not in agent_core._file_locks


@pytest.mark.asyncio
async def test_create_project_file_skips_verification_when_path_vanishes(monkeypatch):
    from app.utils import agent_core

    class _FakeHandle:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def write(self, _content):
            return None

    fake_path = SimpleNamespace(
        parent=SimpleNamespace(
            mkdir=lambda *a, **k: None,
            exists=lambda: False,
        ),
        exists=lambda: False,
    )
    fake_path.absolute = lambda: fake_path
    monkeypatch.setattr(agent_core, "_resolve_project_write_path", lambda *a, **k: fake_path)
    monkeypatch.setattr("aiofiles.open", lambda *a, **k: _FakeHandle())

    result = await agent_core.create_project_file(
        "projects/demo/main.py", "p = 1\n", output_dir="./projects/demo", session_id="vanish"
    )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_compress_context_skips_unrelated_middle_messages():
    from app.schema.codeRequest import AgentConfig
    from app.utils.agent_core import ProjectGeneratorAgent

    agent = ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "system", "content": "普通提示"},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "short"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]

    compressed = await agent._compress_context(messages)

    assert compressed[0]["content"] == "sys"


@pytest.mark.asyncio
async def test_generate_resume_with_history_but_no_files(monkeypatch, tmp_path):
    from app.schema.codeRequest import AgentConfig
    from app.utils import agent_core
    from app.utils.agent_core import ConversationHistoryManager, ProjectGeneratorAgent

    agent = ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))
    mgr = ConversationHistoryManager()
    monkeypatch.setattr(agent_core, "conversation_history_manager", mgr)
    output = tmp_path / "empty"
    output.mkdir()
    await mgr.set_output_dir("s", str(output))
    await mgr.set_history("s", [{"role": "system", "content": "old"}])
    monkeypatch.setattr(agent_core, "load_project_generation_prompt", lambda **k: "sys")
    monkeypatch.setattr(agent_core, "load_resume_prompt", lambda **k: "resume")

    async def fake_call(messages, **kwargs):
        return {"choices": [{"message": {"content": "done"}}]}

    monkeypatch.setattr(agent, "_call_llm", fake_call)
    result = await agent.generate_project(
        requirement="继续", output_dir=str(output), session_id="s"
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_success_status_without_file_path_is_ignored(monkeypatch, tmp_path):
    from app.schema.codeRequest import AgentConfig
    from app.utils.agent_core import ProjectGeneratorAgent

    agent = ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))
    responses = iter([
        {"choices": [{"message": {"content": "TOOL"}}]},
        {"choices": [{"message": {"content": "done"}}]},
    ])

    async def fake_call(messages, **kwargs):
        return next(responses)

    tool_calls = [
        {"id": "c1", "function": {"name": "create_project_file", "arguments": {}}}
    ]
    monkeypatch.setattr(
        agent, "_parse_tool_calls", lambda content, out: (tool_calls, "") if content == "TOOL" else ([], content)
    )

    async def fake_execute(calls, session_id, callback=None, output_dir=None):
        return [SimpleNamespace(tool_call_id="c1", content='{"status": "success"}')]

    monkeypatch.setattr(agent, "_execute_tools", fake_execute)
    monkeypatch.setattr(agent, "_call_llm", fake_call)

    result = await agent.generate_project(requirement="demo", output_dir=str(tmp_path / "p"))

    assert result["success"] is True


def test_parse_tool_calls_handles_missing_brace_and_unclosed_brace(tmp_path):
    from app.schema.codeRequest import AgentConfig
    from app.utils.agent_core import ProjectGeneratorAgent

    agent = ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))

    assert agent._parse_tool_calls('text "tool_calls" tail') == ([], 'text "tool_calls" tail')
    assert agent._parse_tool_calls('x {"tool_calls": [') == ([], 'x {"tool_calls": [')


@pytest.mark.asyncio
async def test_execute_tools_runs_non_create_tool(tmp_path):
    from app.schema.codeRequest import AgentConfig
    from app.utils.agent_core import ProjectGeneratorAgent

    agent = ProjectGeneratorAgent(config=AgentConfig(enable_validation=False))
    calls = [
        {
            "id": "c1",
            "function": {
                "name": "list_directory",
                "arguments": {"path": str(tmp_path)},
            },
        }
    ]

    results = await agent._execute_tools(calls, None)

    assert len(results) == 1
    assert "error" not in results[0].content


@pytest.mark.asyncio
async def test_run_single_tool_error_without_callback():
    from app.schema.codeRequest import ToolDefinition
    from app.utils.agent_core import ProjectGeneratorAgent

    def boom(**_kwargs):
        raise RuntimeError("tool down")

    tool_def = ToolDefinition(
        name="boom", func=boom, description="", parameters=lambda **_kwargs: None
    )
    agent = ProjectGeneratorAgent.__new__(ProjectGeneratorAgent)

    result = await agent._run_single_tool(tool_def, {}, "c1", None)

    assert "tool down" in result.content


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_skips_active_task_update_when_entry_removed(monkeypatch, tmp_path):
    from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
    from app.api.v1.ai_agent.schemas import OrchestratorRequest
    from tests.unit import test_orchestrate_endpoints_branches as harness

    db, sm, _, manager = harness._patch_stream_common(monkeypatch, tmp_path)
    original_run = endpoints.run_workflow

    async def clearing_run(*args, **kwargs):
        endpoints._active_tasks.clear()
        return await original_run(*args, **kwargs)

    monkeypatch.setattr(endpoints, "run_workflow", clearing_run)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        harness.ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await harness._drain(response)

    assert any('"type": "done"' in event for event in events)
