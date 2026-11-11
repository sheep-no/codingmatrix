"""MultiModelAgent.process 分支补测：委托、分析、审查、文件契约与信号量。"""

from types import SimpleNamespace

import pytest

from app.agent.file_contract import ReviewResult
from app.agent.models import ModelInfo, ModelRegistry, TaskType
from app.agent.multi_model_agent import MultiModelAgent


class _AsyncSem:
    def __init__(self):
        self.entered = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *_exc):
        return False


def _agent(**overrides):
    agent = MultiModelAgent.__new__(MultiModelAgent)
    agent.router = SimpleNamespace(
        route_by_content=lambda task, files=None: TaskType.GENERAL,
        route=lambda task_type, prefer_fast=False: ModelRegistry.get("qwen3-8b"),
        route_dynamic=SimpleNamespace(),
    )
    agent.api_key_token = None
    agent._api_key_token = None
    agent.enable_review = True
    agent.enable_file_contract = True
    agent.complexity = "MEDIUM"
    agent._semaphore = None
    agent._orchestrator_factory = None
    agent._orchestrator = None
    agent.executor = SimpleNamespace()
    agent.reviewer = None
    agent.planner = SimpleNamespace()
    for key, value in overrides.items():
        setattr(agent, key, value)
    return agent


def test_constructor_wires_dependencies():
    agent = MultiModelAgent(enable_review=False, complexity="LARGE", api_key_token="tok")
    assert agent.reviewer is None
    assert agent.complexity == "LARGE"
    assert agent.api_key_token == "tok"
    assert agent._api_key_token == "tok"
    assert agent.enable_file_contract is True
    assert agent._orchestrator is None


def test_constructor_with_review_enabled():
    agent = MultiModelAgent(enable_review=True)
    assert agent.reviewer is not None


@pytest.mark.asyncio
async def test_emit_swallows_callback_errors():
    agent = _agent()
    seen = []

    async def callback(event_type, data):
        seen.append(event_type)
        raise RuntimeError("callback down")

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda task_type, prefer_fast=False: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("do it", task_type=TaskType.GENERAL, stream_callback=callback)
    assert result["success"] is True
    assert "model_selected" in seen


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_delegation_success_returns_orchestrator_result():
    events = []
    generated = {"success": True, "files": 3}

    class Orchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def generate(self, requirement):
            assert requirement == "build app"
            return generated

    agent = _agent(_orchestrator_factory=Orchestrator)

    async def callback(event_type, data):
        events.append(event_type)

    result = await agent.process(
        "build app", task_type=TaskType.CODE_GENERATION, output_dir="/workspace", stream_callback=callback
    )
    assert result == generated
    assert "delegating" in events and "delegation_complete" in events


@pytest.mark.asyncio
async def test_delegation_failure_returns_error_dict():
    class Orchestrator:
        def __init__(self, **_kwargs):
            pass

        async def generate(self, requirement):
            raise RuntimeError("orchestrator down")

    agent = _agent(_orchestrator_factory=Orchestrator)
    events = []

    async def callback(event_type, data):
        events.append(event_type)

    result = await agent.process(
        "build app", task_type=TaskType.CODE_GENERATION, output_dir="/workspace", stream_callback=callback
    )
    assert result["success"] is False
    assert result["delegation_failed"] is True
    assert "orchestrator down" in result["error"]
    assert "delegation_failed" in events


@pytest.mark.asyncio
async def test_code_generation_without_output_dir_keeps_planning_path(monkeypatch):
    agent = _agent(_orchestrator_factory=lambda **kwargs: None)

    async def decompose(*_args, **_kwargs):
        return [{"type": "ai_call", "params": {"task": "x"}}]

    async def execute(step):
        return {"ok": True}

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))
    agent.executor.execute = execute

    result = await agent.process("build app", task_type=TaskType.CODE_GENERATION)
    assert result["success"] is True
    assert result["task_type"] == TaskType.CODE_GENERATION.value


@pytest.mark.asyncio
async def test_analysis_uses_dynamic_route_and_returns_result():
    called = {}

    class Executor:
        async def execute_analysis(self, **kwargs):
            called.update(kwargs)
            return {"success": True, "analysis": "ok"}

    agent = _agent(executor=Executor())
    routed = []

    async def route_dynamic(task_type, prefer_fast=False):
        routed.append(task_type)
        return ModelRegistry.get("qwen3-8b")

    agent.router.route_dynamic = route_dynamic
    result = await agent.process(
        "analyze", task_type=TaskType.CODE_REVIEW, output_dir="/workspace", use_dynamic_routing=True
    )
    assert result["analysis"] == "ok"
    assert routed == [TaskType.CODE_REVIEW]
    assert called["project_path"] == "/workspace"


@pytest.mark.asyncio
async def test_analysis_static_route_and_error_wrapping():
    class Executor:
        async def execute_analysis(self, **_kwargs):
            raise RuntimeError("analysis boom")

    agent = _agent(executor=Executor())
    result = await agent.process(
        "analyze", task_type=TaskType.PLANNING, output_dir="/workspace", use_dynamic_routing=False
    )
    assert result["success"] is False
    assert "analysis boom" in result["error"]


@pytest.mark.asyncio
async def test_route_by_content_when_task_type_missing():
    agent = _agent()
    seen = []

    def route_by_content(task, files=None):
        seen.append(task)
        return TaskType.GENERAL

    async def decompose(*_args, **_kwargs):
        return []

    agent.router.route_by_content = route_by_content
    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("hello")
    assert seen == ["hello"]
    assert result["steps"] == 0


@pytest.mark.asyncio
async def test_call_with_semaphore_acquires_when_available():
    sem = _AsyncSem()
    agent = _agent(_semaphore=sem)

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))
    await agent.process("go", task_type=TaskType.GENERAL)
    assert sem.entered == 1


@pytest.mark.asyncio
async def test_call_with_semaphore_runs_directly_without_semaphore():
    agent = _agent(_semaphore=None)
    agent._get_semaphore = lambda: None

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))
    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_route_is_used_when_dynamic_disabled():
    agent = _agent()
    routed = []
    agent.router.route = lambda task_type, prefer_fast=False: (
        routed.append(task_type) or ModelRegistry.get("glm-4-9b")
    )

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    result = await agent.process("go", task_type=TaskType.GENERAL, use_dynamic_routing=False)
    assert routed == [TaskType.GENERAL]
    assert result["model_used"] == ModelRegistry.get("glm-4-9b").display_name


def test_get_semaphore_returns_fallback_on_import_error(monkeypatch):
    agent = _agent()

    class Boom(Exception):
        pass

    import app.agent.specialist_base as specialist_base

    monkeypatch.setattr(
        specialist_base,
        "get_global_llm_semaphore",
        lambda: (_ for _ in ()).throw(Boom("no sem")),
    )
    assert agent._get_semaphore() is None


@pytest.mark.asyncio
async def test_reviewer_rejects_plan_and_returns_issues():
    class Reviewer:
        model = ModelRegistry.get("qwen3-8b")

        async def review_plan(self, steps):
            return ReviewResult(approved=False, issues=["unsafe"], suggestions=["fix"])

    agent = _agent(reviewer=Reviewer())

    async def decompose(*_args, **_kwargs):
        return [{"type": "ai_call", "params": {}}]

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result == {
        "success": False,
        "error": "计划审查未通过",
        "issues": ["unsafe"],
        "suggestions": ["fix"],
    }


@pytest.mark.asyncio
async def test_reviewer_model_is_switched_by_dynamic_assignment(monkeypatch):
    class Reviewer:
        model = ModelRegistry.get("qwen3-8b")

        async def review_plan(self, steps):
            return ReviewResult(approved=True)

    agent = _agent(reviewer=Reviewer())
    routed_model = ModelRegistry.get("glm-4-9b")

    class Router:
        async def get_assignment_with_learning(self):
            return SimpleNamespace(reviewer_model="glm-4-9b")

    async def get_dynamic_router():
        return Router()

    import app.agent.dynamic_model_router as dynamic_router

    monkeypatch.setattr(dynamic_router, "get_dynamic_router", get_dynamic_router)

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    await agent.process("go", task_type=TaskType.GENERAL)
    assert agent.reviewer.model == routed_model


@pytest.mark.asyncio
async def test_reviewer_model_switch_failure_is_logged(monkeypatch):
    class Reviewer:
        model = ModelRegistry.get("qwen3-8b")

        async def review_plan(self, steps):
            return ReviewResult(approved=True)

    agent = _agent(reviewer=Reviewer())

    async def get_dynamic_router():
        raise RuntimeError("assignment down")

    import app.agent.dynamic_model_router as dynamic_router

    monkeypatch.setattr(dynamic_router, "get_dynamic_router", get_dynamic_router)

    async def decompose(*_args, **_kwargs):
        return []

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is True
    assert agent.reviewer.model.key == "qwen3-8b"


@pytest.mark.asyncio
async def test_file_operation_missing_path_is_rejected():
    agent = _agent()

    async def decompose(*_args, **_kwargs):
        return [{"type": "file_operation", "params": {"operation": "write"}}]

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is False
    assert "缺少 path" in result["error"]
    assert result["failed_step"] == 0


@pytest.mark.asyncio
async def test_file_operation_invalid_contract_path_is_rejected():
    agent = _agent()

    async def decompose(*_args, **_kwargs):
        return [{"type": "file_operation", "params": {"operation": "write", "path": "/etc/passwd"}}]

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is False
    assert "文件契约验证失败" in result["error"]


@pytest.mark.asyncio
async def test_valid_file_operation_runs_executor():
    agent = _agent()
    executed = []

    async def decompose(*_args, **_kwargs):
        return [
            {
                "type": "file_operation",
                "params": {"operation": "write", "path": "/workspace/safe.py", "content": "x = 1"},
            }
        ]

    async def execute(step):
        executed.append(step)
        return {"success": True}

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))
    agent.executor.execute = execute

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is True
    assert len(executed) == 1
    assert result["results"] == [{"success": True}]


@pytest.mark.asyncio
async def test_file_contract_can_be_disabled():
    agent = _agent(enable_file_contract=False)
    executed = []

    async def decompose(*_args, **_kwargs):
        return [{"type": "file_operation", "params": {"operation": "write", "path": "/etc/passwd"}}]

    async def execute(step):
        executed.append(step)
        return {"success": True}

    agent.planner.decompose = decompose
    agent.router.route_dynamic = lambda *a, **k: _async_value(ModelRegistry.get("qwen3-8b"))
    agent.executor.execute = execute

    result = await agent.process("go", task_type=TaskType.GENERAL)
    assert result["success"] is True
    assert len(executed) == 1
