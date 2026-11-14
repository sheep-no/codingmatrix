"""GenerationMixin 初始化、MCP 加载与 generate 异常包装的补测。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.orchestrator_generation import mixin as mixin_module
from app.agent.orchestrator_generation.mixin import GenerationMixin


class _Harness(GenerationMixin):
    def __init__(self, tmp_path, *, topology=True):
        self.use_dynamic_topology = topology
        self.model_assignment = None
        self.api_key_token = "token"
        self.provider_id = 7
        self.cancel_event = None
        self.output_dir = tmp_path
        self.cost_tracker = SimpleNamespace(start_time=None)
        self.reports = []
        self.phase = None

    def _report_progress(self, *args, **kwargs):
        self.reports.append((args, kwargs))

    def _update_phase(self, phase):
        self.phase = phase

    async def _init_mcp_tools(self):
        return

    async def _call_llm_for_patch(self, *args, **kwargs):
        return None


@pytest.fixture
def patched_components(monkeypatch):
    created = {}

    class _Analyzer:
        def analyze(self, requirement):
            return SimpleNamespace(
                level=SimpleNamespace(value="medium"),
                estimated_files=4,
                key_technologies=["python"],
            )

    assignment = SimpleNamespace(
        architect_model="a", frontend_model="f", backend_model="b", reviewer_model="r"
    )

    class _Router:
        def get_assignment(self):
            return assignment

    def factory(name, **defaults):
        def _make(*args, **kwargs):
            obj = SimpleNamespace(name=name, args=args, kwargs=kwargs, **defaults)
            created[name] = obj
            return obj

        return _make

    monkeypatch.setattr(mixin_module, "ComplexityAnalyzer", _Analyzer)
    monkeypatch.setattr(mixin_module, "LayeredModelRouter", _Router)
    for name in (
        "Architect",
        "FrontendEngineer",
        "BackendEngineer",
        "CodeReviewer",
        "CodeValidator",
        "ErrorRecoveryLoop",
        "APIContractChecker",
        "CodePatcher",
        "CrossFilePatcher",
    ):
        monkeypatch.setattr(mixin_module, name, factory(name))
    monkeypatch.setattr(mixin_module, "get_global_llm_semaphore", lambda: "semaphore")
    return created


async def test_initialize_components_builds_all_roles(tmp_path, patched_components):
    harness = _Harness(tmp_path)
    await GenerationMixin._initialize_components(harness, "build a todo app")

    assert harness.phase == "analyzing"
    assert harness.cost_tracker.start_time is not None
    assert harness.complexity.level.value == "medium"
    assert harness.architect.name == "Architect"
    assert harness.architect.kwargs["complexity"] == "medium"
    assert harness.reviewer.kwargs["task_type"] == "review"
    assert harness.validator.args == (tmp_path,)
    assert patched_components["ErrorRecoveryLoop"].kwargs["cost_tracker"] is harness.cost_tracker
    assert any(args[0] == "分配 AI 模型" for args, _ in harness.reports if args)
    assert any(kwargs.get("roles") for _, kwargs in harness.reports)


async def test_initialize_components_without_cost_tracker(tmp_path, patched_components):
    harness = _Harness(tmp_path)
    del harness.cost_tracker

    await GenerationMixin._initialize_components(harness, "script")

    assert not hasattr(harness, "cost_tracker")


async def test_initialize_components_without_dynamic_topology(tmp_path, patched_components):
    harness = _Harness(tmp_path, topology=False)
    harness.model_assignment = SimpleNamespace(
        architect_model="a", frontend_model="f", backend_model="b", reviewer_model="r"
    )

    await GenerationMixin._initialize_components(harness, "script")

    assert harness.model_router is None


async def test_initialize_components_rejects_missing_assignment(tmp_path, patched_components, monkeypatch):
    class _Router:
        def get_assignment(self):
            return None

    monkeypatch.setattr(mixin_module, "LayeredModelRouter", _Router)
    harness = _Harness(tmp_path)

    with pytest.raises(RuntimeError, match="model assignment is required"):
        await GenerationMixin._initialize_components(harness, "script")


async def test_init_mcp_tools_logs_loaded_tools(tmp_path):
    harness = _Harness(tmp_path)

    class _Manager:
        @classmethod
        def get_or_create_instance(cls):
            return cls()

        async def load_servers(self):
            return 2

        def get_tool_names(self):
            return ["read_file", "write_file"]

    monkeypatch_target = "app.agent.mcp_client.MCPClientManager"
    import app.agent.mcp_client as mcp_client

    original = mcp_client.MCPClientManager
    mcp_client.MCPClientManager = _Manager
    try:
        await GenerationMixin._init_mcp_tools(harness)
    finally:
        mcp_client.MCPClientManager = original

    assert harness.reports == [(("mcp_tools_loaded", 1, 5), {"mcp_tools": ["read_file", "write_file"]})]


async def test_init_mcp_tools_skips_when_none_connected(tmp_path):
    harness = _Harness(tmp_path)

    class _Manager:
        @classmethod
        def get_or_create_instance(cls):
            return cls()

        async def load_servers(self):
            return 0

        def get_tool_names(self):
            return []

    import app.agent.mcp_client as mcp_client

    original = mcp_client.MCPClientManager
    mcp_client.MCPClientManager = _Manager
    try:
        await GenerationMixin._init_mcp_tools(harness)
    finally:
        mcp_client.MCPClientManager = original

    assert harness.reports == []


async def test_init_mcp_tools_swallows_failures(tmp_path):
    harness = _Harness(tmp_path)

    class _Manager:
        @classmethod
        def get_or_create_instance(cls):
            raise RuntimeError("no server configured")

    import app.agent.mcp_client as mcp_client

    original = mcp_client.MCPClientManager
    mcp_client.MCPClientManager = _Manager
    try:
        await GenerationMixin._init_mcp_tools(harness)
    finally:
        mcp_client.MCPClientManager = original

    assert harness.reports == []


async def test_generate_reraises_attribute_error():
    async def _generate_traditional(_requirement):
        raise AttributeError("missing hook")

    agent = SimpleNamespace(
        evaluation_only=False,
        incremental=False,
        spec_first=False,
        _generate_traditional=_generate_traditional,
    )

    with pytest.raises(AttributeError, match="missing hook"):
        await GenerationMixin.generate(agent, "build")


async def test_generate_wraps_unexpected_errors():
    async def _generate_traditional(_requirement):
        raise ValueError("boom " + "x" * 500)

    agent = SimpleNamespace(
        evaluation_only=False,
        incremental=False,
        spec_first=False,
        _generate_traditional=_generate_traditional,
    )

    with pytest.raises(RuntimeError, match=r"项目生成失败: boom") as excinfo:
        await GenerationMixin.generate(agent, "build")

    assert len(str(excinfo.value).split("项目生成失败: ", 1)[1]) <= 200


def test_check_requirement_coverage_delegates(monkeypatch):
    captured = {}

    def fake(requirement, architecture, file_plan, association):
        captured.update(
            requirement=requirement,
            architecture=architecture,
            file_plan=file_plan,
            association=association,
        )
        return {"covered": True}

    monkeypatch.setattr(mixin_module, "check_requirement_coverage", fake)
    agent = SimpleNamespace(_association_result={"files": ["a.py"]})

    result = GenerationMixin._check_requirement_coverage(
        agent, "req", {"language": "python"}, [{"path": "a.py"}]
    )

    assert result == {"covered": True}
    assert captured["association"] == {"files": ["a.py"]}


async def test_extract_and_save_feature_list_delegates(monkeypatch):
    fake = AsyncMock(return_value={"features": []})
    monkeypatch.setattr(mixin_module, "extract_and_save_feature_list", fake)

    result = await GenerationMixin._extract_and_save_feature_list(
        SimpleNamespace(), "req", {"a.py": "x = 1"}, domain="backend"
    )

    assert result == {"features": []}
    fake.assert_awaited_once_with("req", {"a.py": "x = 1"}, "backend")
